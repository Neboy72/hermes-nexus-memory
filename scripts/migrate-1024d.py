#!/usr/bin/env python3
"""Migrate all memories from hermes-memory (512d, voyage-3-lite) to hermes-memory-1024d (1024d, voyage-3-large)."""

import json, os, requests, time
from datetime import datetime

QDRANT = "http://localhost:6333"
OLD_COL = "hermes-memory"
NEW_COL = "hermes-memory-1024d"
BATCH = 100
VOYAGE_KEY = os.environ.get("VOYAGE_API_KEY") or "pa--jR64VADYQx-9KVVnywmMGShoqQJ-E_SxCD-H2LGWdK"

def embed(texts):
    """Batch embed via Voyage 3 Large."""
    r = requests.post(
        "https://api.voyageai.com/v1/embeddings",
        headers={"Authorization": f"Bearer {VOYAGE_KEY}", "Content-Type": "application/json"},
        json={"input": texts, "model": "voyage-3-large"},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    return [d["embedding"] for d in data["data"]]

def scroll_all():
    """Scroll all points from old collection."""
    points = []
    offset = None
    while True:
        payload = {"limit": BATCH, "with_payload": True, "with_vector": False}
        if offset:
            payload["offset"] = offset
        r = requests.post(f"{QDRANT}/collections/{OLD_COL}/points/scroll", json=payload)
        data = r.json()["result"]
        points.extend(data["points"])
        offset = data.get("next_page_offset")
        if not offset:
            break
    return points

def write_batch(batch):
    """Write batch to new collection."""
    payload = {
        "points": [
            {
                "id": p["id"],
                "vector": p["vector"],
                "payload": p.get("payload", {}),
            }
            for p in batch
        ]
    }
    r = requests.put(f"{QDRANT}/collections/{NEW_COL}/points", json=payload)
    r.raise_for_status()
    return r.json()

def get_content(payload):
    """Extract content string from payload, whatever format."""
    for key in ("content", "user_content", "assistant_content", "text", "description"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    # Fallback: use any string value
    for v in payload.values():
        if isinstance(v, str) and len(v) > 10:
            return v.strip()
    return ""

# ── Count ──
r = requests.get(f"{QDRANT}/collections/{OLD_COL}")
old_count = r.json()["result"]["points_count"]
print(f"📦 Alte Collection: {old_count} Points")

# ── Scroll ──
all_points = scroll_all()
print(f"📖 Gelesen: {len(all_points)} Points")

# ── Embed + Write in Batches ──
total = len(all_points)
written = 0
for i in range(0, total, BATCH):
    batch = all_points[i:i+BATCH]
    
    # Extract texts
    texts = [get_content(p.get("payload", {})) for p in batch]
    
    # Build valid pairs
    valid = [(p, t) for p, t in zip(batch, texts) if t]
    
    if not valid:
        continue
    
    vectors = embed([t for _, t in valid])
    
    for (p, _), vec in zip(valid, vectors):
        p["vector"] = vec
    
    result = write_batch([p for p, _ in valid])
    written += len(valid)
    print(f"  ✅ {written}/{total} geschrieben", end="\r", flush=True)
    time.sleep(0.5)  # Rate limit safety

print(f"\n✅ Migration abgeschlossen: {written} Points in {NEW_COL}")

# ── Verify ──
r = requests.get(f"{QDRANT}/collections/{NEW_COL}")
new_count = r.json()["result"]["points_count"]
print(f"📊 Neue Collection: {new_count} Points")
print(f"🎯 Verifiziert: {'✅ OK' if new_count == old_count else f'⚠️ Differenz: {old_count - new_count}'}")
