# Changelog

## [1.8.0] — 2026-05-26

### Added

- **Fact Lifecycle Model — `nexus/lifecycle.py`** — Append-only state machine:
  - `FactVersion` with `fact_id` (stable identity), `version_id` (unique per revision), `status` (`pending → canonical | deprecated | rolled_back`)
  - `content_hash` locks payload at creation — tamper detection on promote
  - `supersedes` on version_id-level — precise chain for audit
  - `decision_event` mandatory for every status transition
  - `CanonicalView` — current canonical fact by fact_id
  - TTL excluded for `deprecated`/`rolled_back` — historical records preserved
- **Staging Area — `nexus/staging.py`**:
  - `create_pending()` / `promote()` / `deprecate()` / `rollback()` — live against Qdrant
  - `list_pending()` — shows update-drafts (versions WITH supersedes) alongside new facts
  - `ensure_collections(host, port)` — auto-bootstrap `hermes-memory-canonical` with 512D/Cosine
  - Concurrency Guard: `promote()` verifies `pending.supersedes == current_canonical.version_id`
- **71 Unit Tests** — `tests/test_lifecycle.py` (60) + `tests/test_staging.py` (11): state machine transitions, concurrency guard (stale/fresh/new), collection bootstrap (404/200/500/partial), serialization, CanonicalView

## [1.7.2] — 2026-05-26

### Added

- **Hybrid Search — `nexus_search_hybrid()`** — BM25 + Vector + RRF + Tier-Boost:
  - One function for all 3 embedding providers: `voyage`, `sentence-transformers`, `ollama`
  - Auto-detection of `embed_provider` from Hermes `config.yaml`
  - BM25-only fallback when no embedding provider is configured
  - Source-tier boost (tier1 x1.2, tier2 x1.0, tier3 x0.8)
- **3 Embedding-Provider Endpoints** — `_embed_voyage()`, `_embed_sentence_transformers()`, `_embed_ollama()`:
  - Voyage: `voyage-3-lite` (512d), needs `VOYAGE_API_KEY`
  - Sentence-Transformers: `all-MiniLM-L6-v2` (384d), no API key required
  - Ollama: `nomic-embed-text`, requires running Ollama instance

### Fixed

- `pyproject.toml` optional dependency `hybrid` enables BM25 support (`pip install hermes-nexus-memory[hybrid]`)

## [1.7.1] — 2026-05-25

### Added

- **Provenance Scan** — `nexus/provenance/` gains `scan_provenance()` + `format_provenance_report()`:
  - Scans all Qdrant memory entries for provenance metadata
  - Reports source types, creators, confidence distribution, criticality markers
  - Paginated scroll handles large collections
- **Wikilink Orphan Detection** — `nexus/health/` gains `find_wikilink_orphans()` + `format_orphan_report()`:
  - Finds `[[wikilinks]]` that don't resolve to any file or heading
  - Backtick-aware: skips inline code spans (no false positives)
  - Checks workspace wiki/, MEMORY.md headings, memory/ dates, shared Obsidian wiki

### Changed

- `nexus/provenance/__init__.py` — exports `scan_provenance`, `format_provenance_report`
- `nexus/health/__init__.py` — exports `find_wikilink_orphans`, `format_orphan_report`

---

## [1.7.0] — 2026-05-25

### Added

- **Memory Expiry (Compiled Truth + Timeline)** — Memories now have a shelf life:
  - `expiry_policy` field: `static` (never), `normal` (90d), `volatile` (7d)
  - `compute_expires_at()` calculates expiry from `last_confirmed_at` or `created_at`
  - `valid_until` override: manually set expiry that takes precedence over policy
  - `DriftReport.expired` lists expired entries with `expiry_reason` (`policy` or `valid_until`)
  - Report distinguishes between policy-based and valid_until-based expiry
- **Tiered Enrichment** — `nexus/enrich.py` module:
  - `EnrichmentTier`: `RAW` (1), `TAGGED` (2), `LINKED` (3)
  - `decide_tier()` heuristics: importance > category > content length > signal keywords
  - `enrich()`: T1 no-op, T2 keyword extraction + category validation, T3 semantic linking flag
  - `nexus_remember()` gains optional `tier` param (int/str/None for auto)

### Changed

- **DriftDetector** — `_check_expiry()` now reads `valid_until` before policy-based check
- **`nexus_remember()`** — optional `tier` parameter for enrichment depth control
- All internal `datetime.now()` calls use `timezone.utc` to prevent comparison crashes
- README updated with Memory Expiry + Tiered Enrichment documentation

### Fixed

- **BLOCKER** — `TypeError: can't compare offset-naive and offset-aware datetimes` in `compute_expires_at()` and `_check_expiry()` (`datetime.now()` → `datetime.now(timezone.utc)`)
- **MITTEL** — `valid_until` field was ignored by expiry check (now overrides policy-based expiry)

---

## [1.6.1] — 2026-05-24

### Added

