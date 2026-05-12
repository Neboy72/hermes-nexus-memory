# Hermes Nexus Memory 🧠

![GitHub Stars](https://img.shields.io/github/stars/Neboy72/hermes-nexus-memory?style=flat-square&logo=github)
![MIT License](https://img.shields.io/github/license/Neboy72/hermes-nexus-memory?style=flat-square)
![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue?style=flat-square&logo=python)
![Qdrant v1.17+](https://img.shields.io/badge/qdrant-v1.17+-purple?style=flat-square)
[![Install](https://img.shields.io/badge/install-one%20command-brightgreen?style=flat-square)](https://github.com/Neboy72/hermes-nexus-memory)
[![Documentation](https://img.shields.io/badge/docs-Hermes%20Agent-important?style=flat-square)](https://hermes-agent.nousresearch.com/docs)

> **Qdrant vector memory plugin for Hermes Agent — persistent, local, 400 lines, zero external APIs.**

## Quick Start

One command, done:

```bash
curl -sL https://raw.githubusercontent.com/Neboy72/hermes-nexus-memory/main/install.sh | bash
```

Then restart Hermes gateway:

```bash
hermes gateway restart   # run from terminal, NOT inside agent chat
```

Or use the built-in wizard:

```bash
hermes memory setup
# → Select "nexus"
# → Pick: sentence-transformers | ollama | voyage
# → Done.
```

## What You Get

| Tool | Purpose |
|------|---------|
| `nexus_search(query, limit=5)` | Semantic search — finds memories by meaning |
| `nexus_remember(content, category, source)` | Save facts, decisions, preferences, patterns |
| `nexus_forget(memory_id)` | Remove a specific memory |

**Once saved, it persists across sessions, model switches, and gateway restarts.** Your agent actually remembers.

## Embedding Providers

One plugin. Three backends. Same tools, same API, same results.

| Provider | Type | Setup | Dims | Quality |
|----------|------|-------|------|---------|
| `sentence-transformers` | In-process Python | `pip install sentence-transformers` | 384 | Good ✅ *(default)* |
| `ollama` | Local service | Ollama running + `ollama pull nomic-embed-text` | 768 | Better |
| `voyage` | Cloud API | Voyage API key in `.env` | 1024 | Best |

**Default is `sentence-transformers`** — no external service, no account, no API key. Works immediately.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    NEXUS MEMORY                           │
│                                                          │
│  Episodic   → Hermes Sessions (sync_turn → Qdrant)      │
│  Semantic   → MEMORY.md + nexus_remember()               │
│  Community  → Obsidian Vault (wiki skill)                │
│                                                          │
│         ┌──────────────┐     ┌─────────────────────┐     │
│         │   Qdrant     │     │  Embedding Provider  │     │
│         │ localhost:   │◄────│  (3 to choose from)  │     │
│         │ 6333         │     └─────────────────────┘     │
│         └──────┬───────┘                                  │
│                │                                           │
│   ┌────────────┴────────────────────────────┐             │
│   │  NexusMemoryProvider (~400 LOC)         │             │
│   │  nexus_search │ nexus_remember          │             │
│   │  nexus_forget │ auto-adapts             │             │
│   └─────────────────────────────────────────┘             │
└──────────────────────────────────────────────────────────┘
```

## vs Other Memory Plugins

| | agentmemory | Holographic | Mem0 / Honcho | **Nexus** 🏆 |
|---|---|---|---|---|
| Semantic search | ✅ (Gemini API) | ❌ Hash-based | ✅ (Cloud API) | ✅ (local or cloud) |
| External APIs | Gemini required | None | Multiple cloud APIs | **Optional** |
| Code size | ~50K TypeScript | ~1.5K Python | Varies | **~400 Python** |
| Dependencies | Node.js + npm + engine | SQLite | pip + Cloud accounts | Qdrant + embed |
| Embedding choice | Gemini only | None | Cloud only | **3 providers** |
| Setup time | 30+ min + OAuth | `hermes memory setup` | Cloud account | **1 command** |

**Nexus is the only plugin giving you local-first memory with multiple backends in under 500 lines.**

## Requirements

- Python 3.11+ with `requests`
- Qdrant v1.17+ running on `localhost:6333`
- One embedding provider (default: sentence-transformers)

## Troubleshooting

| Symptom | Check | Fix |
|---------|-------|-----|
| `nexus` tools missing | `grep 'nexus' ~/.hermes/logs/agent.log` | `hermes gateway restart` |
| Qdrant not running | `curl http://127.0.0.1:6333/healthz` | `launchctl start com.qdrant.server` |
| Embedding unhealthy | `grep 'Nexus memory' agent.log` | Switch via `hermes config set` |
| Lost memories after switch | Plugin auto-recreates Qdrant collection | Export before switching |

## License

MIT — use it, modify it, ship it.

---

<sub>Built by [Nebo](https://github.com/Neboy72) · [X](https://x.com/Neboy53623962) · May 2026</sub>
