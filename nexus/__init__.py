"""Nexus Memory — Persistent vector memory for Hermes Agent.

Three layers of intelligence:
- Core: Semantic vector search via Qdrant + multiple embedding backends
- Retrieval: Hybrid BM25 + Vector + Reciprocal Rank Fusion (anti-poisoning)
- Health: Belief drift detection (anti-staleness)
"""

import logging
from datetime import date, datetime
from typing import Any

from nexus.health import DriftDetector, DriftReport
from nexus.retrieval import HybridRetriever
from nexus.provenance import (
    attach_source,
    find_corroboration,
    corroborate_entry,
    add_dependency,
    build_dependency_graph,
    format_source,
    SOURCE_TYPES,
)

__version__ = "1.4.0"

_logger = logging.getLogger(__name__)


# ── Convenience: update an existing memory in-place ──────────────────────


def nexus_update(
    point_id: str,
    new_content: str | None = None,
    new_metadata: dict | None = None,
    modified_by: str | None = None,
    qdrant_host: str = "localhost",
    qdrant_port: int = 6333,
    collection_name: str = "hermes-memory",
) -> dict:
    """Update an existing memory point without losing metadata.

    Unlike forget + remember, this preserves all existing metadata (category,
    source_tier, timestamps, etc.) and only overwrites the fields you specify.

    Automatically tracks ``modified_at`` and ``modified_by`` in the
    provenance dict (Level 3 — Bi-temporal modification tracking).

    Args:
        point_id: The Qdrant point ID to update.
        new_content: New content text (None = keep existing).
        new_metadata: Dict of metadata fields to merge/update (None = keep existing).
        modified_by: Who made this modification (e.g. "Kiosha", "Miosha", "Nebo").
        qdrant_host: Qdrant host.
        qdrant_port: Qdrant port.
        collection_name: Qdrant collection name.

    Returns:
        dict with updated point info.
    """
    import requests as _req

    url = f"http://{qdrant_host}:{qdrant_port}/collections/{collection_name}/points/scroll"
    r = _req.post(url, json={"limit": 1, "with_payload": True,
                              "filter": {"must": [{"key": "id", "match": {"value": point_id}}]}}
                   if isinstance(point_id, str) and len(point_id) > 20
                   else {"limit": 100, "with_payload": True},
                   timeout=10)

    # Find the point
    points = r.json().get("result", {}).get("points", [])
    target = None
    for p in points:
        if str(p.get("id", "")) == str(point_id):
            target = p
            break

    if not target:
        # Try direct point lookup
        r2 = _req.get(
            f"http://{qdrant_host}:{qdrant_port}/collections/{collection_name}/points/{point_id}",
            timeout=10,
        )
        target = r2.json().get("result", None)

    if not target:
        return {"error": f"Point {point_id} not found"}

    payload = target.get("payload", {})
    vector = target.get("vector", None)

    # Merge updates
    if new_content:
        payload["content"] = new_content
    if new_metadata:
        payload.update(new_metadata)

    # Update provenance modification tracking (Level 3)
    now_iso = datetime.now().isoformat()
    prov = payload.get("provenance")
    if prov is None:
        # Legacy entry — create basic provenance
        prov = {
            "source": {"source_type": "manual", "created_by": "System", "timestamp": now_iso},
            "corroborated_by": [],
            "confidence": 0.7,
            "modified_at": now_iso,
            "modified_by": modified_by or "System",
            "depends_on": [],
            "dependents": [],
            "grounded": True,
        }
        payload["provenance"] = prov
    else:
        prov["modified_at"] = now_iso
        if modified_by:
            prov["modified_by"] = modified_by

    # Override point with merged payload
    update_url = f"http://{qdrant_host}:{qdrant_port}/collections/{collection_name}/points"
    update_data = {
        "points": [{
            "id": target["id"],
            "vector": vector if vector else [],
            "payload": payload,
        }]
    }
    r3 = _req.put(update_url, json=update_data, timeout=10)
    return r3.json()