- **Named Entity Matching** — Factual-Signal (`_signal_factual`) migrated from word-overlap to named entity extraction. Detects 30+ technical terms (Nexus, Qdrant, Voyage, BM25, GPT, RAG, etc.) instead of simple words. → sharper hallucination detection
- **Why-Hints** — `nexus-confidence --pretty` now shows an understandable explanation per signal: "Query fits the chunks well", "Technical terms missing from source chunks", etc.
- **Stanford-CS229-Why-Note** — Module docstring explains why Grounding is necessary (SFT trains plausibility, not truth)

### Changed

- **Grounding Rebranding** — `ConfidenceScorer` → `GroundingScorer`, `ConfidenceReport` → `GroundingReport`, `report.confidence` → `report.grounding`. Consistent terminology: it measures source grounding, not model confidence.
- **CLI Rebranding** — `bin/nexus-confidence` imports, labels and output updated to Grounding

### Fixed

- **Factual-Signal** — Old logic only recognized stopword-filtered single words. New logic matches technical named entities more precisely.

### Acknowledgements

- Thanks to [@S_BatMan](https://x.com/S_BatMan) for the discussion on multi-level provenance
- Thanks to Miosha for the v1.6.1 implementation in openclaw-nexus-memory

## [1.6.0] — 2026-05-24

### Added

- **RAG Grounding Scoring** — `nexus/confidence.py` evaluates generated answers with 5 signals:
  - `similarity` — Query-Chunk similarity (cosine max)
  - `dominance` — Top-chunk concentration (stability)
  - `grounding` — Semantic overlap between answer and chunks
  - `factual` — Word-level overlap (hallucination guard)
  - `coverage` — How broadly chunks cover the question
  - Aggregated to a single confidence label (🟢 Very High → ⛔ Very Low)
- **Grounding CLI** — `bin/nexus-confidence --pretty "query" "answer"` for testing
- **3-Provider Embedding** — Confidence Scorer supports voyage, sentence-transformers, ollama (same provider as system config)

### Changed

- `nexus/retrieval/__init__.py` — `search_vector()` now uses the correct `/points/search` endpoint
- `nexus/retrieval/__init__.py` — `search_vector()` now filters on `type: memory` (no more session turns)
- README updated with Grounding Scoring section (tools, architecture, comparison table)

### Fixed

- **Qdrant API endpoint** — Incorrect URL `/collections/{name}/search` → correct `/collections/{name}/points/search` (affected v1.4.0–v1.5.0)
- **Session-turn noise** — Search results were ~89% chat history instead of memory entries — now filtered to `type: "memory"`

## [1.4.0] — 2026-05-23

### Added

- **Multi-Level Provenance** — Four levels of provenance for every memory entry:

  **Level 1 — Source:** Automatic tracking of where a fact came from.
  - `attach_source(session_id, source_type, created_by)` — builds provenance metadata
  - `format_source(provenance)` — human-readable display: "🟢 Chat by Kiosha (2026-05-23)"
  - `SOURCE_TYPES` — trust ranking: chat (1.0) > ingest (0.9) > cron (0.8) > manual (0.7) > inferred (0.5) > unknown (0.3)
  - New parameters for `nexus_remember()`: `provenance`, `created_by`, `session_id`, `source_type`
  - Legacy entries without provenance remain readable (`format_source(None)` → `❓ Unknown origin`)

  **Level 2 — Corroboration:** Which entries confirm or contradict each other.
  - `find_corroboration(content)` — keyword-overlap search for corroborating entries
  - `corroborate_entry(id_a, id_b)` — bidirectional linking + confidence recalibration

  **Level 3 — Bi-temporal (extended):** Beyond `valid_from`/`valid_until`:
  - `modified_at` / `modified_by` — automatically set on every `nexus_update()` (Level 3)
  - `nexus_update()` new parameter: `modified_by`
  - Legacy entries receive baseline data on first update automatically

  **Level 4 — Dependency Graph:** What breaks if this fact is wrong.
  - `build_dependency_graph(point_id)` — recursive traversal of `depends_on`/`dependents`
  - `depends_on` / `dependents` — lists of point IDs
  - `criticality` — number of entries that depend on this fact
  - `grounded` — boolean: directly observed (True) or inferred (False)
  - `max_depth=3` protection against infinite recursion

- **New Module:** `nexus/provenance/__init__.py` — 14 KB, full type annotations

- **UUID Auto-Generation** — `nexus_remember()` auto-generates a UUID when no point ID is passed (fix for Qdrant's `null`-ID rejection)

### Changed

- `nexus_remember()` extended signature: `provenance`, `created_by`, `session_id`, `source_type`
- `nexus_update()` extended signature: `modified_by`
- Version bumped from `1.4.0-dev` to `1.4.0`

### Acknowledgements

- Thanks to [@S_BatMan](https://x.com/S_BatMan) (Steven Batchelor-Manning) for the discussion on why multi-level provenance is critical for self-healing AI memory. His comment was the direct trigger for this feature.

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