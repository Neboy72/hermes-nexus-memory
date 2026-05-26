"""Tests for nexus.graph — EdgeStore + SkillGraph.

All tests use temporary SQLite databases — no external dependencies.
"""

import os
import tempfile
from datetime import datetime, timezone

import networkx as nx
import pytest

from nexus.graph.schema import Edge, EdgeRelation, EdgeStatus
from nexus.graph.store import EdgeStore
from nexus.graph.graph import SkillGraph


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def db_path():
    """Temporary SQLite database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.join(tmpdir, "test.db")


@pytest.fixture
def store(db_path):
    """EdgeStore with initialized schema."""
    s = EdgeStore(db_path=db_path)
    s.initialize()
    yield s
    s.close()


@pytest.fixture
def graph(store):
    """SkillGraph backed by the test EdgeStore."""
    g = SkillGraph(store)
    g.initialize()
    return g


# ─── EdgeSchema ─────────────────────────────────────────────────────────────

class TestEdgeSchema:
    def test_new_creates_active_edge(self):
        e = Edge.new("src-fact", "tgt-fact", EdgeRelation.SUPPORTS.value)
        assert e.status == EdgeStatus.ACTIVE.value
        assert e.edge_id
        assert e.created_at == e.updated_at
        assert e.deprecated_at is None

    def test_edge_id_is_uuid(self):
        e = Edge.new("a", "b", EdgeRelation.DEPENDS_ON.value)
        assert len(e.edge_id) == 36
        assert e.edge_id.count("-") == 4

    def test_new_with_reason(self):
        e = Edge.new("a", "b", EdgeRelation.CONTRADICTS.value, reason="conflict detected")
        assert e.reason == "conflict detected"

    def test_to_dict_roundtrip(self):
        e1 = Edge.new("a", "b", EdgeRelation.SUPPORTS.value, reason="test")
        d = e1.to_dict()
        e2 = Edge.from_dict(d)
        assert e2.edge_id == e1.edge_id
        assert e2.source_fact_id == e1.source_fact_id
        assert e2.target_fact_id == e1.target_fact_id
        assert e2.relation == e1.relation
        assert e2.reason == e1.reason

    def test_enums(self):
        assert EdgeRelation.SUPERSEDES.value == "supersedes"
        assert EdgeRelation.CONTRADICTS.value == "contradicts"
        assert EdgeRelation.SUPPORTS.value == "supports"
        assert EdgeRelation.ALTERNATIVE_TO.value == "alternative_to"
        assert EdgeRelation.DEPENDS_ON.value == "depends_on"
        assert EdgeStatus.ACTIVE.value == "active"
        assert EdgeStatus.DEPRECATED.value == "deprecated"
        assert EdgeStatus.REJECTED.value == "rejected"


# ─── EdgeStore ──────────────────────────────────────────────────────────────

class TestEdgeStore:
    def test_initialize_creates_table(self, db_path):
        store = EdgeStore(db_path=db_path)
        store.initialize()
        # Verify table exists
        tables = store.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='edges'"
        ).fetchall()
        assert len(tables) == 1
        store.close()

    def test_add_edge_returns_edge(self, store):
        edge = store.add_edge("fact-a", "fact-b", EdgeRelation.SUPPORTS.value)
        assert edge.source_fact_id == "fact-a"
        assert edge.target_fact_id == "fact-b"
        assert edge.relation == "supports"
        assert edge.status == "active"

    def test_add_edge_with_metadata(self, store):
        meta = {"source": "drift-detector", "confidence": 0.85}
        edge = store.add_edge("a", "b", EdgeRelation.SUPPORTS.value, reason="auto", metadata=meta)
        import json
        assert json.loads(edge.metadata_json)["confidence"] == 0.85

    def test_get_edge_by_id(self, store):
        added = store.add_edge("a", "b", EdgeRelation.DEPENDS_ON.value)
        fetched = store.get_edge(added.edge_id)
        assert fetched is not None
        assert fetched.edge_id == added.edge_id
        assert fetched.source_fact_id == "a"

    def test_get_edge_missing(self, store):
        assert store.get_edge("nonexistent-id") is None

    def test_list_edges_by_fact(self, store):
        store.add_edge("alice", "bob", EdgeRelation.SUPPORTS.value)
        store.add_edge("alice", "charlie", EdgeRelation.DEPENDS_ON.value)
        store.add_edge("dave", "alice", EdgeRelation.SUPPORTS.value)

        alice_edges = store.list_edges(fact_id="alice")
        assert len(alice_edges) == 3  # 2 outgoing + 1 incoming

    def test_list_edges_filter_by_relation(self, store):
        store.add_edge("a", "b", EdgeRelation.SUPPORTS.value)
        store.add_edge("a", "c", EdgeRelation.DEPENDS_ON.value)

        supports = store.list_edges(fact_id="a", relation="supports")
        assert len(supports) == 1
        assert supports[0].relation == "supports"

    def test_list_edges_status_filter(self, store):
        e = store.add_edge("a", "b", EdgeRelation.SUPPORTS.value)
        store.reject_edge(e.edge_id)

        active = store.list_edges(fact_id="a", status="active")
        assert len(active) == 0

        rejected = store.list_edges(fact_id="a", status="rejected")
        assert len(rejected) == 1

    def test_reject_edge(self, store):
        e = store.add_edge("a", "b", EdgeRelation.SUPPORTS.value)
        rejected = store.reject_edge(e.edge_id, reason="false positive")
        assert rejected is not None
        assert rejected.status == "rejected"
        assert rejected.deprecated_at is not None

    def test_reject_missing_edge(self, store):
        result = store.reject_edge("nonexistent")
        assert result is None

    def test_deprecate_edge(self, store):
        e = store.add_edge("a", "b", EdgeRelation.SUPPORTS.value)
        deprecated = store.deprecate_edge(e.edge_id, reason="outdated")
        assert deprecated.status == "deprecated"
        assert deprecated.deprecated_at is not None

    def test_duplicate_active_edge_raises(self, store):
        store.add_edge("a", "b", EdgeRelation.SUPPORTS.value)
        with pytest.raises(Exception):  # sqlite3.IntegrityError
            store.add_edge("a", "b", EdgeRelation.SUPPORTS.value)

    def test_duplicate_different_relation_allowed(self, store):
        store.add_edge("a", "b", EdgeRelation.SUPPORTS.value)
        # Same pair, different relation — allowed
        e2 = store.add_edge("a", "b", EdgeRelation.CONTRADICTS.value)
        assert e2 is not None

    def test_reject_then_readd_allowed(self, store):
        e = store.add_edge("a", "b", EdgeRelation.SUPPORTS.value)
        store.reject_edge(e.edge_id)
        # After rejection, the UNIQUE constraint no longer blocks
        e2 = store.add_edge("a", "b", EdgeRelation.SUPPORTS.value)
        assert e2.status == "active"
        assert e2.edge_id != e.edge_id

    def test_invalid_relation_raises(self, store):
        with pytest.raises(ValueError, match="Invalid relation"):
            store.add_edge("a", "b", "invalid_relation")

    def test_has_active_edge(self, store):
        assert not store.has_active_edge("a", "b", EdgeRelation.SUPPORTS.value)
        store.add_edge("a", "b", EdgeRelation.SUPPORTS.value)
        assert store.has_active_edge("a", "b", EdgeRelation.SUPPORTS.value)

    def test_count_edges(self, store):
        assert store.count_edges() == 0
        store.add_edge("a", "b", EdgeRelation.SUPPORTS.value)
        store.add_edge("c", "d", EdgeRelation.DEPENDS_ON.value)
        assert store.count_edges() == 2
        assert store.count_edges(status="active") == 2


# ─── SkillGraph (NetworkX Cache) ────────────────────────────────────────────

class TestSkillGraph:
    def test_initialize_builds_cache(self, graph):
        graph.add_edge("a", "b", EdgeRelation.SUPPORTS.value)
        stats = graph.stats()
        assert stats["nodes"] == 2
        assert stats["edges"] == 1

    def test_has_node(self, graph):
        graph.add_edge("a", "b", EdgeRelation.SUPPORTS.value)
        assert graph.has_node("a")
        assert graph.has_node("b")
        assert not graph.has_node("nonexistent")

    def test_neighbors_outgoing(self, graph):
        graph.add_edge("a", "b", EdgeRelation.SUPPORTS.value)
        graph.add_edge("a", "c", EdgeRelation.DEPENDS_ON.value)

        nbs = graph.neighbors("a")
        assert len(nbs) == 2
        targets = {n["fact_id"] for n in nbs}
        assert "b" in targets
        assert "c" in targets

    def test_neighbors_incoming(self, graph):
        graph.add_edge("a", "z", EdgeRelation.DEPENDS_ON.value)
        graph.add_edge("b", "z", EdgeRelation.SUPPORTS.value)

        nbs = graph.neighbors("z")
        assert len(nbs) == 2
        sources = {n["fact_id"] for n in nbs}
        assert "a" in sources
        assert "b" in sources

    def test_neighbors_filter_by_relation(self, graph):
        graph.add_edge("a", "b", EdgeRelation.SUPPORTS.value)
        graph.add_edge("a", "c", EdgeRelation.DEPENDS_ON.value)

        supports = graph.neighbors("a", relation="supports")
        assert len(supports) == 1
        assert supports[0]["fact_id"] == "b"

    def test_neighbors_empty_for_unknown(self, graph):
        assert graph.neighbors("nonexistent") == []

    def test_mutation_triggers_rebuild(self, graph):
        graph.add_edge("x", "y", EdgeRelation.SUPPORTS.value)
        assert graph._graph.size() == 1

        # Find the edge and reject it
        edges = graph.store.list_edges(fact_id="x")
        graph.reject_edge(edges[0].edge_id)
        assert graph._graph.size() == 0  # Rebuilt: no active edges

    def test_add_edge_through_graph(self, graph):
        edge = graph.add_edge("a", "b", EdgeRelation.SUPPORTS.value, reason="via graph")
        assert edge.source_fact_id == "a"
        assert edge.reason == "via graph"

    def test_reject_edge_through_graph(self, graph):
        e = graph.add_edge("a", "b", EdgeRelation.SUPPORTS.value)
        result = graph.reject_edge(e.edge_id, reason="nope")
        assert result.status == "rejected"
        # Cache should be empty now
        assert graph._graph.size() == 0


# ─── find_path (BFS) ────────────────────────────────────────────────────────

class TestFindPath:
    def test_direct_path(self, graph):
        graph.add_edge("a", "b", EdgeRelation.DEPENDS_ON.value)
        path = graph.find_path("a", "b")
        assert len(path) == 1
        assert path[0]["source"] == "a"
        assert path[0]["target"] == "b"

    def test_indirect_path(self, graph):
        graph.add_edge("a", "b", EdgeRelation.DEPENDS_ON.value)
        graph.add_edge("b", "c", EdgeRelation.DEPENDS_ON.value)
        path = graph.find_path("a", "c")
        assert len(path) == 2
        assert path[0]["target"] == "b"
        assert path[1]["target"] == "c"

    def test_no_path(self, graph):
        graph.add_edge("a", "b", EdgeRelation.SUPPORTS.value)
        path = graph.find_path("a", "z")
        assert path == []

    def test_path_not_reversed(self, graph):
        """Path is directed — reverse should not work."""
        graph.add_edge("a", "b", EdgeRelation.SUPPORTS.value)
        path = graph.find_path("b", "a")
        assert path == []  # Directed edge a→b, not b→a

    def test_self_path(self, graph):
        path = graph.find_path("a", "a")
        assert path == []  # Self is not a path

    def test_unknown_source(self, graph):
        path = graph.find_path("unknown", "a")
        assert path == []

    def test_path_via_chain(self, graph):
        """Longer chain: a → b → c → d → e."""
        for src, tgt in [("a", "b"), ("b", "c"), ("c", "d"), ("d", "e")]:
            graph.add_edge(src, tgt, EdgeRelation.DEPENDS_ON.value)
        path = graph.find_path("a", "e")
        assert len(path) == 4
        assert path[-1]["target"] == "e"

    def test_max_depth_respected(self, graph):
        """Path longer than max_depth returns empty."""
        graph.add_edge("a", "b", EdgeRelation.DEPENDS_ON.value)
        graph.add_edge("b", "c", EdgeRelation.DEPENDS_ON.value)
        path = graph.find_path("a", "c", max_depth=1)
        assert path == []  # Path length 2 > max_depth 1


# ─── contradicts Symmetry ──────────────────────────────────────────────────

class TestContradictsSymmetry:
    def test_contradicts_is_symmetric_in_store(self, store):
        """list_edges returns contradicts for both source and target."""
        store.add_edge("a", "b", EdgeRelation.CONTRADICTS.value)

        a_edges = store.list_edges(fact_id="a")
        b_edges = store.list_edges(fact_id="b")

        # Both should find the edge (one active row matches both sides)
        assert len(a_edges) == 1
        assert len(b_edges) == 1

    def test_contradicts_is_symmetric_in_graph(self, graph):
        """graph.neighbors returns contradicts for both sides."""
        graph.add_edge("a", "b", EdgeRelation.CONTRADICTS.value)

        a_nbs = graph.neighbors("a")
        b_nbs = graph.neighbors("b")

        a_ids = {n["fact_id"] for n in a_nbs}
        b_ids = {n["fact_id"] for n in b_nbs}

        assert "b" in a_ids
        assert "a" in b_ids

    def test_contradicts_is_directed_in_storage(self, store):
        """Only ONE row is stored — not duplicated."""
        store.add_edge("a", "b", EdgeRelation.CONTRADICTS.value)
        count = store.count_edges(status="active")
        assert count == 1  # Single row, symmetric on read

    def test_no_duplicate_neighbors(self, graph):
        """contradicts neighbor should appear exactly once per query."""
        graph.add_edge("a", "b", EdgeRelation.CONTRADICTS.value)
        nbs = graph.neighbors("a")
        b_entries = [n for n in nbs if n["fact_id"] == "b"]
        assert len(b_entries) == 1  # Exactly once
