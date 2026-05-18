# Changelog

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