# ── Bi-temporal Metadata ─────────────────────────────────────────────────


def _today_iso() -> str:
    """Return today's date as ISO-8601 string."""
    return date.today().isoformat()


# ── Convenience: store a new memory with bi-temporal metadata ──────────


def nexus_remember(
    content: str,
    category: str = "fact",
    metadata: dict | None = None,
    valid_from: str | None = None,
    provenance: dict | None = None,
    created_by: str = "System",
    session_id: str | None = None,
    source_type: str = "chat",
    qdrant_host: str = "localhost",
    qdrant_port: int = 6333,
    collection_name: str = "hermes-memory",
    **kwargs: Any,
) -> dict:
    """Store a new memory with bi-temporal metadata and optional provenance.

    Automatically sets ``valid_from`` to today if not provided.  Pass
    ``valid_until`` inside *metadata* (or via keyword) for expiry-aware
    storage.

    If *provenance* is not provided, one is auto-built from *created_by*,
    *session_id*, and *source_type* (Level 1 — Source).  Pass an explicit
    ``provenance`` dict to override (Level 2-4 fields).

    Args:
        content: The memory content text.
        category: Category tag (default ``"fact"``).
        metadata: Additional metadata dict to merge.
        valid_from: ISO-8601 date string. Defaults to today if omitted.
        provenance: Full provenance dict. If None, auto-built from args.
        created_by: Who created this fact (used for auto-provenance).
        session_id: Hermes session ID (used for auto-provenance).
        source_type: Source type hint (used for auto-provenance).
        qdrant_host: Qdrant host.
        qdrant_port: Qdrant port.
        collection_name: Qdrant collection name.
        **kwargs: Extra keyword arguments forwarded as metadata fields.

    Returns:
        dict with the Qdrant API upsert response.

    Raises:
        ImportError: If ``requests`` is not available.
        ConnectionError: If Qdrant is unreachable.
    """
    import requests as _req
    from nexus.provenance import attach_source

    # Build payload
    payload: dict[str, Any] = {
        "content": content,
        "category": category,
        "timestamp": datetime.now().isoformat(),
        "valid_from": valid_from or _today_iso(),
        "valid_until": None,
    }
    if metadata:
        payload.update(metadata)
    for k, v in kwargs.items():
        payload[k] = v
    # Ensure valid_from is always set
    if payload.get("valid_from") is None:
        payload["valid_from"] = _today_iso()

    # Attach provenance (Level 1 — Source)
    if provenance is not None:
        payload["provenance"] = provenance
    elif "provenance" not in payload:
        payload["provenance"] = attach_source(
            session_id=session_id,
            source_type=source_type,
            created_by=created_by,
            content=content,
        )

    # Build vector (empty — Qdrant will fail if no vector; caller
    # is expected to have set up an auto-embedding pipeline, or
    # embed beforehand and pass via ``vector`` kwarg).
    vector = payload.pop("vector", None) or []

    # Ensure point has a valid ID (UUID or integer)
    point_id = payload.pop("id", None)
    if point_id is None:
        import uuid
        point_id = str(uuid.uuid4())

    url = f"http://{qdrant_host}:{qdrant_port}/collections/{collection_name}/points"
    data = {"points": [{"id": point_id, "vector": vector, "payload": payload}]}
    r = _req.put(url, json=data, timeout=10)
    return r.json()


# ── Auto-Fix / Consolidation ────────────────────────────────────────────


