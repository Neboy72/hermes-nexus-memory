# Hermes Nexus Memory 🧠

![GitHub Stars](https://img.shields.io/github/stars/Neboy72/hermes-nexus-memory?style=flat-square&logo=github)
![GitHub License](https://img.shields.io/github/license/Neboy72/hermes-nexus-memory?style=flat-square)
![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue?style=flat-square&logo=python)
![Qdrant v1.17+](https://img.shields.io/badge/qdrant-v1.17+-purple?style=flat-square)
![Version](https://img.shields.io/badge/version-1.2.0-green?style=flat-square)
![Bot Self-Install](https://img.shields.io/badge/bot-self--install-brightgreen?style=flat-square)

> **Production-grade vector memory for AI agents — hybrid retrieval, drift detection, RAG poisoning defense. 🤖 Bot self-installs.**

Your agent forgets everything after each session. **Nexus fixes that.**

Semantic search over facts, decisions, and patterns. Persists across restarts. Now with **Hybrid Retrieval** (BM25 + Vector + RRF) against poisoning, and **Belief Drift Detection** against stale memories.

---

## What's New

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

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                       NEXUS MEMORY v1.1                       │
│                                                              │
│  Core ──────────── Semantic vector search (Qdrant)           │
│  Retrieval ─────── Hybrid BM25 + Vector + RRF + Tier Boost   │
│  Health ────────── Belief Drift Detection (0–10 scoring)     │
│                                                              │
│         ┌──────────────┐     ┌─────────────────────┐        │
│         │   Qdrant     │     │  Embedding Provider  │        │
│         │ localhost:   │◄────│  (3 to choose from)  │        │
│         │ 6333        │     └─────────────────────┘        │
│         └──────┬───────┘                                     │
│                │                                              │
│   ┌────────────┴────────────────────────┐                   │
│   │  NexusMemoryProvider (~400 LOC)     │                   │
│   │  + HybridRetriever  (~250 LOC)      │                   │
│   │  + DriftDetector    (~150 LOC)      │                   │
│   └─────────────────────────────────────┘                   │
└──────────────────────────────────────────────────────────────┘
```

---

## vs Other Memory Plugins

| | agentmemory | Holographic | Mem0 / Honcho | **Nexus** 🏆 |
|---|---|---|---|---|
| Semantic search | ✅ (Gemini API) | ❌ Hash-based | ✅ (Cloud API) | ✅ (local or cloud) |
| **Hybrid retrieval** | ❌ | ❌ | ❌ | **✅ BM25 + Vector + RRF** |
| **Drift detection** | ❌ | ❌ | ❌ | **✅ Scored 0–10** |
| **Anti-poisoning** | ❌ | ❌ | ❌ | **✅ Source tiers** |
| External APIs | Gemini required | None | Multiple cloud APIs | **Optional** |
| Code size | ~50K TypeScript | ~1.5K Python | Varies | **~800 Python** |
| Setup time | 30+ min + OAuth | `hermes memory setup` | Cloud account | **1 command** |

**Nexus is the only memory plugin with hybrid retrieval, drift detection, and anti-poisoning — in under 1000 lines.**

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

## License

MIT — use it, modify it, ship it.

---

<sub>Built by [Nebo](https://github.com/Neboy72) · May 2026 · v1.1.0 — Hybrid Retrieval + Drift Detection</sub>