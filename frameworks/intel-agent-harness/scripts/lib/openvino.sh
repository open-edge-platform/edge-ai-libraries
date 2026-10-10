# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=bash
# OpenVINO Model Server (OVMS) — serves an OpenAI-compatible chat-completions
# endpoint on Intel Core Ultra iGPU and Arc (CRI) GPUs.

HARNESS_OVMS_IMAGE="${HARNESS_OVMS_IMAGE:-openvino/model_server:2026.4.0-gpu}"
HARNESS_OVMS_REST_PORT="${HARNESS_OVMS_REST_PORT:-8000}"
HARNESS_MODELS_DIR="${HARNESS_MODELS_DIR:-$HOME/.intel-agent/models}"
HARNESS_OVMS_CONTAINER="${HARNESS_OVMS_CONTAINER:-intel-agent-ovms}"
# Extra OVMS server flags, e.g. "--tool_parser hermes3 --task text_generation"
# for agents that need OpenAI-style tool calls.
HARNESS_OVMS_EXTRA_ARGS="${HARNESS_OVMS_EXTRA_ARGS:-}"

# Set HARNESS_LLM_ROUTER_ENDPOINT to route the agent at an existing
# OpenAI-compatible router/gateway instead of this installer's own OVMS
# container — e.g. an internal LiteLLM instance, a corporate API gateway, or
# a cloud endpoint. When set, this installer never starts, stops, or
# health-checks OVMS; HARNESS_LLM_PROVIDER is then ignored.
HARNESS_LLM_PROVIDER="${HARNESS_LLM_PROVIDER:-ovms}"
HARNESS_LLM_ROUTER_ENDPOINT="${HARNESS_LLM_ROUTER_ENDPOINT:-}"

# Which tool performs --hf-model export: docker-pull (default) runs OVMS's
# own "-py" Docker image in --pull mode to download/convert/quantize a HF
# model entirely via Docker -- no host Python venv or separate script fetch
# needed, since it reuses the same trusted, version-pinned image this
# installer already runs OVMS itself from. export-model-py (legacy) runs
# OVMS's export_model.py in a host-side venv, fetched/pinned from GitHub
# raw content -- kept for hosts that can't/won't run the conversion inside
# Docker. model-download is a third, newer/less battle-tested alternative
# (edge-ai-libraries' Model Download microservice -- see
# export_model_via_model_download below). All three register the resulting
# model into config.json the same way (a model_config_list entry).
HARNESS_OVMS_EXPORTER="${HARNESS_OVMS_EXPORTER:-docker-pull}"

# export_model.py is OVMS's own model-export tool — unlike plain
# `optimum-cli export openvino`, it also writes the graph.pbtxt MediaPipe
# servable definition OVMS's /v3/chat/completions endpoint requires for LLMs.
# Pinned to the release tag matching HARNESS_OVMS_IMAGE for reproducible,
# version-compatible exports.
HARNESS_OVMS_EXPORT_MODEL_REF="${HARNESS_OVMS_EXPORT_MODEL_REF:-v2026.4.0}"

# Known-good SHA-256 for export_model.py / requirements.txt at the pinned
# ref above (verified against openvinotoolkit/model_server). IMPORTANT:
# update both hashes whenever HARNESS_OVMS_EXPORT_MODEL_REF's default
# changes; they are only applied when the ref in use matches this exact tag.
_OVMS_EXPORT_MODEL_PINNED_REF="v2026.4.0"
_OVMS_EXPORT_MODEL_PY_SHA256="783df4b5bfbadd6b19574bef5a6deb3b5d51dc1218b8e375740a2a7edea2fb88"
_OVMS_EXPORT_MODEL_REQUIREMENTS_SHA256="3068c47e01543fb2d8c4e4b30aadcf2922dc1288e5e733c880a562f523529663"

