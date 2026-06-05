# Hermes Nexus Memory 🧠

> **Your agent remembers — across sessions, model switches, and gateway restarts.**

[![Stars](https://img.shields.io/github/stars/Neboy72/hermes-nexus-memory?style=flat-square&logo=github)](https://github.com/Neboy72/hermes-nexus-memory)
[![License](https://img.shields.io/github/license/Neboy72/hermes-nexus-memory?style=flat-square)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue?style=flat-square&logo=python)](https://www.python.org/)
[![Qdrant v1.17+](https://img.shields.io/badge/qdrant-v1.17+-purple?style=flat-square)](https://qdrant.tech/)
[![CI](https://img.shields.io/github/actions/workflow/status/Neboy72/hermes-nexus-memory/ci.yml?style=flat-square&logo=githubactions)](https://github.com/Neboy72/hermes-nexus-memory/actions)
[![Version](https://img.shields.io/badge/version-2.6.1-green?style=flat-square)](https://github.com/Neboy72/hermes-nexus-memory/releases)

Hybrid retrieval (BM25 + Vector) kills RAG poisoning. Drift detection flags stale memories automatically. SkillGraph, auto-discovery, fact lifecycle — **no nonsense. Just memory that works.**

---

## Install — 30 seconds

### 1. Install the package

```bash
pip install hermes-nexus-memory
```

That's it. Qdrant client is included — no extra pip commands.

### 2. Start Qdrant

The setup script detects your OS and starts Qdrant automatically:

```bash
curl -sL https://raw.githubusercontent.com/Neboy72/hermes-nexus-memory/main/setup.sh | bash
```

Or manually:
- **macOS:** `brew install qdrant && brew services start qdrant`
- **Linux:** `docker run -d --name qdrant -p 6333:6333 qdrant/qdrant:v1.17`
- **Already running?** `curl http://127.0.0.1:6333/healthz` to verify

### 3. Verify installation

```bash
nexus-export --help
```

You should see the Nexus CLI help.

### 4. Run a health check

```python
python3 -c "
from nexus.health import health_check
print(health_check())
"
```

Expected output: `HealthResponse(healthy=True, ...)`.

---

## Quick Start — first memory in 2 minutes

```python
from nexus import NexusMemory

# Connect to your Qdrant
nexus = NexusMemory(collection_name="my-memories")

# Save a fact
nexus.remember(
    content="The database runs on Qdrant v1.17 at localhost:6333",
    category="config",
    source="install"
)

# Search it back
results = nexus.search("Qdrant database")
for r in results:
    print(f"  [{r.category}] {r.content}")
```

### Or use the convenience tools:

```bash
# Remember something
python3 -c "from nexus import nexus_remember; nexus_remember('Nexus Memory installed on Mac Mini M4', category='config', source='setup')"

# Search
python3 -c "from nexus import nexus_search; print(nexus_search('Mac Mini'))"
```

---

## Upgrade from an older version

### v1.x → v2.x or v2.x → latest

```bash
# 1. Upgrade the package
curl -sL https://raw.githubusercontent.com/Neboy72/hermes-nexus-memory/main/setup.sh | bash  # detects upgrade automatically

Or manually:
```bash
pip install --upgrade hermes-nexus-memory
```

# 2. Restart your Hermes gateway (if used as plugin)
hermes gateway restart

# 3. Run the migration (if v1.x → v2.x)
nexus-migrate
```

**Note:** v2.x changes the collection structure from `hermes-memory` to `hermes-memory-canonical`. The migration script handles this automatically. Your old data is preserved — nothing is deleted.

**Rollback:** `pip install hermes-nexus-memory==<previous-version>`

---

## 🤖 Bot Self-Install

Tell your Hermes agent this single prompt:

```
Read https://raw.githubusercontent.com/Neboy72/hermes-nexus-memory/main/AGENTS.md and follow the installation instructions.
```

Your agent checks prerequisites, installs everything, configures the provider, and verifies. **Zero manual steps.**

---

## Features at a glance

| What | Why it matters |
|------|---------------|
| **Hybrid Retrieval** (BM25 + Vector + RRF) | Kills RAG poisoning — keyword precision + semantic search combined |
| **Belief Drift Detection** | Scored 0-10 — catches stale entries before they corrupt your agent |
| **Multi-Level Provenance** | Track source, corroboration, and dependency graph for every fact |
| **Authority Chain** | 6-level priority — resolves conflicting facts automatically |
| **Fact Lifecycle** | Append-only state machine (pending → canonical → deprecated). Full audit trail |
| **Staging + Rollback** | Stage changes before going live. Undo mistakes without losing history |
| **Skill Export** | `nexus-export --deploy` — turn learned facts into reusable agent skills |
| **SkillGraph** | Qdrant-backed directed graph with 5 relation types, BFS/DFS queries |
| **Auto-Discovery** | Zero-token relation discovery — facts connect themselves |
| **Graph Analytics + Boost** | Hub scores, knowledge gaps, connected facts rank higher |
| **Memory Expiry** | 3 policies (static/normal/volatile). Auto-cleanup of stale configs |
| **Grounding Scoring** | 5-signal RAG evaluation — know how reliable an answer is |
| **3 Embedding Providers** | sentence-transformers (local), Ollama (local), Voyage (cloud) — same API |

---

## Requirements

- **Python 3.11+**
- **Qdrant v1.17+** (Docker: `docker run -d --name qdrant -p 6333:6333 qdrant/qdrant:v1.17`)
- **Optional:** `pip install bm25s` for hybrid retrieval (recommended)

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `ModuleNotFoundError: qdrant_client` | `pip install hermes-nexus-memory` (qdrant is a core dependency now) |
| Qdrant not running | `curl http://127.0.0.1:6333/healthz` → start Qdrant |
| `nexus` tools not showing | `hermes gateway restart` (from terminal, not agent chat) |
| Hybrid search not working | `pip install bm25s` — auto-detected |
| `collection not found` | Run `nexus_remember()` once to auto-create the collection |

---

## CLI Tools

| Command | What it does |
|---------|-------------|
| `nexus-export` | Export facts as deployable Hermes skills (`--skill topic --deploy`) |
| `nexus-migrate` | Migrate from older collection formats |
| `nexus-discover` | Run auto-discovery — let facts find their relations |
| `nexus-graph-report` | Generate graph analytics report |

---

## Embedding Providers

Pick one — same API, different tradeoffs:

| Provider | Setup | Dimensions | Quality |
|----------|-------|-----------|---------|
| `sentence-transformers` | `pip install sentence-transformers` (built-in) | 384 | Good ✅ *(default)* |
| `ollama` | `ollama pull nomic-embed-text` | 768 | Better |
| `voyage` | Get API key → set in `.env` | 1024 | Best |

**No account needed by default** — sentence-transformers works immediately.

---

## Related Projects

- **[OpenClaw Nexus Memory](https://github.com/Neboy72/openclaw-nexus-memory)** — Nexus Memory for OpenClaw agents (SQLite-backed, no database required)

---

## What's New

### v2.6.1 — Collection-Default-Cleanup + Base Dependency Fix

- Qdrant-client promoted from optional (`[all]`) to core dependency — **no more `ModuleNotFoundError` on fresh install**
- CI pipeline added: automatic tests on every push (224 tests, Python 3.11 + 3.12)
- Bugfix: Base install no longer crashes on `import nexus`

See [CHANGELOG.md](CHANGELOG.md) for the full version history.

---

> ⭐ Found it useful? [Star on GitHub](https://github.com/Neboy72/hermes-nexus-memory) — takes 2 seconds and helps others find it.

MIT — use it, modify it, ship it.
