# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=bash
# `./install.sh observability <enable|disable|show>` -- one switch for telemetry
# collection across the blocks of a deployment:
#
#   harness  The installed agent. Hermes uses the hermes-otel plugin (spans and
#            metrics per turn go to the plugin's local SQLite store and,
#            optionally, over OTLP to a Jaeger). OpenClaw (diagnostics-otel
#            plugin) exports OTLP itself; for `--backend sqlite` a small
#            loopback OTLP receiver (metrics-otlp-receiver.py) stores those
#            spans in the same SQLite layout Hermes uses, for `--backend jaeger`
#            they go straight to Jaeger. With --runtime openshell the exporter
#            is configured inside the sandbox (the sandbox image carries the
#            exporter, since the default sandbox policy allows no egress to a
#            collector; for Hermes the hermes-otel plugin is baked in and
#            switched through its hermes_otel.yaml) and a hot-loaded policy
#            rule lets it reach the host receiver or Jaeger through
#            host.openshell.internal. dcode has native
#            tracing for LangSmith only, so a small dcode extension
#            (dcode-otel-extension.py, dropped into ~/.deepagents/extensions;
#            inside a sandbox it is baked into the image and copied there)
#            exports its LangChain runs as OTLP spans, to the same loopback
#            receiver (--backend sqlite) or to Jaeger.
#   router   Inference Router. It cannot export OTLP; its telemetry backend is
#            either "memory" (default, lost on restart) or "file" (JSONL in its
#            workspace). Both are readable through its /v1/metrics endpoint.
#            With --backend sqlite|jaeger a host-side bridge
#            (metrics-router-bridge.py) tails the JSONL file and forwards each
#            request as a trace (service inference-router) to a local SQLite
#            store or to the same Jaeger the harness uses; the Router itself
#            is not modified.
#
# Chosen settings are kept in ~/.agent-harness-install/metrics.json so that a
# later install (which regenerates the Router's config.yaml) preserves them.

HARNESS_JAEGER_IMAGE="${HARNESS_JAEGER_IMAGE:-jaegertracing/all-in-one:1.76.0}"
HARNESS_JAEGER_CONTAINER="${HARNESS_JAEGER_CONTAINER:-agent-harness-install-jaeger}"
HARNESS_JAEGER_UI_PORT="${HARNESS_JAEGER_UI_PORT:-16686}"
HARNESS_JAEGER_OTLP_PORT="${HARNESS_JAEGER_OTLP_PORT:-4318}"
# Label stamped on the Jaeger container this installer creates. A container is
# only reused or removed when it carries it, so a same-named container that
# someone else created (and its traces) is never adopted or deleted.
METRICS_JAEGER_LABEL_KEY="io.agent-harness-install.managed-by"
METRICS_JAEGER_LABEL_VALUE="metrics-jaeger"
# Plugin source handed to `hermes plugins install`. The bare catalog name makes
# Hermes install the commit pinned in its reviewed plugin catalog (and apply
# its removal kill-list); override with an explicit <owner>/<repo>/<plugin>
# reference to use a different source. HARNESS_HERMES_OTEL_REF additionally
# pins any source to an exact 40-character commit SHA (`--ref`).
HARNESS_HERMES_OTEL_PLUGIN="${HARNESS_HERMES_OTEL_PLUGIN:-hermes_otel}"
HARNESS_HERMES_OTEL_REF="${HARNESS_HERMES_OTEL_REF:-}"
# OpenClaw's OTel exporter plugin. Empty means the npm package at the version of
# the installed OpenClaw; set it to any npm spec to override (e.g.
# @openclaw/diagnostics-otel@2026.9.5).
HARNESS_OPENCLAW_OTEL_PLUGIN="${HARNESS_OPENCLAW_OTEL_PLUGIN:-}"
# Loopback port of the OTLP receiver behind `--backend sqlite` for OpenClaw
# (Jaeger's own OTLP port, 4318, stays free for --backend jaeger).
HARNESS_OTLP_RECEIVER_PORT="${HARNESS_OTLP_RECEIVER_PORT:-4319}"
# Rows kept by that receiver; the oldest are pruned beyond it.
HARNESS_OTLP_RECEIVER_MAX_ROWS="${HARNESS_OTLP_RECEIVER_MAX_ROWS:-200000}"
METRICS_RECEIVER_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/metrics-otlp-receiver.py"
# dcode: extension source, and the markers around the one line this installer adds to the profile's .env
# (dcode loads extensions only when DEEPAGENTS_CODE_EXPERIMENTAL is set).
METRICS_DCODE_EXTENSION_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/dcode-otel-extension.py"
METRICS_DCODE_ENV_BEGIN="# BEGIN agent-harness-install managed observability -- do not edit between markers"
METRICS_DCODE_ENV_END="# END agent-harness-install managed observability"
# --runtime openshell: sandbox-side half (piped into the sandbox's node) and the
# name of the policy rule that lets the agent reach the host collector.
METRICS_OS_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/openshell/observability-config.mjs"
METRICS_OS_RULE=harness_otel
# Host-side daemon that forwards the Router's JSONL events as spans (sqlite or OTLP); the Router has no exporter.
METRICS_BRIDGE_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/metrics-router-bridge.py"
HARNESS_ROUTER_BRIDGE_MAX_ROWS="${HARNESS_ROUTER_BRIDGE_MAX_ROWS:-200000}"
# Set by metrics_resolve_router_settings: bridge backend (empty = file only), exporter URL, managed Jaeger, content mode.
R_BACKEND="" R_ENDPOINT="" R_MANAGED=false R_CONTENT=off
# The Router's JSONL file is rotated to ir_metrics.jsonl.1 (one generation) when
# the installer next prepares it and it is larger than this many bytes; 0 turns
# rotation off. The Router re-reads the whole file for every /v1/metrics call.
HARNESS_IR_TELEMETRY_MAX_BYTES="${HARNESS_IR_TELEMETRY_MAX_BYTES:-20971520}"
# Mode of that file. 664 lets only the owner and the host user's primary group
# write it (the Router container joins that group, see metrics_router_file_group);
# 666 is the fallback for rootless Docker or user-namespace remapping, where
# container group ids do not match host ones.
HARNESS_IR_TELEMETRY_FILE_MODE="${HARNESS_IR_TELEMETRY_FILE_MODE:-664}"

METRICS_CONFIG_MARKER="# Managed by agent-harness-install (metrics)"
METRICS_ROUTER_JSONL_NAME="ir_metrics.jsonl"
# Set by metrics_harness_check; the default keeps direct calls to the helpers working.
M_AGENT="${M_AGENT:-hermes}"
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
        [[ "$verb" == disable ]] || error "${flag} is only valid with 'observability disable'."
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
        [[ "$verb" == enable ]] || error "${flag} is only valid with 'observability enable'."
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
  [[ "$verb" == enable ]] || return 0
  # Omitted flags keep the saved harness settings (see metrics_enable_harness).
  M_BACKEND_GIVEN="$M_BACKEND" M_CONTENT_GIVEN="$M_CONTENT"
  M_BACKEND="${M_BACKEND:-sqlite}"
  M_CONTENT="${M_CONTENT:-off}"
  case "$M_BACKEND" in
    sqlite | jaeger) ;;
    *) error "--backend must be sqlite or jaeger (got '${M_BACKEND}')." ;;
  esac
  case "$M_CONTENT" in
    off | preview | full) ;;
    *) error "--content must be off, preview or full (got '${M_CONTENT}')." ;;
  esac
  if [[ -n "$M_BACKEND_GIVEN" && "$M_BACKEND" == sqlite && -n "$M_ENDPOINT" ]]; then
    error "--endpoint cannot be combined with --backend sqlite (nothing is exported)."
  fi
  if [[ -n "$M_ENDPOINT" ]]; then
    # No userinfo, query or quotes: the value is written into YAML and shown
    # in output, and credentials must not travel in argv or config files. The
    # rejected value is never echoed back: it may carry a secret that would
    # then reach terminal and CI logs.
    [[ "$M_ENDPOINT" =~ $METRICS_ENDPOINT_RE ]] \
      || error "--endpoint must be a plain http(s) URL without credentials or query string."
    local authority="${M_ENDPOINT#*://}"
    authority="${authority%%/*}"
    if [[ "$authority" =~ :([0-9]+)$ ]] && (( 10#${BASH_REMATCH[1]} < 1 || 10#${BASH_REMATCH[1]} > 65535 )); then
      error "--endpoint port must be between 1 and 65535."
    fi
  fi
  # Whether the backend and endpoint fit together depends on the saved harness
  # settings for omitted options; see metrics_resolve_harness_settings.
}

# metrics_resolve_harness_settings -- combines the options given on the command
# line with the saved harness settings (an enabled harness keeps whatever this
# invocation does not name) and validates the effective combination. Sets
# H_BACKEND/H_ENDPOINT/H_CONTENT/H_MANAGED; changes no state.
metrics_resolve_harness_settings() {
  local given_endpoint="${M_ENDPOINT:-}" saved_backend="" saved_endpoint="" saved_managed="" saved_content=""
  H_BACKEND="$M_BACKEND" H_ENDPOINT="$given_endpoint" H_CONTENT="$M_CONTENT" H_MANAGED=false
  if [[ "$(metrics_state_get harness.enabled)" == true && "$(metrics_state_get harness.agent)" == "${M_AGENT:-hermes}" ]]; then
    saved_backend="$(metrics_state_get harness.backend)"
    saved_endpoint="$(metrics_state_get harness.endpoint)"
    saved_managed="$(metrics_state_get harness.managed_jaeger)"
    if [[ -z "${M_BACKEND_GIVEN:-}" ]]; then
      case "$saved_backend" in
        sqlite | jaeger) H_BACKEND="$saved_backend" ;;
        *) H_BACKEND=sqlite saved_backend="" ;;
      esac
    fi
    # A saved external endpoint stays with the backend it was saved for; the
    # managed Jaeger's own loopback URL is derived again below.
    if [[ -z "$H_ENDPOINT" && "$saved_managed" != true && "$H_BACKEND" == "$saved_backend" \
      && "$saved_endpoint" =~ $METRICS_ENDPOINT_RE ]]; then
      H_ENDPOINT="$saved_endpoint"
    fi
    if [[ -z "${M_CONTENT_GIVEN:-}" ]]; then
      saved_content="$(metrics_state_get harness.content)"
      case "$saved_content" in
        off | preview | full) H_CONTENT="$saved_content" ;;
      esac
    fi
  fi
  case "$H_BACKEND" in
    sqlite)
      [[ -z "$given_endpoint" ]] \
        || error "--endpoint needs an exporting backend; add --backend jaeger (sqlite exports nothing)."
      H_ENDPOINT="" ;;
    jaeger)
      if [[ -z "$H_ENDPOINT" ]]; then
        H_MANAGED=true
        H_ENDPOINT="http://127.0.0.1:${HARNESS_JAEGER_OTLP_PORT}/v1/traces"
      fi ;;
  esac
  # The hermes-otel plugin and the dcode extension have a preview mode; OpenClaw's
  # exporter either sends prompt text or not, and the receiver can only shorten it.
  if [[ "${M_AGENT:-hermes}" == openclaw && "$H_BACKEND" == jaeger && "$H_CONTENT" == preview ]]; then
    error "--content preview needs --backend sqlite for $(agent_display_name "$M_AGENT") (its exporter has no preview mode); use off or full with Jaeger."
  fi
}

# ---------------------------------------------------------------------------
# Managed Jaeger (harness --backend jaeger without --endpoint)
# ---------------------------------------------------------------------------

metrics_validate_jaeger_ports() {
  local port
  for port in "$HARNESS_JAEGER_UI_PORT" "$HARNESS_JAEGER_OTLP_PORT"; do
    if [[ ! "$port" =~ ^[0-9]+$ ]] || (( port < 1 || port > 65535 )); then
      error "Jaeger ports must be between 1 and 65535 (got '${port}')."
    fi
  done
}

# metrics_container_exists <name> -- fails the command, rather than reporting
# the container as absent, when Docker cannot be queried (denied, daemon down).
metrics_container_exists() {
  local names
  names="$(docker container ls -a --format '{{.Names}}')" \
    || error "Cannot inspect Docker containers (is the daemon running, and are you in the docker group?)."
  grep -Fxq -- "$1" <<<"$names"
}

