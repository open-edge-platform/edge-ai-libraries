#!/usr/bin/env bash
# End-to-end observability test for the OpenShell harnesses, per agent:
#   install sandbox -> baseline chat -> enable telemetry -> chat -> read telemetry
#   -> disable (--clean) -> uninstall sandbox.
# Runs against an isolated environment file (default ~/ahi-e2e.env), never the default state dir.
# The file must set HARNESS_STATE_DIRNAME (not .agent-harness-install) and SRC (the agent-harness-install
# checkout), plus its own container names, ports and HARNESS_IR_WORKSPACE_DIR so a live deployment is untouched.
#
# Usage: otel-openshell-e2e.sh [--harness hermes,openclaw]
#                              [--backend sqlite,jaeger] [--skip-install] [--keep]
#                              [--full-uninstall] [--env-file FILE]
#   --skip-install    reuse an already installed sandbox
#   --keep            leave the sandbox installed at the end
#   --full-uninstall  also run the full isolated uninstall (router, OVMS, models, state)
# Env: MODEL, CHAT_TIMEOUT (s, default 400), SETTLE (s to wait for spans, default 40), LOG_DIR
set -uo pipefail

ENV_FILE="${ENV_FILE:-$HOME/ahi-e2e.env}"
HARNESSES="hermes,openclaw"
BACKENDS="sqlite,jaeger"
MODEL="${MODEL:-OpenVINO/Qwen3.5-9B-int8-ov}"
CHAT_TIMEOUT="${CHAT_TIMEOUT:-400}"
SETTLE="${SETTLE:-40}"
SKIP_INSTALL=0 KEEP=0 FULL_UNINSTALL=0

die() { printf 'ERROR: %s\n' "$*" >&2; exit 2; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --harness) HARNESSES="${2:?--harness needs a value}"; shift 2 ;;
    --backend) BACKENDS="${2:?--backend needs a value}"; shift 2 ;;
    --env-file) ENV_FILE="${2:?--env-file needs a value}"; shift 2 ;;
    --skip-install) SKIP_INSTALL=1; shift ;;
    --keep) KEEP=1; shift ;;
    --full-uninstall) FULL_UNINSTALL=1; shift ;;
    -h | --help) sed -n '2,14p' "$0"; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

[[ -f "$ENV_FILE" ]] || die "missing $ENV_FILE (set ENV_FILE or pass --env-file)"
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
[[ -n "${HARNESS_STATE_DIRNAME:-}" && "$HARNESS_STATE_DIRNAME" != .agent-harness-install ]] \
  || die "refusing to run without an isolated HARNESS_STATE_DIRNAME (would touch the live deployment)"
[[ -d "${SRC:-}" ]] || die "SRC is not a directory: ${SRC:-unset}"
for tool in node python3 curl openshell docker; do command -v "$tool" >/dev/null || die "$tool not found on PATH"; done

STATE="$HOME/$HARNESS_STATE_DIRNAME"
LOG_DIR="${LOG_DIR:-$HOME/otel-e2e-logs/$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$LOG_DIR"
cd "$SRC" || die "cannot cd to $SRC"

RESULTS=() FAILS=0 AGENT="" SB_NAME="" SB_GW="" LAST_LOG=""

step() { printf '\n== %s\n' "$*"; }
record() {
  RESULTS+=("$1|$AGENT|$2")
  [[ "$1" == PASS ]] || FAILS=$((FAILS + 1))
  printf '  [%s] %s\n' "$1" "$2"
}
# run <name> <cmd...> -- output goes to a per-agent log; the log path is kept in LAST_LOG.
run() {
  local name="$1"
  shift
  LAST_LOG="$LOG_DIR/${AGENT}-${name}.log"
  "$@" >"$LAST_LOG" 2>&1
}
fail_tail() { tail -n 12 "$LAST_LOG" 2>/dev/null | cut -c1-200 | sed 's/^/        /'; }