# Ensures a valid (possibly empty) config.json exists. export_model.py updates
# this file itself on every export (appending to mediapipe_config_list), so
# this must never overwrite an existing file or it would erase prior models.
ensure_ovms_config() {
  mkdir -p "$HARNESS_MODELS_DIR"
  local config_file="${HARNESS_MODELS_DIR}/config.json"
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

# export_model_via_docker_pull hf_model_id [model_name] -- default exporter
# (HARNESS_OVMS_EXPORTER=docker-pull): runs OVMS's own "-py" image (bundles
# optimum-cli) in --pull mode, which downloads, converts, and quantizes the
# HF model and writes the graph.pbtxt MediaPipe servable OVMS needs, all
# inside the container -- confirmed against openvinotoolkit/model_server's
# own "Pull mode with optimum cli" docs. No host Python venv, no separate
# GitHub-raw script fetch/pinning: supply-chain trust rides on the same
# versioned, officially-published OVMS image this installer already runs
# the server itself from (HARNESS_OVMS_IMAGE).
export_model_via_docker_pull() {
  local hf_model_id="$1" model_name="${2:-${1##*/}}" out_dir pull_image target_device
  out_dir="${HARNESS_MODELS_DIR}/${model_name}"
  if [[ -d "$out_dir" ]]; then
    info "Model '${model_name}' is already exported."
    return 0
  fi
  command_exists docker || error "Docker is required to pull/convert models via the OVMS -py image."
  ensure_ovms_config
  # The "-py" variant bundles optimum-cli for on-the-fly conversion -- the
  # regular serving image (HARNESS_OVMS_IMAGE) doesn't carry it at runtime.
  case "$HARNESS_OVMS_IMAGE" in
    *-gpu) pull_image="${HARNESS_OVMS_IMAGE%-gpu}-py" ;;
    *) pull_image="${HARNESS_OVMS_IMAGE}-py" ;;
  esac
  target_device="CPU"
  [[ -n "$(intel_gpu_docker_device_args)" ]] && target_device="GPU"
  local -a proxy_args=()
  docker_proxy_env_args_into proxy_args
  if ! spin "Pulling+converting ${hf_model_id} via ${pull_image} (--pull, target: ${target_device})" \
    docker run --rm -u "$(id -u):$(id -g)" \
      -v "${HARNESS_MODELS_DIR}:/models:rw" \
      "${proxy_args[@]}" \
      "$pull_image" --pull \
      --source_model "$hf_model_id" --model_name "$model_name" \
      --model_repository_path /models --task text_generation \
      --weight-format int8 --target_device "$target_device"; then
    rm -rf -- "$out_dir"
    error "Pulling/converting ${hf_model_id} via ${pull_image} failed. Check network
access to huggingface.co, and that '${pull_image}' is a published tag
(the -py variant may lag behind HARNESS_OVMS_IMAGE's own release) -- or try
HARNESS_OVMS_EXPORTER=export-model-py as a fallback."
  fi
  if [[ ! -f "${out_dir}/graph.pbtxt" ]]; then
    error "No graph.pbtxt found at ${out_dir} after pull -- OVMS will not serve chat
completions for '${model_name}'."
  fi
  if with_state_lock ovms-config _add_model_config_entry_locked \
      "${HARNESS_MODELS_DIR}/config.json" "$model_name" "$model_name"; then
    ok "Exported ${hf_model_id} -> ${out_dir} (registered with OVMS)"
  else
    error "Converted ${hf_model_id} but could not update OVMS's config.json --
add a model_config_list entry for base_path '${model_name}' manually."
  fi
}

