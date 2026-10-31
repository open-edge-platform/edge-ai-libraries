# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=bash
# `./install.sh metrics <enable|disable|show>` -- one switch for telemetry
# collection across the blocks of a deployment:
#
#   harness  Hermes, through the hermes-otel plugin. Spans/metrics per turn go
#            to the plugin's local SQLite store and, optionally, to an OTLP
#            backend (Jaeger). OpenClaw and Deep Agents Code have no such
#            plugin; OpenShell sandboxes cannot install it (no egress).
#   router   Inference Router. It cannot export OTLP; its telemetry backend is
#            either "memory" (default, lost on restart) or "file" (JSONL in its
#            workspace). Both are readable through its /v1/metrics endpoint.
#
# Chosen settings are kept in ~/.agent-harness-install/metrics.json so that a
# later install (which regenerates the Router's config.yaml) preserves them.

HARNESS_JAEGER_IMAGE="${HARNESS_JAEGER_IMAGE:-jaegertracing/all-in-one:1.76.0}"
HARNESS_JAEGER_CONTAINER="${HARNESS_JAEGER_CONTAINER:-agent-harness-install-jaeger}"
HARNESS_JAEGER_UI_PORT="${HARNESS_JAEGER_UI_PORT:-16686}"
HARNESS_JAEGER_OTLP_PORT="${HARNESS_JAEGER_OTLP_PORT:-4318}"
# Plugin source handed to `hermes plugins install`. The bare catalog name makes
# Hermes install the commit pinned in its reviewed plugin catalog (and apply
# its removal kill-list); override with an explicit <owner>/<repo>/<plugin>
# reference to use a different source. HARNESS_HERMES_OTEL_REF additionally
# pins any source to an exact 40-character commit SHA (`--ref`).
HARNESS_HERMES_OTEL_PLUGIN="${HARNESS_HERMES_OTEL_PLUGIN:-hermes_otel}"
HARNESS_HERMES_OTEL_REF="${HARNESS_HERMES_OTEL_REF:-}"
# The Router's JSONL file is rotated to telemetry.jsonl.1 (one generation) when
# the installer next prepares it and it is larger than this many bytes; 0 turns
# rotation off. The Router re-reads the whole file for every /v1/metrics call.
HARNESS_IR_TELEMETRY_MAX_BYTES="${HARNESS_IR_TELEMETRY_MAX_BYTES:-20971520}"
# Mode of that file. 664 lets only the owner and the host user's primary group
# write it (the Router container joins that group, see metrics_router_file_group);
# 666 is the fallback for rootless Docker or user-namespace remapping, where
# container group ids do not match host ones.
HARNESS_IR_TELEMETRY_FILE_MODE="${HARNESS_IR_TELEMETRY_FILE_MODE:-664}"

METRICS_CONFIG_MARKER="# Managed by agent-harness-install (metrics)"
METRICS_ROUTER_JSONL_NAME="telemetry.jsonl"
# Plain http(s) URL, no userinfo/query/quotes: the value is written into YAML.
# The host is a name, an IPv4 address or a bracketed IPv6 literal.
METRICS_ENDPOINT_RE='^https?://([A-Za-z0-9._-]+|\[[0-9A-Fa-f:]+\])(:[0-9]{1,5})?(/[A-Za-z0-9._~%/-]*)?$'

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

metrics_state_file() {
  printf '%s/metrics.json' "$(harness_state_root)"
}

# metrics_state_get <dotted.key> -- prints the value ("true"/"false" for
# booleans), or nothing when the file/key is absent or unreadable.
metrics_state_get() {
  local file
  file="$(metrics_state_file)"
  [[ -f "$file" && ! -L "$file" ]] || return 0
  node -e '
    const fs = require("node:fs");
    let s = {};
    try { s = JSON.parse(fs.readFileSync(process.argv[1], "utf8")); } catch { process.exit(0); }
    const v = process.argv[2].split(".").reduce((o, k) => (o == null ? o : o[k]), s);
    if (v != null && typeof v !== "object") console.log(String(v));
  ' "$file" "$1" 2>/dev/null || true
}

# metrics_state_set <dotted.key> <value> [<key> <value>]... -- keys are fixed
# strings from this file; "true"/"false" are stored as JSON booleans.
metrics_state_set() {
  local file new
  file="$(metrics_state_file)"
  ensure_state_dir >/dev/null
  assert_state_path_safe "$file"
  assert_owned_by_current_user "$file"
  new="$(node - "$file" "$@" <<'JS'
const fs = require("node:fs");
const [file, ...kv] = process.argv.slice(2);
let s = {};
try { s = JSON.parse(fs.readFileSync(file, "utf8")); } catch {}
if (typeof s !== "object" || s === null || Array.isArray(s)) s = {};
for (let i = 0; i < kv.length; i += 2) {
  const path = kv[i].split(".");
  let v = kv[i + 1];
  if (v === "true") v = true; else if (v === "false") v = false;
  let o = s;
  for (const k of path.slice(0, -1)) {
    if (typeof o[k] !== "object" || o[k] === null) o[k] = {};
    o = o[k];
  }
  o[path[path.length - 1]] = v;
}
console.log(JSON.stringify(s, null, 2));
JS
  )" || error "Could not update the metrics state."
  atomic_write_file "$file" "$new"
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

