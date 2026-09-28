# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=bash
# OpenVINO Model Server (OVMS) — serves an OpenAI-compatible chat-completions
# endpoint on Intel Arc / Data Center GPU Max.

PLATFORM_OVMS_IMAGE="${PLATFORM_OVMS_IMAGE:-openvino/model_server:2026.4.0-gpu}"
PLATFORM_OVMS_REST_PORT="${PLATFORM_OVMS_REST_PORT:-8000}"
PLATFORM_MODELS_DIR="${PLATFORM_MODELS_DIR:-$HOME/.intel-agent/models}"
PLATFORM_OVMS_CONTAINER="${PLATFORM_OVMS_CONTAINER:-intel-agent-ovms}"
# Extra OVMS server flags, e.g. "--tool_parser hermes3 --task text_generation"
# for Harness agents that need OpenAI-style tool calls.
PLATFORM_OVMS_EXTRA_ARGS="${PLATFORM_OVMS_EXTRA_ARGS:-}"

# Set PLATFORM_LLM_ROUTER_ENDPOINT to route the Harness agent at an existing
# OpenAI-compatible router/gateway instead of this installer's own OVMS
# container — e.g. an internal LiteLLM instance, a corporate API gateway, or
# a cloud endpoint. When set, this installer never starts, stops, or
# health-checks OVMS; PLATFORM_LLM_PROVIDER is then ignored.
PLATFORM_LLM_PROVIDER="${PLATFORM_LLM_PROVIDER:-ovms}"
PLATFORM_LLM_ROUTER_ENDPOINT="${PLATFORM_LLM_ROUTER_ENDPOINT:-}"

# export_model.py is OVMS's own model-export tool — unlike plain
# `optimum-cli export openvino`, it also writes the graph.pbtxt MediaPipe
# servable definition OVMS's /v3/chat/completions endpoint requires for LLMs.
# Pinned to the release tag matching PLATFORM_OVMS_IMAGE for reproducible,
# version-compatible exports.
PLATFORM_OVMS_EXPORT_MODEL_REF="${PLATFORM_OVMS_EXPORT_MODEL_REF:-v2026.4.0}"

# Known-good SHA-256 for export_model.py / requirements.txt at the pinned
# ref above (verified against openvinotoolkit/model_server). IMPORTANT:
# update both hashes whenever PLATFORM_OVMS_EXPORT_MODEL_REF's default
# changes; they are only applied when the ref in use matches this exact tag.
_OVMS_EXPORT_MODEL_PINNED_REF="v2026.4.0"
_OVMS_EXPORT_MODEL_PY_SHA256="783df4b5bfbadd6b19574bef5a6deb3b5d51dc1218b8e375740a2a7edea2fb88"
_OVMS_EXPORT_MODEL_REQUIREMENTS_SHA256="3068c47e01543fb2d8c4e4b30aadcf2922dc1288e5e733c880a562f523529663"

# Ensures a valid (possibly empty) config.json exists. export_model.py updates
# this file itself on every export (appending to mediapipe_config_list), so
# this must never overwrite an existing file or it would erase prior models.
ensure_ovms_config() {
  mkdir -p "$PLATFORM_MODELS_DIR"
  local config_file="${PLATFORM_MODELS_DIR}/config.json"
  [[ -f "$config_file" ]] || printf '{"model_config_list": [], "mediapipe_config_list": []}' >"$config_file"
}

# The HF/OpenVINO export tooling shells out via httpx, which only understands
# http/https/socks5/socks5h proxy schemes — a bare "socks://" (missing the
# "5") fails deep inside httpx with a raw traceback instead of a clear error.
# Checked before any install/export work so a misconfigured proxy fails fast.
assert_proxy_scheme_supported() {
  local var_name value scheme
  for var_name in ALL_PROXY all_proxy HTTPS_PROXY https_proxy HTTP_PROXY http_proxy; do
    value="${!var_name:-}"
    [[ -n "$value" ]] || continue
    scheme="${value%%://*}"
    case "$scheme" in
      http | https | socks5 | socks5h) ;;
      socks)
        error "\$${var_name} uses proxy scheme 'socks://', which the Python
export tooling's HTTP client (httpx) does not support — it only understands
http/https/socks5/socks5h. Change ${var_name} to socks5h://${value#*://}
(or socks5://) and retry."
        ;;
      *)
        warn "\$${var_name} uses proxy scheme '${scheme}://', which the model
export step's HTTP client may not support (only http/https/socks5/socks5h are)."
        ;;
    esac
  done
}

