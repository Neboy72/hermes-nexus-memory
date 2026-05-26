# AGENTS.md — Bot Self-Installation Guide

> **Tell your AI agent to install Nexus Memory. It will handle everything.**

## For Users

Copy this prompt and send it to your agent:

```
Read https://raw.githubusercontent.com/Neboy72/hermes-nexus-memory/main/AGENTS.md and follow the installation instructions.
```

That's it. Your agent will:
1. Check prerequisites (Python, Qdrant)
2. Install the Nexus Memory plugin
3. Configure your embedding provider
4. Set up drift detection (optional)
5. Restart the gateway
6. Verify everything works

---

## For AI Agents — Installation Instructions

You are a Hermes Agent (or compatible). The user wants Nexus Memory installed or upgraded. **First determine if this is a fresh install or an upgrade.**

### Step 0: Detect Existing Installation

```bash
# Check if Nexus Memory is already configured
hermes config get memory.provider 2>/dev/null
# If "nexus" → this is an UPGRADE, skip to Step 2b
# If empty/other → this is a FRESH INSTALL, continue with Step 1

# Check current version
pip show hermes-nexus-memory 2>/dev/null | grep Version
# If v1.0.x → upgrade to v1.1.0 (add hybrid + drift detection)
# If not installed → fresh install

# 🚨 PRE-1.5.0 LEGACY CHECK: Old plugin.yaml structure?
if [ -f ~/.hermes/plugins/nexus/plugin.yaml ]; then
    echo "⚠️ Old plugin structure detected (pre-v1.5.0, plugin.yaml)"
    echo "→ v1.5.0+ uses pyproject.toml instead of plugin.yaml"
    echo "→ Removing old plugin directory..."
    rm -rf ~/.hermes/plugins/nexus/
    echo "✅ Old plugin removed. New code installs via pip."
fi
# If no legacy structure → clean install or modern upgrade, proceed normally

# 🔔 AUTO-UPDATE CHECK: Compare local version with GitHub latest
LOCAL=$(pip show hermes-nexus-memory 2>/dev/null | grep Version | cut -d' ' -f2)
REMOTE=$(curl -s https://api.github.com/repos/Neboy72/hermes-nexus-memory/releases/latest 2>/dev/null \
         | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('tag_name',''))" 2>/dev/null)
if [ -n "$REMOTE" ] && [ "$LOCAL" != "$REMOTE" ]; then
    echo "📢 New version $REMOTE available (you have $LOCAL). Update by saying: upgrade nexus memory"
fi
```

**If already installed (upgrade path):** Skip Step 1 and go directly to **Step 2b: Upgrade**. Do NOT reinstall from scratch — the existing Qdrant collection and memories must be preserved.

**If not installed (fresh install):** Continue with Step 1 below.

### Step 1: Check Prerequisites

```bash
# Python 3.11+ required
python3 --version

# pip available
pip --version

# Qdrant running?
curl -s http://127.0.0.1:6333/healthz
# Expected: {"status":"ok"}
```

**If Qdrant is not running:**
- macOS: `brew install qdrant && brew services start qdrant`
- Linux: `docker run -d -p 6333:6333 qdrant/qdrant`
- Ask the user if you should install it.

**If Python < 3.11:** Inform the user that Python 3.11+ is required. Abort.

### Step 2: Install the Plugin (Fresh Install)

```bash
# Clone the repo
git clone https://github.com/Neboy72/hermes-nexus-memory.git ~/.hermes/hermes-nexus-memory

# Install into Hermes venv (if available)
if [ -d ~/.hermes/hermes-agent/venv ]; then
  source ~/.hermes/hermes-agent/venv/bin/activate
fi

pip install -e ~/.hermes/hermes-nexus-memory[all]
```

### Step 2b: Upgrade (Existing Installation)

**Only follow this if Step 0 detected an existing Nexus installation.**

```bash
# Pull latest code
cd ~/.hermes/hermes-nexus-memory
git pull origin main

# Reinstall (preserves existing Qdrant collection)
if [ -d ~/.hermes/hermes-agent/venv ]; then
  source ~/.hermes/hermes-agent/venv/bin/activate
fi
pip install -e ~/.hermes/hermes-nexus-memory[all]

# Skip Step 3 — config already set, embedding provider already configured
# Go directly to Step 4 (Hybrid Retrieval)

**Important:** Do NOT change the embedding provider or Qdrant collection during upgrade. The existing memories must be preserved.

### Step 3: Configure Hermes

```bash
# Set memory provider to nexus
hermes config set memory.provider nexus

# Choose ONE embedding provider:
# Option A: sentence-transformers (default, no API key needed, works offline)
hermes config set nexus-memory.embed_provider sentence-transformers

# Option B: ollama (local, needs Ollama running)
# First: ollama pull nomic-embed-text
hermes config set nexus-memory.embed_provider ollama

# Option C: voyage (cloud, best quality, needs API key)
# Add VOYAGE_API_KEY to ~/.hermes/.env
hermes config set nexus-memory.embed_provider voyage
```

If the user has no preference, use **sentence-transformers** — it works immediately with zero setup.

### Step 4: Hybrid Retrieval (Recommended)

```bash
# Install BM25 for anti-poisoning hybrid search
pip install bm25s
```

This enables `HybridRetriever` automatically. No extra config needed.

### Step 5: Drift Detection + Memory Expiry (Recommended)

**Do NOT skip this.** Memory goes stale. Without drift detection, your agent will trust outdated facts. See **What's New** in the README for the latest features (v2.0.0: SkillGraph Edge Store + Query Layer, v1.9.0: Skill Export — turn canonical facts into ready-to-use SKILL.md files).

Set up a nightly cron job:

```bash
hermes cron add \
  --name "Nexus Drift Detection" \
  --schedule "0 4 * * *" \
  --model none \
  --script "nexus/health/__init__.py" \
  --deliver telegram