# metrics_jaeger_ownership -- sets M_JAEGER_OWNER to absent, owned (carries this
# installer's label) or foreign (a same-named container somebody else made).
# Sets a variable instead of printing so a Docker failure stops the caller.
metrics_jaeger_ownership() {
  local label
  M_JAEGER_OWNER=absent
  metrics_container_exists "$HARNESS_JAEGER_CONTAINER" || return 0
  label="$(docker inspect -f "{{index .Config.Labels \"${METRICS_JAEGER_LABEL_KEY}\"}}" "$HARNESS_JAEGER_CONTAINER")" \
    || error "Cannot inspect the container ${HARNESS_JAEGER_CONTAINER}."
  if [[ "$label" == "$METRICS_JAEGER_LABEL_VALUE" ]]; then M_JAEGER_OWNER=owned; else M_JAEGER_OWNER=foreign; fi
}

# An existing container keeps the ports it was created with, and may only be
# reused while it publishes exactly the two loopback ports: a wider binding
# would expose the trace UI and any captured prompt text to the network.
metrics_check_jaeger_ports() {
  local bindings
  bindings="$(docker inspect -f '{{json .HostConfig.PortBindings}}' "$HARNESS_JAEGER_CONTAINER")" \
    || error "Cannot inspect the container ${HARNESS_JAEGER_CONTAINER}."
  node -e '
    let b;
    try { b = JSON.parse(process.argv[1]); } catch { process.exit(1); }
    const want = { "16686/tcp": process.argv[2], "4318/tcp": process.argv[3] };
    if (b === null || typeof b !== "object" || Object.keys(b).length !== 2) process.exit(1);
    for (const [k, port] of Object.entries(want)) {
      const v = b[k];
      if (!Array.isArray(v) || v.length !== 1 || v[0].HostIp !== "127.0.0.1" || v[0].HostPort !== port) process.exit(1);
    }
  ' "$bindings" "$HARNESS_JAEGER_UI_PORT" "$HARNESS_JAEGER_OTLP_PORT" \
    || error "Existing container ${HARNESS_JAEGER_CONTAINER} must publish exactly 127.0.0.1:${HARNESS_JAEGER_UI_PORT}->16686 and 127.0.0.1:${HARNESS_JAEGER_OTLP_PORT}->4318; remove it (docker rm -f ${HARNESS_JAEGER_CONTAINER}) or set HARNESS_JAEGER_UI_PORT/HARNESS_JAEGER_OTLP_PORT to match."
}

# Fails before any side effect when an existing container must not be reused.
metrics_jaeger_preflight() {
  command_exists docker || error "Docker is required to run the managed Jaeger container.
Pass --endpoint to use an existing Jaeger instead."
  metrics_validate_jaeger_ports
  metrics_jaeger_ownership
  case "$M_JAEGER_OWNER" in
    foreign)
      error "A container named ${HARNESS_JAEGER_CONTAINER} exists but was not created by this installer, so it is not reused or removed.
Rename or remove it, or set HARNESS_JAEGER_CONTAINER to another name." ;;
    owned) metrics_check_jaeger_ports ;;
  esac
}

metrics_ensure_jaeger() {
  metrics_jaeger_preflight
  if [[ "$M_JAEGER_OWNER" == owned ]]; then
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
    --label "${METRICS_JAEGER_LABEL_KEY}=${METRICS_JAEGER_LABEL_VALUE}" \
    -p "127.0.0.1:${HARNESS_JAEGER_UI_PORT}:16686" \
    -p "127.0.0.1:${HARNESS_JAEGER_OTLP_PORT}:4318" \
    -e COLLECTOR_OTLP_ENABLED=true \
    "$HARNESS_JAEGER_IMAGE" >/dev/null \
    || error "Could not start Jaeger -- a common cause is port ${HARNESS_JAEGER_UI_PORT} or ${HARNESS_JAEGER_OTLP_PORT} already in use."
  ok "Jaeger started: UI http://127.0.0.1:${HARNESS_JAEGER_UI_PORT}, OTLP http://127.0.0.1:${HARNESS_JAEGER_OTLP_PORT}/v1/traces"
}

# Also used by the uninstaller. Removes the container only when this installer
# created it; a foreign one of the same name is left alone.
metrics_remove_jaeger() {
  command_exists docker || return 0
  metrics_jaeger_ownership
  case "$M_JAEGER_OWNER" in
    owned)
      docker rm -f "$HARNESS_JAEGER_CONTAINER" >/dev/null \
        || error "Could not remove the Jaeger container ${HARNESS_JAEGER_CONTAINER}."
      ok "Jaeger container removed" ;;
    foreign)
      warn "Not removing the container ${HARNESS_JAEGER_CONTAINER}: it was not created by this installer." ;;
  esac
}

# metrics_jaeger_in_use_by <harness|router> -- that target uses (or was told to keep) the managed Jaeger.
metrics_jaeger_in_use_by() {
  [[ "$(metrics_state_get "$1.managed_jaeger")" == true || "$(metrics_state_get "$1.kept_jaeger")" == true ]]
}

# metrics_info_jaeger_stays <harness|router> -- says why the managed Jaeger outlives the other target's disable.
metrics_info_jaeger_stays() {
  local other="$1" what="the harness still sends"
  [[ "$other" != router ]] || what="the Router telemetry bridge still sends"
  if [[ "$(metrics_state_get "${other}.managed_jaeger")" == true ]]; then
    info "The managed Jaeger (${HARNESS_JAEGER_CONTAINER}) stays: ${what} to it."
  else
    info "The managed Jaeger (${HARNESS_JAEGER_CONTAINER}) stays: it was kept for the ${other} by --keep-jaeger; remove it with './install.sh observability disable --target ${other}'."
  fi
}

# ---------------------------------------------------------------------------
# Harness (Hermes, OpenClaw, dcode)
# ---------------------------------------------------------------------------

metrics_hermes_home() {
  printf '%s' "${HERMES_HOME:-$HOME/.hermes}"
}

metrics_dcode_home() {
  printf '%s' "${DEEPAGENTS_HOME:-$HOME/.deepagents}"
}

metrics_openclaw_home() {
  printf '%s' "${OPENCLAW_STATE_DIR:-$HOME/.openclaw}"
}

metrics_openshell() {
  [[ "${HARNESS_RUNTIME:-host}" == openshell ]]
}

# The runtime the enabled harness telemetry was set up for (host when unrecorded).
metrics_harness_runtime() {
  local runtime
  runtime="$(metrics_state_get harness.runtime)"
  printf '%s' "${runtime:-host}"
}

# metrics_runtime_mismatch -- true (and prints the recorded runtime) when harness
# telemetry is enabled for a different runtime than the one selected now.
metrics_runtime_mismatch() {
  local recorded want=host
  [[ -n "$(metrics_harness_owner)" ]] || return 1
  if metrics_openshell; then want=openshell; fi
  recorded="$(metrics_harness_runtime)"
  [[ "$recorded" != "$want" ]] || return 1
  printf '%s' "$recorded"
}

# metrics_os_exec <command> [args...] -- runs the sandbox-side script in the sandbox of $HARNESS_AGENT.
metrics_os_exec() {
  openshell_agent_exec /usr/local/bin/node --input-type=module - "$@" <"$METRICS_OS_SCRIPT"
}

# metrics_harness_store <agent> -- SQLite file the agent's spans end up in: the
# hermes-otel plugin's own store, or the one the OTLP receiver fills. For a
# sandbox it lives in the installer's state directory, not in the sandbox.
metrics_harness_store() {
  if metrics_openshell; then
    case "$1" in
      openclaw) printf '%s/openshell-telemetry/openclaw_otel_live.db' "$(harness_state_root)" ;;
      hermes) printf '%s/openshell-telemetry/hermes_otel_live.db' "$(harness_state_root)" ;;
      deepagents-code) printf '%s/openshell-telemetry/dcode_otel_live.db' "$(harness_state_root)" ;;
    esac
    return 0
  fi
  case "$1" in
    hermes) printf '%s/hermes_otel_live.db' "$(metrics_hermes_home)" ;;
    openclaw) printf '%s/openclaw_otel_live.db' "$(metrics_openclaw_home)" ;;
    deepagents-code) printf '%s/dcode_otel_live.db' "$(metrics_dcode_home)" ;;
  esac
}

# Sets M_AGENT; on failure sets M_SKIP_REASON and returns 1. For show and disable the
# agent whose exporter this installer enabled is used, whichever agent is selected now.
metrics_harness_check() {
  local verb="${1:-}" owner=""
  M_SKIP_REASON=""
  if [[ "$verb" == show || "$verb" == disable ]]; then
    owner="$(metrics_harness_owner)"
    case "$owner" in
      hermes | openclaw | deepagents-code)
        M_AGENT="$owner"
        if metrics_openshell; then HARNESS_AGENT="$owner"; fi
        return 0 ;;
    esac
  fi
  if metrics_openshell; then
    # Whether the sandbox exists is checked by the verbs: disable and show must
    # still work when it is gone.
    M_AGENT="$(canonical_agent_name "${HARNESS_AGENT:-openclaw}")"
    HARNESS_AGENT="$M_AGENT"
    case "$M_AGENT" in
      openclaw | hermes | deepagents-code) return 0 ;;
      *) M_SKIP_REASON="no telemetry support for the selected harness (${M_AGENT})" ;;
    esac
    return 1
  fi
  M_AGENT="$(resolve_installed_agent)"
  case "$M_AGENT" in
    hermes | openclaw | deepagents-code) ;;
    *)
      M_SKIP_REASON="no telemetry support for the selected harness (${M_AGENT})"
      return 1 ;;
  esac
  return 0
}

metrics_check_plugin_source() {
  [[ "$HARNESS_HERMES_OTEL_PLUGIN" =~ ^[A-Za-z0-9_][A-Za-z0-9._-]*(/[A-Za-z0-9_][A-Za-z0-9._-]*){0,2}$ ]] \
    || error "HARNESS_HERMES_OTEL_PLUGIN must be a plugin name or <owner>/<repo>[/<plugin>] (got '${HARNESS_HERMES_OTEL_PLUGIN}')."
  [[ -z "$HARNESS_HERMES_OTEL_REF" || "$HARNESS_HERMES_OTEL_REF" =~ ^[0-9a-f]{40}$ ]] \
    || error "HARNESS_HERMES_OTEL_REF must be a full 40-character lowercase commit SHA (got '${HARNESS_HERMES_OTEL_REF}')."
}

metrics_install_hermes_otel_plugin() {
  local home plugin_dir
  metrics_check_plugin_source
  local -a ref_args=()
  if [[ -n "$HARNESS_HERMES_OTEL_REF" ]]; then
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
      "# Regenerated by './install.sh observability enable'; edit settings through that command."
    # "off" must stay quoted: bare off is a YAML 1.1 boolean.
    printf 'content_capture: "%s"\n' "$content"
    if [[ "$backend" == jaeger ]]; then
      printf 'backends:\n  - type: jaeger\n    endpoint: "%s"\n' "$endpoint"
      [[ "$managed" != true ]] || printf '    query_port: %s\n' "$HARNESS_JAEGER_UI_PORT"
    fi
  } >"$tmp" || { rm -f "$tmp"; error "Could not write ${cfg}."; }
  chmod 600 "$tmp"
  mv -f "$tmp" "$cfg"
}

# ---------------------------------------------------------------------------
# dcode: agent-harness OpenTelemetry extension
# ---------------------------------------------------------------------------

metrics_dcode_extension_file() { printf '%s/extensions/agent_harness_otel.py' "$(metrics_dcode_home)"; }
metrics_dcode_settings_file() { printf '%s/agent-harness-otel.json' "$(metrics_dcode_home)"; }
metrics_dcode_env_file() { printf '%s/.env' "$(metrics_dcode_home)"; }
METRICS_DCODE_SETTINGS_MARK='"managed_by": "agent-harness-install (metrics)"'

# metrics_dcode_python -- the Python of dcode's own environment (the extension
# runs inside it), when it can be found next to the dcode executable.
metrics_dcode_python() {
  local bin
  bin="$(command -v dcode 2>/dev/null)" || return 1
  bin="$(readlink -f "$bin" 2>/dev/null)" || return 1
  if [[ -x "${bin%/*}/python" ]]; then
    printf '%s' "${bin%/*}/python"
    return 0
  fi
  return 1
}

