# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=bash

HARNESS_RUNTIME="${HARNESS_RUNTIME:-}"
HARNESS_OPENSHELL_VERSION="0.1.5"
HARNESS_OPENSHELL_INSTALL_SHA256="7bf6706741b8b59c1b61e0c47030f0a34fefba6cee3c74cd52638cbf7cdc3655"

load_openshell_node() {
  if ! command_exists node; then
    set +u
    ensure_nvm_loaded
    set -u
  fi
  command_exists node || error "Node.js is required for OpenShell profile handling; run ./startup.sh."
}

validate_runtime() {
  case "${HARNESS_RUNTIME:-host}" in
    host) ;;
    openshell)
      case "$(canonical_agent_name "${HARNESS_AGENT:-openclaw}")" in
        openclaw | hermes) ;;
        *) error "OpenShell supports openclaw and hermes only; use --runtime host for this agent." ;;
      esac ;;
    *) error "Unknown runtime '${HARNESS_RUNTIME}'; expected host or openshell." ;;
  esac
}

select_runtime() {
  if [[ -z "$HARNESS_RUNTIME" && -z "${NON_INTERACTIVE:-}" && -t 0 ]]; then
    local answer
    printf '  Runtime [host/openshell] (default: host): '
    IFS= read -r answer || error "Could not read runtime selection."
    HARNESS_RUNTIME="${answer:-host}"
  fi
  HARNESS_RUNTIME="${HARNESS_RUNTIME:-host}"
  validate_runtime
}

openshell_apply_model_defaults() {
  [[ "${HARNESS_RUNTIME:-host}" == openshell ]] || return 0
  local selected_file profile source_file
  selected_file="$(harness_state_root)/openshell-model"
  profile="$(openshell_profile_dir)/profile.json"
  OPENSHELL_MODEL_REQUESTED="${HARNESS_HF_MODEL:+1}"
  if [[ "${HARNESS_HF_MODEL:-}" == Qwen3.5-9B-int8-ov && "$HARNESS_MODEL_HUB" == openvino ]]; then
    HARNESS_HF_MODEL=OpenVINO/Qwen3.5-9B-int8-ov
  fi
  source_file="$(harness_state_root)/openshell-model-source.json"
  assert_state_path_safe "$(harness_state_root)/openshell-model-pending.json"
  if [[ -f "$(harness_state_root)/openshell-model-pending.json" ]]; then
    source_file="$(harness_state_root)/openshell-model-pending.json"
    [[ -z "${HARNESS_HF_MODEL:-}${HARNESS_LLM_MODEL:-}" ]] \
      || error "A model transition is pending. Re-run install without --model to resume it before choosing another model."
  fi
  if [[ -z "${HARNESS_HF_MODEL:-}" && -z "${HARNESS_LLM_MODEL:-}" ]]; then
    if [[ -e "$source_file" || -L "$source_file" ]]; then
      openshell_restore_model_source "$source_file"
    elif [[ -e "$selected_file" || -L "$selected_file" ]]; then
      assert_state_path_safe "$selected_file"
      assert_owned_by_current_user "$selected_file"
      HARNESS_LLM_MODEL="$(cat "$selected_file")"
      [[ -n "$HARNESS_LLM_MODEL" && ! "$HARNESS_LLM_MODEL" =~ [[:cntrl:]] ]] \
        || error "Invalid saved OpenShell model selection: ${selected_file}"
    elif [[ -e "$profile" || -L "$profile" ]]; then
      load_openshell_node
      openshell_load_profile
      HARNESS_LLM_MODEL="$OPENSHELL_MODEL"
    elif [[ -z "${HARNESS_LLM_ROUTER_ENDPOINT:-}" && "$HARNESS_MODEL_HUB" == openvino ]] &&
         ! model_selection_satisfied; then
      HARNESS_HF_MODEL="OpenVINO/Qwen3.5-9B-int8-ov"
    fi
  fi
  # These weights are already OpenVINO IR; the snapshot exporter generates
  # the OVMS graph. Explicit exporter/hub choices still win.
  if [[ "${HARNESS_HF_MODEL:-}" == OpenVINO/Qwen3.5-9B-int8-ov &&
        -z "${HARNESS_OVMS_EXPORTER_WAS_SET:-}" && "$HARNESS_MODEL_HUB" == openvino ]]; then
    HARNESS_OVMS_EXPORTER=hf-snapshot
  fi
  if [[ -n "${HARNESS_HF_MODEL:-}" && -z "${HARNESS_LLM_MODEL:-}" ]]; then
    HARNESS_LLM_MODEL="$(model_dir_name "$HARNESS_HF_MODEL")"
  fi
  export HARNESS_HF_MODEL HARNESS_LLM_MODEL HARNESS_OVMS_EXPORTER
}

