"""Tests for nexus.graph — SkillGraph v2.0.0."""

import os
import tempfile

import pytest

from nexus.graph import Edge, EdgeRelation, EdgeStatus, EdgeStore, SkillGraph


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory() as tmp:
        yield os.path.join(tmp, "test_graph.db")


@pytest.fixture
def store(db_path):
    s = EdgeStore(db_path=db_path)
    s.initialize()
    return s


@pytest.fixture
def graph(db_path):
    g = SkillGraph(sqlite_path=db_path)
    g.initialize()
    return g


@pytest.fixture
def populated_graph(graph):
    """Graph with sample edges for query tests."""
    g = graph
    g.add_edge("fact-a", "fact-b", "supersedes", reason="v1.1")
    g.add_edge("fact-b", "fact-c", "supersedes", reason="v2.0")
    g.add_edge("fact-a", "fact-d", "contradicts", reason="conflict")
    g.add_edge("fact-e", "fact-a", "contradicts", reason="audit")
    g.add_edge("fact-f", "fact-c", "supports", reason="evidence")
    g.add_edge("fact-f", "fact-g", "supports", reason="evidence2")
    g.add_edge("fact-d", "fact-e", "alternative_to")
    g.add_edge("fact-g", "fact-h", "depends_on")
    return g


# ── Schema & Edge ──────────────────────────────────────────────────────────


class TestEdge:
    def test_new_creates_active_edge(self):
        e = Edge.new("f1", "f2", EdgeRelation.SUPPORTS.value)
        assert e.source_fact_id == "f1"
        assert e.target_fact_id == "f2"
        assert e.relation == "supports"
        assert e.status == "active"
        assert e.edge_id is not None

    def test_to_dict(self):
        e = Edge.new("a", "b", "contradicts", reason="test")
        d = e.to_dict()
        assert d["source_fact_id"] == "a"
        assert d["relation"] == "contradicts"
        assert d["reason"] == "test"

    def test_from_dict(self):
        d = {
            "edge_id": "abc123",
            "source_fact_id": "s",
            "target_fact_id": "t",
            "relation": "supports",
            "status": "active",
            "created_at": "2026-01-01",
            "updated_at": "2026-01-01",
        }
        e = Edge.from_dict(d)
        assert e.edge_id == "abc123"
        assert e.relation == "supports"


# ── EdgeStore CRUD ─────────────────────────────────────────────────────────


class TestEdgeStore:
    def test_add_edge(self, store):
        e = store.add_edge("f1", "f2", "contradicts", reason="conflict")
        assert e.edge_id is not None
        assert e.relation == "contradicts"
        assert e.reason == "conflict"

    def test_add_edge_invalid_relation(self, store):
        with pytest.raises(ValueError, match="Invalid relation"):
            store.add_edge("f1", "f2", "invalid")

    def test_get_edge(self, store):
        created = store.add_edge("f1", "f2", "supports")
        fetched = store.get_edge(created.edge_id)
        assert fetched is not None
        assert fetched.source_fact_id == "f1"

    def test_get_edge_not_found(self, store):
        assert store.get_edge("nonexistent") is None

    def test_list_edges_by_fact(self, store):
        store.add_edge("a", "b", "supports")
        store.add_edge("a", "c", "contradicts")
        edges = store.list_edges(fact_id="a")
        assert len(edges) == 2

    def test_list_edges_by_relation(self, store):
        store.add_edge("a", "b", "supports")
        store.add_edge("a", "c", "contradicts")
        edges = store.list_edges(relation="supports")
        assert len(edges) == 1

    def test_has_active_edge(self, store):
        store.add_edge("a", "b", "supports")
        assert store.has_active_edge("a", "b", "supports") is True
        assert store.has_active_edge("a", "c", "supports") is False

    def test_reject_edge(self, store):
        e = store.add_edge("a", "b", "supports")
        rejected = store.reject_edge(e.edge_id)
        assert rejected.status == "rejected"
        assert store.count_edges(status="active") == 0

    def test_deprecate_edge(self, store):
        e = store.add_edge("a", "b", "supports")
        deprecated = store.deprecate_edge(e.edge_id)
        assert deprecated.status == "deprecated"

    def test_count_edges(self, store):
        store.add_edge("a", "b", "supports")
        store.add_edge("c", "d", "contradicts")
        assert store.count_edges() == 2
        assert store.count_edges(status="active") == 2

    def test_persistence(self, db_path):
        """Edges survive across EdgeStore instances."""
        s1 = EdgeStore(db_path=db_path)
        s1.initialize()
        s1.add_edge("f1", "f2", "supersedes")

        s2 = EdgeStore(db_path=db_path)
        s2.initialize()
        assert s2.count_edges() == 1


# ── SkillGraph Queries ─────────────────────────────────────────────────────


