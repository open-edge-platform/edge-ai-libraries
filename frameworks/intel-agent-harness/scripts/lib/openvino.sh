# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=bash
# OpenVINO Model Server (OVMS) — serves an OpenAI-compatible chat-completions
# endpoint on Intel Core Ultra iGPU and Arc (CRI) GPUs.

# Pinned to 2026.1 rather than a newer release (e.g. 2026.4.x) because
# OVMS's "-py" convenience variant (used by the default docker-pull
# exporter below) is published under a different, coarser version scheme
# than "-gpu"/the base serving image -- two-part "X.Y-py" tags, not
# "X.Y.Z-py" -- and has not had a new "-py" tag published since 2026.1,
# even though "-gpu"/base images have since moved through 2026.2.x,
# 2026.3.x, and 2026.4.x. Confirmed against the openvino/model_server
# Docker Hub tag list (2026-10-14): "2026.1-gpu" and "2026.1-py" are the
# newest release where both variants actually exist together, so this is
# the newest version the default exporter can actually pull working.
# Bump this once OVMS publishes a newer matching "-py" tag.
HARNESS_OVMS_IMAGE="${HARNESS_OVMS_IMAGE:-openvino/model_server:2026.1-gpu}"
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
HARNESS_OVMS_EXPORT_MODEL_REF="${HARNESS_OVMS_EXPORT_MODEL_REF:-v2026.1}"

# Known-good SHA-256 for export_model.py / requirements.txt at the pinned
# ref above (verified against openvinotoolkit/model_server). IMPORTANT:
# update both hashes whenever HARNESS_OVMS_EXPORT_MODEL_REF's default
# changes; they are only applied when the ref in use matches this exact tag.
_OVMS_EXPORT_MODEL_PINNED_REF="v2026.1"
_OVMS_EXPORT_MODEL_PY_SHA256="7e419913a1ce3e93aab01d9b66b2f8ac008a2a6bce29069fe2ecd6152b323b05"
_OVMS_EXPORT_MODEL_REQUIREMENTS_SHA256="95b51ba80b33f66fbec3ec7e4c27fa440391b88b25ff6a43f2fdbe436adcb25e"

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
  # --model_name's documented effect on output placement (OVMS's own "Pull
  # mode with optimum cli" doc) has been observed not to hold on at least
  # one real release (2026.1-py): the export instead lands nested under the
  # full --source_model path -- the same layout export_model_via_model_download
  # below already has to account for -- so both locations are checked
  # throughout this function, not just the documented flat one.
  local existing_base_path=""
  if [[ -f "${out_dir}/graph.pbtxt" ]]; then
    existing_base_path="$model_name"
  elif [[ -f "${HARNESS_MODELS_DIR}/${hf_model_id}/graph.pbtxt" ]]; then
    existing_base_path="$hf_model_id"
  fi
  if [[ -n "$existing_base_path" ]]; then
    info "Model '${model_name}' is already exported."
    # Re-registering unconditionally (not just when the directory first
    # appears) is cheap and idempotent (_add_model_config_entry_locked
    # replaces any existing same-name entry) -- without this, a directory
    # that exists but was never registered (or whose config.json entry was
    # later lost -- e.g. a reset/edited config.json, or a crash between
    # pull and registration on an earlier run) would be silently treated as
    # "fully set up" forever, since this fast path used to return before
    # ever reaching the registration step below.
    ensure_ovms_config
    with_state_lock ovms-config _add_model_config_entry_locked \
      "${HARNESS_MODELS_DIR}/config.json" "$model_name" "$existing_base_path" \
      || warn "Model '${model_name}' is already exported but could not confirm its
OVMS config.json registration -- add a model_config_list entry for base_path
'${existing_base_path}' manually if it doesn't serve requests."
    return 0
  fi
  command_exists docker || error "Docker is required to pull/convert models via the OVMS -py image."
  # The -py image's bundled optimum-cli/httpx tooling is the same conversion
  # stack export_model_to_openvino/export_model_via_model_download use
  # host-side -- it chokes the same way on a malformed proxy scheme, so this
  # exporter needs the same fail-fast check before doing any pull/convert work.
  assert_proxy_scheme_supported
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
    rm -rf -- "$out_dir" "${HARNESS_MODELS_DIR}/${hf_model_id}"
    error "Pulling/converting ${hf_model_id} via ${pull_image} failed. Check network