# Sets M_TARGET/M_BACKEND/M_ENDPOINT/M_CONTENT (enable) and M_CLEAN/
# M_KEEP_JAEGER (disable). Flags are parsed here (not in main) because main
# passes unknown tokens through as positionals.
metrics_parse_args() {
  local verb="$1" flag value seen=" "
  shift
  M_TARGET=all M_BACKEND="" M_ENDPOINT="" M_CONTENT="" M_BACKEND_GIVEN="" M_CONTENT_GIVEN=""
  M_CLEAN="" M_KEEP_JAEGER=""
  while [[ $# -gt 0 ]]; do
    flag="$1"
    case "$flag" in
      --clean | --keep-jaeger)
        [[ "$verb" == disable ]] || error "${flag} is only valid with 'metrics disable'."
        if [[ "$flag" == --clean ]]; then M_CLEAN=1; else M_KEEP_JAEGER=1; fi
        shift
        continue ;;
      --*=*)
        value="${flag#*=}"; flag="${flag%%=*}"; shift ;;
      --*)
        [[ $# -ge 2 && "$2" != --* ]] || error "${flag} requires a value."
        value="$2"; shift 2 ;;
      *) error "Unexpected argument for 'metrics ${verb}': ${flag}" ;;
    esac
    [[ "$seen" != *" ${flag} "* ]] || error "${flag} was given more than once."
    seen+="${flag} "
    case "$flag" in
      --target) M_TARGET="$value" ;;
      --backend | --endpoint | --content)
        [[ "$verb" == enable ]] || error "${flag} is only valid with 'metrics enable'."
        case "$flag" in
          --backend) M_BACKEND="$value" ;;
          --endpoint) M_ENDPOINT="$value" ;;
          --content) M_CONTENT="$value" ;;
        esac ;;
      *) error "Unknown option for 'metrics ${verb}': ${flag}" ;;
    esac
  done
  case "$M_TARGET" in
    harness | router | all) ;;
    *) error "--target must be harness, router or all (got '${M_TARGET}')." ;;
  esac
  if [[ -n "$M_CLEAN" && -n "$M_KEEP_JAEGER" ]]; then
    error "--clean and --keep-jaeger conflict: cleaning removes the managed Jaeger and its traces."
  fi
  if [[ -n "$M_KEEP_JAEGER" && "$M_TARGET" == router ]]; then
    error "--keep-jaeger applies to the harness; use --target harness or --target all."
  fi
  [[ "$verb" == enable ]] || return 0
  if [[ "$M_TARGET" == router && ( -n "$M_BACKEND" || -n "$M_ENDPOINT" || -n "$M_CONTENT" ) ]]; then
    error "--backend/--endpoint/--content apply to the harness; use --target harness or --target all."
  fi
  # Omitted flags keep the saved harness settings (see metrics_enable_harness).
  M_BACKEND_GIVEN="$M_BACKEND" M_CONTENT_GIVEN="$M_CONTENT"
  M_BACKEND="${M_BACKEND:-sqlite}"
  M_CONTENT="${M_CONTENT:-off}"
  case "$M_BACKEND" in
    sqlite | jaeger | otlp) ;;
    *) error "--backend must be sqlite, jaeger or otlp (got '${M_BACKEND}')." ;;
  esac
  case "$M_CONTENT" in
    off | preview | full) ;;
    *) error "--content must be off, preview or full (got '${M_CONTENT}')." ;;
  esac
  if [[ "$M_BACKEND" == sqlite && -n "$M_ENDPOINT" ]]; then
    error "--endpoint cannot be combined with --backend sqlite (nothing is exported)."
  fi
  if [[ "$M_BACKEND" == otlp && -z "$M_ENDPOINT" ]]; then
    error "--backend otlp requires --endpoint <http(s)://host:port/v1/traces>."
  fi
  if [[ -n "$M_ENDPOINT" ]]; then
    # No userinfo, query or quotes: the value is written into YAML and shown
    # in output, and credentials must not travel in argv or config files.
    [[ "$M_ENDPOINT" =~ $METRICS_ENDPOINT_RE ]] \
      || error "--endpoint must be a plain http(s) URL without credentials or query string (got '${M_ENDPOINT}')."
    local authority="${M_ENDPOINT#*://}"
    authority="${authority%%/*}"
    if [[ "$authority" =~ :([0-9]+)$ ]] && (( 10#${BASH_REMATCH[1]} < 1 || 10#${BASH_REMATCH[1]} > 65535 )); then
      error "--endpoint port must be between 1 and 65535 (got '${M_ENDPOINT}')."
    fi
  fi
}

# ---------------------------------------------------------------------------
# Managed Jaeger (harness --backend jaeger without --endpoint)
# ---------------------------------------------------------------------------

metrics_validate_jaeger_ports() {
  local port
  for port in "$HARNESS_JAEGER_UI_PORT" "$HARNESS_JAEGER_OTLP_PORT"; do
    [[ "$port" =~ ^[0-9]+$ ]] && (( port > 0 && port < 65536 )) \
      || error "Jaeger ports must be between 1 and 65535 (got '${port}')."
  done
}

# An existing container keeps the ports it was created with.
metrics_check_jaeger_ports() {
  local container_port host_port published
  for container_port in 16686:"$HARNESS_JAEGER_UI_PORT" 4318:"$HARNESS_JAEGER_OTLP_PORT"; do
    host_port="${container_port#*:}"
    published="$(docker port "$HARNESS_JAEGER_CONTAINER" "${container_port%%:*}/tcp" 2>/dev/null || true)"
    [[ "$published" == *":${host_port}"* ]] \
      || error "Existing container ${HARNESS_JAEGER_CONTAINER} does not publish port ${host_port}; remove it (docker rm -f ${HARNESS_JAEGER_CONTAINER}) or set HARNESS_JAEGER_UI_PORT/HARNESS_JAEGER_OTLP_PORT to match."
  done
}

metrics_ensure_jaeger() {
  command_exists docker || error "Docker is required to run the managed Jaeger container.
Pass --endpoint to use an existing Jaeger/OTLP collector instead."
  metrics_validate_jaeger_ports
  if docker inspect "$HARNESS_JAEGER_CONTAINER" >/dev/null 2>&1; then
    metrics_check_jaeger_ports
    if [[ "$(docker inspect -f '{{.State.Running}}' "$HARNESS_JAEGER_CONTAINER" 2>/dev/null)" != true ]]; then
      docker start "$HARNESS_JAEGER_CONTAINER" >/dev/null \
        || error "Could not start the existing Jaeger container ${HARNESS_JAEGER_CONTAINER}."
    fi
    ok "Jaeger is running (${HARNESS_JAEGER_CONTAINER})"
    return 0
  fi
  if ! docker image inspect "$HARNESS_JAEGER_IMAGE" >/dev/null 2>&1; then
    spin "Pulling Jaeger image ${HARNESS_JAEGER_IMAGE}" docker pull "$HARNESS_JAEGER_IMAGE" \
      || error "Could not pull ${HARNESS_JAEGER_IMAGE} -- check network access and Docker Hub rate limits."
  fi
  # Published on loopback only: traces can contain prompts/tool arguments.
  docker run -d --name "$HARNESS_JAEGER_CONTAINER" --restart unless-stopped \
    -p "127.0.0.1:${HARNESS_JAEGER_UI_PORT}:16686" \
    -p "127.0.0.1:${HARNESS_JAEGER_OTLP_PORT}:4318" \
    -e COLLECTOR_OTLP_ENABLED=true \
    "$HARNESS_JAEGER_IMAGE" >/dev/null \
    || error "Could not start Jaeger -- a common cause is port ${HARNESS_JAEGER_UI_PORT} or ${HARNESS_JAEGER_OTLP_PORT} already in use."
  ok "Jaeger started: UI http://127.0.0.1:${HARNESS_JAEGER_UI_PORT}, OTLP http://127.0.0.1:${HARNESS_JAEGER_OTLP_PORT}/v1/traces"
}

metrics_remove_jaeger() {
  command_exists docker || return 0
  if docker inspect "$HARNESS_JAEGER_CONTAINER" >/dev/null 2>&1; then
    docker rm -f "$HARNESS_JAEGER_CONTAINER" >/dev/null \
      || error "Could not remove the Jaeger container ${HARNESS_JAEGER_CONTAINER}."
    ok "Jaeger container removed"
  fi
}

# ---------------------------------------------------------------------------
# Harness (Hermes + hermes-otel)
# ---------------------------------------------------------------------------

metrics_hermes_home() {
  printf '%s' "${HERMES_HOME:-$HOME/.hermes}"
}

# Sets M_AGENT; on failure sets M_SKIP_REASON and returns 1.
metrics_harness_check() {
  M_AGENT="$(resolve_installed_agent)"
  M_SKIP_REASON=""
  if [[ "$M_AGENT" != hermes ]]; then
    M_SKIP_REASON="harness telemetry needs the hermes-otel plugin, so only Hermes is supported (selected: ${M_AGENT})"
    return 1
  fi
  if [[ "${HARNESS_RUNTIME:-host}" == openshell ]]; then
    M_SKIP_REASON="OpenShell sandboxes have no network egress to fetch the plugin and its Python dependencies; the plugin must be baked into the sandbox image, which is not supported yet"
    return 1
  fi
  return 0
}

metrics_install_hermes_otel_plugin() {
  local home plugin_dir
  [[ "$HARNESS_HERMES_OTEL_PLUGIN" =~ ^[A-Za-z0-9_][A-Za-z0-9._-]*(/[A-Za-z0-9_][A-Za-z0-9._-]*){0,2}$ ]] \
    || error "HARNESS_HERMES_OTEL_PLUGIN must be a plugin name or <owner>/<repo>[/<plugin>] (got '${HARNESS_HERMES_OTEL_PLUGIN}')."
  local -a ref_args=()
  if [[ -n "$HARNESS_HERMES_OTEL_REF" ]]; then
    [[ "$HARNESS_HERMES_OTEL_REF" =~ ^[0-9a-f]{40}$ ]] \
      || error "HARNESS_HERMES_OTEL_REF must be a full 40-character lowercase commit SHA (got '${HARNESS_HERMES_OTEL_REF}')."
    ref_args=(--ref "$HARNESS_HERMES_OTEL_REF")
  fi
  home="$(metrics_hermes_home)"
  plugin_dir="${home}/plugins/hermes_otel"
  if [[ ! -d "$plugin_dir" ]]; then
    spin "Installing the hermes-otel plugin" hermes plugins install "$HARNESS_HERMES_OTEL_PLUGIN" ${ref_args[@]+"${ref_args[@]}"} \
      || error "'hermes plugins install ${HARNESS_HERMES_OTEL_PLUGIN}' failed (see output above).
Requires Hermes >= 0.21 and network access to the plugin source."
  fi
  # Enabling also prepares the plugin's declared Python dependencies.
  spin "Enabling the hermes-otel plugin" hermes plugins enable hermes_otel \
    || error "'hermes plugins enable hermes_otel' failed (see output above)."
}

# Fails before any side effect (Jaeger, plugin) if the config cannot be written.
metrics_check_hermes_otel_config_path() {
  local home cfg
  home="$(metrics_hermes_home)"
  [[ -d "$home" && ! -L "$home" ]] || error "Hermes data directory ${home} not found or is a symlink."
  cfg="${home}/hermes_otel.yaml"
  [[ ! -L "$cfg" ]] || error "Refusing to write through a symlink: ${cfg}"
  if [[ -e "$cfg" ]] && ! grep -Fq "$METRICS_CONFIG_MARKER" "$cfg"; then
    error "${cfg} exists and is not managed by this installer; move it aside and re-run."
  fi
}

# Removes hermes_otel.yaml only when this installer wrote it. Also used by the
# uninstaller, so --keep-agent-data does not leave an exporter config behind.
metrics_remove_managed_config() {
  local home cfg
  home="$(metrics_hermes_home)"
  cfg="${home}/hermes_otel.yaml"
  [[ ! -L "$home" && -f "$cfg" && ! -L "$cfg" ]] || return 0
  if grep -Fq "$METRICS_CONFIG_MARKER" "$cfg"; then
    rm -f -- "$cfg"
  fi
}

# metrics_write_hermes_otel_config <backend> <endpoint> <content> <managed_jaeger>
metrics_write_hermes_otel_config() {
  local backend="$1" endpoint="$2" content="$3" managed="$4" home cfg tmp
  metrics_check_hermes_otel_config_path
  home="$(metrics_hermes_home)"
  cfg="${home}/hermes_otel.yaml"
  tmp="$(mktemp "${cfg}.tmp.XXXXXX")"
  {
    printf '%s\n' "$METRICS_CONFIG_MARKER" \
      "# Regenerated by './install.sh metrics enable'; edit settings through that command."
    # "off" must stay quoted: bare off is a YAML 1.1 boolean.
    printf 'content_capture: "%s"\n' "$content"
    case "$backend" in
      jaeger)
        printf 'backends:\n  - type: jaeger\n    endpoint: "%s"\n' "$endpoint"
        [[ "$managed" != true ]] || printf '    query_port: %s\n' "$HARNESS_JAEGER_UI_PORT"
        ;;
      otlp)
        printf 'backends:\n  - type: otlp\n    name: ahi-otlp\n    endpoint: "%s"\n' "$endpoint"
        ;;
    esac
  } >"$tmp" || { rm -f "$tmp"; error "Could not write ${cfg}."; }
  chmod 600 "$tmp"
  mv -f "$tmp" "$cfg"
}