# Fails before any side effect when dcode cannot run the extension.
metrics_check_dcode_environment() {
  local py
  command_exists dcode || error "dcode not found on PATH. Install it first: ./install.sh --harness deepagents-code --model <model>"
  if py="$(metrics_dcode_python)"; then
    "$py" -c 'import langchain_core, opentelemetry.sdk.trace, opentelemetry.exporter.otlp.proto.http.trace_exporter' >/dev/null 2>&1 \
      || error "dcode's Python environment (${py%/*}) lacks langchain-core, opentelemetry-sdk or opentelemetry-exporter-otlp-proto-http, which the telemetry extension needs."
  else
    warn "Could not find dcode's Python environment, so its langchain-core and OpenTelemetry packages were not checked; without them the telemetry extension stays inactive."
  fi
}

# Fails before any side effect if the extension, its settings or the profile .env cannot be written.
metrics_check_dcode_paths() {
  local home path
  home="$(metrics_dcode_home)"
  [[ -d "$home" && ! -L "$home" ]] || error "dcode data directory ${home} not found or is a symlink."
  [[ ! -L "${home}/extensions" ]] || error "Refusing to write through a symlink: ${home}/extensions"
  path="$(metrics_dcode_extension_file)"
  [[ ! -L "$path" ]] || error "Refusing to write through a symlink: ${path}"
  if [[ -e "$path" ]] && ! grep -Fq "$METRICS_CONFIG_MARKER" "$path"; then
    error "${path} exists and is not managed by this installer; move it aside and re-run."
  fi
  path="$(metrics_dcode_settings_file)"
  [[ ! -L "$path" ]] || error "Refusing to write through a symlink: ${path}"
  if [[ -e "$path" ]] && ! grep -Fq "$METRICS_DCODE_SETTINGS_MARK" "$path"; then
    error "${path} exists and is not managed by this installer; move it aside and re-run."
  fi
  path="$(metrics_dcode_env_file)"
  [[ ! -L "$path" ]] || error "Refusing to write through a symlink: ${path}"
}

# metrics_dcode_env_set <on|off> -- adds or removes the installer's block in the
# profile .env (dcode reads DEEPAGENTS_CODE_EXPERIMENTAL from it); the rest of the file is kept.
metrics_dcode_env_set() {
  local envf tmp
  envf="$(metrics_dcode_env_file)"
  tmp="$(mktemp "${envf}.tmp.XXXXXX")" || error "Could not write ${envf}."
  if [[ -f "$envf" ]]; then
    awk -v b="$METRICS_DCODE_ENV_BEGIN" -v e="$METRICS_DCODE_ENV_END" \
      '{ line = $0; sub(/\r$/, "", line) } line == b { skip = 1; next } line == e { skip = 0; next } !skip' "$envf" >"$tmp" \
      || { rm -f "$tmp"; error "Could not rewrite ${envf}."; }
    chmod --reference="$envf" "$tmp" 2>/dev/null || chmod 600 "$tmp"
  else
    chmod 600 "$tmp"
  fi
  if [[ "$1" == on ]]; then
    # A last line without a newline would otherwise swallow the marker.
    if [[ -s "$tmp" && -n "$(tail -c 1 "$tmp")" ]]; then printf '\n' >>"$tmp"; fi
    printf '%s\nDEEPAGENTS_CODE_EXPERIMENTAL=1\n%s\n' "$METRICS_DCODE_ENV_BEGIN" "$METRICS_DCODE_ENV_END" >>"$tmp"
  fi
  if [[ "$1" == off ]] && ! grep -q '[^[:space:]]' "$tmp"; then
    rm -f -- "$tmp" "$envf"
  else
    mv -f "$tmp" "$envf"
  fi
}

# metrics_write_dcode_config <backend> <endpoint> <content> -- installs the
# extension, its settings and the .env switch. dcode picks them up on its next start.
metrics_write_dcode_config() {
  local backend="$1" endpoint="$2" content="$3" home ext settings tmp traces
  metrics_check_dcode_paths
  [[ -f "$METRICS_DCODE_EXTENSION_SRC" ]] || error "Missing ${METRICS_DCODE_EXTENSION_SRC}."
  home="$(metrics_dcode_home)"
  ext="$(metrics_dcode_extension_file)"
  settings="$(metrics_dcode_settings_file)"
  if [[ "$backend" == sqlite ]]; then
    traces="http://127.0.0.1:${HARNESS_OTLP_RECEIVER_PORT}/v1/traces"
  else
    traces="$endpoint"
  fi
  mkdir -p -- "${home}/extensions"
  tmp="$(mktemp "${ext}.tmp.XXXXXX")" || error "Could not write ${ext}."
  cp -- "$METRICS_DCODE_EXTENSION_SRC" "$tmp" || { rm -f "$tmp"; error "Could not write ${ext}."; }
  chmod 600 "$tmp"
  mv -f "$tmp" "$ext"
  tmp="$(mktemp "${settings}.tmp.XXXXXX")" || error "Could not write ${settings}."
  # endpoint and content were validated (plain http(s) URL, fixed words), so they are safe to embed.
  printf '{\n  %s,\n  "enabled": true,\n  "endpoint": "%s",\n  "content": "%s"\n}\n' \
    "$METRICS_DCODE_SETTINGS_MARK" "$traces" "$content" >"$tmp" \
    || { rm -f "$tmp"; error "Could not write ${settings}."; }
  chmod 600 "$tmp"
  mv -f "$tmp" "$settings"
  metrics_dcode_env_set on
}

# Removes only what this installer wrote. Also used by the uninstaller, so
# --keep-agent-data does not leave an exporter behind.
metrics_remove_dcode_managed() {
  local home path
  home="$(metrics_dcode_home)"
  [[ -d "$home" && ! -L "$home" ]] || return 0
  path="$(metrics_dcode_extension_file)"
  if [[ -f "$path" && ! -L "$path" ]] && grep -Fq "$METRICS_CONFIG_MARKER" "$path"; then rm -f -- "$path"; fi
  path="$(metrics_dcode_settings_file)"
  if [[ -f "$path" && ! -L "$path" ]] && grep -Fq "$METRICS_DCODE_SETTINGS_MARK" "$path"; then rm -f -- "$path"; fi
  path="$(metrics_dcode_env_file)"
  if [[ -f "$path" && ! -L "$path" ]] && grep -Fq "$METRICS_DCODE_ENV_BEGIN" "$path"; then metrics_dcode_env_set off; fi
}

# ---------------------------------------------------------------------------
# OTLP receiver (OpenClaw with --backend sqlite)
# ---------------------------------------------------------------------------

metrics_receiver_pidfile() { printf '%s/metrics-otlp-receiver.pid' "$(harness_state_root)"; }
metrics_receiver_logfile() { printf '%s/metrics-otlp-receiver.log' "$(harness_state_root)"; }

# metrics_receiver_pid -- prints the pid of this installer's receiver when it is
# alive (the pidfile alone is not trusted: the pid may have been reused).
metrics_receiver_pid() {
  local pidfile pid
  pidfile="$(metrics_receiver_pidfile)"
  [[ -f "$pidfile" && ! -L "$pidfile" ]] || return 1
  pid="$(cat "$pidfile" 2>/dev/null)" || return 1
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  tr '\0' ' ' <"/proc/${pid}/cmdline" 2>/dev/null | grep -Fq "metrics-otlp-receiver" || return 1
  printf '%s' "$pid"
}

metrics_receiver_check() {
  command_exists curl || error "curl is required to check the local OTLP receiver behind --backend sqlite."
  command_exists python3 || error "python3 is required for the local OTLP receiver behind --backend sqlite.
Install it, or use --backend jaeger."
  python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' \
    || error "python3 >= 3.8 is required for the local OTLP receiver behind --backend sqlite."
  [[ -f "$METRICS_RECEIVER_SCRIPT" ]] || error "Missing ${METRICS_RECEIVER_SCRIPT}."
  if [[ ! "$HARNESS_OTLP_RECEIVER_PORT" =~ ^[0-9]+$ ]] || (( HARNESS_OTLP_RECEIVER_PORT < 1 || HARNESS_OTLP_RECEIVER_PORT > 65535 )); then
    error "HARNESS_OTLP_RECEIVER_PORT must be between 1 and 65535 (got '${HARNESS_OTLP_RECEIVER_PORT}')."
  fi
  if [[ ! "$HARNESS_OTLP_RECEIVER_MAX_ROWS" =~ ^[0-9]+$ ]]; then
    error "HARNESS_OTLP_RECEIVER_MAX_ROWS must be a number (got '${HARNESS_OTLP_RECEIVER_MAX_ROWS}')."
  fi
}

# metrics_receiver_healthy -- true when something answers on the receiver port.
metrics_receiver_healthy() {
  command_exists curl || return 1
  curl --noproxy '*' -sf --max-time 3 "http://127.0.0.1:${HARNESS_OTLP_RECEIVER_PORT}/healthz" >/dev/null 2>&1
}

metrics_receiver_stop() {
  local pid
  pid="$(metrics_receiver_pid)" || { rm -f -- "$(metrics_receiver_pidfile)"; return 0; }
  kill "$pid" 2>/dev/null || true
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.5
  done
  if kill -0 "$pid" 2>/dev/null; then
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f -- "$(metrics_receiver_pidfile)"
  ok "OTLP receiver stopped"
}

# metrics_receiver_start <agent> <store> <content> -- (re)starts the receiver
# detached from this shell, listening on 127.0.0.1 only. It does not survive a
# reboot; 'observability enable' starts it again.
metrics_receiver_start() {
  local agent="$1" store="$2" content="$3" log
  metrics_receiver_check
  metrics_receiver_stop
  if metrics_receiver_healthy; then
    error "Port ${HARNESS_OTLP_RECEIVER_PORT} is already served by another process; set HARNESS_OTLP_RECEIVER_PORT to a free port."
  fi
  ensure_state_dir >/dev/null
  [[ ! -L "$store" ]] || error "Refusing to write through a symlink: ${store}"
  mkdir -p -- "$(dirname "$store")"
  log="$(metrics_receiver_logfile)"
  [[ ! -L "$log" ]] || error "Refusing to write through a symlink: ${log}"
  # fd 200 is the deployment/state lock (see with_deployment_lock): a daemon that
  # inherited it would hold the lock, and block every later command, until it exits.
  nohup setsid python3 "$METRICS_RECEIVER_SCRIPT" --port "$HARNESS_OTLP_RECEIVER_PORT" --db "$store" \
    --agent "$agent" --content "$content" --max-rows "$HARNESS_OTLP_RECEIVER_MAX_ROWS" \
    --pidfile "$(metrics_receiver_pidfile)" >"$log" 2>&1 </dev/null 200>&- &
  disown 2>/dev/null || true
  for _ in $(seq 1 20); do
    metrics_receiver_healthy && break
    sleep 0.5
  done
  metrics_receiver_healthy || error "The OTLP receiver did not start; see ${log}."
  ok "OTLP receiver listening on 127.0.0.1:${HARNESS_OTLP_RECEIVER_PORT} (store: ${store})"
}

# metrics_agent_otlp_base <backend> <endpoint> -- base URL the agent's exporter
# gets (it appends /v1/traces itself, unlike the hermes-otel plugin).
metrics_agent_otlp_base() {
  local base
  if metrics_openshell; then
    # The sandbox reaches host loopback services through this alias. The
    # managed Jaeger is one of them; an external --endpoint is used as given.
    if [[ "$1" == sqlite ]]; then
      printf 'http://host.openshell.internal:%s' "$HARNESS_OTLP_RECEIVER_PORT"
      return 0
    fi
    if [[ "$2" == "http://127.0.0.1:${HARNESS_JAEGER_OTLP_PORT}/v1/traces" ]]; then
      printf 'http://host.openshell.internal:%s' "$HARNESS_JAEGER_OTLP_PORT"
      return 0
    fi
  fi
  if [[ "$1" == sqlite ]]; then
    printf 'http://127.0.0.1:%s' "$HARNESS_OTLP_RECEIVER_PORT"
    return 0
  fi
  base="${2%/}"
  printf '%s' "${base%/v1/traces}"
}

# ---------------------------------------------------------------------------
# OpenClaw: @openclaw/diagnostics-otel plugin
# ---------------------------------------------------------------------------

