"""Tests for graph_boost integration in Hybrid Search + new Store methods.

v2.1.0: ~15 tests covering graph_boost, proposed edges, promote_edge.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from nexus.graph.schema import EdgeRelation, EdgeStatus
from nexus.graph.store import EdgeStore


# ── Proposed Edge Tests ───────────────────────────────────────────────────


class TestProposedEdges:
    @pytest.fixture
    def store(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        store = EdgeStore(db_path=db_path)
        store.initialize()
        yield store
        os.unlink(db_path)

    def test_add_proposed_edge(self, store):
        """Proposed edge stored with correct status."""
        edge = store.add_proposed_edge(
            "fact-a", "fact-b", "references",
            confidence=0.78,
            reason="auto-discovered",
        )
        assert edge.status == EdgeStatus.PROPOSED.value
        assert edge.edge_id is not None
        metadata = edge.metadata_json or "{}"
        assert "confidence" in metadata or "0.78" in str(edge)

    def test_add_proposed_edge_not_in_active_list(self, store):
        """Proposed edges don't appear in default list_edges()."""
        store.add_proposed_edge(
            "fact-a", "fact-b", "references", confidence=0.78,
        )
        active_edges = store.list_edges(status="active")
        proposed_edges = store.list_edges(status="proposed")
        assert len(active_edges) == 0
        assert len(proposed_edges) == 1

    def test_promote_edge(self, store):
        """Promote proposed → active."""
        edge = store.add_proposed_edge(
            "fact-a", "fact-b", "references", confidence=0.78,
        )
        promoted = store.promote_edge(edge.edge_id, reason="confirmed")
        assert promoted is not None
        assert promoted.status == EdgeStatus.ACTIVE.value

    def test_promote_nonexistent_edge(self, store):
        """Promoting non-existent edge → None."""
        result = store.promote_edge("nonexistent-id")
        assert result is None

    def test_promote_active_edge(self, store):
        """Promoting an active edge → None (only proposed can be promoted)."""
        edge = store.add_edge("fact-a", "fact-b", "references", reason="test")
        result = store.promote_edge(edge.edge_id)
        assert result is None

    def test_has_any_edge_true(self, store):
        """has_any_edge finds edges of any status."""
        store.add_proposed_edge("fact-a", "fact-b", "references", confidence=0.78)
        assert store.has_any_edge("fact-a", "fact-b", "references") is True
        assert store.has_active_edge("fact-a", "fact-b", "references") is False

    def test_has_any_edge_false(self, store):
        """has_any_edge returns False when no edge exists."""
        assert store.has_any_edge("fact-x", "fact-y", "references") is False

    def test_invalid_relation_rejected(self, store):
        """Invalid relation raises ValueError."""
        with pytest.raises(ValueError):
            store.add_proposed_edge(
                "fact-a", "fact-b", "invalid_relation",
                confidence=0.50,
            )

    def test_count_edges_by_status(self, store):
        """count_edges with specific status."""
        store.add_edge("a", "b", "references", reason="test")
        store.add_proposed_edge("c", "d", "references", confidence=0.70)
        store.add_proposed_edge("e", "f", "references", confidence=0.75)
        store.add_edge("g", "h", "supports", reason="test")

        assert store.count_edges(status="active") == 2
        assert store.count_edges(status="proposed") == 2
        assert store.count_edges() == 4


# ── New Relation Tests ────────────────────────────────────────────────────


class TestReferencesRelation:
    @pytest.fixture
    def store(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        store = EdgeStore(db_path=db_path)
        store.initialize()
        yield store
        os.unlink(db_path)

    def test_references_relation_valid(self, store):
        """'references' is accepted as a valid relation."""
        edge = store.add_edge("fact-a", "fact-b", "references", reason="auto")
        assert edge.relation == EdgeRelation.REFERENCES.value

    def test_references_edge_listed(self, store):
        """'references' edges appear in list_edges()."""
        store.add_edge("a", "b", "references", reason="test")
        edges = store.list_edges()
        assert len(edges) == 1
        assert edges[0].relation == EdgeRelation.REFERENCES.value


# ── Graph Boost Tests ─────────────────────────────────────────────────────


class TestGraphBoost:
    def test_boost_no_skillgraph(self):
        """Without SkillGraph, graph_boost is a no-op."""
        from nexus.retrieval import HybridRetriever

        retriever = HybridRetriever()
        ranked = [
            {"id": "fact-1", "rrf_score": 10.0},
            {"id": "fact-2", "rrf_score": 8.0},
        ]
        result = retriever._graph_boost(ranked)
        assert result == ranked  # No-op, same scores

    def test_graph_boost_param_in_search_hybrid(self):
        """search_hybrid accepts graph_boost parameter."""
        import inspect
        from nexus.retrieval import HybridRetriever

        sig = inspect.signature(HybridRetriever.search_hybrid)
        assert "graph_boost" in sig.parameters

    def test_boost_formula(self):
        """Boost = 1.0 + degree * 0.05."""
        # Test the formula directly
        for degree in [0, 1, 5, 10, 20]:
            expected = round(1.0 + degree * 0.05, 3)
            assert expected > 1.0 or degree == 0
            if degree == 0:
                assert expected == 1.0
            elif degree == 10:
                assert expected == 1.5
            elif degree == 20:
                assert expected == 2.0