metrics_enable_harness() {
  local backend="$M_BACKEND" endpoint="$M_ENDPOINT" content="$M_CONTENT" managed=false
  local prev_managed prev_enabled saved managed_state
  export PATH="$HOME/.local/bin:$PATH"
  command_exists hermes || error "Hermes CLI not found on PATH. Install it first: ./install.sh --harness hermes --model <model>
(Hermes inside an OpenShell sandbox is not supported for harness telemetry.)"
  prev_managed="$(metrics_state_get harness.managed_jaeger)"
  prev_enabled="$(metrics_state_get harness.enabled)"
  # Re-running enable (e.g. to turn on the Router) must not silently reset
  # harness settings that this invocation did not name.
  if [[ "$prev_enabled" == true ]]; then
    if [[ -z "${M_BACKEND_GIVEN:-}" ]]; then
      backend="$(metrics_state_get harness.backend)"
      endpoint="$(metrics_state_get harness.endpoint)"
      managed="${prev_managed:-false}"
      case "$backend" in
        sqlite | jaeger | otlp) ;;
        *) backend=sqlite endpoint="" managed=false ;;
      esac
      [[ -z "$endpoint" || "$endpoint" =~ $METRICS_ENDPOINT_RE ]] || endpoint=""
      if [[ "$backend" == sqlite ]]; then endpoint=""; fi
    fi
    if [[ -z "${M_CONTENT_GIVEN:-}" ]]; then
      saved="$(metrics_state_get harness.content)"
      case "$saved" in
        off | preview | full) content="$saved" ;;
      esac
    fi
  fi
  metrics_check_hermes_otel_config_path
  if [[ "$backend" == sqlite ]]; then
    local stray
    stray="$(compgen -e | grep -E '^(HERMES_OTEL_|OTEL_[A-Z]+_ENDPOINT$|OTEL_EXPORTER_)' | tr '\n' ' ' || true)"
    [[ -z "$stray" ]] || warn "Exporter variables set in this shell (${stray% }) may make Hermes export traces even with --backend sqlite."
  fi
  metrics_install_hermes_otel_plugin
  if [[ "$backend" == jaeger && ( -z "$endpoint" || "$managed" == true ) ]]; then
    metrics_ensure_jaeger
    endpoint="http://127.0.0.1:${HARNESS_JAEGER_OTLP_PORT}/v1/traces"
    managed=true
    # Recorded at once so 'metrics disable' can clean up if a later step fails.
    metrics_state_set harness.managed_jaeger true
  fi
  if [[ "$content" != off && "$backend" != sqlite ]]; then
    local export_host="${endpoint#*://}"
    export_host="${export_host%%/*}"
    if [[ "$export_host" == \[* ]]; then export_host="${export_host%%]*}]"; else export_host="${export_host%%:*}"; fi
    case "$export_host" in
      127.0.0.1 | localhost | "[::1]") ;;
      *) warn "--content ${content} sends prompt/response text to ${endpoint}, which is not on this machine." ;;
    esac
  fi
  metrics_write_hermes_otel_config "$backend" "$endpoint" "$content" "$managed"
  managed_state="$managed"
  if [[ "$prev_managed" == true && "$managed" != true ]]; then
    if [[ "$prev_enabled" == true ]]; then
      metrics_remove_jaeger
    else
      # Left running on purpose by 'metrics disable --keep-jaeger'; only an
      # explicit disable (or uninstall) may remove it and its traces.
      managed_state=true
      info "Kept the managed Jaeger (${HARNESS_JAEGER_CONTAINER}) left by 'metrics disable --keep-jaeger'; remove it with './install.sh metrics disable --target harness'."
    fi
  fi
  metrics_state_set harness.enabled true harness.agent hermes harness.backend "$backend" \
    harness.endpoint "$endpoint" harness.content "$content" harness.managed_jaeger "$managed_state"
  ok "Harness telemetry enabled for Hermes (backend: ${backend}, content: ${content})"
  info "Restart running Hermes sessions/gateways to apply; verify with: ./install.sh metrics show --target harness"
}