```

This runs every night at 4 AM and sends a health report to your Telegram. If nothing is wrong, you get `[SILENT]` — no spam.

**If the user doesn't use Telegram**, adapt the `--deliver` flag to their messaging platform (discord, slack, etc.).

**If cron jobs are not supported**, set up a system crontab instead:
```bash
# Add to crontab: runs drift detection nightly at 4 AM
(crontab -l 2>/dev/null; echo "0 4 * * * cd ~/.hermes/hermes-nexus-memory && python3 -c \"from nexus.health import DriftDetector; r=DriftDetector().run(); print(r.summary)\"") | crontab -
```

### Step 6: Restart Gateway

**IMPORTANT:** Run this from a terminal, NOT from inside an agent chat session.

```bash
hermes gateway restart
```

If you are an agent running inside a gateway session, inform the user:
> "Please restart the gateway from your terminal: `hermes gateway restart`"

### Step 7: Verify

```bash
# Check Nexus tools are available
hermes status | grep -i nexus

# Test memory save and retrieve
# In the next agent session, try:
# nexus_remember(content="Nexus Memory v1.8.0 installed successfully", category="fact", tier=2)
# nexus_remember(content="Primary API key goes in .env", category="config", tier=3)
# nexus_search(query="installed successfully", limit=1)

# Note: v2.0.0 introduces SkillGraph — Edge Store + Graph Query Layer for fact relationships.
# - nexus/graph/ module: add_edge(), get_related(), get_path() via BFS/DFS
# - SQLite-backed with NetworkX in-memory cache, incremental updates
# Note: v1.9.0 introduces Skill Export — turn canonical facts into SKILL.md files.
# - Run: nexus-export --list (see exportable topics)
# - Run: nexus-export --skill topic-name --deploy (write to ~/.hermes/skills/)
# - Run: from nexus.export import export_skill, search_knowledge, list_topics
# - Set tier=2 or tier=3 for important memories (default T1 = raw storage)
# - Expiry policies: static / normal (90d) / volatile (7d) — set via expiry_policy in payload
```

### Step 8: Report to User

After installation, report:

```
✅ Nexus Memory v2.0.0 installed

• Embedding: <provider chosen>
• Hybrid Retrieval: <installed/skipped>
• Drift Detection: <cron set up / manual only>
• Memory Expiry: ✅ active (policies: static/normal/volatile)
• Skill Export: ✅ available (nexus-export CLI)
• Qdrant: running on localhost:6333
• Auto-Update: ✅ I'll check for new versions at startup

Tools available: nexus_search, nexus_remember, nexus_forget
```

### Step 9: Auto-Update Check (Hassle-Free)

The bot checks for new releases on **every session start** automatically.
If one is found, it tells the user — no watch, no email, nothing manual needed.

The check runs automatically via the code in **Step 0** above. When a new release
appears, the user sees:

> 📢 New version v2.0.0 available (you have v1.9.0). Update by saying: upgrade nexus memory

The bot then performs the upgrade on its own (Step 2b). No manual intervention needed.

---

## Troubleshooting for Agents

| Problem | Check | Fix |
|---------|-------|-----|
| `nexus` tools missing after restart | `hermes status` shows nexus? | `hermes config set memory.provider nexus` then restart |
| Qdrant connection refused | `curl http://127.0.0.1:6333/healthz` | Start Qdrant (see Step 1) |
| Embedding error in logs | `grep "Nexus memory" ~/.hermes/logs/agent.log` | Switch provider (Step 3) |
| `bm25s` import error | `pip list \| grep bm25s` | `pip install bm25s` |
| Hybrid not activating | Check `nexus.retrieval` imports | bm25s must be installed |

**Upgrade from v1.7.x → v2.0.0+:**
If you are upgrading an existing Nexus installation with real Qdrant data, legacy entries lack v1.8.0 lifecycle fields (`fact_id`, `status`, `content_hash`). The system handles them transparently via fallback (treats them as `canonical`). For optimal filtering and export accuracy, run the optional one-time migration:
```bash
python3 ~/.hermes/hermes-nexus-memory/scripts/migrate-lifecycle.py
```
This scrolls all points, adds lifecycle fields, and preserves existing payloads. Safe to run multiple times — skips already-migrated entries. Not required, but recommended for 200+ entry databases.

---

## What This Gives the User

- **Persistent memory** — your agent remembers across sessions
- **Hybrid search** — keyword + semantic = better results, poison-resistant
- **Drift detection** — stale + expired memories get flagged automatically
- **Memory expiry** — set policies: static (never), normal (90d), volatile (7d)
- **Tiered enrichment** — automatically tags important memories (T2/T3) for deeper analysis
- **Source tier boosting** — your own data ranks higher than random internet content
- **3 embedding backends** — from zero-config local to cloud-powered best quality

---

*Built for Hermes Agent. Works with any AI agent that can read and execute instructions.*