openshell_model_source() {
  node - "${HARNESS_HF_MODEL:-}" "${HARNESS_LLM_MODEL:-$(resolve_onboarding_model_hint)}" \
    "$HARNESS_MODEL_HUB" "$HARNESS_OVMS_EXPORTER" "${HARNESS_HF_MODEL_REVISION:-}" \
    "$HARNESS_MODEL_PRECISION" "$HARNESS_MODEL_DEVICE" "${HARNESS_MODEL_CONFIG_JSON:-}" \
    "${HARNESS_MODEL_TYPE:-}" "${HARNESS_MODEL_DOWNLOAD_REVISION:-}" <<'JS'
const keys = ["source", "model", "hub", "exporter", "revision", "precision", "device", "config", "type", "downloadRevision"];
const s = Object.fromEntries(keys.map((k, i) => [k, process.argv[i + 2]]));
if (s.config) s.config = JSON.stringify(JSON.parse(s.config));
console.log(JSON.stringify(s));
JS
}

openshell_restore_model_source() {
  local file="$1" fields
  load_openshell_node
  assert_state_path_safe "$file"
  assert_owned_by_current_user "$file"
  fields="$(node - "$file" <<'JS'
const s = JSON.parse(require("node:fs").readFileSync(process.argv[2], "utf8"));
const keys = ["source", "model", "hub", "exporter", "revision", "precision", "device", "config", "type", "downloadRevision"];
if (keys.some(k => typeof s[k] !== "string" || /[\x00-\x1f]/.test(s[k])) || !s.model)
  throw Error("Invalid saved model source");
console.log(keys.map(k => s[k]).join("\n") + "\nEND");
JS
  )" || error "Could not restore saved model source: ${file}"
  local -a values
  mapfile -t values <<<"$fields"
  HARNESS_HF_MODEL="${values[0]}"; HARNESS_LLM_MODEL="${values[1]}"
  HARNESS_MODEL_HUB="${values[2]}"; HARNESS_OVMS_EXPORTER="${values[3]}"
  HARNESS_HF_MODEL_REVISION="${values[4]}"; HARNESS_MODEL_PRECISION="${values[5]}"
  HARNESS_MODEL_DEVICE="${values[6]}"; HARNESS_MODEL_CONFIG_JSON="${values[7]}"
  HARNESS_MODEL_TYPE="${values[8]}"; HARNESS_MODEL_DOWNLOAD_REVISION="${values[9]}"
  export HARNESS_HF_MODEL HARNESS_LLM_MODEL HARNESS_MODEL_HUB HARNESS_OVMS_EXPORTER
  export HARNESS_HF_MODEL_REVISION HARNESS_MODEL_PRECISION HARNESS_MODEL_DEVICE
  export HARNESS_MODEL_CONFIG_JSON HARNESS_MODEL_TYPE HARNESS_MODEL_DOWNLOAD_REVISION
}

openshell_ensure_shared_inference() {
  with_state_lock openshell-inference _openshell_ensure_shared_inference
}

_openshell_ensure_shared_inference() {
  [[ "$(resolve_bind_host)" == 127.0.0.1 ]] \
    || error "OpenShell mode requires HARNESS_BIND_HOST=127.0.0.1; inference must not be LAN-published."
  local containers pending source model
  pending="$(harness_state_root)/openshell-model-pending.json"
  containers="$(docker container ls -a --format '{{.Names}}')" \
    || error "Cannot inspect shared inference containers; check the Docker daemon and permissions."
  if [[ -n "${OPENSHELL_MODEL_REQUESTED:-}" || -f "$pending" ]] ||
     ! grep -Fxq "$HARNESS_IR_CONTAINER" <<<"$containers"; then
    # Never reinterpret a partial/older installation as a fresh deployment.
    if [[ -z "${OPENSHELL_MODEL_REQUESTED:-}" && ! -f "$pending" ]] &&
       { grep -Fxq "$HARNESS_OVMS_CONTAINER" <<<"$containers" ||
       [[ -f "${HARNESS_MODELS_DIR}/config.json" ||
          -f "$(harness_state_root)/openshell-model" ||
          -d "$(harness_state_root)/openshell" ]]; }; then
      error "Shared inference is incomplete. Repair it explicitly with ./install.sh inference --runtime openshell --model <model>."
    fi
    openshell_preflight_model_update
    source="$(openshell_model_source)"
    atomic_write_file "$(ensure_state_dir)/openshell-model-pending.json" "$source"
    ensure_inference_backend
  fi
  openshell_validate_shared_inference
  if [[ -z "${HARNESS_LLM_ROUTER_ENDPOINT:-}" ]]; then
    openshell_validate_managed_backend
    model="${HARNESS_LLM_MODEL:-$(resolve_onboarding_model_hint)}"
    [[ -n "$model" && ! "$model" =~ [[:cntrl:]] ]] || error "Invalid OpenShell model selection."
  fi
  openshell_sync_models
  source="$(openshell_model_source)"
  atomic_write_file "$(ensure_state_dir)/openshell-model-source.json" "$source"
  atomic_write_file "$(harness_state_root)/openshell-model" \
    "${HARNESS_LLM_MODEL:-$(resolve_onboarding_model_hint)}"
  rm -f -- "$pending"
}