metrics_disable_harness() {
  local home keep_jaeger=false endpoint
  export PATH="$HOME/.local/bin:$PATH"
  home="$(metrics_hermes_home)"
  endpoint="$(metrics_state_get harness.endpoint)"
  if [[ -d "${home}/plugins/hermes_otel" ]] && command_exists hermes; then
    hermes plugins disable hermes_otel \
      || warn "'hermes plugins disable hermes_otel' failed; run it manually."
  fi
  metrics_remove_managed_config
  if [[ "$(metrics_state_get harness.managed_jaeger)" == true ]]; then
    if [[ -n "${M_KEEP_JAEGER:-}" ]]; then
      keep_jaeger=true
      info "Kept managed Jaeger (${HARNESS_JAEGER_CONTAINER}) and its traces: http://127.0.0.1:${HARNESS_JAEGER_UI_PORT}"
      info "Remove it later with './install.sh metrics disable --target harness' or uninstall."
    else
      metrics_remove_jaeger
    fi
  elif [[ -n "${M_CLEAN:-}" && -n "$endpoint" ]]; then
    info "Traces already exported to ${endpoint} are not removed; clear them in that backend."
  fi
  metrics_state_set harness.enabled false harness.managed_jaeger "$keep_jaeger"
  if [[ -n "${M_CLEAN:-}" ]]; then
    if metrics_clean_harness_store "$home"; then
      ok "Harness telemetry disabled and collected data cleaned"
    else
      warn "Harness telemetry disabled, but its collected data was not cleaned (see above)."
    fi
  else
    ok "Harness telemetry disabled (plugin left installed; its local store was kept; add --clean to delete it)"
  fi
  info "Restart running Hermes sessions/gateways to apply."
}

