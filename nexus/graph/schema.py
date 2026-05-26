"""SkillGraph schema — Edge dataclass, enums, SQLite DDL.

Design decisions (verified by Miosha, v2.0.0 review):
  - relation and status are separate columns (never mixed).
  - UNIQUE on (source_fact_id, target_fact_id, relation, status) where
    status = 'active' — prevents duplicate active edges.
  - edge_id is a UUID primary key.
  - deprecated_at is NULL until the edge is rejected.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


# ── Enums ──────────────────────────────────────────────────────────────────


class EdgeRelation(str, Enum):
    """Semantic relation between two facts.

    Core set for v2.0.0 — no extensions yet.
    """

    SUPERSEDES = "supersedes"        # A replaces B (B is obsolete)
    CONTRADICTS = "contradicts"      # A conflicts with B (semantic opposition)
    SUPPORTS = "supports"            # A reinforces / confirms B
    ALTERNATIVE_TO = "alternative_to"  # A is a viable alternative to B
    DEPENDS_ON = "depends_on"        # A requires B (dependency)


class EdgeStatus(str, Enum):
    """Lifecycle status of an edge.

    Kept deliberately simpler than the Fact lifecycle:
    active → deprecated | rejected
    """
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    REJECTED = "rejected"


# ── Edge Dataclass ─────────────────────────────────────────────────────────


@dataclass
class Edge:
    """A single directed edge between two facts in the SkillGraph."""

    edge_id: str
    source_fact_id: str               # from-fact
    target_fact_id: str               # to-fact
    relation: str                     # EdgeRelation value
    status: str                       # EdgeStatus value
    created_at: str                   # ISO timestamp
    updated_at: str                   # ISO timestamp
    deprecated_at: Optional[str] = None  # set on reject / deprecate
    reason: Optional[str] = None      # why this edge was created or rejected
    metadata_json: Optional[str] = None  # optional JSON blob

    @classmethod
    def new(
        cls,
        source_fact_id: str,
        target_fact_id: str,
        relation: str,
        reason: Optional[str] = None,
        metadata_json: Optional[str] = None,
    ) -> "Edge":
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            edge_id=str(uuid.uuid4()),
            source_fact_id=source_fact_id,
            target_fact_id=target_fact_id,
            relation=relation,
            status=EdgeStatus.ACTIVE.value,
            created_at=now,
            updated_at=now,
            reason=reason,
            metadata_json=metadata_json,
        )

    def to_dict(self) -> dict:
        return {
            "edge_id": self.edge_id,
            "source_fact_id": self.source_fact_id,
            "target_fact_id": self.target_fact_id,
            "relation": self.relation,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "deprecated_at": self.deprecated_at,
            "reason": self.reason,
            "metadata_json": self.metadata_json,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Edge":
        return cls(
            edge_id=d["edge_id"],
            source_fact_id=d["source_fact_id"],
            target_fact_id=d["target_fact_id"],
            relation=d["relation"],
            status=d.get("status", EdgeStatus.ACTIVE.value),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            deprecated_at=d.get("deprecated_at"),
            reason=d.get("reason"),
            metadata_json=d.get("metadata_json"),
        )


# ── SQLite DDL ─────────────────────────────────────────────────────────────


CREATE_EDGES_TABLE = """
CREATE TABLE IF NOT EXISTS edges (
    edge_id          TEXT PRIMARY KEY,
    source_fact_id   TEXT NOT NULL,
    target_fact_id   TEXT NOT NULL,
    relation         TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'active',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    deprecated_at    TEXT,
    reason           TEXT,
    metadata_json    TEXT
);
"""

CREATE_EDGES_INDEX_ACTIVE_UNIQUE = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_edges_active_unique
    ON edges(source_fact_id, target_fact_id, relation)
    WHERE status = 'active';
"""

CREATE_EDGES_INDEX_SOURCE = """
CREATE INDEX IF NOT EXISTS idx_edges_source
    ON edges(source_fact_id);
"""

CREATE_EDGES_INDEX_TARGET = """
CREATE INDEX IF NOT EXISTS idx_edges_target
    ON edges(target_fact_id);
"""

CREATE_EDGES_INDEX_STATUS = """
CREATE INDEX IF NOT EXISTS idx_edges_status
    ON edges(status);
"""


def get_create_statements() -> list[str]:
    return [
        CREATE_EDGES_TABLE,
        CREATE_EDGES_INDEX_ACTIVE_UNIQUE,
        CREATE_EDGES_INDEX_SOURCE,
        CREATE_EDGES_INDEX_TARGET,
        CREATE_EDGES_INDEX_STATUS,
    ]
