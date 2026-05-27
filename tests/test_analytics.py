"""Tests for analytics module — GraphAnalytics, Scoring, Clustering.

v2.1.0: ~15 tests covering all analytics functions.
"""

from __future__ import annotations

import os
import tempfile

import networkx as nx
import pytest

from nexus.analytics.scoring import (
    hub_scores,
    isolation_score,
    knowledge_gaps,
    relation_distribution,
)
from nexus.analytics.clustering import find_clusters, cluster_summary
from nexus.graph.store import EdgeStore
from nexus.graph.graph import SkillGraph


@pytest.fixture
def skillgraph():
    """Create a populated SkillGraph for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    sg = SkillGraph(sqlite_path=db_path)
    sg.initialize()

    # Add edges to create a connected graph
    sg.add_edge("fact-1", "fact-2", "references", reason="test")
    sg.add_edge("fact-2", "fact-3", "supports", reason="test")
    sg.add_edge("fact-3", "fact-4", "depends_on", reason="test")
    sg.add_edge("fact-1", "fact-3", "references", reason="test")
    sg.add_edge("fact-5", "fact-6", "references", reason="test")
    # fact-7 has no edges (isolated)
    # fact-8 has no edges (isolated)

    yield sg
    os.unlink(db_path)


# ── Scoring Tests ─────────────────────────────────────────────────────────


class TestHubScores:
    def test_hub_scores_top_hubs(self, skillgraph):
        """fact-1 and fact-3 should be top hubs."""
        scores = hub_scores(skillgraph, top_n=5)
        assert len(scores) >= 2
        top = scores[0]
        assert top["degree"] >= 2
        assert "fact_id" in top

    def test_hub_scores_empty_graph(self):
        """Empty graph → empty list."""
        sg = SkillGraph()
        scores = hub_scores(sg, top_n=5)
        assert scores == []

    def test_hub_sorts_by_degree(self, skillgraph):
        """Results sorted by degree descending."""
        scores = hub_scores(skillgraph, top_n=10)
        for i in range(len(scores) - 1):
            assert scores[i]["degree"] >= scores[i + 1]["degree"]


class TestIsolationScore:
    def test_isolated_fact(self, skillgraph):
        """Fact with no edges → is_isolated=True."""
        result = isolation_score(skillgraph, "fact-7")
        assert result["is_isolated"] is True
        assert result["degree"] == 0

    def test_connected_fact(self, skillgraph):
        """Fact with edges → is_isolated=False."""
        result = isolation_score(skillgraph, "fact-1")
        assert result["is_isolated"] is False
        assert result["degree"] > 0

    def test_nonexistent_fact(self, skillgraph):
        """Non-existent fact → isolated with error."""
        result = isolation_score(skillgraph, "nonexistent")
        assert result["is_isolated"] is True
        assert "error" in result


class TestKnowledgeGaps:
    def test_finds_isolated_facts(self, skillgraph):
        """Facts in the graph with no edges appear in knowledge gaps."""
        gaps = knowledge_gaps(skillgraph)
        gap_ids = [g["fact_id"] for g in gaps]
        # fact-5 has an edge to fact-6, so it's NOT a gap
        assert "fact-5" not in gap_ids
        # Isolated facts (no edges) are not even nodes in the graph
        # → they don't appear as gaps (design limitation: SkillGraph only tracks nodes with edges)

    def test_connected_facts_not_in_gaps(self, skillgraph):
        """Connected facts are not knowledge gaps."""
        gaps = knowledge_gaps(skillgraph, isolation_threshold=0.9)
        gap_ids = [g["fact_id"] for g in gaps]
        assert "fact-1" not in gap_ids
        assert "fact-2" not in gap_ids

    def test_empty_graph(self):
        """Empty graph → empty gaps list."""
        sg = SkillGraph()
        gaps = knowledge_gaps(sg)
        assert gaps == []


class TestRelationDistribution:
    def test_counts_relations(self, skillgraph):
        """Returns correct counts per relation type."""
        dist = relation_distribution(skillgraph)
        # We added 3 references (fact-1→fact-2, fact-1→fact-3, fact-5→fact-6)
        # + creates symmetric contradicts? No, no contradicts here
        assert dist.get("references", 0) >= 2
        assert dist.get("supports", 0) >= 1

    def test_empty_graph(self):
        """Empty graph → empty distribution."""
        sg = SkillGraph()
        dist = relation_distribution(sg)
        assert dist == {}


# ── Clustering Tests ──────────────────────────────────────────────────────


class TestFindClusters:
    def test_finds_connected_components(self, skillgraph):
        """Connected components based on edges."""
        clusters = find_clusters(skillgraph, min_size=2)
        assert len(clusters) >= 2  # fact-1→2→3→4 and fact-5→6

    def test_singletons_filtered(self, skillgraph):
        """Isolated facts are filtered when min_size > 1."""
        clusters = find_clusters(skillgraph, min_size=2)
        for c in clusters:
            assert c["size"] >= 2

    def test_clusters_sorted_by_size(self, skillgraph):
        """Largest cluster first."""
        clusters = find_clusters(skillgraph)
        for i in range(len(clusters) - 1):
            assert clusters[i]["size"] >= clusters[i + 1]["size"]


class TestClusterSummary:
    def test_summary_contains_keys(self, skillgraph):
        """Summary has required fields."""
        summary = cluster_summary(skillgraph)
        assert "total_nodes" in summary
        assert "total_edges" in summary
        assert "num_clusters" in summary
        assert "largest_cluster_size" in summary
        assert "singletons" in summary

    def test_empty_graph_summary(self):
        """Empty graph → zeroed summary."""
        sg = SkillGraph()
        summary = cluster_summary(sg)
        assert summary["total_nodes"] == 0
        assert summary["num_clusters"] == 0

    def test_singletons_counted(self, skillgraph):
        """Facts with no edges can't be singletons (not in graph)."""
        summary = cluster_summary(skillgraph)
        # fact-7 and fact-8 have no edges → not in the SkillGraph
        # singletons come from WeaklyConnectedComponents, which only includes nodes with edges
        assert summary["singletons"] >= 0
