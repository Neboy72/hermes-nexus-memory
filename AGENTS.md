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

You are a Hermes Agent (or compatible). The user wants Nexus Memory installed. Execute these steps in order. Do NOT skip verification.

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

### Step 2: Install the Plugin

```bash
# Clone the repo
git clone https://github.com/Neboy72/hermes-nexus-memory.git ~/.hermes/hermes-nexus-memory

# Install into Hermes venv (if available)
if [ -d ~/.hermes/hermes-agent/venv ]; then
  source ~/.hermes/hermes-agent/venv/bin/activate
fi

pip install -e ~/.hermes/hermes-nexus-memory[all]
```

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

### Step 5: Drift Detection (Optional)

Set up a nightly cron job to detect stale memories:

```bash
hermes cron add \
  --name "Nexus Drift Detection" \
  --schedule "0 4 * * *" \
  --model none \
  --script "nexus/health/__init__.py" \
  --deliver telegram
```

Or if the user prefers a simpler approach:
```bash
# Just run it manually anytime:
python3 -c "from nexus.health import DriftDetector; d=DriftDetector(); r=d.run(); print(r.summary)"
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
# nexus_remember(content="Nexus Memory v1.1.0 installed successfully", category="fact")
# nexus_search(query="installed successfully", limit=1)
```

### Step 8: Report to User

After installation, report:

```
✅ Nexus Memory v1.1.0 installed

• Embedding: <provider chosen>
• Hybrid Retrieval: <installed/skipped>
• Drift Detection: <cron set up / manual only>
• Qdrant: running on localhost:6333

Tools available: nexus_search, nexus_remember, nexus_forget
```

---

## Troubleshooting for Agents

| Problem | Check | Fix |
|---------|-------|-----|
| `nexus` tools missing after restart | `hermes status` shows nexus? | `hermes config set memory.provider nexus` then restart |
| Qdrant connection refused | `curl http://127.0.0.1:6333/healthz` | Start Qdrant (see Step 1) |
| Embedding error in logs | `grep "Nexus memory" ~/.hermes/logs/agent.log` | Switch provider (Step 3) |
| `bm25s` import error | `pip list \| grep bm25s` | `pip install bm25s` |
| Hybrid not activating | Check `nexus.retrieval` imports | bm25s must be installed |

---

## What This Gives the User

- **Persistent memory** — your agent remembers across sessions
- **Hybrid search** — keyword + semantic = better results, poison-resistant
- **Drift detection** — stale memories get flagged automatically
- **Source tier boosting** — your own data ranks higher than random internet content
- **3 embedding backends** — from zero-config local to cloud-powered best quality

---

*Built for Hermes Agent. Works with any AI agent that can read and execute instructions.*