access to huggingface.co, and that '${pull_image}' is a published tag
(the -py variant may lag behind HARNESS_OVMS_IMAGE's own release) -- or try
HARNESS_OVMS_EXPORTER=export-model-py as a fallback."
  fi
  local relative_base_path
  if [[ -f "${out_dir}/graph.pbtxt" ]]; then
    relative_base_path="$model_name"
  elif [[ -f "${HARNESS_MODELS_DIR}/${hf_model_id}/graph.pbtxt" ]]; then
    out_dir="${HARNESS_MODELS_DIR}/${hf_model_id}"
    relative_base_path="$hf_model_id"
  else
    error "No graph.pbtxt found at ${out_dir} or ${HARNESS_MODELS_DIR}/${hf_model_id}
after pull -- OVMS will not serve chat completions for '${model_name}'."
  fi
  if with_state_lock ovms-config _add_model_config_entry_locked \
      "${HARNESS_MODELS_DIR}/config.json" "$model_name" "$relative_base_path"; then
    ok "Exported ${hf_model_id} -> ${out_dir} (registered with OVMS)"
  else
    error "Converted ${hf_model_id} but could not update OVMS's config.json --
add a model_config_list entry for base_path '${relative_base_path}' manually."
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
  # mktemp creates its file mode 0600, owned by whichever host user is
  # running the installer -- but the OVMS *server* container (unlike the
  # -py pull/export helper, which runs with an explicit `-u $(id -u):$(id
  # -g)`) runs as the image's own fixed internal user (the published
  # openvino/model_server image's Dockerfile.redhat ends in `USER ovms`,
  # uid/gid 5000), which essentially never matches the host user. Without
  # this chmod, replacing config.json here leaves it unreadable by that
  # uid, so OVMS's own ifs.good() check on /models/config.json fails at
  # startup ("Configuration file is invalid") and the container crash-loops
  # on every restart after the very first model registration -- confirmed
  # against a real OVMS server log. ensure_ovms_config's initial plain
  # `printf >file` happens to avoid this (its permissions come from umask,
  # typically 644), which is why only the *first* registration ever breaks.
  chmod 644 "$tmp"
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
    record_ovms_managed 0
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
      record_ovms_managed 1
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
        # wait_for_ovms_model_ready returning 1 means "still loading, not
        # confirmed ready yet" -- its own warn() message is the complete,
        # intended signal for that ("retry if the next step fails"), not a
        # fatal condition. Without `|| true`, that bare return 1 was
        # silently killing the *entire* installer right here under set -e
        # (no [ERROR], the script just exited) whenever a model took longer
        # than 60s to report ready, well before reaching the "next step" the
        # warning itself refers to.
        wait_for_ovms_model_ready "${HARNESS_HF_MODEL##*/}" || true
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

# ovms_sole_registered_model_name — the one already-registered model's name,
# printed only when config.json's model_config_list has *exactly* one entry
# (unambiguous). Used by run_agent_onboard as a smarter fallback than the
# literal string "default" for a standalone "./install.sh onboard" run with
# neither --hf-model nor HARNESS_LLM_MODEL given -- "default" never matches
# a real registered model name (exports are always registered under the HF
# model's own basename), so that fallback previously 404'd unconditionally
# whenever a model was already exported and serving. Deliberately returns
# nothing (not a guess) when zero or more-than-one models are registered,
# since picking the wrong one silently would be worse than the existing
# "default" 404, which at least prompts the operator to check what's
# actually registered.
ovms_sole_registered_model_name() {
  local config_file="${HARNESS_MODELS_DIR}/config.json"
  [[ -f "$config_file" ]] || return 1
  node -e '
    try {
      const d = JSON.parse(require("node:fs").readFileSync(process.argv[1], "utf8"));
      const names = (Array.isArray(d.model_config_list) ? d.model_config_list : [])
        .map((e) => e?.config?.name)
        .filter(Boolean);
      if (names.length === 1) { process.stdout.write(names[0]); process.exit(0); }
      process.exit(1);
    } catch { process.exit(1); }
  ' "$config_file"
}

harness_llm_endpoint() {
  local host
  if [[ -n "$HARNESS_LLM_ROUTER_ENDPOINT" ]]; then
    printf '%s' "$HARNESS_LLM_ROUTER_ENDPOINT"
    return 0
  fi
  # Assigned as its own plain statement (not inlined into the printf below)
  # so a failure inside resolve_advertised_host (e.g. its
  # assert_state_path_safe/assert_owned_by_current_user tamper checks on
  # ~/.intel-agent/advertised-host) actually aborts via set -e instead of
  # being silently discarded -- a command substitution's exit status is
  # only checked by set -e when it's a bare assignment, not when embedded
  # as another command's argument (confirmed: printf always "succeeds"
  # regardless of what its arguments evaluated to, so the failure would
  # otherwise go unnoticed and harness_llm_endpoint() would return a
  # malformed empty-host URL that then gets persisted into the agent's own
  # config file by run_agent_onboard's callers).
  host="$(resolve_advertised_host)" || return 1
  printf 'http://%s:%s/v3' "$host" "$HARNESS_OVMS_REST_PORT"
}

# Rejects path-traversal/empty/current-dir/hidden names before any
# model_dir/config.json touch — the leading-dot check also keeps this from
# targeting internal dirs like the export venv (.export-venv).
validate_model_name() {
  local name="$1"
  [[ -n "$name" && "$name" != .* && "$name" != *"/"* && "$name" != *".."* ]]
}

# Reads registered models from config.json (the same authoritative source
# remove_exported_model now consults) rather than only scanning top-level
# directories -- some exporters nest an export's files one level deeper
# than the user-facing model name (see export_model_via_docker_pull's
# comment), which a raw directory scan would otherwise misreport (e.g.
# showing "Qwen" instead of "Qwen2.5-0.5B-Instruct" for a model nested
# under "Qwen/..."). Falls back to a directory scan if config.json has no
# entries yet, so models from an exporter/version that registered nothing
# there are still visible.
list_exported_models() {
  local dir="$HARNESS_MODELS_DIR" entry name found=0 line config_file
  config_file="${dir}/config.json"
  if [[ -f "$config_file" ]]; then
    while IFS= read -r line; do
      [[ -n "$line" ]] || continue
      found=1
      printf '  %s\n' "$line"
    done < <(node -e '
      try {
        const data = JSON.parse(require("node:fs").readFileSync(process.argv[1], "utf8"));
        const list = Array.isArray(data.model_config_list) ? data.model_config_list : [];
        for (const e of list) { if (e?.config?.name) console.log(e.config.name); }
      } catch {}
    ' "$config_file")
    [[ "$found" -eq 1 ]] && return 0
  fi
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
  local name="$1" dir="$HARNESS_MODELS_DIR" model_dir config_file base_path
  [[ -n "$name" ]] || error "Usage: ./install.sh models remove <name>"
  validate_model_name "$name" || error "Invalid model name: ${name}"
  config_file="${dir}/config.json"
  # Prefer the base_path OVMS was actually registered with over assuming a
  # flat <models-dir>/<name> layout -- some exporters (docker-pull, at
  # least on OVMS 2026.1-py, and model-download) nest the export under the
  # full HF source_model path (e.g. "Qwen/Qwen2.5-0.5B-Instruct") instead
  # of the flat model name. Falls back to the flat guess for models
  # registered under the older convention or with no config.json entry.
  base_path="$(_ovms_config_base_path_for "$config_file" "$name")"
  if [[ -n "$base_path" ]]; then
    [[ "$base_path" == *".."* ]] && error "Refusing a base_path containing '..' for '${name}' (${base_path})."
    model_dir="${dir}/${base_path}"
  else
    model_dir="${dir}/${name}"
  fi
  [[ -d "$model_dir" ]] || error "Model '${name}' is not exported (looked in ${model_dir})."
  if [[ -f "$config_file" ]]; then
    with_state_lock ovms-config _remove_model_from_ovms_config_locked "$config_file" "$name" \
      || error "Could not update ${config_file} to remove '${name}'; leaving the model
directory in place so OVMS's config and the exported files don't disagree.
Check disk space/permissions on ${config_file} and retry."
  fi
  rm -rf -- "$model_dir"
  # A nested base_path (e.g. "Qwen/Qwen2.5-0.5B-Instruct") leaves an empty
  # parent directory ("Qwen/") behind after removing just the leaf -- clean
  # it up too so list_exported_models' directory-scan fallback doesn't
  # later misreport it as a phantom model. rmdir only succeeds on a truly
  # empty directory, so this is a safe no-op for a flat (non-nested) layout.
  local parent_dir
  parent_dir="$(dirname "$model_dir")"
  [[ "$parent_dir" != "$dir" ]] && { rmdir "$parent_dir" 2>/dev/null || true; }
  ok "Removed exported model '${name}' (${model_dir})"
  if command_exists docker && docker inspect "$HARNESS_OVMS_CONTAINER" >/dev/null 2>&1; then
    docker restart "$HARNESS_OVMS_CONTAINER" >/dev/null 2>&1 \
      && info "Restarted ${HARNESS_OVMS_CONTAINER} so it stops serving the removed model."
  fi
}

# _ovms_config_base_path_for config_file name — looks up the base_path a
# model was actually registered under in config.json's model_config_list,
# empty if not found (e.g. no config.json yet, or a model never registered
# there). The authoritative source for where an exported model's files
# really live, since exporters don't all use the same on-disk layout.
_ovms_config_base_path_for() {
  local config_file="$1" name="$2"
  [[ -f "$config_file" ]] || return 0
  node -e '
    try {
      const data = JSON.parse(require("node:fs").readFileSync(process.argv[1], "utf8"));
      const list = Array.isArray(data.model_config_list) ? data.model_config_list : [];
      const entry = list.find((e) => e?.config?.name === process.argv[2]);
      if (entry?.config?.base_path) process.stdout.write(String(entry.config.base_path));
    } catch {}
  ' "$config_file" "$name"
}


# Lock-protected (with_state_lock) so a concurrent export/remove can't race
# on the same shared config.json read-modify-write.
_remove_model_from_ovms_config_locked() {
  local config_file="$1" name="$2" tmp
  tmp="$(mktemp)"
  # See _add_model_config_entry_locked's matching comment -- same
  # mktemp-defaults-to-0600 vs. OVMS's fixed non-root container uid issue
  # applies here too.
  chmod 644 "$tmp"
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

# ovms_managed_marker_file / record_ovms_managed / ovms_is_managed — persist
# whether the most recent install run manages OVMS locally (vs. routing to
# an external endpoint), so uninstall reads *that* instead of re-deriving it
# from HARNESS_LLM_ROUTER_ENDPOINT's *current* value. Without this, changing
# the router endpoint between install and uninstall can either leave a
# harness-owned OVMS container behind, or remove an unrelated container that
# merely happens to share its name.
ovms_managed_marker_file() {
  printf '%s/ovms-managed' "$(harness_state_root)"
}

record_ovms_managed() {
  ensure_state_dir >/dev/null
  atomic_write_file "$(ovms_managed_marker_file)" "$1"
}

# Falls back to the current HARNESS_LLM_ROUTER_ENDPOINT only when no marker
# exists yet (installs made before this marker was introduced).
ovms_is_managed() {
  local file
  file="$(ovms_managed_marker_file)"
  if [[ -f "$file" ]]; then
    assert_state_path_safe "$file"
    assert_owned_by_current_user "$file"
    [[ "$(cat "$file" 2>/dev/null)" == "1" ]]
    return
  fi
  [[ -z "$HARNESS_LLM_ROUTER_ENDPOINT" ]]
}

# Used by the uninstaller; leaves the image and models dir untouched. No-op
# when this install routed externally, since this installer never started
# that backend (see ovms_is_managed above for how that's determined).
remove_openvino_model_server() {
  ovms_is_managed || return 0
  command_exists docker || return 0
  docker rm -f "$HARNESS_OVMS_CONTAINER" >/dev/null 2>&1 || true
}