def nexus_consolidate(
    contradiction_pairs: list[dict],
    dry_run: bool = True,
    qdrant_host: str = "localhost",
    qdrant_port: int = 6333,
    collection_name: str = "hermes-memory",
) -> list[dict]:
    """Resolve detected contradictions by marking older entries as historical.

    For each contradiction pair, the **older** entry (determined by
    ``created_at`` / ``timestamp`` in payload) is marked:
      - ``valid_until`` → today's date
      - ``status`` → ``"HISTORICAL"``

    The **newer** entry gets:
      - ``valid_from`` → today's date (if not already set)

    Works via Qdrant HTTP API — same pattern as :func:`nexus_update`.

    Args:
        contradiction_pairs: List of dicts as returned by
            :meth:`DriftDetector.detect_contradictions`.  Each pair must
            contain ``id_a`` and ``id_b`` keys.
        dry_run: If ``True`` (default), simulate the actions without
            modifying Qdrant.
        qdrant_host: Qdrant host.
        qdrant_port: Qdrant port.
        collection_name: Qdrant collection name.

    Returns:
        List of action dicts, for example::

            [
                {
                    "action": "mark_historical",
                    "id": "abc-123",
                    "reason": "Older entry in contradiction pair (id_b=def-456)",
                },
                {
                    "action": "set_valid_from",
                    "id": "def-456",
                    "reason": "Newer entry in contradiction pair — valid_from set to today",
                },
            ]

    Raises:
        ImportError: If ``requests`` is not available.
    """
    import requests as _req

    today = _today_iso()
    actions: list[dict] = []

    for pair in contradiction_pairs:
        id_a = pair.get("id_a", "")
        id_b = pair.get("id_b", "")
        if not id_a or not id_b:
            _logger.warning("Skipping contradiction pair missing id_a/id_b: %s", pair)
            continue

        # Fetch both points to determine timestamps
        def _fetch_point(pid: str) -> dict | None:
            base = f"http://{qdrant_host}:{qdrant_port}"
            # Direct point lookup
            try:
                r = _req.get(
                    f"{base}/collections/{collection_name}/points/{pid}",
                    timeout=10,
                )
                if r.status_code == 200:
                    result = r.json().get("result")
                    if result:
                        return result
            except Exception:
                pass
            # Fallback: scroll filter
            try:
                r = _req.post(
                    f"{base}/collections/{collection_name}/points/scroll",
                    json={
                        "limit": 1,
                        "with_payload": True,
                        "filter": {
                            "must": [{"key": "id", "match": {"value": pid}}]
                        },
                    },
                    timeout=10,
                )
                points = r.json().get("result", {}).get("points", [])
                return points[0] if points else None
            except Exception:
                return None

        point_a = _fetch_point(id_a)
        point_b = _fetch_point(id_b)

        if not point_a or not point_b:
            _logger.warning(
                "Could not fetch one or both points for contradiction pair: %s, %s",
                id_a,
                id_b,
            )
            continue

        payload_a = point_a.get("payload", {})
        payload_b = point_b.get("payload", {})

        # Determine older vs newer by timestamp
        ts_a = payload_a.get("timestamp", payload_a.get("created_at", ""))
        ts_b = payload_b.get("timestamp", payload_b.get("created_at", ""))

        # If timestamps cannot be resolved, use id ordering as fallback
        if ts_a and ts_b:
            older_id, newer_id = (id_a, id_b) if ts_a < ts_b else (id_b, id_a)
            older_payload, newer_payload = (
                (payload_a, payload_b)
                if ts_a < ts_b
                else (payload_b, payload_a)
            )
        else:
            # Fallback: treat id_a as older (as returned by detection)
            older_id, newer_id = id_a, id_b
            older_payload, newer_payload = payload_a, payload_b

        # ── Action 1: Mark older entry as historical ─────────────────────
        action_older = {
            "action": "mark_historical",
            "id": older_id,
            "reason": (
                f"Older entry in contradiction pair (id_b={newer_id}, "
                f"type={pair.get('type', 'contradiction')})"
            ),
        }
        actions.append(action_older)

        # ── Action 2: Set valid_from on newer entry ─────────────────────
        action_newer = {
            "action": "set_valid_from",
            "id": newer_id,
            "reason": (
                f"Newer entry in contradiction pair (id_a={older_id}) — "
                f"valid_from set to {today}"
            ),
        }
        actions.append(action_newer)

        if not dry_run:
            # Apply older entry changes
            _apply_consolidation(
                older_id,
                {"valid_until": today, "status": "HISTORICAL"},
                qdrant_host,
                qdrant_port,
                collection_name,
            )
            # Apply newer entry changes
            if not newer_payload.get("valid_from"):
                _apply_consolidation(
                    newer_id,
                    {"valid_from": today},
                    qdrant_host,
                    qdrant_port,
                    collection_name,
                )

    return actions


