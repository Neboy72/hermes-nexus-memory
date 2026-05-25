# Hermes Nexus Memory 🧠

> **One prompt — your bot never forgets again.**

You talk to your bot. Next day it asks you the same thing.  
Nexus Memory fixes that. **Permanently.**

[![Bot Self-Install](https://img.shields.io/badge/bot--self--install-brightgreen?style=flat-square)](AGENTS.md)
[![GitHub Stars](https://img.shields.io/github/stars/Neboy72/hermes-nexus-memory?style=flat-square&logo=github)](https://github.com/Neboy72/hermes-nexus-memory)
[![GitHub License](https://img.shields.io/github/license/Neboy72/hermes-nexus-memory?style=flat-square)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue?style=flat-square&logo=python)](https://www.python.org/)
[![Qdrant v1.17+](https://img.shields.io/badge/qdrant-v1.17+-purple?style=flat-square)](https://qdrant.tech/)
[![Version](https://img.shields.io/badge/version-1.7.1-green?style=flat-square)](https://github.com/Neboy72/hermes-nexus-memory/releases)

> ⭐ **If this project helps your agent remember — drop a star so others find it too. Takes 2 seconds.**

> **Bot Self-Install:** Tell your AI: *"Read AGENTS.md and install Nexus Memory."* It does the rest.

Your agent remembers across sessions — facts, decisions, patterns.  
Hybrid retrieval (BM25 + Vector) kills RAG poisoning. Drift detection flags stale memories automatically.  
**No nonsense. No bloat. Just memory that works.**  
**No API keys needed. Local by default — cloud if you want.**

[![Star the repo](https://img.shields.io/badge/⭐-Star%20on%20GitHub-gold?style=flat-square)](https://github.com/Neboy72/hermes-nexus-memory)

---

[![Architecture](docs/images/architecture.png)](docs/images/architecture.png)

---

## What's New

### v1.7.1

| Feature | What it does | Why it matters |
|---------|-------------|---------------|
| 🔍 **Provenance Scan** | `scan_provenance()` scrollt alle Qdrant-Entries und zeigt Source-Typen, Confidence-Verteilung, Criticality-Marker | Transparenz über die Herkunft jeder Memory — wichtig für Audits und Debugging |
| 🔗 **Wikilink Orphan Detection** | `find_wikilink_orphans()` findet `[[wikilinks]]` die nirgends auflösen — backtick-aware, kein Rauschen | Stellt sicher dass dein Wiki keine toten Links hat |

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

| | agentmemory | Holographic | Mem0 / Honcho | **Nexus** 🏆 |
|---|---|---|---|---|
| Semantic search | ✅ (Gemini API) | ❌ Hash-based | ✅ (Cloud API) | ✅ (local or cloud) |
| **Hybrid retrieval** | ❌ | ❌ | ❌ | **✅ BM25 + Vector + RRF** |
| **Drift detection** | ❌ | ❌ | ❌ | **✅ Scored 0–10** |
| **Anti-poisoning** | ❌ | ❌ | ❌ | **✅ Source tiers** |
| 🔗 **Multi-Level Provenance** | ❌ | ❌ | ❌ | **✅ Source + Corroboration + Dependency Graph** |
| 🗣️ **Authority Chain** | ❌ | ❌ | ❌ | **✅ 6-level priority resolution** |
| ✅ **RAG Grounding Scoring** | ❌ | ❌ | ❌ | **✅ 5-signal evaluation** |
| 🔧 **Auto-Fix / Consolidation** | ❌ | ❌ | ❌ | **✅ `nexus_consolidate()`** |
| 📅 **Memory Expiry** | ❌ | ❌ | ❌ | **✅ 3 policies (static/normal/volatile)** |
| 📊 **Tiered Enrichment** | ❌ | ❌ | ❌ | **✅ Auto T1/T2/T3 Heuristik** |
| External APIs | Gemini required | None | Multiple cloud APIs | **Optional** |
| Code size | ~50K TypeScript | ~1.5K Python | Varies | **~2.2K Python** |
| Setup time | 30+ min + OAuth | `hermes memory setup` | Cloud account | **1 command** |

**Nexus is the only memory plugin with drift detection, provenance, authority chain, memory expiry, and tiered enrichment — plus hybrid retrieval, all in one package.**

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

[comment]: <> (last refreshed 2026-05-24)

---

<sub>Built by [Nebo](https://github.com/Neboy72) · May 2026 · v1.6.1 — Grounding Rebranding + Named Entity Matching</sub>