class TestSkillGraph:
    def test_add_and_rebuild(self, graph):
        graph.add_edge("a", "b", "contradicts")
        assert graph.has_node("a")
        assert graph.has_node("b")

    def test_get_neighbors_outgoing(self, populated_graph):
        neighbors = populated_graph.neighbors("fact-a")
        assert len(neighbors) >= 2  # a→b (supersedes), a→d (contradicts) + symmetric
        outgoing = [n for n in neighbors if n["direction"] == "outgoing"]
        # contradicts is symmetric: fact-e→a creates also a→e in the graph
        # so we get: a→b, a→d, a→e = 3 outgoing
        assert len(outgoing) >= 2

    def test_get_neighbors_filter_by_relation(self, populated_graph):
        neighbors = populated_graph.neighbors("fact-a", relation="supersedes")
        assert len(neighbors) == 1
        assert neighbors[0]["fact_id"] == "fact-b"

    def test_find_path_direct(self, populated_graph):
        paths = populated_graph.find_path("fact-a", "fact-c")
        assert len(paths) >= 1
        assert paths[0]["source"] == "fact-a"
        assert paths[0]["relation"] == "supersedes"

    def test_find_path_no_path(self, populated_graph):
        paths = populated_graph.find_path("fact-a", "fact-z")
        assert paths == []

    def test_find_path_max_depth(self, graph):
        """Beyond max_depth, BFS should not find the path."""
        graph.add_edge("a", "b", "supersedes")
        graph.add_edge("b", "c", "supersedes")
        # Default max_depth is 10, so this should work
        path = graph.find_path("a", "c", max_depth=1)
        # a→b is 1 step, b→c would be step 2 which exceeds max_depth
        assert path == []

    def test_find_path_same_node(self, graph):
        graph.add_edge("a", "b", "supports")
        assert graph.find_path("a", "a") == []

    def test_find_path_missing_node(self, graph):
        assert graph.find_path("does-not-exist", "a") == []

    def test_list_edges_on_graph(self, populated_graph):
        edges = populated_graph.list_edges(fact_id="fact-a")
        assert len(edges) >= 3  # outgoing + incoming

    def test_get_edge(self, populated_graph):
        e = populated_graph.add_edge("x", "y", "supports")
        fetched = populated_graph.get_edge(e.edge_id)
        assert fetched is not None
        assert fetched.source_fact_id == "x"


# ── Contradiction Chain ────────────────────────────────────────────────────


class TestContradictionChain:
    def test_direct_contradictions(self, populated_graph):
        chain = populated_graph.get_contradiction_chain("fact-a")
        assert len(chain) >= 2  # fact-d + fact-e contradict a

    def test_transitive_contradictions(self, graph):
        graph.add_edge("a", "b", "contradicts")
        graph.add_edge("b", "c", "contradicts")
        chain = graph.get_contradiction_chain("a")
        assert len(chain) == 2
        assert chain[0]["fact_id"] == "b"
        assert chain[1]["fact_id"] == "c"

    def test_no_contradictions(self, populated_graph):
        chain = populated_graph.get_contradiction_chain("fact-h")
        assert chain == []


# ── Support Chain ──────────────────────────────────────────────────────────


class TestSupportChain:
    def test_direct_support(self, populated_graph):
        chain = populated_graph.get_support_chain("fact-f")
        assert len(chain) == 2  # f→c, f→g

    def test_no_support(self, graph):
        chain = graph.get_support_chain("orphan")
        assert chain == []


# ── Edge Lifecycle Integration ─────────────────────────────────────────────


class TestLifecycleIntegration:
    def test_deprecated_edge_removed_from_neighbors(self, graph):
        e = graph.add_edge("a", "b", "supports")
        graph.add_edge("a", "c", "supports")
        graph.deprecate_edge(e.edge_id)

        neighbors = graph.neighbors("a")
        assert len(neighbors) == 1  # only a→c
        assert neighbors[0]["fact_id"] == "c"

    def test_path_excludes_deprecated(self, graph):
        graph.add_edge("a", "b", "supersedes")
        e2 = graph.add_edge("b", "c", "supersedes")
        graph.deprecate_edge(e2.edge_id)

        path = graph.find_path("a", "c")
        assert path == []

    def test_rejected_edge_removed(self, graph):
        e = graph.add_edge("a", "b", "contradicts")
        graph.reject_edge(e.edge_id)

        chain = graph.get_contradiction_chain("a")
        assert chain == []


# ── Stats ──────────────────────────────────────────────────────────────────


class TestStats:
    def test_empty_graph(self, graph):
        s = graph.stats()
        assert s["nodes"] == 0
        assert s["edges"] == 0

    def test_populated(self, populated_graph):
        s = populated_graph.stats()
        assert s["nodes"] > 0
        assert s["edges"] > 0
        assert "db_path" in s
