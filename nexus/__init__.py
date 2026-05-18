"""Nexus Memory — Persistent vector memory for Hermes Agent.

Three layers of intelligence:
- Core: Semantic vector search via Qdrant + multiple embedding backends
- Retrieval: Hybrid BM25 + Vector + Reciprocal Rank Fusion (anti-poisoning)
- Health: Belief drift detection (anti-staleness)
"""

from nexus.health import DriftDetector, DriftReport
from nexus.retrieval import HybridRetriever

__version__ = "1.2.0"

# ── Convenience: update an existing memory in-place ──────────────────────

def nexus_update(
    point_id: str,
    new_content: str | None = None,
    new_metadata: dict | None = None,
    qdrant_host: str = "localhost",
    qdrant_port: int = 6333,
    collection_name: str = "hermes-memory",
) -> dict:
    """Update an existing memory point without losing metadata.

    Unlike forget + remember, this preserves all existing metadata (category,
    source_tier, timestamps, etc.) and only overwrites the fields you specify.

    Args:
        point_id: The Qdrant point ID to update.
        new_content: New content text (None = keep existing).
        new_metadata: Dict of metadata fields to merge/update (None = keep existing).
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


__all__ = [
    "HybridRetriever",
    "DriftDetector",
    "DriftReport",
    "nexus_update",
]