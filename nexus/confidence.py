"""Grounding Scoring for RAG — 4-Signal-Methode.

Bewertet wie vertrauenswürdig eine generierte Antwort basierend auf
den retrieved Chunks ist. Ändert nichts an der bestehenden Pipeline.

**Warum Grounding?**
Stanford CS229 (Yann Dubois) zeigt: SFT (Supervised Fine-Tuning) trainiert
Modelle dazu plausibel klingende Antworten zu geben, selbst wenn sie die
Fakten nicht im Pre-Training gelernt haben. Die Folge: Halluzination.
Grounding ist die Gegenmassnahme — es prüft ob die Antwort tatsächlich
durch die abgerufenen Fakten gedeckt ist, nicht nur ob sie gut klingt.

Signale:
1. **similarity** — Query-Embedding ↔ Chunk-Embeddings (max cosine)
2. **dominance**  — Wie stark stützt sich alles auf einen Top-Chunk?
3. **grounding**  — Antwort-Embedding ↔ Chunk-Embeddings (max cosine)
4. **coverage**   — Chunk-Vielfalt / Query-Breite abgedeckt?

Usage:
    from nexus.confidence import ConfidenceScorer
    scorer = ConfidenceScorer()
    report = scorer.evaluate(query="Was ist Nexus?", answer="Nexus ist...")
    print(report.json())
"""

from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import dataclass, field, asdict
from typing import Optional

from nexus.config import get_collection

_logger = logging.getLogger(__name__)

# ── Optional dependencies ──────────────────────────────────────────

HAS_REQUESTS = False
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    pass

HAS_VOYAGE = False
try:
    import voyageai
    HAS_VOYAGE = True
except ImportError:
    pass

HAS_SKLEARN = False
try:
    import numpy as np
    from sklearn.metrics.pairwise import cosine_similarity
    HAS_SKLEARN = True
except ImportError:
    pass


# ── Data classes ───────────────────────────────────────────────────


@dataclass
class SignalScores:
    """Die fünf Einzelsignale, jeweils 0.0 – 1.0."""
    similarity: float = 0.0
    dominance: float = 0.0
    grounding: float = 0.0
    coverage: float = 0.0
    factual: float = 0.0


@dataclass
class GroundingReport:
    """Vollständiger Grounding-Report für einen evaluate()-Durchlauf."""
    query: str = ""
    answer: str = ""
    signals: SignalScores = field(default_factory=SignalScores)
    grounding: float = 0.0
    label: str = ""
    num_chunks: int = 0
    top_chunk_score: float = 0.0
    chunk_count: int = 0
    error: Optional[str] = None

    def json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)


# ── Helper: Cosine Similarity ──────────────────────────────────────