openshell_preflight_model_update() {
  local agent HARNESS_AGENT
  for agent in openclaw hermes; do
    HARNESS_AGENT="$agent"
    [[ -f "$(openshell_profile_dir)/profile.json" ]] || continue
    openshell_load_profile
    if openshell_resource_exists sandbox; then
      openshell_assert_owned
      local phase
      phase="$(openshell sandbox get "$OPENSHELL_NAME" -g "$OPENSHELL_GATEWAY" -o json \
        | node -e 'let d="";process.stdin.on("data",x=>d+=x).on("end",()=>console.log(JSON.parse(d).phase))')" \
        || error "Cannot inspect sandbox before model update."
      if [[ "$phase" == Stopped ]]; then
        openshell sandbox start "$OPENSHELL_NAME" -g "$OPENSHELL_GATEWAY" \
          || error "Cannot resume stopped sandbox during model transition."
        openshell_wait_phase Ready
      fi
      openshell_agent_exec /usr/bin/test -f /opt/harness/model-config.mjs \
        || error "Sandbox ${OPENSHELL_NAME} predates restart-safe model updates. Upgrade its image before changing shared inference; no model change was made."
    fi
  done
}

openshell_wait_phase() {
  local expected="$1" phase attempt
  for attempt in {1..90}; do
    phase="$(openshell sandbox get "$OPENSHELL_NAME" -g "$OPENSHELL_GATEWAY" -o json \
      | node -e 'let d="";process.stdin.on("data",x=>d+=x).on("end",()=>console.log(JSON.parse(d).phase))')" \
      || error "Cannot read sandbox phase during model update."
    [[ "$phase" != "$expected" ]] || return 0
    sleep 2
  done
  error "Sandbox ${OPENSHELL_NAME} did not reach ${expected}; model transition retained for retry."
}

openshell_sync_models() {
  local agent dir profile model endpoint HARNESS_AGENT
  model="${HARNESS_LLM_MODEL:-$(resolve_onboarding_model_hint)}"
  endpoint="http://host.openshell.internal:${HARNESS_IR_PORT}/v1"
  for agent in openclaw hermes; do
    HARNESS_AGENT="$agent"
    dir="$(openshell_profile_dir)"
    [[ -f "$dir/profile.json" ]] || continue
    openshell_load_profile
    [[ "$OPENSHELL_MODEL" != "$model" ]] || continue
    if openshell_resource_exists sandbox; then
      openshell_assert_owned
      openshell_agent_exec /usr/bin/test -f /opt/harness/model-config.mjs \
        || error "Sandbox ${OPENSHELL_NAME} needs a restart-safe image before its model can be changed."
      openshell_agent_exec /usr/local/bin/node --input-type=module - "$agent" "$model" "$endpoint" select \
        <"${SCRIPT_DIR}/openshell/model-config.mjs" \
        || error "Could not persist ${agent}'s model configuration; re-run install without --model."
      openshell sandbox stop "$OPENSHELL_NAME" -g "$OPENSHELL_GATEWAY" \
        || error "Could not stop ${agent} for its model update."
      openshell_wait_phase Stopped
      openshell sandbox start "$OPENSHELL_NAME" -g "$OPENSHELL_GATEWAY" \
        || error "Could not restart ${agent}; model transition retained for retry."
      openshell_wait_phase Ready
      openshell_agent_exec /usr/local/bin/node -e '
        const fs = require("node:fs");
        const [agent, model] = process.argv.slice(1);
        (async () => {
          for (let attempt = 0; attempt < 90; attempt++) {
            const s = JSON.parse(fs.readFileSync(`${process.env.HOME}/.harness-model.json`, "utf8"));
            if (s.model !== model) throw Error("Sandbox selection did not persist");
            if (s.applied === true) {
              if (agent === "openclaw") {
                const c = JSON.parse(fs.readFileSync(`${process.env.HOME}/.openclaw/openclaw.json`, "utf8"));
                if (c.agents?.defaults?.model?.primary !== `ovms/${model}` ||
                    c.models?.providers?.ovms?.models?.[0]?.id !== model)
                  throw Error("OpenClaw did not apply its selected model after restart");
              }
              return;
            }
            await new Promise(resolve => setTimeout(resolve, 2000));
          }
          throw Error("Agent startup did not apply the selected model within 180 seconds");
        })().catch(error => { console.error(error.message); process.exitCode = 1; });
      ' "$agent" "$model" || error "Agent model did not survive restart; pending transition retained."
    fi
    profile="$(node - "$dir/profile.json" "$model" <<'JS'
const fs = require("node:fs");
const p = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
p.model = process.argv[3];
console.log(JSON.stringify(p));
JS
    )" || error "Could not update ${agent}'s profile."
    atomic_write_file "$dir/profile.json" "$profile"
  done
}