# export_model_to_openvino hf_model_id [model_name] -- legacy exporter
# (HARNESS_OVMS_EXPORTER=export-model-py): converts a Hugging Face model to
# OpenVINO IR *and* generates the graph.pbtxt MediaPipe servable OVMS's
# /v3/chat/completions endpoint needs, via OVMS's own export_model.py run in
# a host-side venv (plain optimum-cli only produces IR weights, not a
# servable LLM graph). Superseded by export_model_via_docker_pull above for
# hosts that already have Docker; kept for hosts that don't.
export_model_to_openvino() {
  local hf_model_id="$1" model_name="${2:-${1##*/}}" out_dir venv exporter requirements_file
  out_dir="${HARNESS_MODELS_DIR}/${model_name}"
  if [[ -d "$out_dir" ]]; then
    info "Model '${model_name}' is already exported."
    return 0
  fi
  command_exists python3 || error "python3 is required to export models to OpenVINO IR."
  assert_proxy_scheme_supported
  ensure_ovms_config
  venv="${HARNESS_MODELS_DIR}/.export-venv"
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
  # from; an operator-overridden ref has no known-good hash to check against
  # unless they supply one explicitly.
  local expected_py_sha256="" expected_requirements_sha256=""
  if [[ "$HARNESS_OVMS_EXPORT_MODEL_REF" == "$_OVMS_EXPORT_MODEL_PINNED_REF" ]]; then
    expected_py_sha256="$_OVMS_EXPORT_MODEL_PY_SHA256"
    expected_requirements_sha256="$_OVMS_EXPORT_MODEL_REQUIREMENTS_SHA256"
  elif [[ -n "${HARNESS_OVMS_EXPORT_MODEL_PY_SHA256:-}" && -n "${HARNESS_OVMS_EXPORT_MODEL_REQUIREMENTS_SHA256:-}" ]]; then
    expected_py_sha256="$HARNESS_OVMS_EXPORT_MODEL_PY_SHA256"
    expected_requirements_sha256="$HARNESS_OVMS_EXPORT_MODEL_REQUIREMENTS_SHA256"
  elif [[ "${HARNESS_ALLOW_UNVERIFIED_OVMS_EXPORTER:-}" != "1" ]]; then
    error "HARNESS_OVMS_EXPORT_MODEL_REF is set to a non-default ref
(${HARNESS_OVMS_EXPORT_MODEL_REF}) with no known-good checksum. Review
export_model.py/requirements.txt for that ref yourself, then set
HARNESS_OVMS_EXPORT_MODEL_PY_SHA256 and
HARNESS_OVMS_EXPORT_MODEL_REQUIREMENTS_SHA256 to pin them (or
HARNESS_ALLOW_UNVERIFIED_OVMS_EXPORTER=1 to accept the risk)."
  fi
  # Always re-fetch+verify rather than trusting a cached file on disk -- a
  # stale or modified cache in the venv would otherwise bypass integrity
  # checking entirely.
  info "Fetching OVMS's export_model.py (ref: ${HARNESS_OVMS_EXPORT_MODEL_REF})…"
  fetch_and_verify \
    "https://raw.githubusercontent.com/openvinotoolkit/model_server/${HARNESS_OVMS_EXPORT_MODEL_REF}/demos/common/export_models/export_model.py" \
    "$exporter" "OVMS export_model.py" "$expected_py_sha256"
  fetch_and_verify \
    "https://raw.githubusercontent.com/openvinotoolkit/model_server/${HARNESS_OVMS_EXPORT_MODEL_REF}/demos/common/export_models/requirements.txt" \
    "$requirements_file" "OVMS export_model.py requirements.txt" "$expected_requirements_sha256"
  # httpx[socks]'s socksio dependency is what actually lets a socks5/socks5h
  # proxy work, not just parse — installed alongside regardless of whether a
  # proxy is configured, since it's a small, side-effect-free addition.
  spin "Installing export_model.py's dependencies" pip install --quiet -r "$requirements_file" "httpx[socks]"
  if ! spin "Exporting ${hf_model_id} to OpenVINO IR + OVMS graph" \
    python3 "$exporter" text_generation \
      --source_model "$hf_model_id" \
      --model_name "$model_name" \
      --weight-format int8 \
      --config_file_path "${HARNESS_MODELS_DIR}/config.json" \
      --model_repository_path "$HARNESS_MODELS_DIR"; then
    # Remove a partial out_dir so a retry doesn't see it and skip export
    # entirely via the already-exported shortcut above.
    rm -rf -- "$out_dir"
    error "export_model.py failed to export ${hf_model_id}. Check network
access to huggingface.co, and that HARNESS_OVMS_EXPORT_MODEL_REF
(${HARNESS_OVMS_EXPORT_MODEL_REF}) is compatible with HARNESS_OVMS_IMAGE
(${HARNESS_OVMS_IMAGE}) — run 'python3 ${exporter} text_generation --help'
inside the venv to check its exact current flags if this keeps failing."
  fi
  deactivate
  ok "Exported ${hf_model_id} -> ${out_dir}"
}

