"""Deduplication — check edges to avoid re-discovering known relations.

v2.1.0: Checks against SQLite EdgeStore. Supports both active and proposed edges.
"""

from __future__ import annotations

import logging
from typing import Optional

from nexus.graph.store import EdgeStore

_logger = logging.getLogger(__name__)


def filter_new_edges(
    candidates: list[dict],
    store: EdgeStore,
) -> list[dict]:
    """Filter out candidates that already exist in the edge store.

    Args:
        candidates: List of ``{"source", "target", "relation", ...}`` dicts.
        store: An initialised ``EdgeStore`` instance.

    Returns:
        Only the candidates that do NOT already have an edge (any status)
        between the same source-target-relation triple.
    """
    new = []
    skipped = 0
    for c in candidates:
        source = c.get("source", "")
        target = c.get("target", "")
        relation = c.get("relation", "")

        if not source or not target or not relation:
            continue

        if store.has_any_edge(source, target, relation):
            skipped += 1
            _logger.debug(
                "Dedup skipped: %s --[%s]--> %s (already exists)",
                source, relation, target,
            )
            continue

        new.append(c)

    if skipped:
        _logger.info("Dedup: %d candidates skipped, %d new", skipped, len(new))
    return new


def count_existing(store: EdgeStore, source: str, target: str) -> int:
    """Count how many edges (any status) exist between two facts."""
    rows = store.conn.execute(
        """SELECT COUNT(*) FROM edges
           WHERE source_fact_id = ? AND target_fact_id = ?""",
        (source, target),
    ).fetchone()
    return rows[0] if rows else 0
