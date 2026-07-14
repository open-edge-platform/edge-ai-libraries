#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# VIPPET Benchmark Suite — single entry point.
# Assumes VIPPET is already running (make vippet-up from the handheld-multi-modal dir).
#
# Usage:
#   ./run.sh               # full benchmark, all pipelines / all variants / 1,3,5,10 streams
#   ./run.sh --quick       # CPU+GPU only, 1 and 3 streams
#   ./run.sh --dry-run     # show test matrix without running
#   ./run.sh --variants cpu,gpu --streams 1,3
#   ./run.sh --pipelines motion-detection,object-detection
#   ./run.sh --report-only results/bench_20260701_015223/bench_20260701_015223.json

set -euo pipefail
SUITE_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}[bench]${NC} $*"; }
success() { echo -e "${GREEN}[bench]${NC} $*"; }
warn()    { echo -e "${YELLOW}[bench]${NC} $*"; }
error()   { echo -e "${RED}[bench]${NC} $*" >&2; }

# ── report-only shortcut ──────────────────────────────────────────────────────
if [[ "${1:-}" == "--report-only" ]]; then
    shift
    JSON="${1:?Usage: ./run.sh --report-only <result.json>}"
    HTML="${JSON%.json}.html"
    info "Generating HTML report from $JSON ..."
    python3 "$SUITE_DIR/scripts/generate_report.py" "$JSON" -o "$HTML"
    success "Report: $HTML"
    exit 0
fi

# ── check Python deps ─────────────────────────────────────────────────────────
info "Checking Python dependencies..."
if ! python3 -c "import httpx, yaml" 2>/dev/null; then
    warn "Installing missing dependencies..."
    pip3 install -q -r "$SUITE_DIR/requirements.txt"
fi

# ── check VIPPET is reachable ─────────────────────────────────────────────────
VIPPET_BASE_URL="${VIPPET_BASE_URL:-http://localhost:7860/api/v1}"
info "Checking VIPPET at $VIPPET_BASE_URL ..."
TRIES=0
until curl -sf "$VIPPET_BASE_URL/health" | grep -q '"healthy":true'; do
    TRIES=$((TRIES+1))
    if [[ $TRIES -ge 12 ]]; then
        error "VIPPET is not reachable at $VIPPET_BASE_URL after 60s."
        error "Start it first:"
        error "  cd /path/to/vippet-fedaero/tools/visual-pipeline-and-platform-evaluation-tool"
        error "  . .env && docker compose -f compose.yml -f compose.npu.yml up -d"
        exit 1
    fi
    warn "VIPPET not ready yet, retrying in 5s... ($TRIES/12)"
    sleep 5
done
success "VIPPET is up."

# ── check VIPPET has finished initialising ────────────────────────────────────
info "Waiting for VIPPET to finish initialising..."
TRIES=0
until curl -sf "$VIPPET_BASE_URL/devices" | grep -q "device_family"; do
    TRIES=$((TRIES+1))
    if [[ $TRIES -ge 24 ]]; then
        error "VIPPET still initialising after 2 min — check docker logs vippet"
        exit 1
    fi
    echo -n "."
    sleep 5
done
echo ""
success "VIPPET ready."

# ── run benchmark ─────────────────────────────────────────────────────────────
info "Starting benchmark..."
cd "$SUITE_DIR"
python3 scripts/benchmark.py \
    --config config/default.yaml \
    --vippet-url "$VIPPET_BASE_URL" \
    "$@"

# ── open report ───────────────────────────────────────────────────────────────
LATEST_HTML="$(ls -t results/*/**.html 2>/dev/null | head -1 || true)"
if [[ -n "$LATEST_HTML" ]]; then
    success "HTML report: $SUITE_DIR/$LATEST_HTML"
    if command -v xdg-open &>/dev/null; then
        xdg-open "$SUITE_DIR/$LATEST_HTML" &>/dev/null &
    fi
fi