# export_model_to_openvino hf_model_id [model_name] — converts a Hugging Face
# model to OpenVINO IR *and* generates the graph.pbtxt MediaPipe servable
# OVMS's /v3/chat/completions endpoint needs, via OVMS's own export_model.py
# (plain optimum-cli only produces IR weights, not a servable LLM graph).
export_model_to_openvino() {
  local hf_model_id="$1" model_name="${2:-${1##*/}}" out_dir venv exporter requirements_file
  out_dir="${PLATFORM_MODELS_DIR}/${model_name}"
  if [[ -d "$out_dir" ]]; then
    info "Model '${model_name}' is already exported."
    return 0
  fi
  command_exists python3 || error "python3 is required to export models to OpenVINO IR."
  assert_proxy_scheme_supported
  ensure_ovms_config
  venv="${PLATFORM_MODELS_DIR}/.export-venv"
  [[ -d "$venv" ]] || python3 -m venv "$venv"
  # shellcheck disable=SC1091
  . "${venv}/bin/activate"
  # A freshly created venv inherits whatever old pip ships with the system
  # python3 (e.g. 22.0.2's resolver has a known topological-sort assertion
  # bug on some dependency sets) — upgrading first avoids that recurring on
  # every venv recreation.
  spin "Upgrading pip in the export venv" pip install --quiet --upgrade pip
  exporter="${venv}/export_model.py"
  requirements_file="${venv}/export_model-requirements.txt"
  # The pinned checksums above only apply to the exact ref they were taken
  # from; an operator-overridden ref has no known-good hash to check against.
  local expected_py_sha256="" expected_requirements_sha256=""
  if [[ "$PLATFORM_OVMS_EXPORT_MODEL_REF" == "$_OVMS_EXPORT_MODEL_PINNED_REF" ]]; then
    expected_py_sha256="$_OVMS_EXPORT_MODEL_PY_SHA256"
    expected_requirements_sha256="$_OVMS_EXPORT_MODEL_REQUIREMENTS_SHA256"
  fi
  if [[ ! -f "$exporter" ]]; then
    info "Fetching OVMS's export_model.py (ref: ${PLATFORM_OVMS_EXPORT_MODEL_REF})…"
    fetch_and_verify \
      "https://raw.githubusercontent.com/openvinotoolkit/model_server/${PLATFORM_OVMS_EXPORT_MODEL_REF}/demos/common/export_models/export_model.py" \
      "$exporter" "OVMS export_model.py" "$expected_py_sha256"
  fi
  if [[ ! -f "$requirements_file" ]]; then
    fetch_and_verify \
      "https://raw.githubusercontent.com/openvinotoolkit/model_server/${PLATFORM_OVMS_EXPORT_MODEL_REF}/demos/common/export_models/requirements.txt" \
      "$requirements_file" "OVMS export_model.py requirements.txt" "$expected_requirements_sha256"
  fi
  # httpx[socks]'s socksio dependency is what actually lets a socks5/socks5h
  # proxy work, not just parse — installed alongside regardless of whether a
  # proxy is configured, since it's a small, side-effect-free addition.
  spin "Installing export_model.py's dependencies" pip install --quiet -r "$requirements_file" "httpx[socks]"
  spin "Exporting ${hf_model_id} to OpenVINO IR + OVMS graph" \
    python3 "$exporter" text_generation \
      --source_model "$hf_model_id" \
      --model_name "$model_name" \
      --weight-format int8 \
      --config_file_path "${PLATFORM_MODELS_DIR}/config.json" \
      --model_repository_path "$PLATFORM_MODELS_DIR" \
    || error "export_model.py failed to export ${hf_model_id}. Check network
access to huggingface.co, and that PLATFORM_OVMS_EXPORT_MODEL_REF
(${PLATFORM_OVMS_EXPORT_MODEL_REF}) is compatible with PLATFORM_OVMS_IMAGE
(${PLATFORM_OVMS_IMAGE}) — run 'python3 ${exporter} text_generation --help'
inside the venv to check its exact current flags if this keeps failing."
  deactivate
  ok "Exported ${hf_model_id} -> ${out_dir}"
}

ensure_openvino_model_server() {
  local gpu_args
  local -a proxy_args=()
  ensure_ovms_config
  if docker inspect "$PLATFORM_OVMS_CONTAINER" >/dev/null 2>&1; then
    docker restart "$PLATFORM_OVMS_CONTAINER" >/dev/null 2>&1 || true
    ok "OpenVINO Model Server restarted (${PLATFORM_OVMS_CONTAINER})"
    return 0
  fi
  gpu_args="$(intel_gpu_docker_device_args)"
  docker_proxy_env_args_into proxy_args
  info "Starting OpenVINO Model Server on port ${PLATFORM_OVMS_REST_PORT}…"
  # shellcheck disable=SC2086
  docker run -d --name "$PLATFORM_OVMS_CONTAINER" --restart unless-stopped \
    -p "${PLATFORM_OVMS_REST_PORT}:8000" $gpu_args \
    "${proxy_args[@]}" \
    -v "${PLATFORM_MODELS_DIR}:/models" \
    "$PLATFORM_OVMS_IMAGE" \
    --rest_port 8000 --config_path /models/config.json $PLATFORM_OVMS_EXTRA_ARGS \
    || error "Could not start OpenVINO Model Server."
  ok "OpenVINO Model Server is running on port ${PLATFORM_OVMS_REST_PORT}"
}