# Changing OpenClaw's config or plugins needs the Gateway stopped ('openclaw
# config set' refuses otherwise and 'plugins install' stalls on its lock).
METRICS_OPENCLAW_GATEWAY_HINT="If the OpenClaw Gateway is running, stop it first ('openclaw gateway stop'), re-run this command, then start the Gateway again."

# Runs the OpenClaw CLI with a time limit. Plain 'timeout' moves the command into
# its own background process group; OpenClaw touches the terminal, so the kernel
# stops it (SIGTTIN/SIGTTOU) and the install hangs. --foreground keeps it in the
# terminal's group, and stdin from /dev/null stops it waiting on a prompt.
metrics_openclaw_run() {
  local seconds="$1"
  shift
  timeout --foreground -k 10 "$seconds" openclaw "$@" </dev/null
}

metrics_openclaw_plugin_spec() {
  local spec="$HARNESS_OPENCLAW_OTEL_PLUGIN" version
  if [[ -z "$spec" ]]; then
    version="$(installed_npm_global_version openclaw 2>/dev/null || true)"
    [[ -n "$version" ]] \
      || error "Cannot tell which OpenClaw version is installed; set HARNESS_OPENCLAW_OTEL_PLUGIN to an npm spec such as @openclaw/diagnostics-otel@<version>."
    spec="@openclaw/diagnostics-otel@${version}"
  fi
  [[ "$spec" =~ ^@?[A-Za-z0-9._/-]+(@[A-Za-z0-9._-]+)?$ ]] \
    || error "HARNESS_OPENCLAW_OTEL_PLUGIN must be an npm package spec (got '${spec}')."
  printf '%s' "$spec"
}

# Fails before any side effect when a diagnostics exporter that this installer
# did not configure is already set up: enabling would overwrite it.
metrics_check_openclaw_otel_config() {
  local current rc=0
  [[ "$(metrics_state_get harness.agent)" == openclaw && "$(metrics_state_get harness.enabled)" == true ]] && return 0
  current="$(metrics_openclaw_run 60 config get diagnostics.otel.enabled --json 2>/dev/null)" || rc=$?
  # Another non-zero exit is taken as 'not set'; a timeout (124, or 137 after -k) must not pass as that.
  (( rc != 124 && rc != 137 )) \
    || error "Timed out reading OpenClaw's diagnostics.otel.enabled. ${METRICS_OPENCLAW_GATEWAY_HINT}"
  [[ "$current" != true ]] \
    || error "OpenClaw already has diagnostics.otel enabled that this installer did not set up; it is not overwritten.
Disable it ('openclaw config set diagnostics.otel.enabled false --strict-json') and re-run."
}

metrics_install_openclaw_otel_plugin() {
  local spec rc=0
  spec="$(metrics_openclaw_plugin_spec)"
  # Not piped: with pipefail, grep -q closing early would fail the listing and force a reinstall.
  if ! grep -Fq '"diagnostics-otel"' <<<"$(metrics_openclaw_run 60 plugins list --json 2>/dev/null || true)"; then
    info "Installing the OpenClaw diagnostics-otel plugin (${spec})"
    metrics_openclaw_run 300 plugins install "$spec" --accept-capabilities || rc=$?
    if (( rc != 0 )); then
      # A bare spec is resolved on ClawHub first, which some networks block;
      # 'npm:' goes straight to the npm registry the spec names.
      warn "Install from ClawHub failed; retrying from the npm registry (npm:${spec})"
      rc=0
      metrics_openclaw_run 300 plugins install "npm:${spec}" --accept-capabilities || rc=$?
    fi
    (( rc == 0 )) || error "'openclaw plugins install ${spec}' failed (rc=${rc}; see output above).
${METRICS_OPENCLAW_GATEWAY_HINT}"
  fi
  # A previous 'disable' leaves the plugin installed but disabled.
  metrics_openclaw_run 120 plugins enable diagnostics-otel >/dev/null \
    || error "'openclaw plugins enable diagnostics-otel' failed (see above).
${METRICS_OPENCLAW_GATEWAY_HINT}"
}

# metrics_write_openclaw_otel_config <backend> <endpoint> <content>
metrics_write_openclaw_otel_config() {
  local backend="$1" endpoint="$2" content="$3" base capture=false json
  base="$(metrics_agent_otlp_base "$backend" "$endpoint")"
  [[ "$content" == off ]] || capture=true
  json="{\"enabled\":true,\"otel\":{\"enabled\":true,\"endpoint\":\"${base}\",\"protocol\":\"http/protobuf\",\"serviceName\":\"openclaw\",\"traces\":true,\"metrics\":false,\"logs\":false,\"captureContent\":${capture},\"flushIntervalMs\":1000}}"
  metrics_openclaw_run 120 config set diagnostics "$json" --strict-json --merge >/dev/null \
    || error "'openclaw config set diagnostics' failed.
${METRICS_OPENCLAW_GATEWAY_HINT}"
}

metrics_disable_openclaw() {
  # Only an exporter this installer enabled is turned off; one the user set up
  # themselves is left alone even when its plugin is installed.
  [[ "$(metrics_state_get harness.enabled)" == true && "$(metrics_state_get harness.agent)" == openclaw ]] || return 0
  command_exists openclaw \
    || error "OpenClaw CLI not found on PATH, so its telemetry cannot be disabled and may keep exporting.
Run 'openclaw config set diagnostics.otel.enabled false --strict-json' yourself or fix PATH, then retry."
  command_exists timeout || error "'timeout' (coreutils) is required."
  metrics_openclaw_run 120 config set diagnostics.otel.enabled false --strict-json >/dev/null \
    || error "'openclaw config set diagnostics.otel.enabled false' failed; telemetry may still be exported.
${METRICS_OPENCLAW_GATEWAY_HINT}"
  # Best effort: the exporter is already off, but a later manual re-enable must not capture content.
  metrics_openclaw_run 120 config set diagnostics.otel.captureContent false --strict-json >/dev/null 2>&1 || true
  metrics_openclaw_run 120 plugins disable diagnostics-otel >/dev/null 2>&1 || true
}

# metrics_harness_owner -- the agent whose exporter this installer has enabled
# (empty when none). State from before agents were recorded means Hermes.
metrics_harness_owner() {
  local owner
  if [[ "$(metrics_state_get harness.enabled)" == true ]]; then
    owner="$(metrics_state_get harness.agent)"
    printf '%s' "${owner:-hermes}"
  fi
}

# Disable and show act on the recorded owner, not on whichever agent is selected now.
metrics_adopt_harness_owner() {
  local owner
  owner="$(metrics_harness_owner)"
  if [[ -n "$owner" && "$owner" != "$M_AGENT" ]]; then
    info "Harness telemetry is enabled for $(agent_display_name "$owner"), not $(agent_display_name "$M_AGENT"); using that."
    M_AGENT="$owner"
    if metrics_openshell; then HARNESS_AGENT="$owner"; fi
  fi
}

# Fails before any side effect unless the agent's sandbox can be instrumented.
metrics_openshell_preflight() {
  openshell_load_profile
  openshell_resource_exists sandbox \
    || error "The $(agent_display_name "$M_AGENT") sandbox does not exist. Install it first: ./install.sh --runtime openshell --harness ${M_AGENT} --model <model>"
  openshell_assert_owned
  openshell_ensure_ready
  metrics_os_exec check "$M_AGENT" \
    || error "The sandbox cannot be instrumented (see above)."
}

metrics_enable_harness_preflight() {
  local owner recorded
  export PATH="$HOME/.local/bin:$PATH"
  if recorded="$(metrics_runtime_mismatch)"; then
    error "Harness telemetry is enabled for the ${recorded} runtime; disable it first ('./install.sh observability disable --target harness --runtime ${recorded}')."
  fi
  owner="$(metrics_harness_owner)"
  if [[ -n "$owner" && "$owner" != "$M_AGENT" ]]; then
    error "Harness telemetry is enabled for $(agent_display_name "$owner"); disable it first ('./install.sh observability disable --target harness'), then enable it for $(agent_display_name "$M_AGENT")."
  fi
  if metrics_openshell; then
    metrics_openshell_preflight
  else
    case "$M_AGENT" in
      hermes)
        command_exists hermes || error "Hermes CLI not found on PATH. Install it first: ./install.sh --harness hermes --model <model>" ;;
      openclaw)
        command_exists openclaw || error "OpenClaw CLI not found on PATH. Install it first: ./install.sh --harness openclaw --model <model>"
        command_exists timeout || error "'timeout' (coreutils) is required."
        metrics_check_openclaw_otel_config ;;
      deepagents-code)
        metrics_check_dcode_environment
        metrics_check_dcode_paths ;;
    esac
  fi
  metrics_resolve_harness_settings
  if metrics_openshell && [[ "$H_BACKEND" == jaeger && "$H_MANAGED" != true ]]; then
    metrics_openshell_check_endpoint "$H_ENDPOINT"
  fi
  if [[ "$M_AGENT" == hermes ]] && ! metrics_openshell; then
    metrics_check_plugin_source
    metrics_check_hermes_otel_config_path
  elif [[ "$H_BACKEND" == sqlite ]]; then
    metrics_receiver_check
  fi
  if [[ "$H_MANAGED" == true ]]; then
    metrics_jaeger_preflight
  fi
}

metrics_enable_harness() {
  local backend endpoint content managed prev_managed prev_kept kept runtime=host
  if metrics_openshell; then runtime=openshell; fi
  metrics_enable_harness_preflight
  backend="$H_BACKEND" endpoint="$H_ENDPOINT" content="$H_CONTENT" managed="$H_MANAGED"
  prev_managed="$(metrics_state_get harness.managed_jaeger)"
  prev_kept="$(metrics_state_get harness.kept_jaeger)"
  if [[ "$backend" == sqlite && "$M_AGENT" == hermes ]] && ! metrics_openshell; then
    local stray
    stray="$(compgen -e | grep -E '^(HERMES_OTEL_|OTEL_[A-Z]+_ENDPOINT$|OTEL_EXPORTER_)' | tr '\n' ' ' || true)"
    [[ -z "$stray" ]] || warn "Exporter variables set in this shell (${stray% }) may make Hermes export traces even with --backend sqlite."
  fi
  case "$M_AGENT" in
    hermes) if ! metrics_openshell; then metrics_install_hermes_otel_plugin; fi ;;
    openclaw) if ! metrics_openshell; then metrics_install_openclaw_otel_plugin; fi ;;
  esac
  if [[ "$managed" == true ]]; then
    metrics_ensure_jaeger
    # Recorded at once so 'observability disable' can clean up if a later step fails.
    metrics_state_set harness.managed_jaeger true harness.kept_jaeger false
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
  case "$M_AGENT" in
    hermes | openclaw)
      if metrics_openshell; then
        # Recorded before the first change, so a failed enable can still be disabled.
        metrics_state_set harness.enabled true harness.agent "$M_AGENT" harness.runtime openshell
        metrics_enable_openshell_sandbox "$backend" "$endpoint" "$content"
      elif [[ "$M_AGENT" == hermes ]]; then
        metrics_write_hermes_otel_config "$backend" "$endpoint" "$content" "$managed"
      else
        # Recorded before the first change, so a failed enable can still be disabled.
        metrics_state_set harness.enabled true harness.agent openclaw harness.runtime "$runtime"
        # The receiver is up before the agent is pointed at it, so no span is lost.
        if [[ "$backend" == sqlite ]]; then
          metrics_receiver_start "$M_AGENT" "$(metrics_harness_store "$M_AGENT")" "$content"
        fi
        metrics_write_openclaw_otel_config "$backend" "$endpoint" "$content"
        if [[ "$backend" != sqlite ]]; then metrics_receiver_stop; fi
      fi ;;
    deepagents-code)
      # Recorded before the first change, so a failed enable can still be disabled.
      metrics_state_set harness.enabled true harness.agent deepagents-code harness.runtime "$runtime"
      if metrics_openshell; then
        metrics_enable_openshell_sandbox "$backend" "$endpoint" "$content"
      else
        # The receiver is up before dcode is pointed at it, so no span is lost.
        if [[ "$backend" == sqlite ]]; then
          metrics_receiver_start "$M_AGENT" "$(metrics_harness_store "$M_AGENT")" "$content"
        fi
        metrics_write_dcode_config "$backend" "$endpoint" "$content"
        if [[ "$backend" != sqlite ]]; then metrics_receiver_stop; fi
      fi ;;
  esac
  kept=false
  if [[ "$managed" != true ]]; then
    if [[ "$prev_managed" == true ]]; then
      # Switching away from a Jaeger that was in use.
      if ! metrics_jaeger_in_use_by router; then metrics_remove_jaeger; fi
    elif [[ "$prev_kept" == true ]]; then
      # Left running on purpose by 'observability disable --keep-jaeger'; only an
      # explicit disable (or uninstall) may remove it and its traces.
      kept=true
      info "Kept the managed Jaeger (${HARNESS_JAEGER_CONTAINER}) left by 'observability disable --keep-jaeger'; remove it with './install.sh observability disable --target harness'."
    fi
  fi
  metrics_state_set harness.enabled true harness.agent "$M_AGENT" harness.backend "$backend" \
    harness.endpoint "$endpoint" harness.content "$content" harness.managed_jaeger "$managed" harness.kept_jaeger "$kept" \
    harness.runtime "$runtime"
  ok "Harness telemetry enabled for $(agent_display_name "$M_AGENT") (backend: ${backend}, content: ${content})"
  case "$M_AGENT" in
    hermes)
      if metrics_openshell; then
        info "The Hermes gateway inside the sandbox was restarted to apply this; the next Hermes turn exports spans.