# Empties the plugin's SQLite store in place (rows, not the file): a running
# Hermes gateway keeps the file open in WAL mode, and unlinking it would leave
# that process writing to a deleted inode.
metrics_clean_harness_store() {
  local store="${1}/hermes_otel_live.db" count
  if [[ -L "$store" ]]; then
    warn "Refusing to clean a symlinked store: ${store}"
    return 1
  fi
  if [[ ! -f "$store" ]]; then
    info "No local store to clean (${store})"
    return 0
  fi
  if ! command_exists python3; then
    warn "python3 not found; delete ${store}* manually to clean the local store."
    return 1
  fi
  if count="$(python3 - "$store" <<'PY'
import sqlite3, sys

con = sqlite3.connect(sys.argv[1], timeout=10)
try:
    n = 0
    if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='events'").fetchone():
        n = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        con.execute("DELETE FROM events")
        con.commit()
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    print(n)
except sqlite3.Error as e:
    print(f"{type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(1)
finally:
    con.close()
PY
  )"; then
    ok "Cleaned ${count} records from the local store (${store})"
  else
    warn "Could not clean the local store (${store}); it may be locked or from another plugin version."
    return 1
  fi
}

# CLI summary of the plugin's local store, opened read-only. Prints nothing
# but a notice when the store is unreadable.
metrics_show_harness_store() {
  local store="$1"
  command_exists python3 || { info "python3 not found; cannot summarise the local store"; return 0; }
  python3 - "$store" <<'PY' || info "Could not read the local store (it may be locked or from another plugin version)."
import sqlite3, sys, urllib.parse
from datetime import datetime, timezone

def clean(s, n=60):
    return "".join(c if c.isprintable() else "?" for c in str(s))[:n]

def utc(ns):
    return datetime.fromtimestamp(ns / 1e9, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

try:
    con = sqlite3.connect("file:" + urllib.parse.quote(sys.argv[1]) + "?mode=ro", uri=True, timeout=5)
    q = lambda sql: con.execute(sql).fetchall()
    if not q("SELECT 1 FROM sqlite_master WHERE type='table' AND name='events'"):
        print("  no records yet")
        sys.exit(0)
    kinds = dict(q("SELECT kind, COUNT(*) FROM events GROUP BY kind"))
    total = sum(kinds.values())
    if not total:
        print("  no records yet")
        sys.exit(0)
    sessions = q("SELECT COUNT(DISTINCT session_id) FROM events WHERE kind='span' AND session_id IS NOT NULL")[0][0]
    errors = q("SELECT COUNT(*) FROM events WHERE kind='span' AND status='ERROR'")[0][0]
    lo, hi = q("SELECT MIN(ts), MAX(ts) FROM events")[0]
    detail = ", ".join(f"{clean(k, 20)}={v}" for k, v in sorted(kinds.items()))
    print(f"  records: {total} ({detail}); sessions: {sessions}; error spans: {errors}")
    print(f"  window: {utc(lo)} .. {utc(hi)} UTC")
    rows = q("SELECT name, COUNT(*), AVG(duration_ms), MAX(duration_ms) FROM events "
             "WHERE kind='span' AND name IS NOT NULL GROUP BY name ORDER BY COUNT(*) DESC, name LIMIT 8")
    if rows:
        print("  top spans:")
        for name, n, avg, mx in rows:
            print(f"    {clean(name)}: n={n} avg={(avg or 0):.1f}ms max={(mx or 0):.1f}ms")
except Exception as e:
    print(f"{type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(1)
PY
}

metrics_show_harness() {
  local home store enabled backend endpoint content size plugin_line
  printf "\n${C_BOLD}Harness telemetry${C_RESET}\n"
  if ! metrics_harness_check; then
    info "Not available: ${M_SKIP_REASON}."
    return 0
  fi
  export PATH="$HOME/.local/bin:$PATH"
  home="$(metrics_hermes_home)"
  enabled="$(metrics_state_get harness.enabled)"
  backend="$(metrics_state_get harness.backend)"
  endpoint="$(metrics_state_get harness.endpoint)"
  content="$(metrics_state_get harness.content)"
  if [[ "$enabled" == true ]]; then
    ok "Enabled for Hermes -- backend: ${backend:-sqlite}${endpoint:+ (${endpoint})}, content capture: ${content:-off}"
  else
    info "Disabled (enable with: ./install.sh metrics enable --target harness)"
  fi
  if [[ -d "${home}/plugins/hermes_otel" ]]; then
    ok "hermes-otel plugin installed (${home}/plugins/hermes_otel)"
    if command_exists hermes; then
      plugin_line="$(hermes plugins list 2>/dev/null | grep -i 'hermes_otel' | head -n 1 || true)"
      [[ -z "$plugin_line" ]] || info "hermes plugins list: ${plugin_line}"
    fi
  else
    info "hermes-otel plugin not installed"
  fi
  if [[ -f "${home}/hermes_otel.yaml" ]]; then
    info "Config: ${home}/hermes_otel.yaml"
  fi
  store="${home}/hermes_otel_live.db"
  if [[ -f "$store" ]]; then
    size="$(stat -c '%s' "$store" 2>/dev/null || echo 0)"
    # WAL mode keeps recent writes in the sidecar file, so count it too.
    [[ ! -f "${store}-wal" ]] || size=$(( size + $(stat -c '%s' "${store}-wal" 2>/dev/null || echo 0) ))
    info "Local store: ${store} (${size} bytes)"
    metrics_show_harness_store "$store"
  else
    info "Local store not created yet (${store}); it appears after the first Hermes turn"
  fi
  if [[ "$enabled" == true && "$backend" != sqlite && "$(metrics_state_get harness.managed_jaeger)" != true && -n "$endpoint" ]]; then
    info "Full trace view: open the UI of the backend receiving ${endpoint}"
  fi
  if [[ "$(metrics_state_get harness.managed_jaeger)" == true ]]; then
    if command_exists curl \
      && curl --noproxy '*' -sf --max-time 5 "http://127.0.0.1:${HARNESS_JAEGER_UI_PORT}/" >/dev/null 2>&1; then
      ok "Jaeger UI reachable: http://127.0.0.1:${HARNESS_JAEGER_UI_PORT}"
    else
      warn "Managed Jaeger (${HARNESS_JAEGER_CONTAINER}) is not reachable on port ${HARNESS_JAEGER_UI_PORT}"
    fi
  fi
  info "For the plugin's own details run: hermes plugins show hermes_otel"
}

# ---------------------------------------------------------------------------
# Inference Router
# ---------------------------------------------------------------------------

# metrics_router_telemetry_file -- host path of the Router's JSONL store.
metrics_router_telemetry_file() {
  printf '%s/%s' "$(inference_router_workspace_dir)" "$METRICS_ROUTER_JSONL_NAME"
}

# Replaces only the telemetry block of the generated config.yaml (up to the
# next top-level key), so the rest of the Router's configuration is kept.
_metrics_router_rewrite_config_locked() {
  local cfg tmp
  cfg="$(inference_router_workspace_dir)/config.yaml"
  [[ -f "$cfg" && ! -L "$cfg" ]] || return 1
  tmp="$(mktemp "${cfg}.tmp.XXXXXX")"
  awk '/^telemetry:/ { skip = 1; next } skip && /^[^[:space:]#]/ { skip = 0 } !skip { print }' "$cfg" >"$tmp" \
    || { rm -f "$tmp"; error "Could not rewrite ${cfg}."; }
  printf '%s\n' "$(inference_router_telemetry_block)" >>"$tmp"
  # IR runs as its image's fixed uid, not the host user (see
  # _write_inference_router_config_locked), so it needs world-readable config.
  chmod 644 "$tmp" || { rm -f "$tmp"; error "Could not set permissions on ${cfg}."; }
  mv -f "$tmp" "$cfg" || { rm -f "$tmp"; error "Could not replace ${cfg}."; }
}

# metrics_router_host_gid -- the user's primary group from the account database,
# not `id -g`: after the installer re-runs itself under `sg docker`, `id -g` is
# the docker group, which would differ between runs.
metrics_router_host_gid() {
  local gid=""
  gid="$(getent passwd "$(id -un)" 2>/dev/null | cut -d: -f4)" || gid=""
  [[ "$gid" =~ ^[0-9]+$ ]] || gid="$(id -g)"
  printf '%s' "$gid"
}

# metrics_router_file_mode -- the mode the telemetry file gets. A root-owned
# installer has no private group the container could join, so it keeps 666.
metrics_router_file_mode() {
  case "$HARNESS_IR_TELEMETRY_FILE_MODE" in
    664) if [[ "$(metrics_router_host_gid)" == 0 ]]; then printf 666; else printf 664; fi ;;
    666) printf 666 ;;
    *) error "HARNESS_IR_TELEMETRY_FILE_MODE must be 664 or 666 (got '${HARNESS_IR_TELEMETRY_FILE_MODE}')." ;;
  esac
}