profile_field() {
  node -e 'const p=JSON.parse(require("fs").readFileSync(process.argv[1],"utf8"));console.log(p[process.argv[2]])' \
    "$STATE/openshell/$AGENT/profile.json" "$1"
}
load_sandbox() {
  SB_NAME="$(profile_field name)" && SB_GW="$(profile_field gateway)" && [[ -n "$SB_NAME" && -n "$SB_GW" ]]
}
sx() { openshell sandbox exec --name "$SB_NAME" --no-login-shell -g "$SB_GW" -- "$@"; }

service_name() {
  case "$AGENT" in hermes) echo hermes-agent ;; openclaw) echo openclaw ;; esac
}
store_path() {
  case "$AGENT" in
    hermes) echo "$STATE/openshell-telemetry/hermes_otel_live.db" ;;
    openclaw) echo "$STATE/openshell-telemetry/openclaw_otel_live.db" ;;
  esac
}

obs() { bash ./install.sh observability "$@" --harness "$AGENT" --runtime openshell; }
rule_present() { openshell policy get "$SB_NAME" -g "$SB_GW" --full 2>/dev/null | grep -Eq '^[[:space:]]*harness_otel:'; }

# chat_once <marker> -- one non-interactive turn; output in $LAST_LOG.
chat_once() {
  local mk="$1"
  LAST_LOG="$LOG_DIR/${AGENT}-chat-${mk}.log"
  case "$AGENT" in
    hermes)
      timeout "$CHAT_TIMEOUT" openshell sandbox exec --name "$SB_NAME" --no-login-shell -g "$SB_GW" -- \
        /home/node/.local/bin/hermes -z "Reply with exactly: ${mk}" >"$LAST_LOG" 2>&1 ;;
    openclaw)
      timeout "$CHAT_TIMEOUT" openshell sandbox exec --name "$SB_NAME" --no-login-shell -g "$SB_GW" -- \
        /home/node/.local/bin/openclaw agent --agent main --message "Say hello. ${mk}" --json >"$LAST_LOG" 2>&1 ;;
  esac
}
# chat <marker> -- OpenClaw can refuse for ~15 s after its sandbox restarts, so it is retried.
chat() {
  local attempts=1 n
  [[ "$AGENT" != openclaw ]] || attempts=4
  for ((n = 1; n <= attempts; n++)); do
    if chat_once "$1" && [[ -s "$LAST_LOG" ]]; then return 0; fi
    ((n == attempts)) || sleep 15
  done
  return 1
}

store_stats() { # -> "<spans> <spans containing marker>"
  python3 - "$(store_path)" "$1" <<'PY'
import os, sqlite3, sys
path, marker = sys.argv[1:3]
if not os.path.exists(path):
    print("0 0")
    sys.exit()
try:
    con = sqlite3.connect("file:%s?mode=ro" % path, uri=True, timeout=5)
    total = con.execute("select count(*) from events where kind='span'").fetchone()[0]
    hits = con.execute("select count(*) from events where kind='span' and data like ?", ("%" + marker + "%",)).fetchone()[0]
    print(total, hits)
except Exception:
    print("0 0")
PY
}
jaeger_hits() { # -> number of Jaeger responses lines containing the marker
  curl --noproxy '*' -sf --max-time 10 \
    "http://127.0.0.1:${HARNESS_JAEGER_UI_PORT}/api/traces?service=$(service_name)&limit=50&lookback=1h" 2>/dev/null \
    | grep -o "$1" | wc -l
}

# wait_for_marker <backend> <marker> -- polls until the marker shows up in the backend.
wait_for_marker() {
  local backend="$1" mk="$2" waited=0 spans=0 hits=0
  while ((waited <= SETTLE)); do
    if [[ "$backend" == sqlite ]]; then
      read -r spans hits < <(store_stats "$mk")
    else
      hits="$(jaeger_hits "$mk")"
      spans="$hits"
    fi
    ((hits > 0)) && break
    sleep 5
    waited=$((waited + 5))
  done
  WAIT_SPANS="$spans" WAIT_HITS="$hits"
  ((hits > 0))
}

