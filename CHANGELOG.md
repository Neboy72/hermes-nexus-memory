# Changelog

## [1.7.2] — 2026-05-26

### Added

- **Hybrid Search — `nexus_search_hybrid()`** — BM25 + Vector + RRF + Tier-Boost:
  - Eine Funktion für alle 3 Embedding-Provider: `voyage`, `sentence-transformers`, `ollama`
  - Auto-Detection des `embed_provider` aus Hermes `config.yaml`
  - BM25-only Fallback wenn kein Embedding-Provider konfiguriert
  - Source-Tier-Boost (tier1 x1.2, tier2 x1.0, tier3 x0.8)
- **3 Embedding-Provider Endpoints** — `_embed_voyage()`, `_embed_sentence_transformers()`, `_embed_ollama()`:
  - Voyage: `voyage-3-lite` (512d), braucht `VOYAGE_API_KEY`
  - Sentence-Transformers: `all-MiniLM-L6-v2` (384d), keine API-Key nötig
  - Ollama: `nomic-embed-text`, braucht laufende Ollama-Instanz

### Fixed

- `pyproject.toml` optional dependency `hybrid` aktiviert BM25-Unterstützung (`pip install hermes-nexus-memory[hybrid]`)

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

- **Named Entity Matching** — Factual-Signal (`_signal_factual`) von Wort-Overlap auf Named Entity Extraction umgestellt. Erkennt 30+ technische Fachbegriffe (Nexus, Qdrant, Voyage, BM25, GPT, RAG, etc.) statt einfacher Wörter. → schärfere Halluzinations-Erkennung
- **Why-Hints** — `nexus-confidence --pretty` zeigt jetzt pro Signal eine verständliche Erklärung: „Query passt gut zu den Chunks“, „Fachbegriffe fehlen in den Quell-Chunks“, etc.
- **Stanford-CS229-Why-Hinweis** — Modul-Docstring erklärt warum Grounding nötig ist (SFT trainiert Plausibilität statt Wahrheit)

### Changed

- **Grounding Rebranding** — `ConfidenceScorer` → `GroundingScorer`, `ConfidenceReport` → `GroundingReport`, `report.confidence` → `report.grounding`. Konsequente Terminologie: Es misst Quellenabstützung, nicht Modell-Vertrauen.
- **CLI Rebranding** — `bin/nexus-confidence` Importe, Labels und Ausgabe auf Grounding umgestellt

### Fixed

- **Factual-Signal** — Alte Logik erkannte nur Stopwort-gefilterte Einzelwörter. Neue Logik matched technische Named Entities präziser.

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

- **Multi-Level Provenance** — Vier Ebenen von Provenance für jeden Memory-Eintrag:

  **Level 1 — Source:** Automatisches Tracking woher ein Fakt kommt.
  - `attach_source(session_id, source_type, created_by)` — baut Provenance-Metadaten
  - `format_source(provenance)` — menschenlesbare Anzeige: "🟢 Chat by Kiosha (2026-05-23)"
  - `SOURCE_TYPES` — Vertrauens-Ranking: chat (1.0) > ingest (0.9) > cron (0.8) > manual (0.7) > inferred (0.5) > unknown (0.3)
  - Neue Parameter für `nexus_remember()`: `provenance`, `created_by`, `session_id`, `source_type`
  - Legacy-Einträge ohne Provenance bleiben lesbar (`format_source(None)` → `❓ Unknown origin`)

  **Level 2 — Corroboration:** Welche Einträge bestätigen oder widersprechen sich.
  - `find_corroboration(content)` — Keyword-Overlap-Suche nach bestätigenden Einträgen
  - `corroborate_entry(id_a, id_b)` — bidirektionales Verlinken + Confidence-Rekalibrierung

  **Level 3 — Bi-temporal (erweitert):** Zusätzlich zu `valid_from`/`valid_until`:
  - `modified_at` / `modified_by` — automatisch gesetzt bei jedem `nexus_update()` (Level 3)
  - `nexus_update()` neuer Parameter: `modified_by`
  - Legacy-Einträge bekommen beim ersten Update automatisch Basisdaten

  **Level 4 — Dependency Graph:** Was bricht wenn dieser Fakt falsch ist.
  - `build_dependency_graph(point_id)` — rekursive Traversierung von `depends_on`/`dependents`
  - `depends_on` / `dependents` — Listen von Point-IDs
  - `criticality` — Anzahl der Einträge die von diesem Fakt abhängen
  - `grounded` — Boolean: direkt beobachtet (True) oder abgeleitet (False)
  - `max_depth=3` Schutz vor Endlos-Rekursion

- **Neues Modul:** `nexus/provenance/__init__.py` — 14 KB, vollständige Typannotationen

- **UUID-Auto-Generierung** — `nexus_remember()` erzeugt automatisch eine UUID wenn keine Point-ID übergeben wird (fix für Qdrant's `null`-ID-Ablehnung)

### Changed

- `nexus_remember()` erweiterte Signatur: `provenance`, `created_by`, `session_id`, `source_type`
- `nexus_update()` erweiterte Signatur: `modified_by`
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