openshell_validate_managed_backend() {
  local records model
  records="$(docker inspect "$HARNESS_OVMS_CONTAINER" "$HARNESS_IR_CONTAINER")" \
    || error "Installer-managed OVMS/IR containers are unavailable."
  model="${HARNESS_LLM_MODEL:-$(resolve_onboarding_model_hint)}"
  node - "$HARNESS_OVMS_REST_PORT" "$HARNESS_BACKEND_NETWORK" "$model" "$records" <<'JS' \
    || error "Managed OVMS validation failed; repair shared inference explicitly."
const [port, network, model, input] = process.argv.slice(2);
async function validate() {
  const [ovms, ir] = JSON.parse(input);
  const bindings = ovms?.HostConfig?.PortBindings?.["8000/tcp"];
  if (!Array.isArray(bindings) || !bindings.length ||
      bindings.some(b => b.HostIp !== "127.0.0.1" || b.HostPort !== port))
    throw Error("OVMS must be published only on the expected host loopback port");
  if (!ovms.NetworkSettings?.Networks?.[network] || !ir?.NetworkSettings?.Networks?.[network])
    throw Error("OVMS and IR must share the configured private backend network");
  const r = await fetch(`http://127.0.0.1:${port}/v2/models/${encodeURIComponent(model)}/ready`,
    {signal: AbortSignal.timeout(10000)});
  if (!r.ok) throw Error(`OVMS model '${model}' is not ready (HTTP ${r.status})`);
}
validate().catch(e => { console.error(e.message); process.exitCode = 1; });
JS
}

openshell_profile_dir() {
  local agent
  agent="$(canonical_agent_name "${HARNESS_AGENT:-openclaw}")"
  case "$agent" in openclaw | hermes) ;; *) error "Unsupported OpenShell agent: $agent" ;; esac
  printf '%s/openshell/%s' "$(harness_state_root)" "$agent"
}

ensure_openshell_cli() {
  if ! command_exists openshell; then
    command_exists apt-get || error "Automatic OpenShell provisioning currently requires Debian/Ubuntu. Install OpenShell ${HARNESS_OPENSHELL_VERSION} manually on other Linux distributions."
    local installer owned
    owned="$(harness_state_root)/openshell-owned"
    if [[ ! -f "$owned" ]]; then
      [[ ! -e "$HOME/.config/openshell" && ! -L "$HOME/.config/openshell" &&
         ! -e "$HOME/.local/state/openshell" && ! -L "$HOME/.local/state/openshell" ]] \
        || error "Existing OpenShell state found without its CLI. Restore that installation before continuing; refusing to adopt its data."
      [[ "${HARNESS_OPENSHELL_GATEWAY:-openshell}" == openshell ]] \
        || error "Fresh managed OpenShell setup uses the local 'openshell' gateway."
    fi
    installer="$(mktemp)"
    fetch_and_verify \
      "https://raw.githubusercontent.com/NVIDIA/OpenShell/v${HARNESS_OPENSHELL_VERSION}/install.sh" \
      "$installer" "OpenShell installer" "$HARNESS_OPENSHELL_INSTALL_SHA256"
    assert_shell_script "$installer" "OpenShell installer"
    atomic_write_file "$(ensure_state_dir)/openshell-owned" "$HARNESS_OPENSHELL_VERSION"
    OPENSHELL_VERSION="v${HARNESS_OPENSHELL_VERSION}" OPENSHELL_INSTALL_METHOD=deb \
      sh "$installer" || { rm -f "$installer"; error "OpenShell installation failed."; }
    rm -f "$installer"
  fi
  [[ "$(openshell --version)" == "openshell ${HARNESS_OPENSHELL_VERSION}" ]] \
    || error "OpenShell ${HARNESS_OPENSHELL_VERSION} is required; refusing to replace a different installed version."
  if [[ -f "$(harness_state_root)/openshell-owned" ]]; then
    assert_state_path_safe "$(harness_state_root)/openshell-owned"
    assert_owned_by_current_user "$(harness_state_root)/openshell-owned"
    [[ "$(cat "$(harness_state_root)/openshell-owned")" == "$HARNESS_OPENSHELL_VERSION" ]] \
      || error "Invalid OpenShell ownership record."
    systemctl --user daemon-reload || error "Could not reload the OpenShell user service."
    systemctl --user enable --now openshell-gateway.service \
      || error "Could not start the managed OpenShell gateway; ownership record retained for uninstall/retry."
    local gateways registered
    gateways="$(openshell gateway list -o json)" || error "Cannot inspect managed OpenShell gateway registration."
    registered="$(node -e '
      const gateways = JSON.parse(process.argv[1]);
      if (!Array.isArray(gateways)) throw Error("Invalid gateway list");
      const gateway = gateways.find(g => g.name === "openshell");
      if (gateway && (gateway.is_remote || gateway.type !== "local"))
        throw Error("Managed gateway must be local");
      console.log(gateway ? "present" : "absent");
    ' "$gateways")" || error "Invalid managed OpenShell gateway registration."
    if [[ "$registered" == absent ]]; then
      openshell gateway add https://127.0.0.1:17670 --local --name openshell \
        || error "Could not register managed OpenShell gateway; ownership record retained for retry."
    fi
  fi
}

