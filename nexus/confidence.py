"""Confidence Scoring for RAG — 4-Signal-Methode.

Bewertet wie vertrauenswürdig eine generierte Antwort basierend auf
den retrieved Chunks ist. Ändert nichts an der bestehenden Pipeline.

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
class ConfidenceReport:
    """Vollständiger Report für einen evaluate()-Durchlauf."""
    query: str = ""
    answer: str = ""
    signals: SignalScores = field(default_factory=SignalScores)
    confidence: float = 0.0
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
    collection: str = "hermes-memory",
    top_k: int = 5,
) -> list[dict]:
    """Hole die Top-K Chunks aus Qdrant (mit voller Payload)."""
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


# ── Confidence Scorer ──────────────────────────────────────────────


class ConfidenceScorer:
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
        collection: str = "hermes-memory",
        top_k: int = 5,
    ):
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
        """Vollständige Confidence-Bewertung.

        Args:
            query: Die ursprüngliche User-Frage.
            answer: Die generierte Antwort.
            chunks: Optional — bereits geretrievede Chunks.
                    Bei None werden sie aus Qdrant geholt.

        Returns:
            ConfidenceReport mit allen Signalen.
        """
        report = ConfidenceReport(query=query, answer=answer)

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

        # Schritt 5: Gesamt-Confidence + Label
        report.confidence = self._aggregate(signals)
        report.chunk_count = len(chunks)
        report.label = self._label(report.confidence)

        return report

    @staticmethod
    def _label(confidence: float) -> str:
        """Menschlesbares Label fuer den Confidence-Wert."""
        if confidence >= 0.8:
            return "🟢 Sehr hoch"
        elif confidence >= 0.6:
            return "🟡 Hoch"
        elif confidence >= 0.4:
            return "🟠 Mittel"
        elif confidence >= 0.2:
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

    @staticmethod
    def _signal_factual(
        answer: str,
        chunk_texts: list[str],
    ) -> float:
        """Signal 5: Faktische Überlappung — Schutz vor Halluzinationen.

        Extrahiert signifikante Wörter (>3 Buchstaben, keine Stopwords)
        aus der Antwort und prüft ob sie in den Chunk-Texten vorkommen.
        Niedriger Wert = Antwort verwendet Begriffe die in keinem Chunk stehen.
        """
        if not chunk_texts or not answer:
            return 0.0

        # Einfache Stopwords (Deutsch + Englisch)
        stopwords = {
            "der", "die", "das", "den", "dem", "des", "ein", "eine", "einer",
            "eines", "einem", "und", "oder", "aber", "mit", "von", "für",
            "auf", "bei", "aus", "nach", "vor", "durch", "über", "unter",
            "zwischen", "an", "am", "im", "in", "ist", "sind", "war", "wird",
            "werden", "hat", "haben", "hätte", "the", "and", "for", "with",
            "this", "that", "from", "have", "been", "were", "nicht", "kein",
            "keine", "auch", "nur", "schon", "noch", "bis", "wie", "als",
            "wenn", "dann", "dort", "hier", "da", "es", "sie", "er", "wir",
            "ihr", "sie", "sich", "zum", "zur", "beim", "ins", "dass",
        }

        # Tokenisiere Antwort
        ans_words = set(
            w.lower().strip(".,!?;:()[]{}'\"-")
            for w in answer.split()
            if len(w) > 3 and w.lower().strip(".,!?;:()[]{}'\"-") not in stopwords
        )

        if not ans_words:
            return 1.0  # Keine signifikanten Wörter → neutral

        # Tokenisiere alle Chunks
        chunk_all_words = set()
        for ct in chunk_texts:
            for w in ct.split():
                cleaned = w.lower().strip(".,!?;:()[]{}'\"-")
                if len(cleaned) > 3 and cleaned not in stopwords:
                    chunk_all_words.add(cleaned)

        if not chunk_all_words:
            return 0.0

        # Overlap: wie viele Antwort-Wörter kommen in Chunks vor?
        overlap = ans_words & chunk_all_words
        return len(overlap) / len(ans_words)

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
        """Berechne Gesamt-Confidence aus den 5 Einzelsignalen.

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