Send a message ('./install.sh connect --runtime openshell --harness hermes') and verify with: ./install.sh observability show --target harness --runtime openshell"
      else
        info "Run 'hermes gateway restart' now: a Hermes process that was already running (the gateway, or the plugin host it relaunches) loads the plugin's Python dependencies only after a restart, and until then every turn reports '[hermes-otel] OpenTelemetry packages not available'.
Then start a new session and verify with: ./install.sh observability show --target harness"
      fi ;;
    openclaw)
      if metrics_openshell; then
        info "The sandbox was restarted to apply this (a running OpenClaw session in it was ended).
Send a message ('./install.sh connect --runtime openshell --harness openclaw') and verify with: ./install.sh observability show --target harness --runtime openshell"
      else
        info "Start (or restart) the OpenClaw Gateway to apply this: only the running Gateway exports spans, 'openclaw agent --local' does not.
Then send a message and verify with: ./install.sh observability show --target harness"
      fi ;;
    deepagents-code)
      if metrics_openshell; then
        info "Start dcode in the sandbox again to apply this (extensions load only at start): ./install.sh connect --runtime openshell --harness deepagents-code
Then chat and verify with: ./install.sh observability show --target harness --runtime openshell"
      else
        info "Restart dcode to apply this (a running session loads extensions only at start, or on /restart).
Then chat and verify with: ./install.sh observability show --target harness
The telemetry extension is experimental dcode functionality: it is switched on through DEEPAGENTS_CODE_EXPERIMENTAL=1 in $(metrics_dcode_env_file), which dcode reads at start."
      fi ;;
  esac
}

# metrics_openshell_host_port <url> -- prints "<host> <port>" of an http(s) URL
# (port 80/443 by scheme when omitted).
metrics_openshell_host_port() {
  local url="$1" scheme authority
  scheme="${url%%://*}"
  authority="${url#*://}"
  authority="${authority%%/*}"
  if [[ "$authority" =~ ^(.+):([0-9]+)$ ]]; then
    printf '%s %s\n' "${BASH_REMATCH[1]}" "$((10#${BASH_REMATCH[2]}))"
  elif [[ "$scheme" == https ]]; then
    printf '%s 443\n' "$authority"
  else
    printf '%s 80\n' "$authority"
  fi
}

# metrics_openshell_check_endpoint <url> -- an external collector must be
# reachable from inside the sandbox, which cannot see this host's loopback.
metrics_openshell_check_endpoint() {
  local host
  read -r host _ < <(metrics_openshell_host_port "$1")
  case "$host" in
    127.* | localhost | 0.0.0.0 | \[*)
      error "--endpoint ${host} cannot be reached from inside the sandbox (loopback and IPv6 literals are not supported). Use a hostname or IPv4 address of the collector, host.openshell.internal for a collector on this machine, or omit --endpoint for the managed Jaeger." ;;
  esac
}

# metrics_enable_openshell_sandbox <backend> <endpoint> <content> -- points the
# agent inside its sandbox at the host collector. The receiver (or Jaeger) is up
# and the policy rule is in place before the agent is told to export, so no span
# is lost or blocked.
metrics_enable_openshell_sandbox() {
  local backend="$1" endpoint="$2" content="$3" base host port traces
  base="$(metrics_agent_otlp_base "$backend" "$endpoint")"
  read -r host port < <(metrics_openshell_host_port "$base")
  if [[ "$backend" == sqlite ]]; then
    metrics_receiver_start "$M_AGENT" "$(metrics_harness_store "$M_AGENT")" "$content"
  fi
  openshell_allow_host_port "$METRICS_OS_RULE" "$port" "$host"
  ok "Sandbox egress allowed to ${host}:${port}"
  case "$M_AGENT" in
    hermes | deepagents-code)
      # Both exporters take the full traces URL; an external one is used exactly as given.
      traces="${base}/v1/traces"
      if [[ "$backend" != sqlite && "$endpoint" != "http://127.0.0.1:${HARNESS_JAEGER_OTLP_PORT}/v1/traces" ]]; then
        traces="${endpoint%/}"
      fi
      if [[ "$M_AGENT" == hermes ]]; then
        metrics_os_exec hermes-enable "$traces" "$content" \
          || error "Could not write Hermes's exporter settings inside the sandbox (see above)."
      else
        metrics_os_exec dcode-enable "$traces" "$content" \
          || error "Could not install the dcode telemetry extension inside the sandbox (see above)."
      fi ;;
    openclaw)
      metrics_os_exec openclaw-stage on "$base" "$content" \
        || error "Could not stage OpenClaw's exporter settings inside the sandbox (see above)."
      info "Restarting the sandbox so OpenClaw loads the exporter settings"
      openshell_restart_sandbox
      metrics_openshell_wait_openclaw on "$base" ;;
  esac
  if [[ "$backend" != sqlite ]]; then metrics_receiver_stop; fi
}

# metrics_openshell_wait_openclaw <on|off> [base] -- waits for the restarted
# sandbox's start script to have applied the staged OpenClaw settings and its gateway to accept connections.
metrics_openshell_wait_openclaw() {
  local applied=false deadline
  deadline=$((SECONDS + 60))
  while :; do
    if metrics_os_exec openclaw-verify "$@" >/dev/null 2>&1; then applied=true; break; fi
    (( SECONDS < deadline )) || break
    sleep 2
  done
  [[ "$applied" == true ]] \
    || error "OpenClaw did not apply the telemetry settings after the sandbox restart; inspect it with './install.sh connect --runtime openshell --harness openclaw'."
  deadline=$((SECONDS + 60))
  while :; do
    if metrics_os_exec openclaw-gateway-ready >/dev/null 2>&1; then return 0; fi
    (( SECONDS < deadline )) || break
    sleep 2
  done
  warn "The OpenClaw gateway in the sandbox is not accepting connections yet; retry in a moment."
}

metrics_disable_hermes() {
  local home cfg
  home="$(metrics_hermes_home)"
  cfg="${home}/hermes_otel.yaml"
  if [[ -d "${home}/plugins/hermes_otel" ]] \
    && { [[ "$(metrics_state_get harness.enabled)" == true ]] \
      || { [[ -f "$cfg" && ! -L "$cfg" ]] && grep -Fq "$METRICS_CONFIG_MARKER" "$cfg"; }; }; then
    command_exists hermes \
      || error "Hermes CLI not found on PATH, so the hermes-otel plugin cannot be disabled and may keep collecting telemetry.
Run 'hermes plugins disable hermes_otel' yourself or fix PATH, then retry."
    if ! hermes plugins disable hermes_otel; then
      # Only a listing that positively says "disabled" lets a failed command pass
      # (it may fail simply because the plugin was already turned off by hand).
      hermes plugins list 2>/dev/null | grep -i 'hermes_otel' | grep -Eiq 'disabled|not enabled' \
        || error "'hermes plugins disable hermes_otel' failed (see above); the plugin may still be collecting telemetry. Fix it and retry."
      info "hermes_otel is already disabled."
    fi
  fi
  metrics_remove_managed_config
}

metrics_disable_harness() {
  local keep_jaeger=false endpoint store recorded
  export PATH="$HOME/.local/bin:$PATH"
  if recorded="$(metrics_runtime_mismatch)"; then
    error "Harness telemetry is enabled for the ${recorded} runtime; disable it with './install.sh observability disable --target harness --runtime ${recorded}'."
  fi
  metrics_adopt_harness_owner
  store="$(metrics_harness_store "$M_AGENT")"
  endpoint="$(metrics_state_get harness.endpoint)"
  # Nothing is removed or recorded until the exporter is really off: a failure
  # here must leave the state as it was so the command can be retried.
  if metrics_openshell; then
    metrics_disable_openshell_sandbox
  else
    case "$M_AGENT" in
      hermes) metrics_disable_hermes ;;
      openclaw) metrics_disable_openclaw ;;
      deepagents-code) metrics_remove_dcode_managed ;;
    esac
  fi
  if [[ "$M_AGENT" != hermes ]] || metrics_openshell; then metrics_receiver_stop; fi
  if [[ "$(metrics_state_get harness.managed_jaeger)" == true || "$(metrics_state_get harness.kept_jaeger)" == true ]]; then
    if [[ -n "${M_KEEP_JAEGER:-}" ]]; then
      keep_jaeger=true
      info "Kept managed Jaeger (${HARNESS_JAEGER_CONTAINER}) and its traces: http://127.0.0.1:${HARNESS_JAEGER_UI_PORT}"
      info "Remove it later with './install.sh observability disable --target harness' or uninstall."
    elif metrics_jaeger_in_use_by router; then
      metrics_info_jaeger_stays router
    else
      metrics_remove_jaeger
    fi
  elif [[ -n "${M_CLEAN:-}" && -n "$endpoint" ]]; then
    info "Traces already exported to ${endpoint} are not removed; clear them in that backend."
  fi
  metrics_state_set harness.enabled false harness.managed_jaeger false harness.kept_jaeger "$keep_jaeger"
  if [[ -n "${M_CLEAN:-}" ]]; then
    if metrics_clean_harness_store "$store"; then
      ok "Harness telemetry disabled and collected data cleaned"
    else
      warn "Harness telemetry disabled, but its collected data was not cleaned (see above)."
    fi
  else
    ok "Harness telemetry disabled (exporter $([[ "$M_AGENT" == deepagents-code ]] && echo removed || echo 'left installed'); its local store was kept; add --clean to delete it)"
  fi
  case "$M_AGENT" in
    hermes)
      if metrics_openshell; then info "The Hermes gateway inside the sandbox was restarted to apply this."
      else info "Restart running Hermes sessions/gateways to apply."; fi ;;
    openclaw) if ! metrics_openshell; then info "Restart the OpenClaw Gateway to apply."; fi ;;
    deepagents-code) info "The dcode telemetry extension and its settings were removed; restart dcode to apply." ;;
  esac
}

# Turns the exporter off inside the sandbox and withdraws its egress rule. A
# sandbox that is already gone has nothing left to turn off.
metrics_disable_openshell_sandbox() {
  local dir
  dir="$(openshell_profile_dir)"
  if [[ ! -f "$dir/profile.json" ]]; then
    warn "No OpenShell profile for $(agent_display_name "$M_AGENT"); nothing to turn off inside a sandbox."
    return 0
  fi
  openshell_load_profile
  if ! openshell_resource_exists sandbox; then
    warn "The $(agent_display_name "$M_AGENT") sandbox no longer exists; nothing to turn off inside it."
    return 0
  fi
  openshell_assert_owned
  openshell_ensure_ready
  case "$M_AGENT" in
    openclaw)
      # Only an exporter this installer enabled is turned off, as on the host.
      if [[ "$(metrics_state_get harness.enabled)" == true ]]; then
        metrics_os_exec openclaw-stage off \
          || error "Could not stage turning OpenClaw's exporter off inside the sandbox (see above)."
        info "Restarting the sandbox so OpenClaw stops exporting"
        openshell_restart_sandbox
        metrics_openshell_wait_openclaw off
      fi ;;
    hermes)
      # Only an exporter this installer enabled is turned off, as on the host.
      if [[ "$(metrics_state_get harness.enabled)" == true ]]; then
        metrics_os_exec hermes-disable \
          || error "Could not turn Hermes's exporter off inside the sandbox (see above)."
      fi ;;
    deepagents-code)
      if [[ "$(metrics_state_get harness.enabled)" == true ]]; then
        metrics_os_exec dcode-disable \
          || error "Could not remove the dcode telemetry extension inside the sandbox (see above)."
      fi ;;
  esac
  openshell_remove_policy_rule "$METRICS_OS_RULE"
}