openshell_remove_owned_runtime() {
  local owned records gateways path processes kind containers
  owned="$(harness_state_root)/openshell-owned"
  [[ -e "$owned" || -L "$owned" ]] || {
    info "Preserving OpenShell CLI/gateway: not installed by this harness deployment."
    return 0
  }
  assert_state_path_safe "$owned"
  assert_owned_by_current_user "$owned"
  [[ "$(cat "$owned")" == "$HARNESS_OPENSHELL_VERSION" ]] \
    || error "Invalid OpenShell installation ownership record."
  if command_exists openshell; then
    [[ "$(openshell --version)" == "openshell ${HARNESS_OPENSHELL_VERSION}" ]] \
      || error "OpenShell was replaced since installation; refusing to purge a different version."
    gateways="$(openshell gateway list -o json)" || error "Cannot inspect OpenShell gateways before removal."
    node -e '
      const g = JSON.parse(process.argv[1]);
      if (!Array.isArray(g) || g.some(x => x.name !== "openshell" || x.is_remote || x.type !== "local"))
        throw Error("Additional or remote gateways exist; refusing shared OpenShell removal");
    ' "$gateways" || error "OpenShell has non-installer gateway registrations."
    for kind in sandbox provider; do
      records="$(openshell "$kind" list -g openshell -o json)" \
        || error "Cannot check remaining OpenShell ${kind} resources."
      node -e '
        const d = JSON.parse(process.argv[1]), key = process.argv[2] === "sandbox" ? "sandboxes" : "providers";
        if (!Array.isArray(d[key]) || d[key].length || d.next_page_token)
          throw Error("Remaining or paginated OpenShell resources");
      ' "$records" "$kind" || error "OpenShell ${kind} resources remain; refusing to remove a shared gateway."
    done
    containers="$(docker container ls -a --format '{{.Names}}')" \
      || error "Cannot check for remaining OpenShell runtime containers."
    if grep -Eq '^openshell-.*--' <<<"$containers"; then
      error "OpenShell runtime containers remain, possibly in another workspace; refusing gateway/CLI removal."
    fi
    processes="$(ps -eo uid=,comm=)" || error "Cannot inspect other gateway users."
    if awk -v uid="$(id -u)" '$2 ~ /^openshell-gate/ && $1 != uid {found=1} END {exit !found}' <<<"$processes"; then
      error "Another account is running an OpenShell gateway; refusing system-wide package removal."
    fi
    systemctl --user disable --now openshell-gateway.service \
      || error "Could not stop the owned OpenShell gateway."
    require_sudo_or_fail "dpkg --purge openshell"
    sudo dpkg --purge openshell || error "Could not purge OpenShell; ownership record retained."
    systemctl --user daemon-reload || error "Could not reload user services after OpenShell removal."
    command_exists openshell && error "OpenShell CLI remains after package purge."
  fi
  for path in "$HOME/.config/openshell" "$HOME/.local/state/openshell"; do
    [[ ! -L "$path" ]] || error "Refusing symlinked OpenShell data: ${path}"
    assert_owned_by_current_user "$path"
    rm -rf -- "$path"
  done
  rm -f -- "$owned"
}