# metrics_router_file_group -- the host group id the Router container must join
# to append to the 664 file; prints nothing in 666 mode.
metrics_router_file_group() {
  [[ "$(metrics_router_file_mode)" == 664 ]] && metrics_router_host_gid
  return 0
}

# Fails when an existing Router container was created without the group needed
# to write the 664 file (an install from before this setting existed).
metrics_router_check_container_group() {
  local group groups
  group="$(metrics_router_file_group)"
  [[ -n "$group" ]] || return 0
  docker inspect "$HARNESS_IR_CONTAINER" >/dev/null 2>&1 || return 0
  groups="$(docker inspect -f '{{json .HostConfig.GroupAdd}}' "$HARNESS_IR_CONTAINER" 2>/dev/null || true)"
  [[ "$groups" == *"\"${group}\""* ]] \
    || error "The Inference Router container ${HARNESS_IR_CONTAINER} was created without access to group ${group}, so it could not write its telemetry file.
Re-run ./install.sh (or './install.sh inference --model <model>') once to recreate it, then enable telemetry again.
Alternatively set HARNESS_IR_TELEMETRY_FILE_MODE=666 (world-writable file; for rootless Docker)."
}

# Rootless Docker and user-namespace remapping renumber container uids/gids, so
# the host group the container joins would not match the file's group and the
# Router could not append to it; warn instead of silently collecting nothing.
metrics_router_warn_if_remapped() {
  local opts
  [[ "$(metrics_router_file_mode)" == 664 ]] || return 0
  opts="$(docker info --format '{{.SecurityOptions}}' 2>/dev/null || true)"
  case "$opts" in
    *rootless* | *userns*)
      warn "Docker runs rootless or with user-namespace remapping, so the Router may not be able to write its 664 telemetry file.
