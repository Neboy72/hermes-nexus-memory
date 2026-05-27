"""
Hybrid Retrieval — BM25 + Vector + Reciprocal Rank Fusion.

Defense against RAG poisoning: BM25 catches keyword-exact matches,
vector search catches semantics, RRF merges both with source-tier boosting.

Based on: "I Compared 5 RAG Poisoning Defenses — Only 2 Actually Work"

Usage:
    from nexus.retrieval import HybridRetriever

    retriever = HybridRetriever(qdrant_host="localhost", qdrant_port=6333)
    retriever.index_memories()                         # build BM25 index
    results = retriever.search("fallback routing")     # hybrid search

Requirements: bm25s (pip install bm25s)
"""

from __future__ import annotations
import json, re
from collections import defaultdict
from pathlib import Path
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nexus.graph.graph import SkillGraph

try:
    import bm25s
    HAS_BM25 = True
except ImportError:
    HAS_BM25 = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# ── Source Tiers (Poisoning Defense) ────────────────────────────────────────

SOURCE_TIERS = {
    "tier1": {  # Highest trust — agent itself, user, config, official docs
        "keywords": ["kiosha", "nebo", "hermes-config", "official", "skill"],
        "boost": 1.2,
        "emoji": "🟢",
    },
    "tier2": {  # Medium trust — curated sources
        "keywords": ["medium", "arxiv", "hacker-news", "github", "youtube"],
        "boost": 1.0,
        "emoji": "🟡",
    },
    "tier3": {  # Low trust — uncurated sources
        "keywords": ["reddit", "twitter", "forum", "unknown"],
        "boost": 0.8,
        "emoji": "🔴",
    },
}

def _resolve_tier(content: str, metadata: dict | None = None) -> tuple[str, float]:
    """Resolve source tier from metadata (preferred) or content keywords (fallback).

    If a ``source_tier`` field is present in metadata (e.g. "tier1"), use it directly.
    Otherwise fall back to keyword matching in the content string.
    """
    if metadata and "source_tier" in metadata:
        tier_name = metadata["source_tier"]
        if tier_name in SOURCE_TIERS:
            return tier_name, SOURCE_TIERS[tier_name]["boost"]
    # Fallback: keyword matching
    text = content.lower()
    for tier_name, cfg in SOURCE_TIERS.items():
        if any(kw in text for kw in cfg["keywords"]):
            return tier_name, cfg["boost"]
    return "tier3", SOURCE_TIERS["tier3"]["boost"]

RRF_K = 60  # Reciprocal Rank Fusion constant