openshell_load_profile() {
  load_openshell_node
  local dir
  dir="$(openshell_profile_dir)"
  assert_state_path_safe "$dir/profile.json"
  assert_owned_by_current_user "$dir/profile.json"
  [[ -f "$dir/profile.json" ]] || error "No OpenShell profile for this agent. Install it first."
  local fields
  # Parse JSON as data rather than sourcing persisted state as shell code.
  fields="$(node - "$dir/profile.json" "$(canonical_agent_name "${HARNESS_AGENT:-openclaw}")" <<'JS'
const fs = require("node:fs");
const p = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
if (!/^[a-f0-9]{32}$/.test(p.owner) ||
    !/^ahi-[a-f0-9]{12}$/.test(p.name) ||
    !/^[a-zA-Z0-9_.-]+$/.test(p.gateway) ||
    p.agent !== process.argv[3] ||
    typeof p.model !== "string" || !p.model || /[\r\n]/.test(p.model))
  throw Error("Invalid OpenShell profile");
console.log([p.owner, p.name, p.gateway, p.model].join("\n"));
JS
  )" || error "Could not read the OpenShell ownership profile."
  mapfile -t _openshell_fields <<<"$fields"
  OPENSHELL_OWNER="${_openshell_fields[0]}"
  OPENSHELL_NAME="${_openshell_fields[1]}"
  OPENSHELL_GATEWAY="${_openshell_fields[2]}"
  OPENSHELL_MODEL="${_openshell_fields[3]}"
}

openshell_resource_exists() {
  local kind="$1" records result
  records="$(openshell "$kind" list -g "$OPENSHELL_GATEWAY" -o json)" \
    || error "Cannot list OpenShell ${kind} resources; refusing to guess their state."
  # An incomplete list must not be mistaken for an absent resource during retries or cleanup.
  result="$(node -e '
    const fs = require("node:fs");
    const d = JSON.parse(fs.readFileSync(0, "utf8"));
    if (d.next_page_token) throw Error("Resource list is paginated; refusing an incomplete ownership check");
    const entries = d[process.argv[1] === "sandbox" ? "sandboxes" : "providers"];
    if (!Array.isArray(entries)) throw Error("Invalid OpenShell resource list");
    console.log(entries.some(x => x.name === process.argv[2]) ? "yes" : "no");
  ' "$kind" "$OPENSHELL_NAME" <<<"$records")" || error "Invalid OpenShell resource response."
  [[ "$result" == yes ]]
}

openshell_assert_owned() {
  local record
  # A matching name alone is insufficient authority to execute in or delete a sandbox.
  record="$(openshell sandbox get "$OPENSHELL_NAME" -g "$OPENSHELL_GATEWAY" -o json)" \
    || error "Cannot inspect sandbox '${OPENSHELL_NAME}'; no lifecycle action was attempted."
  node -e '
    const fs = require("node:fs");
    const d = JSON.parse(fs.readFileSync(0, "utf8"));
    if (d.labels?.["agent-harness.owner"] !== process.argv[1])
      throw Error("Sandbox ownership label does not match this installation");
  ' "$OPENSHELL_OWNER" <<<"$record" || error "Refusing to operate on an unowned sandbox."
}

openshell_validate_shared_inference() {
  local endpoint model
  [[ "$(resolve_bind_host)" == "127.0.0.1" ]] \
    || error "OpenShell mode requires HARNESS_BIND_HOST=127.0.0.1; inference must not be LAN-published."
  [[ "$HARNESS_IR_PORT" =~ ^[0-9]+$ ]] && (( HARNESS_IR_PORT > 0 && HARNESS_IR_PORT < 65536 )) \
    || error "HARNESS_IR_PORT must be between 1 and 65535."
  # Validate the existing container's publication, not just the requested bind setting.
  local bindings
  bindings="$(docker inspect "$HARNESS_IR_CONTAINER" --format '{{json .HostConfig.PortBindings}}')" \
    || error "Shared IR container is not available. Run ./install.sh inference --model <model> first."
  node -e '
    const b = JSON.parse(process.argv[1])["8000/tcp"];
    if (!Array.isArray(b) || !b.length ||
        b.some(x => x.HostIp !== "127.0.0.1" || x.HostPort !== process.argv[2]))
      throw Error("IR must be published only on the expected host loopback port");
  ' "$bindings" "$HARNESS_IR_PORT" || error "Refusing non-loopback or mismatched IR publication."
  endpoint="http://127.0.0.1:${HARNESS_IR_PORT}/v1/models"
  model="${HARNESS_LLM_MODEL:-$(resolve_onboarding_model_hint)}"
  if ! node - "$endpoint" "$model" <<'JS'
const [url, model] = process.argv.slice(2);
fetch(url, {signal: AbortSignal.timeout(10000)})
  .then(async r => {
    if (!r.ok) throw Error(`IR returned HTTP ${r.status}`);
    const d = await r.json();
    if (!d.data?.some(m => m.id === model)) throw Error(`IR does not serve model '${model}'`);
  })
  .catch(e => { console.error(e.message); process.exitCode = 1; });
JS
  then
    error "Shared inference is unavailable. Run ./install.sh inference --model <model> first."
  fi
}