test_agent() {
  local backend mk
  AGENT="$1"
  step "Harness: $AGENT"

  # 1. install the agent in an OpenShell sandbox
  if ((SKIP_INSTALL)) && [[ -f "$STATE/openshell/$AGENT/profile.json" ]]; then
    record PASS "install skipped (sandbox profile exists)"
  elif run install bash ./install.sh --runtime openshell --harness "$AGENT" --model "$MODEL" --non-interactive; then
    record PASS "install in OpenShell sandbox"
  else
    record FAIL "install in OpenShell sandbox (log: $LAST_LOG)"
    fail_tail
    return
  fi
  if ! load_sandbox; then record FAIL "read sandbox profile"; return; fi
  if run status bash ./install.sh status --runtime openshell --harness "$AGENT"; then
    record PASS "sandbox status ($SB_NAME)"
  else
    record FAIL "sandbox status (log: $LAST_LOG)"
  fi
  if rule_present; then record FAIL "no harness_otel rule before enable"; else record PASS "no harness_otel rule before enable"; fi

  # 2. baseline chat, telemetry off
  mk="base$(date +%s)"
  if chat "$mk"; then record PASS "baseline chat"; else record FAIL "baseline chat (log: $LAST_LOG)"; fail_tail; fi

  for backend in ${BACKENDS//,/ }; do
    # 3. enable telemetry, chat with a unique marker, read it back
    if run "enable-$backend" obs enable --backend "$backend" --content full; then
      record PASS "enable telemetry ($backend)"
    else
      record FAIL "enable telemetry ($backend) (log: $LAST_LOG)"
      fail_tail
      continue
    fi
    if rule_present; then record PASS "harness_otel egress rule present ($backend)"; else record FAIL "harness_otel egress rule present ($backend)"; fi
    mk="otelmk${AGENT//-/}${backend}${RANDOM}${RANDOM}"
    if chat "$mk"; then
      record PASS "chat with telemetry ($backend)"
    else
      record FAIL "chat with telemetry ($backend) (log: $LAST_LOG)"
      fail_tail
      continue
    fi
    if wait_for_marker "$backend" "$mk"; then
      record PASS "telemetry captured, marker found ($backend; spans=$WAIT_SPANS, marker hits=$WAIT_HITS)"
    else
      record FAIL "telemetry captured, marker found ($backend; spans=$WAIT_SPANS, marker hits=$WAIT_HITS)"
    fi
    if run "show-$backend" obs show; then record PASS "observability show ($backend)"; else record FAIL "observability show ($backend) (log: $LAST_LOG)"; fi
  done

  # 4. disable and uninstall
  if run disable obs disable --clean; then record PASS "disable telemetry --clean"; else record FAIL "disable telemetry --clean (log: $LAST_LOG)"; fail_tail; fi
  if rule_present; then record FAIL "harness_otel rule removed after disable"; else record PASS "harness_otel rule removed after disable"; fi
  if ((KEEP)); then
    record PASS "uninstall skipped (--keep)"
  elif run uninstall bash ./uninstall.sh --runtime openshell --harness "$AGENT" --sandbox-only --yes; then
    record PASS "uninstall sandbox"
  else
    record FAIL "uninstall sandbox (log: $LAST_LOG)"
    fail_tail
  fi
}

printf 'Source : %s\nState  : %s\nLogs   : %s\nAgents : %s\nBackend: %s\n' "$SRC" "$STATE" "$LOG_DIR" "$HARNESSES" "$BACKENDS"

for agent in ${HARNESSES//,/ }; do
  case "$agent" in
    hermes | openclaw) test_agent "$agent" ;;
    *) die "unsupported harness: $agent" ;;
  esac
done

if ((FULL_UNINSTALL)); then
  AGENT=all
  step "Full isolated uninstall"
  if run uninstall-all bash ./uninstall.sh --runtime openshell --yes; then
    record PASS "full isolated uninstall"
  else
    record FAIL "full isolated uninstall (log: $LAST_LOG)"
    fail_tail
  fi
fi

step "Summary"
for r in "${RESULTS[@]}"; do IFS='|' read -r status agent name <<<"$r"; printf '%-5s %-16s %s\n' "$status" "$agent" "$name"; done
printf '\n%d check(s) failed. Logs: %s\n' "$FAILS" "$LOG_DIR"
((FAILS == 0))