# Empties the SQLite store in place (rows, not the file): a running agent (the
# Hermes gateway) keeps the file open in WAL mode, and unlinking it would leave
# that process writing to a deleted inode.
metrics_clean_harness_store() {
  local store="$1" count
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
  local rc=0
  count="$(python3 - "$store" <<'PY'
import sqlite3, sys

con = sqlite3.connect(sys.argv[1], timeout=10)
try:
    n = 0
    busy = 0
    if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='events'").fetchone():
        n = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        con.execute("DELETE FROM events")
        con.commit()
        # Reports a busy checkpoint (first column 1) instead of raising, and a
        # busy one leaves the deleted rows' text in the WAL file.
        busy = con.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]
    print(n)
    if busy:
        sys.exit(3)
except sqlite3.Error as e:
    print(f"{type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(1)
finally:
    con.close()
PY
  )" || rc=$?
  case "$rc" in
    0) ok "Cleaned ${count} records from the local store (${store})" ;;
    3)
      warn "Deleted ${count} records from the local store, but another process (a running Hermes?) holds it open, so the write-ahead log (${store}-wal) may still contain their text.
Close Hermes sessions/gateways and run the clean again, or delete ${store}* manually."
      return 1 ;;
    *)
      warn "Could not clean the local store (${store}); it may be locked or from another plugin version."
      return 1 ;;
  esac
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

# The plugin reports a failed load only in Hermes's own error log; with the
# store empty that is the one place that says why. A later successful load is
# logged to agent.log instead, so the two are compared by their timestamps.
metrics_show_harness_plugin_errors() {
  local logs="$1/logs" failed="" loaded=""
  [[ -d "$logs" && ! -L "$logs" ]] || return 0
  if [[ -f "$logs/errors.log" && ! -L "$logs/errors.log" ]]; then
    failed="$(grep -E '\[hermes-otel\] .*(packages not available|import error)' "$logs/errors.log" 2>/dev/null | tail -n 1 || true)"
  fi
  [[ -n "$failed" ]] || return 0
  if [[ -f "$logs/agent.log" && ! -L "$logs/agent.log" ]]; then
    loaded="$(grep -F '[hermes-otel] Registered' "$logs/agent.log" 2>/dev/null | tail -n 1 || true)"
  fi
  # Lines start with "YYYY-MM-DD HH:MM:SS,mmm", so string order is time order.
  [[ "${loaded:0:23}" < "${failed:0:23}" ]] || return 0
  warn "The last Hermes process to load the plugin could not import its dependencies (${logs}/errors.log):
  $(printf '%s' "$failed" | tr -cd '[:print:]' | cut -c1-200)
Run 'hermes gateway restart', start a new session, and check again."
}

metrics_show_harness_agent() {
  local home="$1" plugin_line
  if metrics_openshell; then
    metrics_show_harness_sandbox
    return 0
  fi
  case "$M_AGENT" in
    hermes)
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
      fi ;;
    openclaw)
      if command_exists openclaw; then
        if grep -Fq '"diagnostics-otel"' <<<"$(metrics_openclaw_run 60 plugins list --json 2>/dev/null || true)"; then
          ok "diagnostics-otel plugin installed"
        else
          info "diagnostics-otel plugin not installed"
        fi
        info "diagnostics.otel.enabled: $(metrics_openclaw_run 60 config get diagnostics.otel.enabled --json 2>/dev/null || echo unknown)"
      else
        info "OpenClaw CLI not found on PATH"
      fi ;;
    deepagents-code)
      if [[ -f "$(metrics_dcode_extension_file)" ]] && grep -Fq "$METRICS_CONFIG_MARKER" "$(metrics_dcode_extension_file)"; then
        ok "dcode telemetry extension installed ($(metrics_dcode_extension_file))"
        info "Settings: $(metrics_dcode_settings_file)"
      else
        info "dcode telemetry extension not installed (checked $(metrics_dcode_extension_file); set DEEPAGENTS_HOME if dcode uses another home)"
      fi
      if grep -Fq "$METRICS_DCODE_ENV_BEGIN" "$(metrics_dcode_env_file)" 2>/dev/null; then
        info "Extensions switched on through DEEPAGENTS_CODE_EXPERIMENTAL in $(metrics_dcode_env_file)"
      fi ;;
  esac
}

metrics_show_harness_sandbox() {
  local dir phase out line
  dir="$(openshell_profile_dir)"
  if [[ ! -f "$dir/profile.json" ]]; then
    info "No OpenShell sandbox installed for $(agent_display_name "$M_AGENT")"
    return 0
  fi
  openshell_load_profile
  if ! openshell_resource_exists sandbox; then
    info "The $(agent_display_name "$M_AGENT") sandbox no longer exists"
    return 0
  fi
  openshell_assert_owned
  phase="$(openshell_sandbox_phase)" || phase=unknown
  if [[ "$phase" != Ready ]]; then
    info "Sandbox ${OPENSHELL_NAME} is ${phase}; its exporter settings are read when it is Ready"
    return 0
  fi
  if out="$(metrics_os_exec status "$M_AGENT" 2>/dev/null)"; then
    while IFS= read -r line; do info "Sandbox: ${line}"; done <<<"$out"
  else
    info "Could not read the exporter settings inside the sandbox (an image from before telemetry support?)"
  fi
}

# Called when a sandbox is deleted: its exporter went with it, so the host-side
# receiver would only collect nothing and the state would claim it is enabled.
metrics_openshell_sandbox_removed() {
  [[ "$(metrics_state_get harness.enabled)" == true && "$(metrics_harness_runtime)" == openshell \
    && "$(metrics_state_get harness.agent)" == "$1" ]] || return 0
  metrics_receiver_stop
  metrics_state_set harness.enabled false
  info "Harness telemetry for the removed sandbox was switched off (collected data and any managed Jaeger were kept; './install.sh observability disable --target harness --runtime openshell --clean' removes them)."
}

metrics_show_harness_receiver() {
  local pid
  if pid="$(metrics_receiver_pid)" && metrics_receiver_healthy; then
    ok "OTLP receiver running (pid ${pid}, 127.0.0.1:${HARNESS_OTLP_RECEIVER_PORT})"
  elif [[ "$(metrics_state_get harness.enabled)" == true && "$(metrics_state_get harness.backend)" == sqlite ]]; then
    warn "OTLP receiver is not running (it does not survive a reboot); start it again with './install.sh observability enable --target harness'. Log: $(metrics_receiver_logfile)"
  fi
}

metrics_show_harness() {
  local home store enabled backend endpoint content size name recorded
  printf '\n%sHarness telemetry%s\n' "$C_BOLD" "$C_RESET"
  if ! metrics_harness_check show; then
    info "Not available: ${M_SKIP_REASON}."
    return 0
  fi
  export PATH="$HOME/.local/bin:$PATH"
  if recorded="$(metrics_runtime_mismatch)"; then
    info "Enabled for the ${recorded} runtime; add --runtime ${recorded} to inspect it."
    return 0
  fi
  metrics_adopt_harness_owner
  name="$(agent_display_name "$M_AGENT")"
  home="$(metrics_hermes_home)"
  enabled="$(metrics_state_get harness.enabled)"
  backend="$(metrics_state_get harness.backend)"
  endpoint="$(metrics_state_get harness.endpoint)"
  content="$(metrics_state_get harness.content)"
  if [[ "$enabled" == true ]]; then
    ok "Enabled for ${name} -- backend: ${backend:-sqlite}${endpoint:+ (${endpoint})}, content capture: ${content:-off}"
  else
    info "Disabled (enable with: ./install.sh observability enable --target harness)"
  fi
  metrics_show_harness_agent "$home"
  if [[ "$M_AGENT" != hermes ]] || metrics_openshell; then metrics_show_harness_receiver; fi
  store="$(metrics_harness_store "$M_AGENT")"
  if [[ "$enabled" == true && "$backend" == jaeger ]]; then
    info "Spans go to ${endpoint:-Jaeger}; the local store is not written with this backend${store:+ (${store})}"
  elif [[ -f "$store" ]]; then
    size="$(stat -c '%s' "$store" 2>/dev/null || echo 0)"
    # WAL mode keeps recent writes in the sidecar file, so count it too.
    [[ ! -f "${store}-wal" ]] || size=$(( size + $(stat -c '%s' "${store}-wal" 2>/dev/null || echo 0) ))
    info "Local store: ${store} (${size} bytes)"
    metrics_show_harness_store "$store"
  else
    info "Local store not created yet (${store}); it appears after the first ${name} turn"
  fi
  if [[ "$M_AGENT" == hermes && "$enabled" == true ]] && ! metrics_openshell; then metrics_show_harness_plugin_errors "$home"; fi
  if [[ "$enabled" == true && "$backend" != sqlite && "$(metrics_state_get harness.managed_jaeger)" != true && -n "$endpoint" ]]; then
    info "Full trace view: open the UI of the backend receiving ${endpoint}"
  fi
  if [[ "$(metrics_state_get harness.managed_jaeger)" == true || "$(metrics_state_get harness.kept_jaeger)" == true ]]; then
    if command_exists curl \
      && curl --noproxy '*' -sf --max-time 5 "http://127.0.0.1:${HARNESS_JAEGER_UI_PORT}/" >/dev/null 2>&1; then
      ok "Jaeger UI reachable: http://127.0.0.1:${HARNESS_JAEGER_UI_PORT}"
    else
      warn "Managed Jaeger (${HARNESS_JAEGER_CONTAINER}) is not reachable on port ${HARNESS_JAEGER_UI_PORT}"
    fi
  fi
  if [[ "$M_AGENT" == hermes ]] && ! metrics_openshell; then info "For the plugin's own details run: hermes plugins show hermes_otel"; fi
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

# metrics_router_file_mode -- the mode the telemetry file gets. 664 needs a
# private group the container can join; when the installer's primary group is
# root (0) there is none, and the file is never widened to 666 silently.
metrics_router_file_mode() {
  case "$HARNESS_IR_TELEMETRY_FILE_MODE" in
    664)
      [[ "$(metrics_router_host_gid)" != 0 ]] \
        || error "The installer's primary group is root, so the telemetry file has no private group the Router container could join, and 664 would give it to every root-group member.
Run as a regular user, or opt in to a world-writable file explicitly with HARNESS_IR_TELEMETRY_FILE_MODE=666."
      printf 664 ;;
    666) printf 666 ;;
    *) error "HARNESS_IR_TELEMETRY_FILE_MODE must be 664 or 666 (got '${HARNESS_IR_TELEMETRY_FILE_MODE}')." ;;
  esac
}

# metrics_router_file_group -- the host group id the Router container must join
# to append to the 664 file; prints nothing in 666 mode, or when the primary
# group is root (metrics_router_file_mode rejects that case when enabling).
# Safe to call from a plain install, which must not fail because of it.
metrics_router_file_group() {
  local gid
  [[ "$HARNESS_IR_TELEMETRY_FILE_MODE" == 664 ]] || return 0
  gid="$(metrics_router_host_gid)"
  [[ "$gid" == 0 ]] || printf '%s' "$gid"
  return 0
}