# export_model_via_model_download hf_model_id [model_name] — alternate
# exporter (HARNESS_OVMS_EXPORTER=model-download): downloads and runs
# edge-ai-libraries' "Model Download" microservice as a one-shot ephemeral
# container (get_model.sh) instead of the default docker-pull exporter, then
# registers the resulting graph.pbtxt with OVMS the same way (a
# model_config_list entry -- confirmed by inspecting a real export run side
# by side with this exporter; OVMS itself auto-detects the graph.pbtxt
# within base_path, no separate mediapipe_config_list entry is involved).
# Newer/less battle-tested than docker-pull or export-model-py.
HARNESS_MODEL_DOWNLOAD_SCRIPT_REF="${HARNESS_MODEL_DOWNLOAD_SCRIPT_REF:-main}"
HARNESS_MODEL_DOWNLOAD_IMAGE_TAG="${HARNESS_MODEL_DOWNLOAD_IMAGE_TAG:-}"
export_model_via_model_download() {
  local hf_model_id="$1" model_name="${2:-${1##*/}}" script_url script out result_line
  command_exists docker || error "Docker is required by the Model Download microservice's ephemeral container."
  command_exists python3 || error "python3 is required by get_model.sh (builds/parses its request payloads)."
  assert_proxy_scheme_supported
  mkdir -p "$HARNESS_MODELS_DIR"
  script="$(harness_state_root)/model-download/get_model.sh"
  mkdir -p "$(dirname "$script")"
  script_url="https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/${HARNESS_MODEL_DOWNLOAD_SCRIPT_REF}/microservices/model-download/scripts/get_model.sh"
  # This integration is newly explored, unlike the Hermes/Docker installers
  # there is no independently-reviewed hash hardcoded here yet -- same
  # fail-closed-by-default stance until one is pinned.
  if [[ -z "${HARNESS_MODEL_DOWNLOAD_SCRIPT_SHA256:-}" && "${HARNESS_ALLOW_UNVERIFIED_MODEL_DOWNLOAD_SCRIPT:-}" != "1" ]]; then
    error "HARNESS_MODEL_DOWNLOAD_SCRIPT_SHA256 is not set, so refusing to run
get_model.sh unverified. Download and review ${script_url} yourself, then set
HARNESS_MODEL_DOWNLOAD_SCRIPT_SHA256=<sha256> to pin it (or
HARNESS_ALLOW_UNVERIFIED_MODEL_DOWNLOAD_SCRIPT=1 to accept the risk)."
  fi
  info "Fetching the Model Download microservice's get_model.sh (ref: ${HARNESS_MODEL_DOWNLOAD_SCRIPT_REF})…"
  fetch_and_verify "$script_url" "$script" "get_model.sh" "${HARNESS_MODEL_DOWNLOAD_SCRIPT_SHA256:-}"
  assert_shell_script "$script" "get_model.sh"
  chmod +x "$script"

  local -a image_tag_args=()
  if [[ -n "$HARNESS_MODEL_DOWNLOAD_IMAGE_TAG" ]]; then
    image_tag_args=(--image-tag "$HARNESS_MODEL_DOWNLOAD_IMAGE_TAG")
  else
    warn "HARNESS_MODEL_DOWNLOAD_IMAGE_TAG is unset -- get_model.sh defaults to the
floating 'latest' tag for intel/model-download. Set it once you've picked a
known-good version for reproducible exports."
  fi

  out="$(mktemp)"
  info "Downloading+converting ${hf_model_id} via the Model Download microservice (ephemeral, experimental)…"
  # PIPESTATUS, not `if ! ... | tee`, because the pipeline's own exit status
  # is tee's (always 0) unless the caller's shell happens to have pipefail
  # set -- true for scripts/install.sh, but not guaranteed for anyone
  # sourcing this function directly, so don't rely on an external shell
  # option for correctness here.
  bash "$script" --model-name "$hf_model_id" --hub openvino --type llm \
      --is-ovms --precision int8 --device CPU \
      --model-path "$HARNESS_MODELS_DIR" --download-path "$model_name" \
      --plugins huggingface,openvino "${image_tag_args[@]}" 2>&1 | tee "$out"
  if [[ "${PIPESTATUS[0]}" -ne 0 ]]; then
    rm -f "$out"
    error "get_model.sh failed to download/convert ${hf_model_id}. See its output above."
  fi
  result_line="$(grep -o 'output: .*' "$out" | tail -1)"
  rm -f "$out"
  ok "Downloaded/converted ${hf_model_id} via the Model Download microservice${result_line:+ (${result_line})}."

  # get_model.sh reports the *container's* view of the output dir (it bind-
  # mounts $HARNESS_MODELS_DIR at /opt/models); translate back to the host
  # path, then locate the graph.pbtxt OVMS needs -- confirmed (by running
  # both exporters side by side) to sit directly under <output_dir>/<hf_model_id>/,
  # the same "base_path containing graph.pbtxt" shape export_model_to_openvino
  # produces, registered the same way: a model_config_list entry, not
  # mediapipe_config_list (OVMS auto-detects the graph file within base_path).
  local container_output_dir host_output_dir graph_dir relative_base_path
  container_output_dir="${result_line#output: }"
  host_output_dir="${HARNESS_MODELS_DIR}${container_output_dir#/opt/models}"
  graph_dir="${host_output_dir}/${hf_model_id}"
  if [[ -f "${graph_dir}/graph.pbtxt" ]]; then
    relative_base_path="${graph_dir#"${HARNESS_MODELS_DIR}"/}"
    if with_state_lock ovms-config _add_model_config_entry_locked \
        "${HARNESS_MODELS_DIR}/config.json" "$model_name" "$relative_base_path"; then
      ok "Registered '${model_name}' with OVMS (base_path: ${relative_base_path})."
    else
      warn "Converted ${hf_model_id} but could not update OVMS's config.json --
add a model_config_list entry for base_path '${relative_base_path}' manually."
    fi
  else
    warn "No graph.pbtxt found at ${graph_dir} -- OVMS will not serve chat
completions for '${model_name}' until this is resolved (check the Model
Download microservice's logs above)."
  fi
}

# Lock-protected append/replace of a model_config_list entry -- mirrors
# _remove_model_from_ovms_config_locked's locked read-modify-write pattern.
_add_model_config_entry_locked() {
  local config_file="$1" name="$2" base_path="$3" tmp
  tmp="$(mktemp)"
  node -e '
      const fs = require("node:fs");
      const [configFile, name, basePath] = process.argv.slice(1);
      let data = {};
      try { data = JSON.parse(fs.readFileSync(configFile, "utf8")); } catch {}
      data.model_config_list = Array.isArray(data.model_config_list) ? data.model_config_list : [];
      data.model_config_list = data.model_config_list.filter((e) => e?.config?.name !== name);
      data.model_config_list.push({ config: { name, base_path: basePath } });
      data.mediapipe_config_list = Array.isArray(data.mediapipe_config_list) ? data.mediapipe_config_list : [];
      process.stdout.write(JSON.stringify(data, null, 2));
    ' "$config_file" "$name" "$base_path" >"$tmp" && mv -f "$tmp" "$config_file" || { rm -f "$tmp"; return 1; }
}

ensure_openvino_model_server() {
  local gpu_args
  local -a proxy_args=()
  ensure_ovms_config
  if docker inspect "$HARNESS_OVMS_CONTAINER" >/dev/null 2>&1; then
    docker restart "$HARNESS_OVMS_CONTAINER" >/dev/null 2>&1
    if [[ "$(docker inspect -f '{{.State.Running}}' "$HARNESS_OVMS_CONTAINER" 2>/dev/null)" != "true" ]]; then
      error "OpenVINO Model Server container exists but failed to come back up
after restart (${HARNESS_OVMS_CONTAINER}). Check 'docker logs
${HARNESS_OVMS_CONTAINER}' -- a common cause is another process already
using port ${HARNESS_OVMS_REST_PORT} (check with 'docker ps -a' and
'ss -tlnp | grep :${HARNESS_OVMS_REST_PORT}')."
    fi
    ok "OpenVINO Model Server restarted (${HARNESS_OVMS_CONTAINER})"
    return 0
  fi
  gpu_args="$(intel_gpu_docker_device_args)"
  docker_proxy_env_args_into proxy_args
  info "Starting OpenVINO Model Server on port ${HARNESS_OVMS_REST_PORT}…"
  # shellcheck disable=SC2086
  docker run -d --name "$HARNESS_OVMS_CONTAINER" --restart unless-stopped \
    -p "$(resolve_bind_host):${HARNESS_OVMS_REST_PORT}:8000" $gpu_args \
    "${proxy_args[@]}" \
    -v "${HARNESS_MODELS_DIR}:/models" \
    "$HARNESS_OVMS_IMAGE" \
    --rest_port 8000 --config_path /models/config.json $HARNESS_OVMS_EXTRA_ARGS \
    || error "Could not start OpenVINO Model Server."
  ok "OpenVINO Model Server is running on port ${HARNESS_OVMS_REST_PORT}"
}

# wait_for_ovms_model_ready model_name -- polls OVMS's KServe v2 readiness
# endpoint for the given model. A restarted/started container is running as
# soon as `docker restart`/`docker run` returns, but OVMS itself can take a
# few seconds longer to actually load the model into memory -- without this,
# an immediate request (e.g. the onboarding smoke test) can race a model
# that's still loading and get a spurious "graph definition not found".
wait_for_ovms_model_ready() {
  local model_name="$1" endpoint _
  command_exists curl || return 0
  endpoint="http://127.0.0.1:${HARNESS_OVMS_REST_PORT}/v2/models/${model_name}/ready"
  for _ in $(seq 1 30); do
    curl -sf "$endpoint" >/dev/null 2>&1 && return 0
    sleep 2
  done
  warn "Model '${model_name}' did not report ready within 60s (checked
${endpoint}); it may still be loading. Retry if the next step fails."
  return 1
}

