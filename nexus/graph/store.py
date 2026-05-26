from __future__ import annotations

"""EdgeStore — SQLite-backed CRUD for SkillGraph edges.

All mutations go through this class first (Source of Truth).
NetworkX cache in ``graph.py`` is rebuilt from here.
"""

import json
import logging
import os
import sqlite3
from typing import Any, Optional

from nexus.graph.schema import (
    CREATE_EDGES_TABLE,
    CREATE_EDGES_INDEX_ACTIVE_UNIQUE,
    CREATE_EDGES_INDEX_SOURCE,
    CREATE_EDGES_INDEX_TARGET,
    CREATE_EDGES_INDEX_STATUS,
    Edge,
    EdgeRelation,
    EdgeStatus,
)

_logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = os.path.expanduser("~/.hermes/skillgraph.db")


class EdgeStore:
    """SQLite-persisted edge store — the single Source of Truth.

    All edge mutations go through this class.  The ``SkillGraph``
    (``nexus.graph.graph``) reads from here and caches in NetworkX.

    Usage::

        store = EdgeStore()
        store.initialize()
        edge = store.add_edge("fact-a", "fact-b", "supports", reason="confirmed")
        edge = store.get_edge(edge.edge_id)
        edges = store.list_edges("fact-a")
        store.reject_edge(edge.edge_id, reason="false positive")
    """

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or DEFAULT_DB_PATH
        self._conn: sqlite3.Connection | None = None

    # ── Connection ──────────────────────────────────────────────────────────

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ── Schema ──────────────────────────────────────────────────────────────

    def initialize(self) -> None:
        """Create the edges table + indexes if they don't exist."""
        for stmt in (
            CREATE_EDGES_TABLE,
            CREATE_EDGES_INDEX_ACTIVE_UNIQUE,
            CREATE_EDGES_INDEX_SOURCE,
            CREATE_EDGES_INDEX_TARGET,
            CREATE_EDGES_INDEX_STATUS,
        ):
            self.conn.execute(stmt)
        self.conn.commit()

    # ── CRUD ────────────────────────────────────────────────────────────────

    def add_edge(
        self,
        source_fact_id: str,
        target_fact_id: str,
        relation: str,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Edge:
        """Create a new active edge between two facts.

        Args:
            source_fact_id: From-fact.
            target_fact_id: To-fact.
            relation: One of ``EdgeRelation`` values.
            reason: Optional human-readable explanation.
            metadata: Optional dict (stored as JSON).

        Returns:
            The newly created ``Edge``.

        Raises:
            ValueError: If the relation string is not a valid ``EdgeRelation``.
            sqlite3.IntegrityError: If a duplicate active edge already exists.
        """
        # Validate relation
        valid_relations = {e.value for e in EdgeRelation}
        if relation not in valid_relations:
            raise ValueError(
                f"Invalid relation '{relation}'. "
                f"Must be one of: {', '.join(sorted(valid_relations))}"
            )

        edge = Edge.new(
            source_fact_id=source_fact_id,
            target_fact_id=target_fact_id,
            relation=relation,
            reason=reason,
            metadata_json=json.dumps(metadata) if metadata else None,
        )

        self.conn.execute(
            """INSERT INTO edges
               (edge_id, source_fact_id, target_fact_id, relation, status,
                created_at, updated_at, reason, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                edge.edge_id,
                edge.source_fact_id,
                edge.target_fact_id,
                edge.relation,
                edge.status,
                edge.created_at,
                edge.updated_at,
                edge.reason,
                edge.metadata_json,
            ),
        )
        self.conn.commit()
        _logger.info(
            "Edge added: %s (%s) --[%s]--> %s",
            source_fact_id, relation, edge.edge_id, target_fact_id,
        )
        return edge

    def get_edge(self, edge_id: str) -> Edge | None:
        """Fetch a single edge by ID."""
        row = self.conn.execute(
            "SELECT * FROM edges WHERE edge_id = ?", (edge_id,)
        ).fetchone()
        return self._row_to_edge(row) if row else None

    def list_edges(
        self,
        fact_id: str | None = None,
        relation: str | None = None,
        status: str | None = "active",
    ) -> list[Edge]:
        """List edges, optionally filtered.

        ``contradicts`` edges are returned **symmetrically**: an edge
        ``A --[contradicts]--> B`` appears in results for both
        ``list_edges("A")`` and ``list_edges("B")``.
        """
        conditions: list[str] = []
        params: list[Any] = []

        if fact_id:
            conditions.append("(source_fact_id = ? OR target_fact_id = ?)")
            params.extend([fact_id, fact_id])
        if relation:
            conditions.append("relation = ?")
            params.append(relation)
        if status is not None:
            conditions.append("status = ?")
            params.append(status)

        where = " AND ".join(conditions) if conditions else "1"
        rows = self.conn.execute(
            f"SELECT * FROM edges WHERE {where} ORDER BY created_at DESC",
            params,
        ).fetchall()
        results = [self._row_to_edge(r) for r in rows]

        # Symmetric contradicts: if fact_id is set, also return edges
        # where the fact is the TARGET of a contradicts edge.
        # (Already handled above via OR in the WHERE clause.)
        return results

    def reject_edge(self, edge_id: str, reason: str | None = None) -> Edge | None:
        """Reject (soft-delete) an active edge.

        Sets status to ``rejected`` and records ``deprecated_at``.
        The edge stays in the database (append-only principle).

        Returns ``None`` if no active edge was found with that ID.
        """
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        cursor = self.conn.execute(
            """UPDATE edges
               SET status = 'rejected', deprecated_at = ?,
                   updated_at = ?, reason = COALESCE(?, reason)
               WHERE edge_id = ? AND status = 'active'""",
            (now, now, reason, edge_id),
        )
        self.conn.commit()
        if cursor.rowcount == 0:
            _logger.warning("No active edge found with edge_id=%s", edge_id)
            return None
        return self.get_edge(edge_id)

    def deprecate_edge(self, edge_id: str, reason: str | None = None) -> Edge | None:
        """Deprecate an active edge (softer than reject).

        Returns ``None`` if no active edge was found with that ID.
        """
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        cursor = self.conn.execute(
            """UPDATE edges
               SET status = 'deprecated', deprecated_at = ?,
                   updated_at = ?, reason = COALESCE(?, reason)
               WHERE edge_id = ? AND status = 'active'""",
            (now, now, reason, edge_id),
        )
        self.conn.commit()
        if cursor.rowcount == 0:
            _logger.warning("No active edge found with edge_id=%s", edge_id)
            return None
        return self.get_edge(edge_id)

    # ── Edge existence check ────────────────────────────────────────────────

    def has_active_edge(
        self,
        source_fact_id: str,
        target_fact_id: str,
        relation: str,
    ) -> bool:
        """Check if an active edge already exists between these facts."""
        row = self.conn.execute(
            """SELECT 1 FROM edges
               WHERE source_fact_id = ? AND target_fact_id = ?
                 AND relation = ? AND status = 'active'
               LIMIT 1""",
            (source_fact_id, target_fact_id, relation),
        ).fetchone()
        return row is not None

    # ── Count / Stats ───────────────────────────────────────────────────────

    def count_edges(self, status: str | None = None) -> int:
        if status:
            row = self.conn.execute(
                "SELECT COUNT(*) FROM edges WHERE status = ?", (status,)
            ).fetchone()
        else:
            row = self.conn.execute("SELECT COUNT(*) FROM edges").fetchone()
        return row[0] if row else 0

    # ── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_edge(row: sqlite3.Row) -> Edge:
        return Edge.from_dict(dict(row))