# ensure_inference_backend — starts/health-checks whichever backend is
# selected. An explicit router endpoint always wins over PLATFORM_LLM_PROVIDER,
# since routing to infrastructure this installer doesn't own is the point.
ensure_inference_backend() {
  if [[ -n "$PLATFORM_LLM_ROUTER_ENDPOINT" ]]; then
    if [[ -n "${PLATFORM_HF_MODEL:-}" ]]; then
      warn "PLATFORM_HF_MODEL is ignored when PLATFORM_LLM_ROUTER_ENDPOINT is set —
no local model export happens; the external endpoint owns model selection."
    fi
    info "Routing to external endpoint: ${PLATFORM_LLM_ROUTER_ENDPOINT}"
    info "This installer will not start, stop, or health-check that endpoint."
    return 0
  fi
  case "$PLATFORM_LLM_PROVIDER" in
    ovms)
      ensure_openvino_model_server
      if [[ -n "${PLATFORM_HF_MODEL:-}" ]]; then
        export_model_to_openvino "$PLATFORM_HF_MODEL"
        ensure_openvino_model_server
      fi
      ;;
    *)
      error "Unknown PLATFORM_LLM_PROVIDER: ${PLATFORM_LLM_PROVIDER} (expected: ovms).
Set PLATFORM_LLM_ROUTER_ENDPOINT instead to route to an existing external
OpenAI-compatible endpoint without this installer managing a backend."
      ;;
  esac
}

platform_llm_endpoint() {
  if [[ -n "$PLATFORM_LLM_ROUTER_ENDPOINT" ]]; then
    printf '%s' "$PLATFORM_LLM_ROUTER_ENDPOINT"
    return 0
  fi
  printf 'http://%s:%s/v3' "$(resolve_advertised_host)" "$PLATFORM_OVMS_REST_PORT"
}

# Rejects path-traversal/empty/current-dir/hidden names before any
# model_dir/config.json touch — the leading-dot check also keeps this from
# targeting internal dirs like the export venv (.export-venv).
validate_model_name() {
  local name="$1"
  [[ -n "$name" && "$name" != .* && "$name" != *"/"* && "$name" != *".."* ]]
}

list_exported_models() {
  local dir="$PLATFORM_MODELS_DIR" entry name found=0
  [[ -d "$dir" ]] || { info "No models exported yet (${dir})."; return 0; }
  for entry in "$dir"/*/; do
    [[ -d "$entry" ]] || continue
    name="$(basename "$entry")"
    [[ "$name" == .* ]] && continue
    found=1
    printf '  %s\n' "$name"
  done
  [[ "$found" -eq 1 ]] || info "No models exported yet (${dir})."
}

# remove_exported_model name — deletes one exported model's directory, drops
# its entry from config.json (export_model.py appends to model_config_list /
# mediapipe_config_list and never removes), and restarts OVMS so it stops
# serving it. Lets you export/test/delete a small model repeatedly without
# wiping every other exported model.
remove_exported_model() {
  local name="$1" dir="$PLATFORM_MODELS_DIR" model_dir config_file
  [[ -n "$name" ]] || error "Usage: ./install.sh models remove <name>"
  validate_model_name "$name" || error "Invalid model name: ${name}"
  model_dir="${dir}/${name}"
  [[ -d "$model_dir" ]] || error "Model '${name}' is not exported (looked in ${model_dir})."
  config_file="${dir}/config.json"
  [[ -f "$config_file" ]] && with_state_lock ovms-config _remove_model_from_ovms_config_locked "$config_file" "$name"
  rm -rf -- "$model_dir"
  ok "Removed exported model '${name}' (${model_dir})"
  if command_exists docker && docker inspect "$PLATFORM_OVMS_CONTAINER" >/dev/null 2>&1; then
    docker restart "$PLATFORM_OVMS_CONTAINER" >/dev/null 2>&1 \
      && info "Restarted ${PLATFORM_OVMS_CONTAINER} so it stops serving the removed model."
  fi
}

# Lock-protected (with_state_lock) so a concurrent export/remove can't race
# on the same shared config.json read-modify-write.
_remove_model_from_ovms_config_locked() {
  local config_file="$1" name="$2" tmp
  tmp="$(mktemp)"
  node -e '
      const fs = require("node:fs");
      const [configFile, name] = process.argv.slice(1);
      let data = {};
      try { data = JSON.parse(fs.readFileSync(configFile, "utf8")); } catch {}
      for (const key of ["model_config_list", "mediapipe_config_list"]) {
        if (Array.isArray(data[key])) {
          data[key] = data[key].filter((e) => e && e.name !== name && e.config?.name !== name);
        }
      }
      process.stdout.write(JSON.stringify(data, null, 2));
    ' "$config_file" "$name" >"$tmp" && mv -f "$tmp" "$config_file" || { rm -f "$tmp"; warn "Could not update ${config_file}; removing the model directory anyway."; }
}

# Used by the uninstaller; leaves the image and models dir untouched. No-op
# when routed externally, since this installer never started that backend.
remove_openvino_model_server() {
  [[ -z "$PLATFORM_LLM_ROUTER_ENDPOINT" ]] || return 0
  command_exists docker || return 0
  docker rm -f "$PLATFORM_OVMS_CONTAINER" >/dev/null 2>&1 || true
}