# ensure_inference_backend — starts/health-checks whichever backend is
# selected. An explicit router endpoint always wins over HARNESS_LLM_PROVIDER,
# since routing to infrastructure this installer doesn't own is the point.
ensure_inference_backend() {
  if [[ -n "$HARNESS_LLM_ROUTER_ENDPOINT" ]]; then
    if [[ -n "${HARNESS_HF_MODEL:-}" ]]; then
      warn "HARNESS_HF_MODEL is ignored when HARNESS_LLM_ROUTER_ENDPOINT is set —
no local model export happens; the external endpoint owns model selection."
    fi
    info "Routing to external endpoint: ${HARNESS_LLM_ROUTER_ENDPOINT}"
    info "This installer will not start, stop, or health-check that endpoint."
    return 0
  fi
  case "$HARNESS_LLM_PROVIDER" in
    ovms)
      ensure_openvino_model_server
      if [[ -n "${HARNESS_HF_MODEL:-}" ]]; then
        case "$HARNESS_OVMS_EXPORTER" in
          docker-pull) export_model_via_docker_pull "$HARNESS_HF_MODEL" ;;
          export-model-py) export_model_to_openvino "$HARNESS_HF_MODEL" ;;
          model-download) export_model_via_model_download "$HARNESS_HF_MODEL" ;;
          *) error "Unknown HARNESS_OVMS_EXPORTER: ${HARNESS_OVMS_EXPORTER} (expected