If 'metrics show' stays at zero events, set HARNESS_IR_TELEMETRY_FILE_MODE=666 and re-run ./install.sh to recreate the Router." ;;
  esac
}

metrics_router_prepare_file() {
  local file mode size max
  file="$(metrics_router_telemetry_file)"
  mode="$(metrics_router_file_mode)"
  [[ "$HARNESS_IR_TELEMETRY_MAX_BYTES" =~ ^[0-9]{1,15}$ ]] \
    || error "HARNESS_IR_TELEMETRY_MAX_BYTES must be a non-negative integer of at most 15 digits (got '${HARNESS_IR_TELEMETRY_MAX_BYTES}')."
  # 10# keeps a leading zero (e.g. 08) from being read as invalid octal.
  max=$((10#$HARNESS_IR_TELEMETRY_MAX_BYTES))
  mkdir -p "$(inference_router_workspace_dir)"
  [[ ! -L "$file" && ! -L "${file}.1" ]] || error "Refusing to use a symlinked telemetry file: ${file}"
  # Rotated while the Router is stopped or about to restart, so nothing appends
  # to the moved file; the previous generation is replaced.
  if (( max > 0 )) && [[ -f "$file" ]]; then
    size="$(wc -c <"$file" | tr -d ' ')"
    if (( size > max )); then
      mv -f -- "$file" "${file}.1" && chmod 600 "${file}.1" \
        || error "Could not rotate ${file}."
      info "Rotated ${file} (${size} bytes) to ${file}.1; /v1/metrics counts only the new file."
    fi
  fi
  [[ -e "$file" ]] || : >"$file"
  # The container's uid never matches the host user's, and it must append to
  # this bind-mounted file. It holds counters/latencies, not prompt text.
  if [[ "$mode" == 664 ]]; then chgrp "$(metrics_router_host_gid)" "$file" 2>/dev/null || true; fi
  chmod "$mode" "$file"
}

metrics_router_apply() {
  local state="$1" prev
  command_exists docker || error "Docker is required to apply Inference Router telemetry settings."
  if [[ "${HARNESS_RUNTIME:-host}" == openshell ]]; then
    [[ "$(resolve_bind_host)" == 127.0.0.1 ]] \
      || error "OpenShell mode requires HARNESS_BIND_HOST=127.0.0.1; inference must not be LAN-published."
  fi
  prev="$(metrics_state_get router.enabled)"
  if [[ "$state" == true ]]; then
    metrics_router_check_container_group
    metrics_router_warn_if_remapped
  fi
  metrics_state_set router.enabled "$state"
  [[ "$state" != true ]] || metrics_router_prepare_file
  if [[ ! -f "$(inference_router_workspace_dir)/config.yaml" ]]; then
    info "The Inference Router has no generated config yet; the setting applies on its next install."
    return 0
  fi
  with_state_lock inference-router-config _metrics_router_rewrite_config_locked \
    || { metrics_state_set router.enabled "${prev:-false}"; error "Could not update the Inference Router config."; }
  if docker inspect "$HARNESS_IR_CONTAINER" >/dev/null 2>&1; then
    docker restart "$HARNESS_IR_CONTAINER" >/dev/null \
      || error "Could not restart the Inference Router (${HARNESS_IR_CONTAINER}); config was updated."
    wait_for_inference_router_ready || true
  else
    info "The Inference Router container is not installed; the setting applies on its next install."
  fi
}

metrics_enable_router() {
  metrics_router_apply true
  ok "Router telemetry enabled: persisted to $(metrics_router_telemetry_file)"
}

# Once the Router is back on in-memory telemetry (it has been restarted) nothing
# writes the file, so a group- or world-writable mode left by enable is dropped.
metrics_router_secure_file() {
  local file
  file="$(metrics_router_telemetry_file)"
  [[ -f "$file" && ! -L "$file" ]] || return 0
  chmod 600 "$file" 2>/dev/null || warn "Could not restrict the permissions of ${file}."
}

metrics_disable_router() {
  metrics_router_apply false
  metrics_router_secure_file
  if [[ -n "${M_CLEAN:-}" ]]; then
    if metrics_clean_router; then
      ok "Router telemetry reverted to in-memory only and collected data cleaned"
    else
      warn "Router telemetry reverted to in-memory only, but ${METRICS_ROUTER_JSONL_NAME} was not cleaned (see above)."
    fi
  else
    ok "Router telemetry reverted to in-memory only (kept ${METRICS_ROUTER_JSONL_NAME} for inspection; add --clean to empty it)"
  fi
}

# Empties telemetry.jsonl in place. Runs after the restart that switched the
# Router back to memory, so nothing is appending to it; the restart also reset
# the in-memory counters.
metrics_clean_router() {
  local file lines
  file="$(metrics_router_telemetry_file)"
  if [[ -L "$file" || -L "${file}.1" ]]; then
    warn "Refusing to clean a symlinked telemetry file: ${file}"
    return 1
  fi
  if [[ -f "${file}.1" ]]; then
    rm -f -- "${file}.1" || { warn "Could not remove ${file}.1; remove it manually."; return 1; }
    ok "Removed the rotated file ${file}.1"
  fi
  if [[ ! -f "$file" ]]; then
    info "No Router telemetry file to clean (${file})"
    return 0
  fi
  lines="$(wc -l <"$file" 2>/dev/null | tr -d ' ' || echo "?")"
  if : >"$file"; then
    ok "Cleaned ${lines} events from ${file}"
  else
    warn "Could not empty ${file}; remove it manually."
    return 1
  fi
}

metrics_show_router() {
  local cfg probe_host json file lines
  printf "\n${C_BOLD}Inference Router telemetry${C_RESET}\n"
  cfg="$(inference_router_workspace_dir)/config.yaml"
  if [[ "$(metrics_state_get router.enabled)" == true ]]; then
    ok "Persistent collection enabled (file backend)"
  else
    info "Persistent collection disabled (in-memory counters only; enable with: ./install.sh metrics enable --target router)"
  fi
  if [[ -f "$cfg" ]]; then
    info "Configured: $(awk '/^telemetry:/ { f = 1; next } f && NF { gsub(/^ +/, ""); printf "%s ", $0 }' "$cfg")"
  fi
  file="$(metrics_router_telemetry_file)"
  if [[ -f "$file" ]]; then
    local bytes
    lines="$(wc -l <"$file" 2>/dev/null | tr -d ' ' || echo "?")"
    bytes="$(wc -c <"$file" 2>/dev/null | tr -d ' ' || echo 0)"
    info "Events file: ${file} (${lines} events, ${bytes} bytes)"
    if [[ "$HARNESS_IR_TELEMETRY_MAX_BYTES" =~ ^[0-9]{1,15}$ ]] && (( 10#$HARNESS_IR_TELEMETRY_MAX_BYTES > 0 && bytes > 10#$HARNESS_IR_TELEMETRY_MAX_BYTES )); then
      warn "The events file exceeds ${HARNESS_IR_TELEMETRY_MAX_BYTES} bytes and slows /v1/metrics; it is rotated to ${METRICS_ROUTER_JSONL_NAME}.1 on the next install or 'metrics enable', or empty it now with 'metrics disable --target router --clean'."
    fi
  fi
  [[ ! -f "${file}.1" ]] || info "Rotated events file: ${file}.1 (not counted in /v1/metrics)"
  if ! command_exists docker; then
    info "Docker not found; cannot read the Inference Router"
    return 0
  fi
  if ! docker info >/dev/null 2>&1; then
    warn "Docker is not reachable (is the daemon running, and are you in the docker group?); cannot read the Inference Router."
    return 0
  fi
  if ! docker inspect "$HARNESS_IR_CONTAINER" >/dev/null 2>&1; then
    info "Inference Router not installed"
    return 0
  fi
  if ! command_exists curl; then
    warn "curl not found; cannot read /v1/metrics"
    return 0
  fi
  probe_host="$(resolve_probe_host)" || probe_host="127.0.0.1"
  if ! json="$(curl --noproxy '*' -sf --max-time 10 "http://${probe_host}:${HARNESS_IR_PORT}/v1/metrics")"; then
    warn "Could not read http://${probe_host}:${HARNESS_IR_PORT}/v1/metrics (is the Router running?)"
    return 0
  fi
  metrics_format_router_metrics <<<"$json" || warn "Unexpected /v1/metrics response."
}

# Reads the Router's /v1/metrics JSON on stdin and prints the CLI summary.
metrics_format_router_metrics() {
  node -e '
    const d = JSON.parse(require("node:fs").readFileSync(0, "utf8"));
    const t = d.token_metrics.overall, l = d.latency_metrics.overall;
    console.log(`  requests=${t.total_requests} input_tokens=${t.total_input_tokens} output_tokens=${t.total_output_tokens}`);
    console.log(`  avg_latency_ms=${l.avg_latency_ms} avg_ttft_ms=${l.avg_ttft_ms} avg_tpot_ms=${l.avg_tpot_ms}`);
    const by = Object.entries(d.token_metrics.by_provider || {});
    if (by.length) console.log("  by provider/model:");
    for (const [k, v] of by) {
      const share = (100 * Number(v.token_share || 0)).toFixed(1);
      console.log(`    ${k.replace(/[^\x20-\x7e]/g, "?").slice(0, 60)}: requests=${v.request_count} in=${v.input_tokens} out=${v.output_tokens} (${share}% of tokens)`);
    }
  '
}

# ---------------------------------------------------------------------------
# Command entry point
# ---------------------------------------------------------------------------

metrics_wants() {
  [[ "$M_TARGET" == all || "$M_TARGET" == "$1" ]]
}

run_metrics_command() {
  local verb="${1:-}"
  [[ -n "$verb" ]] || { usage; error "metrics requires a verb (enable/disable/show)."; }
  shift
  case "$verb" in
    enable | disable | show) ;;
    *) usage; error "Unknown metrics verb: ${verb}" ;;
  esac
  metrics_parse_args "$verb" "$@"
  set +u
  ensure_nvm_loaded
  set -u
  command_exists node || error "Node.js is required (used for the installer's JSON state handling)."
  # Checked up front so '--target all' cannot enable the harness and then fail on the Router.
  if [[ "$verb" == enable ]] && metrics_wants router; then
    metrics_router_check_container_group
  fi

  if metrics_wants harness; then
    case "$verb" in
      show) metrics_show_harness ;;
      *)
        if metrics_harness_check; then
          "metrics_${verb}_harness"
        elif [[ "$M_TARGET" == harness ]]; then
          error "${M_SKIP_REASON}."
        else
          warn "Skipping the harness: ${M_SKIP_REASON}."
        fi ;;
    esac
  fi
  if metrics_wants router; then
    "metrics_${verb}_router"
  fi
  printf '\n'
}