install_openshell_agent() {
  # Serialize one agent's provisioning without blocking installation of the other agent.
  with_state_lock "openshell-$(canonical_agent_name "${HARNESS_AGENT:-openclaw}")" _install_openshell_agent
}

_install_openshell_agent() {
  local agent dir gateway owner name model profile image
  agent="$(canonical_agent_name "${HARNESS_AGENT:-openclaw}")"
  [[ "$(uname -s)" == Linux ]] || error "OpenShell mode currently supports Linux with Docker only."
  ensure_openshell_cli
  openshell_validate_shared_inference
  dir="$(openshell_profile_dir)"
  assert_state_path_safe "$dir"
  ensure_state_dir >/dev/null
  (umask 077 && mkdir -p "$dir")
  assert_owned_by_current_user "$dir"
  # Reuse the recorded identity after partial failure; never replace an existing owned sandbox.
  if [[ -f "$dir/profile.json" ]]; then
    openshell_load_profile
    [[ "$OPENSHELL_MODEL" == "${HARNESS_LLM_MODEL:-$(resolve_onboarding_model_hint)}" ]] \
      || error "This profile uses model '${OPENSHELL_MODEL}'; refusing to change it implicitly."
    if openshell_resource_exists sandbox; then
      openshell_assert_owned
      ok "Owned OpenShell sandbox already exists: ${OPENSHELL_NAME}; not replacing its state."
      return
    fi
    info "Resuming provisioning from the recorded OpenShell identity."
    gateway="$OPENSHELL_GATEWAY"; name="$OPENSHELL_NAME"; owner="$OPENSHELL_OWNER"; model="$OPENSHELL_MODEL"
  else
    gateway="${HARNESS_OPENSHELL_GATEWAY:-openshell}"
    [[ "$gateway" =~ ^[a-zA-Z0-9_.-]+$ ]] || error "Invalid HARNESS_OPENSHELL_GATEWAY."
    owner="$(node -e 'console.log(require("node:crypto").randomBytes(16).toString("hex"))')"
    # Keep the resource name within OpenShell's 19-character limit; retain the full owner in labels.
    name="ahi-${owner:0:12}"
    model="${HARNESS_LLM_MODEL:-$(resolve_onboarding_model_hint)}"
    profile="$(node -e 'console.log(JSON.stringify({owner:process.argv[1],name:process.argv[2],gateway:process.argv[3],agent:process.argv[4],model:process.argv[5]}))' \
      "$owner" "$name" "$gateway" "$agent" "$model")"
    # Persist identity before remote resource creation so failures leave a recoverable record.
    atomic_write_file "$dir/profile.json" "$profile"
    openshell_load_profile
  fi
  openshell status -g "$gateway" || error "OpenShell gateway is not available."
  image="agent-harness-${agent}-openshell:local"
  docker build --build-arg "HARNESS_AGENT=$agent" \
    --build-arg HTTP_PROXY --build-arg HTTPS_PROXY --build-arg http_proxy --build-arg https_proxy \
    -f "${SCRIPT_DIR}/openshell/Dockerfile" -t "$image" "$SCRIPT_DIR" \
    || error "Could not build the ${agent} sandbox image. Ownership record retained at ${dir}."
  local provider
  # OpenShell's host-service alias reaches loopback IR without exposing it on a LAN interface.
  # Allow the actual HTTP clients, including Hermes's installer-managed Python interpreter.
  provider="$(node - "$name" "$HARNESS_IR_PORT" <<'JS'
const [id, port] = process.argv.slice(2);
console.log(JSON.stringify({
  id, display_name: "Agent Harness shared inference", category: "inference",
  inference_capable: true, credentials: [],
  endpoints: [{host: "host.openshell.internal", port: Number(port), protocol: "rest",
    access: "read-write", enforcement: "enforce"}],
  binaries: ["/usr/bin/curl", "/usr/local/bin/node",
    "/home/node/.hermes/tools/python-*/bin/python*"]
}));
JS
  )"
  atomic_write_file "$dir/provider.json" "$provider"
  openshell profile lint -f "$dir/provider.json" -g "$gateway"
  if ! openshell_resource_exists provider; then
    openshell profile import -f "$dir/provider.json" -g "$gateway"
    openshell provider create --name "$name" --type "$name" -g "$gateway"
  fi
  local policy="${SCRIPT_DIR}/openshell/policy.yaml"
  [[ "$agent" != hermes ]] || policy="${SCRIPT_DIR}/openshell/hermes-policy.yaml"
  openshell sandbox create --name "$name" --from "$image" --provider "$name" \
    --policy "$policy" \
    --label "agent-harness.owner=$owner" --label "agent-harness.agent=$agent" \
    --env "HARNESS_AGENT=$agent" --env "HARNESS_SANDBOX_MODEL=$model" \
    --env "HERMES_HOME=/home/node/.hermes" \
    --env "OPENAI_API_KEY=not-needed" \
    --env "HARNESS_SANDBOX_ENDPOINT=http://host.openshell.internal:${HARNESS_IR_PORT}/v1" \
    --detach -g "$gateway" -- /usr/local/bin/harness-agent-start \
    || error "Sandbox creation failed. Profile retained at ${dir}; inspect it before retrying."
  openshell_assert_owned
  ok "$(agent_display_name "$agent") provisioned in OpenShell sandbox ${name}."
}