docker-pull, export-model-py, or model-download)." ;;
        esac
        ensure_openvino_model_server
        wait_for_ovms_model_ready "${HARNESS_HF_MODEL##*/}"
      elif ! ovms_has_exported_models; then
        warn "No model is exported yet and no HARNESS_HF_MODEL was given -- OVMS is
running but will not serve chat completions until a model is exported.
Re-run with --hf-model <huggingface-model-id>, or set
HARNESS_LLM_ROUTER_ENDPOINT to route to an existing external endpoint instead."
      fi
      ;;
    *)
      error "Unknown HARNESS_LLM_PROVIDER: ${HARNESS_LLM_PROVIDER} (expected: ovms).
Set HARNESS_LLM_ROUTER_ENDPOINT instead to route to an existing external
OpenAI-compatible endpoint without this installer managing a backend."
      ;;
  esac
}

# ovms_has_exported_models — true if config.json already lists at least one
# exported servable, so a fresh install without --hf-model can tell "nothing
# to serve yet" apart from "already has models from a prior export". Checks
# model_config_list -- confirmed (by inspecting a real export) to be what
# export_model.py actually populates; OVMS serves chat completions via the
# graph.pbtxt it finds in that entry's base_path, not a separate
# mediapipe_config_list registration. Checked too, in case that ever changes.
ovms_has_exported_models() {
  local config_file="${HARNESS_MODELS_DIR}/config.json"
  [[ -f "$config_file" ]] || return 1
  node -e '
    try {
      const d = JSON.parse(require("node:fs").readFileSync(process.argv[1], "utf8"));
      const hasModels = Array.isArray(d.model_config_list) && d.model_config_list.length > 0;
      const hasGraphs = Array.isArray(d.mediapipe_config_list) && d.mediapipe_config_list.length > 0;
      process.exit(hasModels || hasGraphs ? 0 : 1);
    } catch { process.exit(1); }
  ' "$config_file"
}

