"""Nexus Memory — Persistent vector memory for Hermes Agent.

Three layers of intelligence:
- Core: Semantic vector search via Qdrant + multiple embedding backends
- Retrieval: Hybrid BM25 + Vector + Reciprocal Rank Fusion (anti-poisoning)
- Health: Belief drift detection (anti-staleness)
"""

from nexus.health import DriftDetector, DriftReport
from nexus.retrieval import HybridRetriever

__version__ = "1.1.0"

__all__ = [
    "HybridRetriever",
    "DriftDetector",
    "DriftReport",
]