# Fails when an existing Router container was created without the group needed
# to write the 664 file (an install from before this setting existed).
metrics_router_check_container_group() {
  local group groups
  group="$(metrics_router_file_group)"
  [[ -n "$group" ]] || return 0
  metrics_container_exists "$HARNESS_IR_CONTAINER" || return 0
  groups="$(docker inspect -f '{{json .HostConfig.GroupAdd}}' "$HARNESS_IR_CONTAINER")" \
    || error "Cannot inspect the Inference Router container ${HARNESS_IR_CONTAINER}."
  [[ "$groups" == *"\"${group}\""* ]] \
    || error "The Inference Router container ${HARNESS_IR_CONTAINER} cannot write the telemetry file: it joined groups ${groups}, but the file's group is ${group}.
Option 1 (recommended): recreate the Router so it joins group ${group}. Re-run ./install.sh (or './install.sh inference --model <model>') with the same HARNESS_IR_PORT as the running Router (a different port would start a second one), then enable telemetry again.
Option 2: keep the current Router and make the file world-writable: HARNESS_IR_TELEMETRY_FILE_MODE=666 ./install.sh observability enable --target router"
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
If 'observability show' stays at zero events, set HARNESS_IR_TELEMETRY_FILE_MODE=666 and re-run ./install.sh to recreate the Router." ;;
  esac
}

# Checks everything metrics_router_prepare_file depends on, without touching
# the file, so enabling can fail before any state is changed.
metrics_router_validate_file_settings() {
  local file
  file="$(metrics_router_telemetry_file)"
  metrics_router_file_mode >/dev/null
  metrics_router_max_bytes_is_valid \
    || error "HARNESS_IR_TELEMETRY_MAX_BYTES must be a non-negative integer of at most 15 digits (got '${HARNESS_IR_TELEMETRY_MAX_BYTES}')."
  [[ ! -L "$file" && ! -L "${file}.1" ]] || error "Refusing to use a symlinked telemetry file: ${file}"
}

# At most 15 digits keeps the value inside Bash's 64-bit arithmetic.
metrics_router_max_bytes_is_valid() {
  [[ "$HARNESS_IR_TELEMETRY_MAX_BYTES" =~ ^[0-9]{1,15}$ ]]
}

metrics_router_prepare_file() {
  local file mode size max
  file="$(metrics_router_telemetry_file)"
  metrics_router_validate_file_settings
  mode="$(metrics_router_file_mode)"
  # 10# keeps a leading zero (e.g. 08) from being read as invalid octal.
  max=$((10#$HARNESS_IR_TELEMETRY_MAX_BYTES))
  mkdir -p "$(inference_router_workspace_dir)"
  # Rotated while the Router is stopped or about to restart, so nothing appends
  # to the moved file; the previous generation is replaced.
  if (( max > 0 )) && [[ -f "$file" ]]; then
    size="$(wc -c <"$file" | tr -d ' ')"
    if (( size > max )); then
      mv -f -- "$file" "${file}.1" || error "Could not rotate ${file}."
      chmod 600 "${file}.1" || error "Could not restrict ${file}.1."
      info "Rotated ${file} (${size} bytes) to ${file}.1; /v1/metrics counts only the new file."
    fi
  fi
  [[ -e "$file" ]] || : >"$file"
  # The container's uid never matches the host user's, and it must append to
  # this bind-mounted file. It holds counters/latencies, not prompt text.
  if [[ "$mode" == 664 ]]; then chgrp "$(metrics_router_host_gid)" "$file" 2>/dev/null || true; fi
  chmod "$mode" "$file"
}

# Docker is needed for any Router change; in OpenShell mode the Router must
# also stay loopback-only.
metrics_router_require_environment() {
  command_exists docker || error "Docker is required to apply Inference Router telemetry settings."
  if [[ "${HARNESS_RUNTIME:-host}" == openshell ]]; then
    [[ "$(resolve_bind_host)" == 127.0.0.1 ]] \
      || error "OpenShell mode requires HARNESS_BIND_HOST=127.0.0.1; inference must not be LAN-published."
  fi
}

# Everything about enabling the Router file backend that can be checked up
# front, with no side effects; also used before the harness is touched.
metrics_router_preflight() {
  metrics_router_require_environment
  metrics_router_validate_file_settings
  metrics_router_check_container_group
}

# ---------------------------------------------------------------------------
# Router telemetry bridge: ir_metrics.jsonl -> spans in SQLite or Jaeger
# ---------------------------------------------------------------------------

metrics_router_bridge_pidfile() { printf '%s/metrics-router-bridge.pid' "$(harness_state_root)"; }
metrics_router_bridge_logfile() { printf '%s/metrics-router-bridge.log' "$(harness_state_root)"; }
metrics_router_bridge_checkpoint() { printf '%s/metrics-router-bridge.json' "$(harness_state_root)"; }
metrics_router_store() { printf '%s/router-telemetry/ir_otel_live.db' "$(harness_state_root)"; }

# Prints the pid of this installer's bridge when it is alive (the pid alone is not trusted: it may be reused).
metrics_router_bridge_pid() {
  local pidfile pid
  pidfile="$(metrics_router_bridge_pidfile)"
  [[ -f "$pidfile" && ! -L "$pidfile" ]] || return 1
  pid="$(cat "$pidfile" 2>/dev/null)" || return 1
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  { tr '\0' ' ' <"/proc/${pid}/cmdline" 2>/dev/null || ps -p "$pid" -o args= 2>/dev/null; } \
    | grep -Fq "metrics-router-bridge" || return 1
  printf '%s' "$pid"
}

metrics_router_bridge_check() {
  command_exists python3 || error "python3 is required for the Router telemetry bridge (--backend sqlite|jaeger)."
  python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' \
    || error "python3 >= 3.8 is required for the Router telemetry bridge."
  [[ -f "$METRICS_BRIDGE_SCRIPT" ]] || error "Missing ${METRICS_BRIDGE_SCRIPT}."
  [[ "$HARNESS_ROUTER_BRIDGE_MAX_ROWS" =~ ^[0-9]+$ ]] \
    || error "HARNESS_ROUTER_BRIDGE_MAX_ROWS must be a number (got '${HARNESS_ROUTER_BRIDGE_MAX_ROWS}')."
}

# Combines the command line with the saved Router settings and sets R_BACKEND/R_ENDPOINT/R_MANAGED/R_CONTENT;
# changes no state. An empty R_BACKEND keeps the Router on its plain file backend. Only --target all adopts
# the sqlite default, so 'enable --target router' alone behaves as before. An --endpoint without a backend is
# an error here as for the harness, unless a saved jaeger backend is kept.
metrics_resolve_router_settings() {
  local given="${M_BACKEND_GIVEN:-}" given_endpoint="${M_ENDPOINT:-}" saved saved_endpoint saved_managed saved_content
  saved="$(metrics_state_get router.bridge)"
  saved_endpoint="$(metrics_state_get router.endpoint)"
  saved_managed="$(metrics_state_get router.managed_jaeger)"
  saved_content="$(metrics_state_get router.content)"
  R_BACKEND="" R_ENDPOINT="" R_MANAGED=false R_CONTENT="${M_CONTENT:-off}"
  if [[ -n "$given" ]]; then
    R_BACKEND="$M_BACKEND"
  elif [[ -n "$saved" ]]; then
    R_BACKEND="$saved"
  elif [[ "${M_TARGET:-router}" == all ]]; then
    R_BACKEND="${M_BACKEND:-sqlite}"
    if ! command_exists python3; then
      # The default must not make '--target all' fail on a host without python3.
      warn "python3 not found: the Router's spans are not exported (its telemetry stays in the JSONL file)."
      R_BACKEND=""
    fi
  fi
  if [[ -z "${M_CONTENT_GIVEN:-}" && "$R_BACKEND" == "$saved" ]]; then
    case "$saved_content" in off | preview | full) R_CONTENT="$saved_content" ;; esac
  fi
  case "$R_BACKEND" in
    "" | sqlite)
      [[ -z "$given_endpoint" ]] \
        || error "--endpoint needs an exporting backend; add --backend jaeger (sqlite exports nothing)."
      if [[ -z "$R_BACKEND" && -n "${M_CONTENT_GIVEN:-}" ]]; then
        error "--content applies to span export; add --backend sqlite or jaeger for the Router."
      fi ;;
    jaeger)
      R_ENDPOINT="$given_endpoint"
      if [[ -z "$R_ENDPOINT" && "$saved" == jaeger && "$saved_managed" != true && "$saved_endpoint" =~ $METRICS_ENDPOINT_RE ]]; then
        R_ENDPOINT="$saved_endpoint"
      fi
      if [[ -z "$R_ENDPOINT" ]]; then
        R_MANAGED=true
        R_ENDPOINT="http://127.0.0.1:${HARNESS_JAEGER_OTLP_PORT}/v1/traces"
      fi ;;
  esac
}

# Everything about the bridge that can be checked before any change is made.
metrics_router_bridge_preflight() {
  metrics_resolve_router_settings
  [[ -n "$R_BACKEND" ]] || return 0
  metrics_router_bridge_check
  if [[ "$R_MANAGED" == true ]]; then metrics_jaeger_preflight; fi
}

metrics_router_bridge_stop() {
  local pid
  pid="$(metrics_router_bridge_pid)" || { rm -f -- "$(metrics_router_bridge_pidfile)"; return 0; }
  kill "$pid" 2>/dev/null || true
  # The bridge makes one last pass over the file before it exits.
  for _ in $(seq 1 30); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.5
  done
  if kill -0 "$pid" 2>/dev/null; then
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f -- "$(metrics_router_bridge_pidfile)"
  ok "Router telemetry bridge stopped"
}

# Starts the bridge detached from this shell; it does not survive a reboot, 'observability enable' starts it again.
metrics_router_bridge_start() {
  local store log _
  local -a sink_args
  metrics_router_bridge_check
  metrics_router_bridge_stop
  ensure_state_dir >/dev/null
  log="$(metrics_router_bridge_logfile)"
  [[ ! -L "$log" && ! -L "$(metrics_router_bridge_checkpoint)" ]] \
    || error "Refusing to write through a symlink in the installer state directory."
  case "$R_BACKEND" in
    sqlite)
      store="$(metrics_router_store)"
      [[ ! -L "$store" ]] || error "Refusing to write through a symlink: ${store}"
      (umask 077 && mkdir -p -- "$(dirname "$store")")
      sink_args=(--db "$store" --max-rows "$HARNESS_ROUTER_BRIDGE_MAX_ROWS") ;;
    jaeger) sink_args=(--endpoint "$R_ENDPOINT") ;;
  esac
  # fd 200 is the deployment/state lock; a daemon that inherited it would hold the lock until it exits.
  (umask 077 && : >>"$log")
  nohup setsid python3 "$METRICS_BRIDGE_SCRIPT" --file "$(metrics_router_telemetry_file)" \
    --checkpoint "$(metrics_router_bridge_checkpoint)" --content "$R_CONTENT" "${sink_args[@]}" \
    --pidfile "$(metrics_router_bridge_pidfile)" >>"$log" 2>&1 </dev/null 200>&- &
  disown 2>/dev/null || true
  for _ in $(seq 1 20); do
    metrics_router_bridge_pid >/dev/null && break
    sleep 0.25
  done
  metrics_router_bridge_pid >/dev/null || error "The Router telemetry bridge did not start; see ${log}."
  ok "Router telemetry bridge running (backend: ${R_BACKEND}, content: ${R_CONTENT})"
}

metrics_router_apply() {
  local state="$1" prev
  metrics_router_require_environment
  prev="$(metrics_state_get router.enabled)"
  if [[ "$state" == true ]]; then
    metrics_router_preflight
    metrics_router_warn_if_remapped
    # Prepared before the choice is saved, so a failure here leaves the saved
    # state (which the next install honours) untouched.
    metrics_router_prepare_file
  fi
  metrics_state_set router.enabled "$state"
  if [[ ! -f "$(inference_router_workspace_dir)/config.yaml" ]]; then
    info "The Inference Router has no generated config yet; the setting applies on its next install."
    return 0
  fi
  with_state_lock inference-router-config _metrics_router_rewrite_config_locked \
    || { metrics_state_set router.enabled "${prev:-false}"; error "Could not update the Inference Router config."; }
  if metrics_container_exists "$HARNESS_IR_CONTAINER"; then
    docker restart "$HARNESS_IR_CONTAINER" >/dev/null \
      || error "Could not restart the Inference Router (${HARNESS_IR_CONTAINER}); config was updated."
    wait_for_inference_router_ready || true
  else
    info "The Inference Router container is not installed; the setting applies on its next install."
  fi
}