openshell_agent_exec() {
  openshell_load_profile
  openshell_assert_owned
  # Login-shell initialization can replace the image PATH; callers use explicit CLI paths.
  openshell sandbox exec --name "$OPENSHELL_NAME" --no-login-shell -g "$OPENSHELL_GATEWAY" -- "$@"
}

onboard_openshell_agent() {
  openshell_agent_exec /usr/bin/curl --fail --silent --show-error --max-time 20 \
    "http://host.openshell.internal:${HARNESS_IR_PORT}/v1/models" \
    || error "Sandbox cannot reach the shared Inference Router."
  ok "Sandbox inference connectivity verified (not a tool-use acceptance test)."
  if [[ "$(canonical_agent_name "${HARNESS_AGENT:-openclaw}")" == openclaw ]]; then
    local response
    response="$(openshell_agent_exec /home/node/.local/bin/openclaw infer model run \
      --prompt "Say hello." --model "ovms/${OPENSHELL_MODEL}" --json)" \
      || error "Sandboxed OpenClaw inference failed."
    node -e '
      const fs = require("node:fs");
      const d = JSON.parse(fs.readFileSync(0, "utf8"));
      if (!d.ok || !d.outputs?.some(x => x.text?.trim())) throw Error("OpenClaw returned no successful inference output");
    ' <<<"$response" || error "OpenClaw inference response did not validate."
    ok "Sandboxed OpenClaw inference passed."
  else
    openshell_agent_exec /home/node/.local/bin/hermes --version \
      || error "Sandboxed Hermes CLI did not start."
    local hermes_response
    hermes_response="$(openshell_agent_exec /home/node/.local/bin/hermes \
      -z "Say hello briefly. Do not use any tools.")" \
      || error "Sandboxed Hermes inference failed."
    [[ -n "${hermes_response//[[:space:]]/}" ]] \
      || error "Sandboxed Hermes returned no inference output."
    printf '%s\n' "$hermes_response"
    ok "Sandboxed Hermes inference returned output; verify task effects separately."
  fi
}

status_openshell_agent() {
  openshell_load_profile
  openshell_assert_owned
  openshell sandbox get "$OPENSHELL_NAME" -g "$OPENSHELL_GATEWAY"
}

connect_openshell_agent() {
  local agent
  agent="$(canonical_agent_name "${HARNESS_AGENT:-openclaw}")"
  case "$agent" in
    openclaw) openshell_agent_exec /home/node/.local/bin/openclaw tui ;;
    hermes) openshell_agent_exec /home/node/.local/bin/hermes ;;
  esac
}

remove_openshell_agent() {
  openshell_load_profile
  if openshell_resource_exists sandbox; then
    openshell_assert_owned
    openshell sandbox delete "$OPENSHELL_NAME" -g "$OPENSHELL_GATEWAY" \
      || error "Could not request sandbox removal; ownership record retained."
    # Deletion is asynchronous; keep its provider and ownership record until cleanup completes.
    local attempt
    for attempt in {1..30}; do
      openshell_resource_exists sandbox || break
      sleep 1
    done
    if openshell_resource_exists sandbox; then
      error "Sandbox cleanup is pending; profile retained. Re-run uninstall after cleanup completes."
    fi
  fi
  if openshell_resource_exists provider; then
    openshell provider delete "$OPENSHELL_NAME" -g "$OPENSHELL_GATEWAY"
    openshell profile delete "$OPENSHELL_NAME" -g "$OPENSHELL_GATEWAY"
  fi
  local dir
  dir="$(openshell_profile_dir)"
  # Only active profile.json records block host uninstall; preserve the removed identity for audit.
  mv -- "$dir/profile.json" "$dir/removed-profile.json"
  info "Owned sandbox/provider removed. Shared inference, host agents and OpenShell gateway were not removed."
  info "Ownership record retained at ${dir}/removed-profile.json."
}