class HybridRetriever:
    """Hybrid BM25 + Vector search with RRF and source-tier boosting."""

    def __init__(
        self,
        qdrant_host: str = "localhost",
        qdrant_port: int = 6333,
        collection_name: str = "hermes-memory",
        skillgraph: "SkillGraph | None" = None,
    ) -> None:
        if not HAS_BM25:
            raise ImportError("bm25s is required: pip install bm25s")

        self.qdrant_url = f"http://{qdrant_host}:{qdrant_port}"
        self.collection = collection_name
        self._skillgraph = skillgraph  # Optional for graph_boost
        self._bm25 = None
        self._ids = []
        self._texts = []

    # ── Indexing ────────────────────────────────────────────────────────────

    def index_memories(self) -> dict:
        """Pull all memories from Qdrant and build BM25 index (full rebuild).

        Returns:
            dict with stats: {indexed, bm25_built, collection}
        """
        if not HAS_REQUESTS:
            raise ImportError("requests is required: pip install requests")

        # Scroll all points from Qdrant
        points = []
        offset = None
        while True:
            body = {"limit": 100, "with_payload": True}
            if offset:
                body["offset"] = offset
            r = requests.post(
                f"{self.qdrant_url}/collections/{self.collection}/points/scroll",
                json=body, timeout=10,
            )
            data = r.json().get("result", {})
            batch = data.get("points", [])
            if not batch:
                break
            points.extend(batch)
            offset = data.get("next_page_offset")
            if not offset:
                break

        self._ids = []
        self._texts = []
        for p in points:
            pid = p.get("id", "")
            payload = p.get("payload", {})
            text = payload.get("content", "")
            if not isinstance(text, str):
                text = str(text) if text else ""
            if not text:
                text = f"{payload.get('user_content', '')} → {payload.get('assistant_content', '')}"
            self._ids.append(str(pid))
            self._texts.append(text.lower())

        # Build BM25 index
        if self._texts:
            corpus_tokens = bm25s.tokenize(self._texts)
            self._bm25 = bm25s.BM25()
            self._bm25.index(corpus_tokens)

        return {
            "indexed": len(self._ids),
            "bm25_built": self._bm25 is not None,
            "collection": self.collection,
        }

    def index_from_texts(self, texts: list[str], ids: list[str]) -> dict:
        """Build BM25 index from a list of texts (no Qdrant needed).

        Useful for testing or offline use.
        """
        self._ids = ids
        self._texts = [t.lower() for t in texts]

        if self._texts:
            corpus_tokens = bm25s.tokenize(self._texts)
            self._bm25 = bm25s.BM25()
            self._bm25.index(corpus_tokens)

        return {"indexed": len(self._ids), "bm25_built": self._bm25 is not None}

    def update_index(
        self,
        memories_to_add: list[tuple[str, str]] | None = None,
        memories_to_remove: list[str] | None = None,
    ) -> dict:
        """Incrementally update the BM25 index without a full Qdrant scroll.

        Adds new memories and/or removes specified entries. BM25 is rebuilt
        from the updated internal corpus (no Qdrant round-trip). This is
        significantly faster than ``index_memories()`` which scrolls every
        point from Qdrant.

        Args:
            memories_to_add: List of ``(id, text)`` tuples to insert.
            memories_to_remove: List of IDs to remove from the index.

        Returns:
            dict with stats: {added, removed, total_ids, bm25_built}

        Raises:
            ImportError: If bm25s is not installed.
        """
        if not HAS_BM25:
            raise ImportError("bm25s is required: pip install bm25s")

        added = 0
        removed = 0
        to_add = memories_to_add or []
        to_remove = memories_to_remove or []

        # --- Handle removals: filter out removed IDs ---
        if to_remove and self._ids:
            remove_set = set(to_remove)
            surviving_ids = []
            surviving_texts = []
            for i, pid in enumerate(self._ids):
                if pid not in remove_set:
                    surviving_ids.append(pid)
                    surviving_texts.append(self._texts[i] if i < len(self._texts) else "")
            removed = len(self._ids) - len(surviving_ids)
            self._ids = surviving_ids
            self._texts = surviving_texts

        # --- Handle additions ---
        if to_add:
            new_ids = []
            new_texts = []
            for pid, text in to_add:
                if isinstance(pid, str) and isinstance(text, str):
                    new_ids.append(pid)
                    new_texts.append(text.lower())
                    added += 1

            if new_ids:
                self._ids.extend(new_ids)
                self._texts.extend(new_texts)

        # Rebuild BM25 from the updated corpus (only if something changed)
        if (added > 0 or removed > 0) and self._texts:
            corpus_tokens = bm25s.tokenize(self._texts)
            self._bm25 = bm25s.BM25()
            self._bm25.index(corpus_tokens)

        return {
            "added": added,
            "removed": removed,
            "total_ids": len(self._ids),
            "bm25_built": self._bm25 is not None,
        }

    # ── Search ──────────────────────────────────────────────────────────────

    def search_bm25(self, query: str, top_k: int = 10) -> list[dict]:
        """Keyword search via BM25."""
        if self._bm25 is None:
            return []
        query_tokens = bm25s.tokenize(query.lower())
        results = self._bm25.retrieve(query_tokens, k=min(top_k, len(self._ids)))

        hits = []
        for rank, doc_idx in enumerate(results.documents[0]):
            score = float(results.scores[0][rank])
            idx = int(doc_idx)
            if idx < len(self._ids):
                hits.append({
                    "id": self._ids[idx],
                    "score": score,
                    "rank": rank + 1,
                    "method": "bm25",
                    "text": self._texts[idx][:200],
                })
        return hits

    def search_vector(self, query_vector: list[float], top_k: int = 10) -> list[dict]:
        """Vector search via Qdrant (you provide the embedding).

        For production use, pass the query embedding from your provider.
        Only returns entries with ``type: "memory"`` to filter out session turns.
        """
        if not HAS_REQUESTS:
            return []

        r = requests.post(
            f"{self.qdrant_url}/collections/{self.collection}/points/search",
            json={
                "vector": query_vector,
                "limit": top_k,
                "with_payload": True,
                "filter": {
                    "must": [{"key": "type", "match": {"value": "memory"}}]
                },
            },
            timeout=10,
        )
        hits = []
        for rank, point in enumerate(r.json().get("result", [])):
            payload = point.get("payload", {})
            # Memory entries have "content", turn entries have user/assistant_content
            text = payload.get("content") or (
                payload.get("user_content", "")
                + ("\n" + payload.get("assistant_content", "") if payload.get("assistant_content") else "")
            )
            hits.append({
                "id": str(point.get("id", "")),
                "score": point.get("score", 0.0),
                "rank": rank + 1,
                "method": "vector",
                "text": text[:500],
            })
        return hits

    def search_hybrid(
        self,
        query: str,
        query_vector: list[float] | None = None,
        top_k: int = 10,
        graph_boost: bool = False,
    ) -> list[dict]:
        """Full hybrid search: BM25 + (optional) vector + RRF + tier + graph boost.

        Args:
            query: Search query string.
            query_vector: Optional pre-computed embedding for vector search.
            top_k: Number of results to return.
            graph_boost: If True, boost results by graph connectivity
                         (requires ``skillgraph`` in constructor).

        Returns:
            List of dicts with id, rrf_score, tier, methods, text.
        """
        bm25_hits = self.search_bm25(query, top_k=top_k * 2)

        vector_hits = []
        if query_vector:
            vector_hits = self.search_vector(query_vector, top_k=top_k * 2)

        # Reciprocal Rank Fusion
        fused = self._rrf(bm25_hits, vector_hits)

        # Tier boost
        fused = self._tier_boost(fused)

        # Graph boost (v2.1.0)
        if graph_boost:
            fused = self._graph_boost(fused)

        return fused[:top_k]

    # ── Internal ────────────────────────────────────────────────────────────

    def _rrf(self, bm25_hits: list[dict], vector_hits: list[dict]) -> list[dict]:
        """Reciprocal Rank Fusion."""
        scores = defaultdict(float)
        methods = defaultdict(set)

        for hit in bm25_hits + vector_hits:
            doc_id = hit["id"]
            rank = hit["rank"]
            scores[doc_id] += 1.0 / (RRF_K + rank)
            methods[doc_id].add(hit["method"])

        # Text lookup
        id_to_text = {}
        if self._ids and self._texts:
            for i, did in enumerate(self._ids):
                if i < len(self._texts):
                    id_to_text[did] = self._texts[i][:200]

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [
            {
                "id": doc_id,
                "rrf_score": score,
                "methods": sorted(methods[doc_id]),
                "text": id_to_text.get(doc_id, ""),
            }
            for doc_id, score in ranked
        ]

    def _tier_boost(self, ranked: list[dict]) -> list[dict]:
        """Apply source-tier boosting — uses metadata source_tier if available, else keywords."""
        for item in ranked:
            text = item.get("text", "")
            metadata = item.get("metadata")  # May be None for BM25-only hits
            tier, boost = _resolve_tier(text, metadata)

            item["tier"] = tier
            item["rrf_score"] *= boost

        return sorted(ranked, key=lambda x: x["rrf_score"], reverse=True)

    def _graph_boost(self, ranked: list[dict]) -> list[dict]:
        """Apply graph connectivity boost to ranked results.

        Boost formula: ``1.0 + (in_degree + out_degree) * 0.05``

        A fact with 10 edges gets 1.5x boost. An isolated fact stays at 1.0x.
        No-op if no SkillGraph was provided in constructor.

        Requires ``skillgraph`` parameter in constructor.
        """
        if self._skillgraph is None:
            return ranked

        for item in ranked:
            fact_id = item.get("id", "")
            if not fact_id:
                continue

            if not self._skillgraph.has_node(fact_id):
                continue

            neighbors = self._skillgraph.neighbors(fact_id)
            degree = len(neighbors)
            boost = 1.0 + degree * 0.05
            item["rrf_score"] *= boost
            item["graph_boost"] = round(boost, 3)

        return sorted(ranked, key=lambda x: x["rrf_score"], reverse=True)