metrics_enable_router() {
  local prev_managed prev_enabled prev_bridge prev_endpoint prev_content jaeger_existed=false was_running=false rc=0
  prev_enabled="$(metrics_state_get router.enabled)"
  prev_bridge="$(metrics_state_get router.bridge)"
  prev_endpoint="$(metrics_state_get router.endpoint)"
  prev_content="$(metrics_state_get router.content)"
  if metrics_router_bridge_pid >/dev/null; then was_running=true; fi
  metrics_router_apply true
  ok "Router telemetry enabled: persisted to $(metrics_router_telemetry_file)"
  if [[ -z "${R_BACKEND:-}" ]]; then
    metrics_router_bridge_stop
    return 0
  fi
  prev_managed="$(metrics_state_get router.managed_jaeger)"
  if metrics_container_exists "$HARNESS_JAEGER_CONTAINER"; then jaeger_existed=true; fi
  # errexit is off around the subshell so a failure is reported through rc and can be rolled back.
  set +e
  ( set -e; metrics_router_start_export "$prev_managed" )
  rc=$?
  set -e
  if (( rc != 0 )); then
    warn "The Router span export could not be started; reverting the changes made by this command."
    set +e
    (
      set -e
      metrics_router_bridge_stop
      if [[ "$R_MANAGED" == true && "$jaeger_existed" != true ]] && ! metrics_jaeger_in_use_by harness; then
        metrics_remove_jaeger
      fi
      metrics_state_set router.bridge "$prev_bridge" router.endpoint "$prev_endpoint" router.content "$prev_content" \
        router.managed_jaeger "${prev_managed:-false}"
      if [[ "$prev_enabled" != true ]]; then
        metrics_router_apply false
        metrics_router_secure_file
      fi
    )
    set -e
    # The old bridge was stopped to start the new one; bring it back so span export is not lost.
    if [[ "$was_running" == true && -n "$prev_bridge" ]]; then
      R_BACKEND="$prev_bridge" R_ENDPOINT="$prev_endpoint" R_CONTENT="${prev_content:-off}"
      ( metrics_router_bridge_start ) \
        || warn "The previous Router telemetry bridge could not be restarted; run 'observability enable --target router'."
    fi
    exit "$rc"
  fi
  if [[ "$R_BACKEND" == jaeger ]]; then
    info "Router spans (service inference-router) go to ${R_ENDPOINT}; each request is one trace, written after it completes."
  else
    info "Router spans are stored in $(metrics_router_store)"
  fi
}

# metrics_router_start_export <previous router.managed_jaeger> -- Jaeger (when managed), saved state, then the bridge.
metrics_router_start_export() {
  local prev_managed="$1"
  if [[ "$R_MANAGED" == true ]]; then
    metrics_ensure_jaeger
    # Recorded at once so 'observability disable' can clean up if a later step fails.
    metrics_state_set router.managed_jaeger true router.kept_jaeger false
  fi
  metrics_state_set router.bridge "$R_BACKEND" router.endpoint "$R_ENDPOINT" router.content "$R_CONTENT"
  metrics_router_bridge_start
  if [[ "$R_MANAGED" != true ]]; then
    metrics_state_set router.managed_jaeger false
    if [[ "$prev_managed" == true ]] && ! metrics_jaeger_in_use_by harness; then
      # Switching away from a Jaeger that was in use.
      metrics_remove_jaeger
    fi
  fi
}

# Stops the bridge and gives up the managed Jaeger unless the harness (or --keep-jaeger) still needs it.
metrics_router_bridge_disable() {
  local owns keep=false
  owns=false
  if metrics_jaeger_in_use_by router; then owns=true; fi
  metrics_router_bridge_stop
  [[ -n "$(metrics_state_get router.bridge)" || "$owns" == true ]] || return 0
  if [[ "$owns" == true ]]; then
    if [[ -n "${M_KEEP_JAEGER:-}" ]]; then
      keep=true
      info "Kept managed Jaeger (${HARNESS_JAEGER_CONTAINER}) and its traces: http://127.0.0.1:${HARNESS_JAEGER_UI_PORT}"
    elif metrics_jaeger_in_use_by harness; then
      metrics_info_jaeger_stays harness
    else
      metrics_remove_jaeger
    fi
  fi
  metrics_state_set router.bridge "" router.managed_jaeger false router.kept_jaeger "$keep"
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
  # Stopped after the Router went back to memory, so its last events are forwarded.
  metrics_router_bridge_disable
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

# Empties ir_metrics.jsonl in place. Runs after the restart that switched the
# Router back to memory, so nothing is appending to it; the restart also reset
# the in-memory counters.
metrics_clean_router() {
  local file lines
  file="$(metrics_router_telemetry_file)"
  if [[ -L "$file" || -L "${file}.1" ]]; then
    warn "Refusing to clean a symlinked telemetry file: ${file}"
    return 1
  fi
  local store
  store="$(metrics_router_store)"
  rm -f -- "$(metrics_router_bridge_checkpoint)"
  if [[ -f "$store" ]]; then metrics_clean_harness_store "$store" || return 1; fi
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

metrics_show_router_bridge() {
  local backend endpoint pid ckpt size file store
  local -a ck
  backend="$(metrics_state_get router.bridge)"
  if [[ -z "$backend" ]]; then
    info "No span export (add it with: ./install.sh observability enable --target router --backend <sqlite|jaeger>)"
    return 0
  fi
  endpoint="$(metrics_state_get router.endpoint)"
  ok "Span export enabled -- backend: ${backend}${endpoint:+ (${endpoint})}, detail capture: $(metrics_state_get router.content)"
  if pid="$(metrics_router_bridge_pid)"; then
    ok "Router telemetry bridge running (pid ${pid})"
  else
    warn "Router telemetry bridge is not running (it does not survive a reboot); start it again with './install.sh observability enable --target router'. Log: $(metrics_router_bridge_logfile)"
  fi
  ckpt="$(metrics_router_bridge_checkpoint)"
  file="$(metrics_router_telemetry_file)"
  if [[ -f "$ckpt" && -f "$file" ]] && command_exists node; then
    mapfile -t ck < <(node -e '
      try {
        const s = JSON.parse(require("node:fs").readFileSync(process.argv[1], "utf8"));
        console.log(Number(s.offset) || 0);
        console.log(Number(s.spans) || 0);
        console.log(String(s.error || "").replace(/[^\x20-\x7e]/g, "?").slice(0, 200));
        console.log(Number(s.dropped) || 0);
        console.log(String(s.drop_reason || "").replace(/[^\x20-\x7e]/g, "?").slice(0, 200));
      } catch {}
    ' "$ckpt" 2>/dev/null || true)
    if [[ "${#ck[@]}" -ge 2 ]]; then
      size="$(wc -c <"$file" 2>/dev/null | tr -d ' ' || echo 0)"
      info "Forwarded ${ck[1]} spans; read ${ck[0]} of ${size} bytes of the events file"
      [[ -z "${ck[2]:-}" ]] || warn "Last export error: ${ck[2]}"
      [[ "${ck[3]:-0}" == 0 ]] \
        || warn "${ck[3]} spans were refused by the collector and dropped (last: ${ck[4]:-unknown}); check the endpoint and the bridge log: $(metrics_router_bridge_logfile)"
    fi
  fi
  if [[ "$backend" == sqlite ]]; then
    store="$(metrics_router_store)"
    if [[ -f "$store" ]]; then
      info "Local store: ${store}"
      metrics_show_harness_store "$store"
    else
      info "Local store not created yet (${store}); it appears after the first Router request"
    fi
  elif [[ "$(metrics_state_get router.managed_jaeger)" == true || "$(metrics_state_get router.kept_jaeger)" == true ]]; then
    if command_exists curl \
      && curl --noproxy '*' -sf --max-time 5 "http://127.0.0.1:${HARNESS_JAEGER_UI_PORT}/" >/dev/null 2>&1; then
      ok "Jaeger UI reachable: http://127.0.0.1:${HARNESS_JAEGER_UI_PORT} (service inference-router)"
    else
      warn "Managed Jaeger (${HARNESS_JAEGER_CONTAINER}) is not reachable on port ${HARNESS_JAEGER_UI_PORT}"
    fi
  elif [[ -n "$endpoint" ]]; then
    info "Full trace view: open the UI of the backend receiving ${endpoint} (service inference-router)"
  fi
}

metrics_show_router() {
  local cfg probe_host json file lines
  printf '\n%sInference Router telemetry%s\n' "$C_BOLD" "$C_RESET"
  cfg="$(inference_router_workspace_dir)/config.yaml"
  if [[ "$(metrics_state_get router.enabled)" == true ]]; then
    ok "Persistent collection enabled (file backend)"
  else
    info "Persistent collection disabled (in-memory counters only; enable with: ./install.sh observability enable --target router)"
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
    if metrics_router_max_bytes_is_valid && (( 10#$HARNESS_IR_TELEMETRY_MAX_BYTES > 0 && bytes > 10#$HARNESS_IR_TELEMETRY_MAX_BYTES )); then
      warn "The events file exceeds ${HARNESS_IR_TELEMETRY_MAX_BYTES} bytes and slows /v1/metrics; it is rotated to ${METRICS_ROUTER_JSONL_NAME}.1 on the next install or 'observability enable', or empty it now with 'observability disable --target router --clean'."
    fi
  fi
  [[ ! -f "${file}.1" ]] || info "Rotated events file: ${file}.1 (not counted in /v1/metrics)"
  metrics_show_router_bridge
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
  # shellcheck disable=SC2016  # JavaScript template literals, not shell expansions
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
  [[ -n "$verb" ]] || { usage; error "observability requires a verb (enable/disable/show)."; }
  shift
  case "$verb" in
    enable | disable | show) ;;
    *) usage; error "Unknown observability verb: ${verb}" ;;
  esac
  metrics_parse_args "$verb" "$@"
  set +u
  ensure_nvm_loaded
  set -u
  command_exists node || error "Node.js is required (used for the installer's JSON state handling)."

  if [[ "$verb" == show ]]; then
    if metrics_wants harness; then metrics_show_harness; fi
    if metrics_wants router; then metrics_show_router; fi
    printf '\n'
    return 0
  fi

  local run_harness=""
  if metrics_wants harness; then
    if metrics_harness_check "$verb"; then
      run_harness=1
    elif [[ "$M_TARGET" == harness ]]; then
      error "${M_SKIP_REASON}."
    else
      warn "Skipping the harness: ${M_SKIP_REASON}."
    fi
  fi

  if [[ "$verb" == enable ]]; then
    # Every predictable failure is checked before either target is changed, so
    # '--target all' cannot half-apply on a bad option or an unusable Router.
    if [[ -n "$run_harness" ]]; then metrics_enable_harness_preflight; fi
    if metrics_wants router; then metrics_router_preflight; metrics_router_bridge_preflight; fi
    metrics_enable_all "$run_harness"
  else
    # A harness failure must not keep the Router from being disabled.
    local rc=0
    if [[ -n "$run_harness" ]]; then
      set +e
      ( set -e; metrics_disable_harness )
      rc=$?
      set -e
    fi
    if metrics_wants router; then metrics_disable_router; fi
    [[ "$rc" -eq 0 ]] || return "$rc"
  fi
  printf '\n'
}

# metrics_enable_all <run_harness> -- applies the Router first, then the harness
# (which has more steps that can still fail, such as fetching the plugin); if
# the harness fails, a Router change made by this command is undone.
metrics_enable_all() {
  local run_harness="$1" prev_router="" prev_bridge="" rc=0
  if metrics_wants router; then
    prev_router="$(metrics_state_get router.enabled)"
    prev_bridge="$(metrics_state_get router.bridge)"
    metrics_enable_router
  fi
  [[ -n "$run_harness" ]] || return 0
  # errexit is switched off around the subshell so that its own failures are
  # reported through rc instead of being masked by the caller's context.
  set +e
  ( set -e; metrics_enable_harness )
  rc=$?
  set -e
  if (( rc != 0 )); then
    if metrics_wants router && [[ "$prev_router" != true ]]; then
      warn "Harness telemetry could not be enabled; reverting the Router telemetry change made by this command."
      set +e
      ( set -e; metrics_router_apply false; metrics_router_bridge_disable; metrics_router_secure_file )
      set -e
    elif metrics_wants router && [[ -z "$prev_bridge" && -n "$(metrics_state_get router.bridge)" ]]; then
      warn "Harness telemetry could not be enabled; stopping the Router span export added by this command."
      set +e
      ( set -e; metrics_router_bridge_disable )
      set -e
    fi
    exit "$rc"
  fi
}
