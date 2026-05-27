# Hermes Nexus Memory 🧠

> **One prompt — your bot never forgets again.**

You talk to your bot. Next day it asks you the same thing.  
Nexus Memory fixes that. **Permanently.**

Your agent remembers across sessions — facts, decisions, patterns.  
Hybrid retrieval (BM25 + Vector) kills RAG poisoning. Drift detection flags stale memories automatically.  
**No nonsense. No bloat. Just memory that works.**

[![Stars](https://img.shields.io/github/stars/Neboy72/hermes-nexus-memory?style=flat-square&logo=github)](https://github.com/Neboy72/hermes-nexus-memory)
[![License](https://img.shields.io/github/license/Neboy72/hermes-nexus-memory?style=flat-square)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue?style=flat-square&logo=python)](https://www.python.org/)
[![Qdrant v1.17+](https://img.shields.io/badge/qdrant-v1.17+-purple?style=flat-square)](https://qdrant.tech/)
[![Version](https://img.shields.io/badge/version-2.1.0-green?style=flat-square)](https://github.com/Neboy72/hermes-nexus-memory/releases)

> **Bot Self-Install:** Tell your AI: *"Read AGENTS.md and install Nexus Memory."* It does the rest.

**No API keys needed. Local by default — cloud if you want.**

👉🏻 click 🤖 [![Bot Self-Install](https://img.shields.io/badge/Bot%20Self--Install-blue?style=for-the-badge)](AGENTS.md) &nbsp;&nbsp; 👉🏻 click ⭐ [![Star on GitHub](https://img.shields.io/badge/Star%20on%20GitHub-gold?style=for-the-badge)](https://github.com/Neboy72/hermes-nexus-memory)

---

[![Architecture](docs/images/architecture.png)](docs/images/architecture.png)

---

## Quick Start

### 🤖 Tell your agent to install it

Send this prompt to your Hermes agent:

```
Read https://raw.githubusercontent.com/Neboy72/hermes-nexus-memory/main/AGENTS.md and follow the installation instructions.
```

Your agent will check prerequisites, install everything, configure the provider, and verify. Zero manual steps.

### 🛠️ Or install manually

```bash
# Install the plugin
curl -sL https://raw.githubusercontent.com/Neboy72/hermes-nexus-memory/main/install.sh | bash

# Or use the built-in wizard:
hermes memory setup   # → Select "nexus" → Pick embedding provider → Done.
```

Restart your gateway (from terminal, not inside agent chat):

```bash
hermes gateway restart
```

### Add Hybrid Retrieval (optional, recommended)

```bash
pip install bm25s
```

That's it. Hybrid search activates automatically when `bm25s` is installed.

---

## What's New

### v2.1.0 — Auto-Discovery + Graph Analytics 🔄

| Feature | What it does | Why it matters |
|---------|-------------|---------------|
| 🔄 **Auto-Discovery** | `AutoDiscovery.discover_all()` — scans all canonical Facts, finds similarity via Qdrant (O(n·k)), classifies relations heuristically (wikilinks, "see also"/"cf.", keyword overlap), deduplicates against SQLite, stores as `active` (≥0.85) or `proposed` (<0.85) | **Zero-token relation discovery.** No LLM, no new dependencies. Facts connect themselves — no manual edges needed. |
| 📊 **Graph Analytics** | `GraphAnalytics.full_report()` — Hub scores (most-connected facts), isolation scores, knowledge gaps, connected components (weakly), relation distribution | **Understand your knowledge graph.** See at a glance which facts are isolated (= knowledge gaps) and which are most connected. |
| 🚀 **Graph Boost** | `HybridRetriever.search_hybrid(graph_boost=True)` — boosts search results by `1.0 + degree * 0.05` based on graph connectivity | **Connected facts rank higher.** A fact with 10 edges gets 1.5x boost, an isolated one stays at 1.0x. |
| 🧪 **219 Unit Tests** | 45 new tests for Discovery + Analytics + Graph Boost + Proposed Edges | All green on Python 3.12 in 2.6s. |
| ✨ **Convenience Tools** | `nexus_discover()` + `nexus_graph_report(as_text=True)` — direct API calls without manual initialization | One call, done. `nexus_discover()` = scan + store, `nexus_graph_report()` = instant analysis. |

Proposed Edges are invisible by default in `list_edges()` — only visible with `status='proposed'`. `promote_edge()` makes them active.

### v2.0.0 — SkillGraph: Edge Store + Query Layer 🔗

| Feature | What it does | Why it matters |
|---------|-------------|---------------|
| 🔗 **SkillGraph Edge Store** | SQLite-backed directed graph — `add_edge()` with 5 relation types (`depends_on`, `extends`, `contradicts`, `required_by`, `references`), 3 lifecycle statuses (`active`, `rejected`, `deprecated`), partial unique index `WHERE status='active'` | **Store WHY facts relate, not just WHAT they are.** No duplicate active edges. Full audit trail through lifecycle states. |
| 🕸️ **Graph Query Layer** | NetworkX in-memory cache — BFS with depth-limit (`get_related()`), DFS chain detection (`get_path()`), symmetric `contradicts` edges auto-inserted. Incremental updates — no full rebuild on mutation. | Query relationships in milliseconds. Multi-hop paths for reasoning chains. Zero-cost updates after one-time startup rebuild. |
| 🏛️ **Schema-First Design** | `EdgeRelation` enum + `EdgeStatus` enum in `schema.py`. SQLite = Source of Truth, NetworkX = readonly cache. `write_to_store()` before `sync_to_cache()`. | **Data integrity before performance.** The schema is the contract — everything validates against it before it touches the store. |
| 🔄 **Incremental Graph Updates** | `_add_edge_to_graph()` / `_remove_edge_from_graph()` update NetworkX in-place. Full `_rebuild()` only on `initialize()`. | One-time rebuild at startup, then zero-cost incremental. No full-graph-scan on every `add_edge()`. |
| 🧪 **165 Unit Tests (35 new)** | `tests/test_graph.py` — SQLite schema validation, edge CRUD, lifecycle (reject/deprecate/reactivate), BFS depth-limiting, DFS chains, persistence, `get_stats()` coverage. | Verified on Python 3.12 — 165/165 pass. |

Install: `pip install --upgrade hermes-nexus-memory`

<details>
<summary>Earlier releases (v1.0.0 – v1.9.0)</summary>

### v1.9.0 — Skill Export 🎯

| Feature | What it does | Why it matters |
|---------|-------------|---------------|
| 🎯 **Skill Export** | `export_skill()` searches canonical facts by topic → clusters into Steps/Pitfalls/Prerequisites/Verification → generates complete `SKILL.md` with frontmatter, traceability, and structured instructions | **Turn learned facts into reusable agent skills.** No more manual SKILL.md editing — one command from Nexus to deployable skill. |
| 🖥️ **nexus-export CLI** | `--list` shows exportable topics, `--skill name` exports as `.md`, `--deploy` writes directly to `~/.hermes/skills/`. Auto-installed via `pip install`. | Integrates directly with Hermes Skill system. `nexus-export --skill review-patterns --deploy` = skill ready next session. |
| 🔍 **Legacy-Compat** | Handles both v1.8.0 FactVersion payloads (dict content) and legacy Hermes conversation format (`user_content` + `assistant_content`). Paginated scroll scans 200+ entries. | Works on existing 2000+ entry databases without migration. No data loss, no schema changes. |
| 🧩 **Heuristic Clustering** | Classifies fact content by keyword patterns into Steps, Pitfalls, Prerequisites, Verification. Dedup by content-key, max 15 items per section, max 10 tags. Topic filter: content text + category tags. | Structured skills without LLM calls. Template-based generation is deterministic, fast, and zero-cost. |

Install: `pip install --upgrade hermes-nexus-memory`

### v1.8.0 — Fact Lifecycle Model 🧬

| Feature | What it does | Why it matters |
|---------|-------------|---------------|
| 🧬 **Fact Lifecycle Model** | Append-only state machine: `pending → canonical \| deprecated \| rolled_back`. Every revision gets `fact_id` (stable), `version_id` (unique), `content_hash` (frozen at create), `supersedes` (on version_id-level), `decision_event` (mandatory reason). | **No silent overwrites. No zombie facts. Full audit trail.** Every change is a new version — history is never rewritten. |
| 🏗️ **Staging Area** | `create_pending()` → pending review → `promote()` to canonical. `list_pending()` shows update-drafts (versions WITH supersedes) alongside new facts. | Stage changes before they go live. Review queue for manual approval. |
| 🔄 **Rollback** | `rollback()` creates a `rolled_back` marker + restores previous canonical. Both stay in append-only history. | Undo mistakes without losing evidence. The bad version persists as historical record. |
| 🛡️ **Concurrency Guard** | `promote()` verifies `pending.supersedes == current_canonical.version_id` before writes. Stale pendings raise `ValueError` with clear message. | Prevents lost-update / fork scenarios when multiple processes stage against the same fact. |
| 🚀 **Auto Collection Bootstrap** | `ensure_collections()` creates `hermes-memory-canonical` with correct 512D on first `create_pending()`/`promote()`. | No more schema/dimension crashes on first promote. |
| 📋 **100 Unit Tests (71 new)** | `tests/test_lifecycle.py` (60) + `tests/test_staging.py` (11) — state machine, concurrency guard, serialization, CanonicalView, collection bootstrap. Existing tests: health (29) + enrich (13) all green. | Verified on Python 3.12 via Hermes venv — 100/100 pass. 2 benign SWIG deprecation-warnings from scikit-learn/sentence-transformers (upstream issue, not ours). |

Install: `pip install --upgrade hermes-nexus-memory`

### v1.7.2

| Feature | What it does | Why it matters |
|---------|-------------|---------------|
| 🔍 **Hybrid Search — `nexus_search_hybrid()`** | BM25 + Vector + RRF + Tier-Boost — one function for all 3 embedding providers: `voyage`, `sentence-transformers`, `ollama`. Auto-detection from config.yaml. Falls back to BM25-only. | Anti-RAG-poisoning: keyword precision + semantic search combined. Source-tier boost pushes trusted sources higher. |
| 🎯 **3 Embedding-Providers** | `voyage` (cloud, voyage-3-lite), `sentence-transformers` (local, all-MiniLM-L6-v2), `ollama` (local, nomic-embed-text) — universal embedding choice | Choose what fits your setup: cloud quality or local privacy. |

Install: `pip install hermes-nexus-memory[hybrid]`

### v1.7.1

| Feature | What it does | Why it matters |
|---------|-------------|---------------|
| 🔍 **Provenance Scan** | `scan_provenance()` scrolls all Qdrant entries and reports source types, confidence distribution, criticality markers | Full transparency on where every memory comes from — essential for audits and debugging |
| 🔗 **Wikilink Orphan Detection** | `find_wikilink_orphans()` finds `[[wikilinks]]` that don't resolve anywhere — backtick-aware, no noise | Ensures your wiki has no dead links |

### v1.7.0

| Feature | What it does | Why it matters |
|---------|-------------|---------------|
| 📅 **Memory Expiry** | 3 policies: `static` (never), `normal` (90d), `volatile` (7d). DriftDetector flags expired entries. `last_confirmed_at` extends life. `valid_until` overrides policy. | Stale configs, old paths and dead API keys finally get caught — Provenance said *where* from, Expiry says *when* done |
| 📊 **Tiered Enrichment** | `nexus/enrich.py` — 3 tiers: T1 (store), T2 (+keywords), T3 (+linking). Hybrid decision: caller override → importance → category → content heuristics → T1 default | Low-value logs stay lean, critical facts get full enrichment — no wasted compute on noise |
| 🧪 **29 Unit Tests** | `tests/test_health.py` (16) + `tests/test_enrich.py` (13) — policy logic, timezone safety, valid_until override, enrichment heuristics, keyword extraction | Each release is verified at both module and integration level |

### v1.6.1

| Feature | What it does | Why it matters |
|---------|-------------|---------------|
| ⚓ **Grounding Rebranding** | `ConfidenceScorer` → `GroundingScorer`, labels now say "Grounding" not "Confidence" | Measures *source grounding*, not model confidence — honest naming |
| 🏷️ **Named Entity Matching** | Factual signal uses 48 tech entities (Nexus, Qdrant, Voyage, BM25, GPT…) | Precision hallucination detection — catches missing facts, not just words |
| 💡 **Why-Hints** | `--pretty` output explains *why* each signal scored low/high | "Query barely fits the chunks" > raw "Similarity: 54%" |

### v1.6.0

| Feature | What it does | Why it matters |
|---------|-------------|---------------|
| ✅ **RAG Grounding Scoring** | 5-signal evaluation: similarity, dominance, grounding, factual overlap, coverage | Know *how reliable* an answer really is — 🟢 Very High → ⛔ Very Low |
| 🧩 **Grounding CLI** | `bin/nexus-confidence --pretty "query" "answer"` | Test confidence of any RAG response in seconds |
| 🎯 **3-Provider Embedding** | Grounding Scorer uses the same provider as your system (voyage/sentence-transformers/ollama) | No dimension mismatch — works with any configuration |
| 🧹 **Retrieval Filter** | `search_vector()` filters on `type: memory` — no more session turns in results | Clean results, only facts, no chat history noise |

### v1.5.0

| Feature | What it does | Why it matters |
|---------|-------------|---------------|
| 🗣️ **Authority Chain** | 6-level priority: direct > policy > recent > sourced > vague > compressed | Resolves conflicting facts automatically — knows which one to trust |
| 🔬 **`resolve_authority(facts)`** | Picks the highest-authority fact from a list | One call, no manual ranking |
| ⚖️ **`nexus_resolve_conflict(facts)`** | Returns winner + runner-up + reasoning | Full transparency on tiebreak decisions |
| 🕐 **Timestamp Tiebreaker** | Among equal authorities, newer fact wins | "Direct instruction now" beats "policy from yesterday" |
| 🤖 **Auto-Detection** | Reads authority level from category, source, and content | Zero config — works out of the box |

### v1.4.0

| Feature | What it does | Why it matters |
|---------|-------------|---------------|
| 📜 **Multi-Level Provenance** | Tracks where every fact comes from (source, corroboration, dependencies) | Know *why* your agent trusts a memory — confidence scores, cross-references, dependency graphs |
| 🔗 **Level 1: Source** | `attach_source()` + auto-tracking in `nexus_remember()` | "This fact came from Kiosha's chat session on May 23" |
| 🤝 **Level 2: Corroboration** | `find_corroboration()` + `corroborate_entry()` | "This fact is confirmed by 3 other entries" — automatic confidence recalibration |
| 🕐 **Level 3: Bi-temporal (extended)** | `modified_at`/`modified_by` in `nexus_update()` | Track who changed what and when |
| 🕸️ **Level 4: Dependency Graph** | `build_dependency_graph()` with `depends_on`/`dependents` | "If this fact is wrong, 5 other entries break" — criticality scoring |
| 🆔 **Auto-UUID** | `nexus_remember()` generates valid Point IDs | No more "value Unit is not a valid point ID" errors |

### v1.3.0

| Feature | What it does | Why it matters |
|---------|-------------|---------------|
| 🔧 **Auto-Fix / `nexus_consolidate()`** | Resolves contradictions automatically, marks older entry as HISTORICAL | Fix problems, not just find them |
| 🕐 **Bi-temporal Metadata** | `valid_from` / `valid_until` on every memory | Never silently overwrite decisions |
| 🏛️ **Historical Exclusion** | HISTORICAL/RESOLVED/ARCHIVED entries skipped by drift detection | No false positives on resolved incidents |
| 📊 **`nexus_query_valid()`** | Filter memories by temporal validity | Query only memories that are currently valid |

### v1.2.0

| Feature | What it does | Why it matters |
|---------|-------------|---------------|
| 🔄 **Incremental BM25** | `update_index()` adds/removes without full rebuild | Growing memory stays fast |
| 🔍 **Contradiction Detection** | Finds semantically opposing memories via embeddings | Catches "X is active" vs "X is disabled" automatically |
| 📊 **Usage Tracking** | `track_usage()` + `prune_unused(days=90)` | Clean up memories that are never accessed |
| 🔧 **`nexus_update()`** | Update memories in-place | No more forget+remember with metadata loss |
| 🏷️ **`source_tier` metadata** | Set tier at store-time, not just keywords | Precise source ranking |

### v1.1.0

| Feature | What it does | Why it matters |
|---------|-------------|---------------|
| 🛡️ **Hybrid Retrieval** | BM25 + Vector + Reciprocal Rank Fusion | Kills RAG poisoning — hybrid search catches what pure vector misses |
| 🏷️ **Source Tier Boosting** | Trust-ranked sources (🟢🟡🔴) | Prioritizes your own data, downgrades untrusted inputs |
| 🔍 **Belief Drift Detection** | Scores memory health 0–10 | Finds stale entries *before* they corrupt your agent |

</details>

---

## Tools

| Tool | Purpose |
|------|---------|
| `nexus_search(query, limit=5)` | Hybrid search — BM25 + vector + RRF fusion |
| `nexus_remember(content, category, source)` | Save facts, decisions, preferences, patterns |
| `nexus_forget(memory_id)` | Remove a specific memory |
| `nexus_confidence(query, answer)` | Grounding scoring — how reliable is this RAG response? |

**Saved once → persists across sessions, model switches, and gateway restarts.**

---

## Hybrid Retrieval 🛡️

Pure vector search is vulnerable to **RAG poisoning** — adversarial documents that rank high semantically but contain garbage. Hybrid retrieval fixes this by blending two search strategies:

| Method | Strengths | Weaknesses |
|--------|----------|------------|
| **BM25** | Keyword-exact, poison-resistant | Misses semantics |
| **Vector** | Semantic matching, fuzzy queries | Vulnerable to poisoning |
| **Hybrid (RRF)** | Best of both | — |

### How it works

```
Query → ┌─ BM25 Index ──────→ Keyword Rankings
        │                          │
        └─ Vector Embeddings ──→ Semantic Rankings
                                       │
                              RRF Fusion ───→ Combined Rankings
                                       │
                              Tier Boost ───→ Final Results
```

**Reciprocal Rank Fusion (RRF):** Each result gets `1/(k + rank)` points from each method. Sum across methods. Simple, effective, no tuning needed.

### Source Tiers

| Tier | Sources | Boost | Example |
|------|---------|-------|---------|
| 🟢 Tier 1 | Agent, user, config, official docs | **1.2×** | Your agent's own memory |
| 🟡 Tier 2 | Curated external sources | **1.0×** | Medium, arXiv, GitHub READMEs |
| 🔴 Tier 3 | Uncurated / unknown sources | **0.8×** | Reddit, Twitter, random forums |

Your own data always wins. Untrusted sources get penalized. Poisoning becomes statistically unlikely.

### Use it standalone

```python
from nexus.retrieval import HybridRetriever

retriever = HybridRetriever(qdrant_host="localhost", qdrant_port=6333)
retriever.index_memories()                          # build BM25 index from Qdrant
results = retriever.search_bm25("fallback routing") # keyword search
results = retriever.search_hybrid("fallback routing", query_vector=vec)  # full hybrid
```

Or without Qdrant (for testing):

```python
retriever = HybridRetriever()
retriever.index_from_texts(
    texts=["DeepSeek V4 is disabled", "Kimi K2.6 is the fallback"],
    ids=["1", "2"],
)
results = retriever.search_bm25("deepseek fallback")
```

---

## Belief Drift Detection 🔍

Agents drift when their memory goes stale. A fact saved 3 months ago might be wrong today. Drift detection catches this automatically.

### What it detects

| Check | Method | Example |
|-------|--------|---------|
| **Stale entries** | Regex patterns for outdated facts | "DeepSeek V4 running as fallback" — but it was disabled |
| **Old entries** | Age threshold (default: 90 days) | Entry from January, now May |
| **Score** | Weighted 0–10 | 🟢 <1 = healthy · 🟡 1–3 = attention · 🔴 >3 = action needed |

### Use it standalone

```python
from nexus.health import DriftDetector, DriftReport

detector = DriftDetector()
report = detector.run()

print(report.summary)     # "🟢 Score: 0.4/10"
print(report.stale)       # list of stale entries with reasons
print(report.json())      # structured JSON output
```

Or without Qdrant:

```python
detector = DriftDetector()
report = detector.run_from_texts([
    {"id": "1", "content": "DeepSeek V4 Pro running as fallback", "timestamp": "2026-04-01T10:00:00Z"},
    {"id": "2", "content": "Nomic embed is the default provider", "timestamp": "2026-03-15T10:00:00Z"},
])
print(report.summary)  # "🟡 Score: 0.8/10" — stale entries found
```

### Custom stale patterns

```python
detector = DriftDetector(stale_patterns=[
    (r"\bmy_old_tool\b.*\bactive\b", "my_old_tool was replaced in March"),
])
```

---

## Embedding Providers

One plugin. Three backends. Same tools, same API, same results.

| Provider | Type | Setup | Dims | Quality |
|----------|------|-------|------|---------|
| `sentence-transformers` | In-process Python | `pip install sentence-transformers` | 384 | Good ✅ *(default)* |
| `ollama` | Local service | Ollama running + `ollama pull nomic-embed-text` | 768 | Better |
| [`voyage`](https://www.voyageai.com) | Cloud API | [Get API key →](https://www.voyageai.com) → `.env` | 1024 | Best |

**Default is `sentence-transformers`** — no account, no API key, works immediately.

---

## vs Other Memory Plugins

| Feature | agentmemory | Holographic | Mem0 | Honcho | **Nexus** 🏆 |
|---------|:-----------:|:-----------:|:----:|:------:|:------------:|
| 🔍 Semantic search | ✅ (Gemini API) | ✅ (HRR algebra) | ✅ (Cloud API) | ✅ (pgvector) | ✅ (local or cloud) |
| 🔀 **Hybrid retrieval** | ❌ | ❌ | ✅ Multi-signal | ❌ | **✅ BM25 + Vector + RRF** |
| 🩺 **Drift detection** | ❌ | ❌ | ❌ * | ❌ | **✅ Scored 0–10** |
| 🛡️ **Anti-poisoning** | ❌ | ❌ | ❌ | ❌ | **✅ Source tiers** |
| 🔗 **Multi-Level Provenance** | ❌ | ❌ | ❌ | ❌ | **✅ Source + Corroboration + Dependency Graph** |
| 🗣️ **Authority Chain** | ❌ | ❌ | ❌ | ❌ | **✅ 6-level priority resolution** |
| ✅ **RAG Grounding Scoring** | ❌ | ❌ | ❌ | ❌ | **✅ 5-signal evaluation** |
| 🔧 **Auto-Fix / Consolidation** | ❌ | ❌ | ❌ | ❌ | **✅ `nexus_consolidate()`** |
| 📅 **Memory Expiry** | ❌ | ❌ | ❌ * | ❌ | **✅ 3 policies (static/normal/volatile)** |
| 📊 **Tiered Enrichment** | ❌ | ❌ | ❌ | ❌ | **✅ Auto T1/T2/T3 Heuristik** |
| 🧬 **Fact Lifecycle Model** | ❌ | ❌ | ❌ | ❌ | **✅ Append-only: pending → canonical \| deprecated \| rolled_back** |
| 🔄 **Staging + Rollback** | ❌ | ❌ | ❌ | ❌ | **✅ `create_pending()` → `promote()` → `deprecate()` → `rollback()`** |
| 🎯 **Skill Export** | ❌ | ❌ | ❌ | ❌ | **✅ `nexus-export --deploy` (Facts → SKILL.md)** |
| 🔗 **SkillGraph (Edge Store)** | ❌ | ❌ | ❌ | ❌ | **✅ SQLite + NetworkX — 5 relation types, BFS/DFS, incremental updates** |
| 🔄 **Auto-Discovery** | ❌ | ❌ | ❌ | ❌ | **✅ Embedding-based + heuristic classification — 0 token cost** |
| 📊 **Graph Analytics** | ❌ | ❌ | ❌ | ❌ | **✅ Hub scores, knowledge gaps, connected components** |
| 🚀 **Graph Boost** | ❌ | ❌ | ❌ | ❌ | **✅ Search ranking boosts connected facts (1.0 + degree × 0.05)** |
| 🌐 External APIs | Gemini required | None | Cloud API required | Cloud / PostgreSQL | **Optional** |
| 📦 Code size | ~50K TypeScript | ~1.5K Python | Managed service | Managed service | **~7.4K Python** |
| ⏱️ Setup time | 30+ min + OAuth | 1 command | API key + signup | Postgres + pgvector | **1 command** |

*Mem0 lists staleness as an "open problem" in their 2026 report but does not ship a solution.*

**Nexus is the only memory plugin with auto-discovery, graph analytics, graph boost, drift detection, provenance, authority chain, memory expiry, tiered enrichment, fact lifecycle model, staging/rollback, skillgraph, and skill export — plus hybrid retrieval, all in one package.**

---

## Requirements

- Python 3.11+ with `requests`
- Qdrant v1.17+ running on `localhost:6333`
- One embedding provider (default: sentence-transformers)
- **Optional:** `bm25s` for hybrid retrieval (`pip install bm25s`)

## Troubleshooting

| Symptom | Check | Fix |
|---------|-------|-----|
| `nexus` tools missing | `grep 'nexus' ~/.hermes/logs/agent.log` | `hermes gateway restart` |
| Qdrant not running | `curl http://127.0.0.1:6333/healthz` | `launchctl start com.qdrant.server` |
| Hybrid search missing | `pip list \| grep bm25s` | `pip install bm25s` |
| Embedding unhealthy | `grep 'Nexus memory' agent.log` | Switch via `hermes config set` |
| Drift score high | Run `DriftDetector` standalone | Review stale entries, clean up |


## Related Projects

- **[OpenClaw Nexus Memory](https://github.com/Neboy72/openclaw-nexus-memory)** — Production-grade memory management for OpenClaw agents (stale auto-fix, contradiction detection, knowledge gaps, wiki integration. No database required.)

> ⭐ Found it useful? Give it a star on [GitHub](https://github.com/Neboy72/hermes-nexus-memory) — it helps others find it!

## License

MIT — use it, modify it, ship it.

[comment]: <> (last refreshed 2026-05-27)

---

<sub>Built by [Nebo](https://github.com/Neboy72) · May 2026 · v2.1.0 — Auto-Discovery + Graph Analytics</sub>