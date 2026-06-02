# Changelog

## v2.4.1 (2026-06-02) — Step-Back Adaptive Retrieval + Type Fix

### Added

- **Step-Back Adaptive Retrieval** — optional `stepback_query` + `stepback_weight` in `search_hybrid()`
  - Runs a secondary search with a broader query when provided
  - Fuses results: primary chunks keep their scores, stepback chunks get weighted (default 0.9x)
  - +0.24% Recall@10 on LoCoMo (200 QA), +0.87% on Adversarial category
  - No change to default behavior — purely opt-in via `stepback_query` parameter

### Fixed

- **Type annotation compatibility** — added `from __future__ import annotations` in `locomo_eval.py`
  - Fixes `TypeError: unsupported operand type(s) for |` on Python 3.11
  - Affected `rerank_cross_encoder()` return type `list[dict] | None`

### Changed

- `locomo_eval.py`: restored proper return type hint on `rerank_cross_encoder()`

---

## v2.4.0 (2026-06-02) — Local Cross-Encoder Reranker + Conversation-Aware Chunking

### Added

- **Local Cross-Encoder Reranker** (`reranker="cross-encoder"`)
  - `cross-encoder/ms-marco-MiniLM-L-12-v2` via sentence-transformers
  - Lazy singleton: loaded once globally, ~4s cold start, ~50ms per 50 pairs
  - +8% accuracy on LoCoMo benchmark (50 QA, Gemini Flash Lite)
  - No API cost, runs on CPU

- **Conversation-Aware Chunking** in `index_memories(chunk_turns=True, window_size=3)`
  - Groups consecutive `type=turn` points by session into 3-turn sliding windows
  - 1-turn overlap between consecutive windows
  - Memory-type points remain as individual documents
  - Improves BM25 Recall by +4-5% on conversational data

### Changed

- **`search_hybrid()`** — new `reranker` parameter (`"voyage"` | `"cross-encoder"`)
  - Pool auto-scales to `5× top_k` when `rerank=True` (was `2×`)
  - `_rerank()` renamed to `_rerank_voyage()` for clarity

- **MCP Server** — `nexus_search` tool gained `reranker` parameter
  - Automatic fallback chain: cross-encoder → voyage → no rerank

### Documentation

- Added cross-encoder evaluation results to `references/locomo-evaluation.md`
- Updated hybrid-search skill with reranker comparison table

---

## v2.1.0 (2026-05-31) — Auto-Discovery + Graph Analytics

### Added
- Auto-Discovery v2.1.0: Qdrant-native O(n·k) fact relation detection
- 5-Tier Heuristic Classifier (confidence-based: ≥0.85 auto, <0.85 proposed)
- Graph Analytics v2.1.0: GraphAnalytics class (isolation, hub scores, knowledge gaps, connected components)
- Full cluster summary report generation

### Changed
- EdgeStore: 6 relation types (supersedes, contradicts, supports, alternative_to, depends_on, references)
- EdgeStore: 4 status states (active, proposed, deprecated, rejected)
- Discovery: Two-layer dedup (in-memory + SQLite filter_new_edges())
- Manual trigger only (no cron)

## v2.0.0 (2026-05-26) — SkillGraph Edge Store

### Added
- SkillGraph v2.0.0: NetworkX-cached edge store backed by SQLite
- Edge CRUD: add/get/remove edges with UNIQUE+WHERE active constraint
- BFS shortest path finder
- Symmetric contradicts relation
- `cursor.rowcount` for miss detection

---

## v1.x Releases

See GitHub Releases for v1.0.0 through v1.9.0.
