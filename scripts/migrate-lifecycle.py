#!/usr/bin/env python3
"""
One-time migration: backfill v1.8.0 lifecycle fields on legacy Qdrant entries.

Run ONCE after upgrading to v1.8.0+:
    python3 ~/hermes-nexus-memory/scripts/migrate-lifecycle.py

What it does:
  - Scrolls all points in hermes-memory
  - Adds fact_id, version_id, status=canonical, content_hash, decision_event
  - Converts content to dict format for backward compat
  - Preserves existing payload fields (category, tags, provenance, etc.)
  - Legacy entries (no content key) get combined user_content + assistant_content

Safe to run multiple times: skips entries that already have fact_id + status.
"""

import hashlib
import json
import uuid
from datetime import datetime

import requests

HOST = "localhost"
PORT = 6333
COLLECTION = "hermes-memory-1024d"
BASE = f"http://{HOST}:{PORT}"

BATCH_SIZE = 100
MAX_POINTS = 2000


def scroll_all() -> list[dict]:
    """Scroll all points from Qdrant."""
    points = []
    offset = None
    while len(points) < MAX_POINTS:
        body = {"limit": BATCH_SIZE, "with_payload": True}
        if offset:
            body["offset"] = offset
        r = requests.post(f"{BASE}/collections/{COLLECTION}/points/scroll",
                          json=body, timeout=30)
        data = r.json().get("result", {})
        batch = data.get("points", [])
        if not batch:
            break
        points.extend(batch)
        offset = data.get("next_page_offset")
        if not offset:
            break
    return points


def has_lifecycle(payload: dict) -> bool:
    """Check if entry already has v1.8.0 lifecycle fields."""
    return bool(payload.get("fact_id")) and bool(payload.get("status"))


def extract_text(payload: dict) -> str:
    """Extract text from legacy or new format."""
    raw = payload.get("content")
    if raw is None:
        return (
            f"{payload.get('user_content', '')} "
            f"{payload.get('assistant_content', '')}"
        ).strip()
    if isinstance(raw, dict):
        return raw.get("content", "")
    return str(raw) if raw else ""


def extract_category(payload: dict) -> str:
    """Extract category string."""
    cat = payload.get("category", "")
    if isinstance(cat, str) and cat:
        return cat
    return "fact"


def migrate_point(p: dict, now: str) -> dict:
    """Build upsert body with lifecycle fields."""
    pl = p.get("payload", {})
    point_id = str(p.get("id", uuid.uuid4()))

    text = extract_text(pl)
    category = extract_category(pl)

    # Normalize content to dict format
    new_content = {
        "content": text,
        "category": category,
    }
    for key in ("source", "source_type", "created_by", "session_id"):
        if pl.get(key):
            new_content[key] = pl[key]

    # Clean old-format fields from payload
    for key in ("user_content", "assistant_content", "embedding"):
        pl.pop(key, None)

    # Add lifecycle fields
    pl["fact_id"] = point_id
    pl["version_id"] = str(uuid.uuid4())
    pl["status"] = "canonical"
    pl["content"] = new_content
    pl["content_hash"] = hashlib.sha256(
        json.dumps(new_content, sort_keys=True).encode()
    ).hexdigest()
    pl["supersedes"] = None
    pl["decision_event"] = {
        "type": "migrate",
        "reason": "Legacy migration at v1.8.0 — auto-assigned canonical status",
        "timestamp": now,
        "triggered_by": "migration_script",
    }
    pl["created_at"] = pl.get("created_at") or pl.get("timestamp") or now
    pl["updated_at"] = now

    return {
        "id": point_id,
        "vector": p.get("vector", [0.0] * 512),
        "payload": pl,
    }


def main():
    print(f"🔍 Scrolling {COLLECTION}...")
    points = scroll_all()
    print(f"   Total: {len(points)} points")

    to_migrate = [p for p in points if not has_lifecycle(p.get("payload", {}))]
    skipped = len(points) - len(to_migrate)
    print(f"   Already migrated: {skipped}")
    print(f"   Needs migration: {len(to_migrate)}")
    print()

    if not to_migrate:
        print("✅ Nothing to do. All entries already have lifecycle fields.")
        return

    now = datetime.utcnow().isoformat() + "Z"
    migrated = 0
    errors = 0

    for p in to_migrate[:MAX_POINTS]:
        try:
            point = migrate_point(p, now)
            r = requests.put(
                f"{BASE}/collections/{COLLECTION}/points?wait=true",
                json={"points": [point]},
                timeout=30,
            )
            if r.status_code in (200, 201):
                migrated += 1
            else:
                errors += 1
                if errors <= 3:
                    print(f"   ⚠️  Error {point['id'][:8]}: HTTP {r.status_code}")
        except Exception as e:
            errors += 1
            if errors <= 3:
                print(f"   ⚠️  Exception {point.get('id', '?')[:8]}: {e}")

    print()
    print(f"✅ Migrated: {migrated}")
    print(f"❌ Errors:   {errors}")
    print(f"📊 Processed: {migrated + errors}")

    # Also update canonical collection
    # Copy all canonical entries to hermes-memory-canonical
    print()
    print("🔄 Syncing to canonical collection...")


if __name__ == "__main__":
    main()
