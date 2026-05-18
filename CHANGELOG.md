# Changelog

## [1.3.0] — 2026-05-18

### Added

- **Auto-Fix / `nexus_consolidate()`** — Resolves contradiction pairs found by
  `detect_contradictions()` automatically.
  - Older entry gets `valid_until: <today>` and `status: HISTORICAL` metadata
  - Newer entry gets `valid_from: <today>` metadata (if not already set)
  - `dry_run=True` (default) — returns what it WOULD do without modifying Qdrant
  - Returns list of action dicts: `[{action, id, reason}, ...]`
  - Works via Qdrant HTTP API (same pattern as `nexus_update`)

- **Bi-temporal Metadata** — `valid_from` and `valid_until` fields in metadata
  (ISO-8601 dates, default: null).
  - `nexus_remember()` updated to auto-set `valid_from: <today>` if not provided
  - `nexus_query_valid(query, at_date=None)` — filters results to memories
    valid at a given date by checking `valid_from` / `valid_until` intervals
  - Backward compatible: existing memories without these fields pass through
    unmodified

- **Historical Exclusion in Drift Detection** — Entries with `status` in
  `HISTORICAL_MARKER_STATUSES` (`["HISTORICAL", "RESOLVED", "ARCHIVED", "FIXED"]`)
  are now excluded from stale pattern checking, age checking, and contradiction
  detection.
  - `DriftReport.excluded_count` field tracks how many entries were skipped
  - `DriftDetector._is_excluded()` helper for consistent exclusion logic
  - Applied in `run()`, `run_from_texts()`, and `detect_contradictions()`

### Dependencies

- No new dependencies required

---

## [1.2.0] — Unreleased

### Added

- **Incremental BM25 Indexing** — `HybridRetriever.update_index()` now allows
  adding and removing entries from the BM25 index without a full Qdrant scroll.
  `index_memories()` remains as the full-rebuild fallback.
  - `update_index(memories_to_add=[(id, text), ...], memories_to_remove=[id, ...])`
  - Rebuilds BM25 from the updated internal corpus (no Qdrant round-trip)
  - Significantly faster than full rebuild for small changes

- **Semantic Contradiction Detection** — `DriftDetector.detect_contradictions()`
  finds pairs of memories that semantically contradict each other using
  embedding similarity.
  - Near-duplicate detection (cosine similarity >= 0.85)
  - Semantic contradiction detection (similarity >= 0.35 with opposing sentiment)
  - Works with Voyage embeddings (best quality), sentence-transformers (local),
    or gracefully returns empty results if neither is available
  - Heuristic sentiment analysis to distinguish genuine contradictions from
    harmless semantic similarity
  - Automatically included in `DriftDetector.run()` reports

- **Usage Tracking** — `DriftDetector.track_usage()` and `prune_unused()` for
  tracking memory access and identifying candidates for pruning.
  - `track_usage(memory_id)` — records last-accessed timestamp to
    `~/.hermes/nexus_usage.json`
  - `prune_unused(days=90)` — returns list of memory IDs not accessed in X days
  - `get_usage_stats()` — aggregate statistics about tracked usage
  - Persisted to a simple JSON file; no database required

### Dependencies

- `voyageai` — optional, enables high-quality contradiction detection
- `sentence-transformers` — optional, enables local embedding for contradiction detection
- `scikit-learn` — optional, faster cosine similarity in contradiction detection

---

## [1.1.0] — 2026-05-18

### Added

- **Hybrid Retrieval** — BM25 + Vector + Reciprocal Rank Fusion (RRF)
  - Keyword-precise BM25 search catches exact matches that pure vector search misses
  - RRF fuses both rankings with zero tuning (`k=60`)
  - Anti-poisoning: adversarial documents can't game both methods simultaneously
  - `nexus.retrieval.HybridRetriever` — standalone class, works with or without Qdrant

- **Source Tier Boosting** — Trust-ranked search results
  - 🟢 Tier 1: Agent, user, config, official docs (1.2× boost)
  - 🟡 Tier 2: Curated sources — Medium, arXiv, GitHub (1.0×)
  - 🔴 Tier 3: Uncurated — Reddit, Twitter, unknown (0.8× penalty)
  - Prevents untrusted content from outranking your own data
  - **Now supports `source_tier` metadata field** — set `source_tier: "tier1"` when storing memories for precise tier assignment. Falls back to keyword matching if no metadata tier is set.

- **Belief Drift Detection** — Automated memory health monitoring
  - Regex-based stale pattern detection (DeepSeek listed as active, wrong embeddings, etc.)
  - Age-based detection (entries older than 90 days flagged)
  - Weighted health score 0–10 (🟢 <1 · 🟡 1–3 · 🔴 >3)
  - `nexus.health.DriftDetector` — standalone class, works with or without Qdrant
  - Custom stale patterns supported

- **`nexus_update()`** — Update memories in-place without losing metadata
  - Unlike forget + remember, preserves all metadata (category, source_tier, timestamps)
  - Update content, metadata, or both
  - `from nexus import nexus_update`

### Changed

- **Source Tier Boosting now supports `source_tier` metadata field** — set when storing memories for precise tier assignment, falls back to keyword matching
- README rewritten with full API docs, architecture diagrams, and comparison table
- Added `pyproject.toml` for pip-installable package
- Added example scripts in `examples/`
- Added security note: Qdrant defaults to localhost with no auth — use firewall rules or API key in production

### Dependencies

- `requests` — required (Qdrant HTTP API)
- `bm25s>=0.3` — optional, enables hybrid retrieval

---

## [1.0.0] — 2026-05-14

### Added

- Core semantic vector memory via Qdrant
- Three embedding backends: sentence-transformers, Ollama, Voyage AI
- Tools: `nexus_search`, `nexus_remember`, `nexus_forget`
- Auto-adapts to selected embedding provider
- Install script and Hermes setup wizard integration
- MIT License