harness_llm_endpoint() {
  if [[ -n "$HARNESS_LLM_ROUTER_ENDPOINT" ]]; then
    printf '%s' "$HARNESS_LLM_ROUTER_ENDPOINT"
    return 0
  fi
  printf 'http://%s:%s/v3' "$(resolve_advertised_host)" "$HARNESS_OVMS_REST_PORT"
}

# Rejects path-traversal/empty/current-dir/hidden names before any
# model_dir/config.json touch — the leading-dot check also keeps this from
# targeting internal dirs like the export venv (.export-venv).
validate_model_name() {
  local name="$1"
  [[ -n "$name" && "$name" != .* && "$name" != *"/"* && "$name" != *".."* ]]
}

list_exported_models() {
  local dir="$HARNESS_MODELS_DIR" entry name found=0
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
  local name="$1" dir="$HARNESS_MODELS_DIR" model_dir config_file
  [[ -n "$name" ]] || error "Usage: ./install.sh models remove <name>"
  validate_model_name "$name" || error "Invalid model name: ${name}"
  model_dir="${dir}/${name}"
  [[ -d "$model_dir" ]] || error "Model '${name}' is not exported (looked in ${model_dir})."
  config_file="${dir}/config.json"
  if [[ -f "$config_file" ]]; then
    with_state_lock ovms-config _remove_model_from_ovms_config_locked "$config_file" "$name" \
      || error "Could not update ${config_file} to remove '${name}'; leaving the model
directory in place so OVMS's config and the exported files don't disagree.
Check disk space/permissions on ${config_file} and retry."
  fi
  rm -rf -- "$model_dir"
  ok "Removed exported model '${name}' (${model_dir})"
  if command_exists docker && docker inspect "$HARNESS_OVMS_CONTAINER" >/dev/null 2>&1; then
    docker restart "$HARNESS_OVMS_CONTAINER" >/dev/null 2>&1 \
      && info "Restarted ${HARNESS_OVMS_CONTAINER} so it stops serving the removed model."
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
    ' "$config_file" "$name" >"$tmp" && mv -f "$tmp" "$config_file" || { rm -f "$tmp"; return 1; }
}

# Used by the uninstaller; leaves the image and models dir untouched. No-op
# when routed externally, since this installer never started that backend.
remove_openvino_model_server() {
  [[ -z "$HARNESS_LLM_ROUTER_ENDPOINT" ]] || return 0
  command_exists docker || return 0
  docker rm -f "$HARNESS_OVMS_CONTAINER" >/dev/null 2>&1 || true
}