def _apply_consolidation(
    point_id: str,
    metadata_updates: dict,
    qdrant_host: str,
    qdrant_port: int,
    collection_name: str,
) -> dict:
    """Apply metadata updates to a Qdrant point (internal helper).

    Uses the same HTTP API pattern as :func:`nexus_update`.
    """
    import requests as _req

    base = f"http://{qdrant_host}:{qdrant_port}"
    url = f"{base}/collections/{collection_name}/points"

    # Fetch existing point
    point = None
    try:
        r = _req.get(f"{url}/{point_id}", timeout=10)
        if r.status_code == 200:
            point = r.json().get("result")
    except Exception:
        pass

    if not point:
        # Fallback scroll
        try:
            r = _req.post(
                f"{base}/collections/{collection_name}/points/scroll",
                json={
                    "limit": 1,
                    "with_payload": True,
                    "filter": {
                        "must": [{"key": "id", "match": {"value": point_id}}]
                    },
                },
                timeout=10,
            )
            points = r.json().get("result", {}).get("points", [])
            point = points[0] if points else None
        except Exception:
            pass

    if not point:
        return {"error": f"Point {point_id} not found"}

    payload = dict(point.get("payload", {}))
    payload.update(metadata_updates)
    vector = point.get("vector", [])

    r = _req.put(
        url,
        json={
            "points": [
                {"id": point["id"], "vector": vector, "payload": payload}
            ]
        },
        timeout=10,
    )
    return r.json()


# ── Temporal Querying ──────────────────────────────────────────────────


def nexus_query_valid(
    query: str,
    at_date: str | None = None,
    qdrant_host: str = "localhost",
    qdrant_port: int = 6333,
    collection_name: str = "hermes-memory",
    limit: int = 10,
) -> list[dict]:
    """Query memories that are valid at a specific date.

    Filters results to only those whose temporal validity interval
    (``valid_from`` … ``valid_until``) covers the given date.

    Args:
        query: The search query text (used via Qdrant scroll — for
            proper vector search, embed first and use the Qdrant
            search API directly).
        at_date: ISO-8601 date string (e.g. ``"2026-06-01"``).
            Defaults to today.
        qdrant_host: Qdrant host.
        qdrant_port: Qdrant port.
        collection_name: Qdrant collection name.
        limit: Maximum number of results to return.

    Returns:
        List of point dicts with payload that are valid at *at_date*.

    Raises:
        ImportError: If ``requests`` is not available.
    """
    import requests as _req

    target_date = at_date or _today_iso()

    base = f"http://{qdrant_host}:{qdrant_port}"
    all_points = []

    # Scroll all points (simple approach — no vector search)
    offset = None
    while True:
        body: dict = {"limit": 100, "with_payload": True}
        if offset:
            body["offset"] = offset
        r = _req.post(
            f"{base}/collections/{collection_name}/points/scroll",
            json=body,
            timeout=10,
        )
        data = r.json().get("result", {})
        batch = data.get("points", [])
        if not batch:
            break
        all_points.extend(batch)
        offset = data.get("next_page_offset")
        if not offset:
            break

    # Filter by temporal validity
    valid = []
    for p in all_points:
        payload = p.get("payload", {})
        vf = payload.get("valid_from")
        vu = payload.get("valid_until")

        if vf and target_date < vf:
            continue
        if vu and target_date > vu:
            continue

        valid.append(p)
        if len(valid) >= limit:
            break

    return valid


__all__ = [
    "HybridRetriever",
    "DriftDetector",
    "DriftReport",
    "nexus_update",
    "nexus_remember",
    "nexus_consolidate",
    "nexus_query_valid",
]
