#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────────────────────────────
# Nexus Memory — Cron Job Setup
# ──────────────────────────────────────────────────────────────────────
# Sets up maintenance cron jobs for Nexus Memory:
#   1. Drift Detection (04:00) — veraltete Fakten erkennen
#   2. SICA Self-Improvement (05:00) — low-confidence Beliefs analysieren
#   3. Session-to-Memory Export (23:00) — Sessions nach Nexus exportieren
#
# Requires: hermes CLI (Hermes Agent) — skips if not found.
# ──────────────────────────────────────────────────────────────────────

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}ℹ${NC}  $1"; }
ok()    { echo -e "${GREEN}✓${NC}  $1"; }
warn()  { echo -e "${YELLOW}⚠${NC}  $1"; }

echo ""
echo -e "${BLUE}══════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Nexus Memory — Maintenance Cron Setup${NC}"
echo -e "${BLUE}══════════════════════════════════════════════${NC}"
echo ""

# ── Prerequisites ──────────────────────────────────────────────────────

if ! command -v hermes &>/dev/null; then
    warn "hermes CLI not found — skipping cron setup."
    echo "  Install Hermes Agent first, then run this script again."
    echo "  Or manually run the Python scripts in ${REPO_DIR}/examples/"
    exit 0
fi

info "hermes CLI found — setting up maintenance jobs."

# Copy analyzer scripts
SCRIPTS_DIR="${HOME}/.hermes/scripts"
mkdir -p "${SCRIPTS_DIR}"

if [ -f "${REPO_DIR}/examples/nexus-sica-analyzer.py" ]; then
    cp "${REPO_DIR}/examples/nexus-sica-analyzer.py" "${SCRIPTS_DIR}/"
    ok "SICA analyzer → ${SCRIPTS_DIR}/nexus-sica-analyzer.py"
fi

# ── Helper: create job if not exists ───────────────────────────────────

job_exists() {
    hermes cron list 2>/dev/null | grep -q "$1"
}

create_job() {
    local name="$1"
    shift
    if job_exists "$name"; then
        ok "Job '$name' already exists — skipping."
        return 0
    fi
    hermes cron create --name "$name" "$@" 2>&1 | tail -1
    ok "Job '$name' created."
}

# ── 1: Drift Detection ─────────────────────────────────────────────────
echo ""
echo -e "${BLUE}── Step 1: Drift Detection ─────────────────────${NC}"

# Nach vorhandenem Job suchen — es könnte einen mit leicht anderem Namen geben
EXISTING_DRIFT=$(hermes cron list 2>/dev/null | grep -i "drift" || echo "")
if [ -n "$EXISTING_DRIFT" ]; then
    ok "Drift detection job already exists — skipping."
else
    hermes cron create \
        --name "Nexus Drift Detection" \
        --schedule "0 4 * * *" \
        --no-agent \
        --script "nexus/health/__init__.py" \
        --deliver origin 2>&1 | tail -1
    ok "Drift Detection created (04:00 daily)."
fi

# ── 2: SICA Self-Improvement ───────────────────────────────────────────
echo ""
echo -e "${BLUE}── Step 2: Self-Improvement Cycle (SICA) ────────${NC}"

EXISTING_SICA=$(hermes cron list 2>/dev/null | grep -i "sica\|self-improvement" || echo "")
if [ -n "$EXISTING_SICA" ]; then
    ok "SICA job already exists — skipping."
else
    hermes cron create \
        --name "SICA Self-Improvement" \
        --schedule "0 5 * * *" \
        --no-agent \
        --script "nexus-sica-analyzer.py" \
        --deliver origin 2>&1 | tail -1
    ok "SICA Self-Improvement created (05:00 daily)."
fi

# ── 3: Session-to-Memory Export ────────────────────────────────────────
echo ""
echo -e "${BLUE}── Step 3: Session-to-Memory Export ─────────────${NC}"

EXISTING_SESSION=$(hermes cron list 2>/dev/null | grep -i "session.*export\|session.*memory" || echo "")
if [ -n "$EXISTING_SESSION" ]; then
    ok "Session Export job already exists — skipping."
else
    warn "Session Export requires an LLM-based cron job (agent, not no_agent)."
    warn "Skipping automated setup — add manually if needed:"
    echo ""
    echo "  hermes cron create \\"
    echo "    --name \"Session-to-Memory Export\" \\"
    echo "    --schedule \"0 23 * * *\" \\"
    echo "    --prompt \"Extract facts from recent sessions...\" \\"
    echo "    --deliver local"
fi

# ── Done ───────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}══════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Cron Setup Complete!${NC}"
echo -e "${GREEN}══════════════════════════════════════════════${NC}"
echo ""
echo "  Active jobs at 04:00, 05:00 — fully automatic."
echo "  Silent when healthy — reports only on issues."
echo ""