def _cosine_sim(a: list[float], b: list[float]) -> float:
    """Cosine similarity zwischen zwei Vektoren."""
    if HAS_SKLEARN:
        return float(cosine_similarity([a], [b])[0][0])
    # NumPy-freier Fallback
    dot = sum(ai * bi for ai, bi in zip(a, b))
    norm_a = math.sqrt(sum(ai * ai for ai in a))
    norm_b = math.sqrt(sum(bi * bi for bi in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── Embedding ──────────────────────────────────────────────────────


def _embed(texts: list[str], provider: str = "voyage") -> Optional[list[list[float]]]:
    """Embed eine Liste von Texten via Voyage, sentence-transformers oder Ollama.

    Args:
        texts: Liste der zu embeddenden Texte.
        provider: "voyage" (512d), "sentence-transformers" (384d) oder "ollama" (768d).

    Returns:
        Liste von Embedding-Vektoren oder None bei Fehler.
    """
    if provider == "voyage":
        if not HAS_VOYAGE:
            _logger.warning("voyageai nicht installiert")
            return None
        try:
            client = voyageai.Client()
            result = client.embed(texts, model="voyage-3-lite", input_type="document")
            return result.embeddings
        except Exception as e:
            _logger.warning(f"Voyage embedding failed: {e}")
            return None

    elif provider == "sentence-transformers":
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("all-MiniLM-L6-v2")
            return model.encode(texts).tolist()
        except Exception as e:
            _logger.warning(f"sentence-transformers embedding failed: {e}")
            return None

    elif provider == "ollama":
        if not HAS_REQUESTS:
            return None
        try:
            r = requests.post(
                "http://localhost:11434/api/embed",
                json={"model": "nomic-embed-text", "input": texts},
                timeout=30,
            )
            data = r.json()
            return data.get("embeddings", None)
        except Exception as e:
            _logger.warning(f"Ollama embedding failed: {e}")
            return None

    else:
        _logger.warning(f"Unbekannter Embedding-Provider: {provider}")
        return None


# ── Qdrant-Abfrage ─────────────────────────────────────────────────


def _fetch_chunks(
    query_embedding: list[float],
    qdrant_host: str = "localhost",
    qdrant_port: int = 6333,
    collection: Optional[str] = None,
    top_k: int = 5,
) -> list[dict]:
    """Hole die Top-K Chunks aus Qdrant (mit voller Payload)."""
    collection = get_collection(collection)
    if not HAS_REQUESTS:
        return []
    try:
        url = f"http://{qdrant_host}:{qdrant_port}/collections/{collection}/points/search"
        r = requests.post(
            url,
            json={
                "vector": query_embedding,
                "limit": top_k,
                "with_payload": True,
                "filter": {
                    "must": [{"key": "type", "match": {"value": "memory"}}]
                },
            },
            timeout=10,
        )
        results = []
        for point in r.json().get("result", []):
            payload = point.get("payload", {})
            results.append({
                "id": str(point.get("id", "")),
                "score": point.get("score", 0.0),
                "text": payload.get("content", ""),
            })
        return results
    except Exception as e:
        _logger.warning(f"Qdrant search failed: {e}")
        return []


# ── Grounding Scorer ──────────────────────────────────────────────


class GroundingScorer:
    """Bewertet die Vertrauenswürdigkeit einer RAG-Antwort.

    Nutzt vier Signale:
    1. similarity  — Query↔Chunk: Passt der beste Chunk zur Frage?
    2. dominance   — Chunk-Verteilung: Ein dominanter Chunk oder viele?
    3. grounding   — Antwort↔Chunk: Nutzt die Antwort wirklich die Chunks?
    4. coverage    — Chunk↔Query: Decken die Chunks die Frage-Breite ab?
    """

    def __init__(
        self,
        embed_provider: str = "voyage",
        qdrant_host: str = "localhost",
        qdrant_port: int = 6333,
        collection: Optional[str] = None,
        top_k: int = 5,
    ):
        collection = get_collection(collection)
        self.embed_provider = embed_provider
        self.qdrant_host = qdrant_host
        self.qdrant_port = qdrant_port
        self.collection = collection
        self.top_k = top_k

    # ─ Öffentliche API ────────────────────────────────────────────

    def evaluate(
        self,
        query: str,
        answer: str,
        chunks: Optional[list[dict]] = None,
    ) -> ConfidenceReport:
        """Vollständige Grounding-Bewertung.

        Args:
            query: Die ursprüngliche User-Frage.
            answer: Die generierte Antwort.
            chunks: Optional — bereits geretrievede Chunks.
                    Bei None werden sie aus Qdrant geholt.

        Returns:
            GroundingReport mit allen Signalen.
        """
        report = GroundingReport(query=query, answer=answer)

        # Schritt 1: Query embedden
        q_emb = _embed([query], provider=self.embed_provider)
        if q_emb is None:
            report.error = "Embedding fehlgeschlagen"
            return report
        q_emb = q_emb[0]

        # Schritt 2: Chunks holen (falls nicht mitgeliefert)
        if chunks is None:
            chunks = _fetch_chunks(
                q_emb,
                qdrant_host=self.qdrant_host,
                qdrant_port=self.qdrant_port,
                collection=self.collection,
                top_k=self.top_k,
            )

        if not chunks:
            report.error = "Keine Chunks gefunden"
            return report

        report.num_chunks = len(chunks)
        report.top_chunk_score = chunks[0].get("score", 0.0) if chunks else 0.0

        # Schritt 3: Chunk-Texte embedden
        chunk_texts = [c.get("text", "") for c in chunks if c.get("text")]
        if not chunk_texts:
            report.error = "Chunks haben keinen Text"
            return report

        chunk_embs = _embed(chunk_texts, provider=self.embed_provider)
        if chunk_embs is None:
            report.error = "Chunk-Embedding fehlgeschlagen"
            return report

        chunk_scores = [c.get("score", 0.0) for c in chunks]

        # Schritt 4: Fünf Signale berechnen
        signals = SignalScores()
        signals.similarity = self._signal_similarity(q_emb, chunk_embs, chunk_scores)
        signals.dominance = self._signal_dominance(chunk_scores)
        signals.coverage = self._signal_coverage(q_emb, chunk_embs)

        # Grounding braucht Antwort-Embedding
        a_emb = _embed([answer], provider=self.embed_provider)
        if a_emb:
            signals.grounding = self._signal_grounding(a_emb[0], chunk_embs)
            # Fakten-Check: Wörtliche Überlappung (schützt vor Halluzinationen)
            signals.factual = self._signal_factual(answer, chunk_texts)

        report.signals = signals

        # Schritt 5: Gesamt-Grounding + Label
        report.grounding = self._aggregate(signals)
        report.chunk_count = len(chunks)
        report.label = self._label(report.grounding)

        return report

    @staticmethod
    def _label(grounding: float) -> str:
        """Menschlesbares Label fuer den Grounding-Wert."""
        if grounding >= 0.8:
            return "🟢 Sehr hoch"
        elif grounding >= 0.6:
            return "🟡 Hoch"
        elif grounding >= 0.4:
            return "🟠 Mittel"
        elif grounding >= 0.2:
            return "🔴 Niedrig"
        else:
            return "⛔ Sehr niedrig"

    # ─ Einzelsignale ──────────────────────────────────────────────

    @staticmethod
    def _signal_similarity(
        query_emb: list[float],
        chunk_embs: list[list[float]],
        chunk_scores: list[float],
    ) -> float:
        """Signal 1: Ähnlichkeit zwischen Query und Chunks.

        Nimmt den höchsten Cosine-Score zwischen Query und Chunks,
        gewichtet mit der Score-Dominanz. Wenn der Top-Chunk einen
        hohen cosine-Wert hat → hohe Similarity.
        """
        if not chunk_embs:
            return 0.0
        similarities = [_cosine_sim(query_emb, ce) for ce in chunk_embs]
        # Maximum + leichter Boost durch Qdrant-Score
        max_sim = max(similarities) if similarities else 0.0
        qdrant_factor = min(chunk_scores[0] / 0.8, 1.0) if chunk_scores else 0.0
        return min((max_sim * 0.7 + qdrant_factor * 0.3), 1.0)

    @staticmethod
    def _signal_dominance(chunk_scores: list[float]) -> float:
        """Signal 2: Chunk-Dominanz.

        Misst wie stark sich die semantische Masse auf den
        Top-Chunk konzentriert. Formel:
            dominance = (top_score / sum(all_scores)) ^ 0.5

        Hohe Dominanz (0.7–1.0) = Antwort stützt sich stark auf
        EINEN Chunk → gut für Faktfragen.
        Niedrige Dominanz (0.0–0.4) = gleichmässige Verteilung
        → gut für synthetisierende Antworten.
        """
        if not chunk_scores or sum(chunk_scores) == 0:
            return 0.0
        ratio = chunk_scores[0] / sum(chunk_scores)
        # Square root, damit moderate Dominanz nicht zu hart bestraft wird
        return math.sqrt(ratio)

    # Technische Named Entities für das Factual-Signal
    _TECH_ENTITIES = {
        # Produkte & Frameworks
        "nexus", "qdrant", "voyage", "ollama", "bm25", "gpt", "claude",
        "gemini", "rag", "hermes", "openclaw", "whisper", "yt-dlp", "twikit",
        "github", "discord", "telegram", "docker", "python",
        # Konzepte
        "embedding", "token", "transformer", "attention", "finetune",
        "pretrain", "rlhf", "sft", "dpo", "ppo", "lora", "quantization",
        "quantization", "vector", "cosine", "similarity",
        # Fachbegriffe
        "grounding", "provenance", "hallucination", "chunk", "retrieval",
        "pipeline", "latency", "throughput", "inference",
        # Spezifisch
        "karpathy", "stanford", "cs229", "scaling", "chinchilla",
    }

    @staticmethod
    def _signal_factual(
        answer: str,
        chunk_texts: list[str],
    ) -> float:
        """Signal 5: Named Entity Matching — schützt vor Halluzinationen.

        Extrahiert technische Named Entities aus der Antwort und prüft
        ob sie in den Chunk-Texten vorkommen. Erkennt Fachbegriffe wie
        Voyage, Qdrant, BM25, GPT, RAG — nicht nur einfache Wörter.

        Niedriger Wert = Antwort verwendet Fachbegriffe die in keinem
        Chunk-Quelltext stehen.
        """
        if not chunk_texts or not answer:
            return 0.0

        ans_lower = answer.lower()
        chunk_all_lower = " ".join(ct.lower() for ct in chunk_texts)

        # Entities in der Antwort finden
        ans_entities = set()
        for entity in GroundingScorer._TECH_ENTITIES:
            if entity in ans_lower:
                ans_entities.add(entity)

        if not ans_entities:
            return 1.0  # Keine technischen Begriffe → neutral

        # Prüfen welche Entities auch in Chunks vorkommen
        matched = sum(1 for e in ans_entities if e in chunk_all_lower)
        score = matched / len(ans_entities)

        # Bonus: Wenn alle Entities matched → 1.0
        # Wenn keine → 0.0, dazwischen linear
        return round(min(score, 1.0), 4)

    @staticmethod
    def _signal_grounding(
        answer_emb: list[float],
        chunk_embs: list[list[float]],
    ) -> float:
        """Signal 3: Grounding — Wie stark basiert die Antwort auf Chunks?

        Embeddet die generierte Antwort und vergleicht sie mit den
        Chunk-Embeddings. Der maximale Cosine-Score zeigt: die Antwort
        überschneidet sich semantisch mit mindestens einem Chunk.

        Niedriges Grounding = Antwort nutzt vor allem LLM-Param-Wissen.
        """
        if not chunk_embs:
            return 0.0
        similarities = [_cosine_sim(answer_emb, ce) for ce in chunk_embs]
        return max(similarities) if similarities else 0.0

    @staticmethod
    def _signal_coverage(
        query_emb: list[float],
        chunk_embs: list[list[float]],
    ) -> float:
        """Signal 4: Coverage — Wie gut decken die Chunks die Frage ab?

        Misst die semantische Distanz zwischen Query und ALLEN Chunks.
        Niedrige std_dev + hohe mean_similarity = Chunks decken
        die Query-Breite gut ab.

        Idee: Je mehr Chunks hohe Ähnlichkeit zur Query haben,
        desto mehr Aspekte der Frage werden abgedeckt.
        """
        if not chunk_embs or len(chunk_embs) < 1:
            return 0.0
        similarities = [_cosine_sim(query_emb, ce) for ce in chunk_embs]
        mean_sim = sum(similarities) / len(similarities)
        # Bonus: mehr Chunks = mehr Coverage (logarithmisch, damit nicht übergewichtet)
        count_bonus = min(math.log2(len(chunk_embs) + 1) / 3.0, 1.0)
        return min((mean_sim * 0.7 + count_bonus * 0.3), 1.0)

    # ─ Aggregation ────────────────────────────────────────────────

    @staticmethod
    def _aggregate(signals: SignalScores) -> float:
        """Berechne Gesamt-Grounding aus den 5 Einzelsignalen.

        Gewichtung:
        - similarity:  25% (Query-Chunk Fit)
        - dominance:   15% (Stabilitat der Chunk-Basis)
        - grounding:   25% (Antwort-Chunk semantisch)
        - factual:     20% (Wort-Overlap, schuetzt vor Halluzinationen)
        - coverage:    15% (Breite der Abdeckung)
        """
        weights = {
            "similarity": 0.25,
            "dominance": 0.15,
            "grounding": 0.25,
            "factual":   0.20,
            "coverage":  0.15,
        }
        score = (
            signals.similarity * weights["similarity"]
            + signals.dominance * weights["dominance"]
            + signals.grounding * weights["grounding"]
            + signals.factual * weights["factual"]
            + signals.coverage * weights["coverage"]
        )
        return round(min(score, 1.0), 4)
