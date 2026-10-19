# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=bash
# OpenVINO Model Server (OVMS) — serves an OpenAI-compatible chat-completions
# endpoint on Intel Core Ultra iGPU and Arc (CRI) GPUs.

# Serving image: tracks a recent OVMS release. The default docker-pull
# exporter below needs OVMS's "-py" convenience variant, which is published
# under a coarser version scheme (two-part "X.Y-py" tags) and has not had a
# new tag since 2026.1 -- so the export image is pinned separately
# (HARNESS_OVMS_EXPORT_IMAGE) instead of being derived from this one.
# Exported model directories are plain OpenVINO IR + graph.pbtxt, which a
# newer serving image is expected to load; that pairing is not covered by
# the smoke test, only by test/full-flow-test.sh on real hardware.
HARNESS_OVMS_IMAGE="${HARNESS_OVMS_IMAGE:-openvino/model_server:2026.4.1-gpu}"
# Image used only by the docker-pull exporter (needs the "-py" variant).
HARNESS_OVMS_EXPORT_IMAGE="${HARNESS_OVMS_EXPORT_IMAGE:-openvino/model_server:2026.1-py}"
HARNESS_OVMS_REST_PORT="${HARNESS_OVMS_REST_PORT:-8000}"
HARNESS_MODELS_DIR="${HARNESS_MODELS_DIR:-$HOME/.agent-harness-install/models}"
HARNESS_OVMS_CONTAINER="${HARNESS_OVMS_CONTAINER:-agent-harness-install-ovms}"
# Shared user-defined network joining OVMS and the Inference Router, so IR
# can reach OVMS by container name + its internal port (8000) regardless of
# HARNESS_OVMS_REST_PORT/HARNESS_BIND_HOST -- the default bridge network
# gives containers no DNS-by-name resolution, and OVMS's host-published port
# is loopback-only by default (resolve_bind_host), neither of which a
# separate container (IR) can reach. See ensure_backend_network.
HARNESS_BACKEND_NETWORK="${HARNESS_BACKEND_NETWORK:-agent-harness-install-backend}"
# Extra OVMS server flags, e.g. "--tool_parser <parser> --task text_generation"
# for agents that need OpenAI-style tool calls.
HARNESS_OVMS_EXTRA_ARGS="${HARNESS_OVMS_EXTRA_ARGS:-}"

# Set HARNESS_LLM_ROUTER_ENDPOINT to point this installer's Inference Router
# (IR) at an existing OpenAI-compatible server instead of its own OVMS
# container -- e.g. an internal LiteLLM instance, a corporate API gateway, or
# a cloud endpoint. Inference still goes through IR (agents are wired to IR
# either way); only IR's upstream provider changes. When set, this installer
# never starts, stops, or health-checks OVMS, and HARNESS_LLM_PROVIDER is
# ignored. HARNESS_LLM_ROUTER_API_KEY, if set, is sent as a bearer token.
# The model name IR forwards upstream comes from --model/HARNESS_HF_MODEL (or
# HARNESS_LLM_MODEL).
HARNESS_LLM_PROVIDER="${HARNESS_LLM_PROVIDER:-ovms}"
HARNESS_LLM_ROUTER_ENDPOINT="${HARNESS_LLM_ROUTER_ENDPOINT:-}"

# Which tool performs --model export: docker-pull (default) runs OVMS's
# own "-py" Docker image in --pull mode to download/convert/quantize a HF
# model entirely via Docker -- no host Python venv or separate script fetch
# needed, since it reuses the same trusted, version-pinned image this
# installer already runs OVMS itself from. export-model-py (legacy) runs
# OVMS's export_model.py in a host-side venv, fetched/pinned from GitHub
# raw content -- kept for hosts that can't/won't run the conversion inside
# Docker. model-download is a third, newer/less battle-tested alternative
# (edge-ai-libraries' Model Download microservice -- see
# export_model_via_model_download below). hf-snapshot is a fourth option
# for HF repos that are already published as ready-to-serve OpenVINO IR +
# an OVMS MediaPipe graph (e.g. the OpenVINO organization's own
# pre-converted model repos) -- a plain huggingface_hub.snapshot_download,
# no optimum-cli conversion step at all (see export_model_via_hf_snapshot
# below). All four register the resulting model into config.json the same
# way (a model_config_list entry).
# Captured before defaulting so apply_model_source_defaults can tell "caller
# chose this exporter explicitly" apart from "left at the default".
HARNESS_OVMS_EXPORTER_WAS_SET="${HARNESS_OVMS_EXPORTER:+1}"
HARNESS_OVMS_EXPORTER="${HARNESS_OVMS_EXPORTER:-docker-pull}"

# Pins an exact HF revision (commit SHA/tag/branch) for the hf-snapshot
# exporter, so a model author updating "main" underneath you can't silently
# change what gets deployed. Empty means "main"/the repo's default branch.
HARNESS_HF_MODEL_REVISION="${HARNESS_HF_MODEL_REVISION:-}"

# export_model.py is OVMS's own model-export tool — unlike plain
# `optimum-cli export openvino`, it also writes the graph.pbtxt MediaPipe
# servable definition OVMS's /v3/chat/completions endpoint requires for LLMs.
# Pinned to the release tag matching HARNESS_OVMS_EXPORT_IMAGE for
# reproducible, version-compatible exports.
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
# the server itself from (HARNESS_OVMS_EXPORT_IMAGE, pinned separately from the
# serving image -- see its comment above).
export_model_via_docker_pull() {
  local hf_model_id="$1" model_name="${2:-${1##*/}}" out_dir pull_image target_device
  local gpu_args group_add_args
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
  pull_image="$HARNESS_OVMS_EXPORT_IMAGE"
  target_device="CPU"
  gpu_args="$(intel_gpu_docker_device_args)"
  group_add_args=""
  if [[ -n "$gpu_args" ]]; then
    target_device="GPU"
    # Needed alongside --device for the same reason as
    # ensure_openvino_model_server's matching comment -- this container runs
    # as the host user (-u "$(id -u):$(id -g)" below), but that user's own
    # render-group membership doesn't carry over into the container unless
    # explicitly added here too.
    group_add_args="$(intel_gpu_docker_group_add_args)"
  fi
  local -a proxy_args=()
  docker_proxy_env_args_into proxy_args
  # Forward a Hugging Face token (by name, so it never appears on the
  # command line) for gated/private models.
  local hf_var
  for hf_var in HF_TOKEN HUGGINGFACEHUB_API_TOKEN; do
    [[ -z "${!hf_var:-}" ]] || proxy_args+=(-e "$hf_var")
  done
  # shellcheck disable=SC2086
  if ! spin "Pulling+converting ${hf_model_id} via ${pull_image} (--pull, target: ${target_device})" \
    docker run --rm -u "$(id -u):$(id -g)" \
      -v "${HARNESS_MODELS_DIR}:/models:rw" \
      $gpu_args $group_add_args \
      "${proxy_args[@]}" \
      "$pull_image" --pull \
      --source_model "$hf_model_id" --model_name "$model_name" \
      --model_repository_path /models --task text_generation \
      --weight-format "$HARNESS_MODEL_PRECISION" --target_device "$target_device"; then
    rm -rf -- "$out_dir" "${HARNESS_MODELS_DIR:?}/${hf_model_id:?}"
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
  if [[ -f "${out_dir}/graph.pbtxt" ]]; then
    info "Model '${model_name}' is already exported."
    return 0
  fi
  command_exists python3 || error "python3 is required to export models to OpenVINO IR --
was it skipped via SKIP_PYTHON=1? Run ./startup.sh --skip-docker --skip-nodejs."
  python_venv_usable || error "python3's venv module is not usable (python3 -m venv
--help fails) -- Debian/Ubuntu ship this as the separate python3-venv package.
Run ./startup.sh --skip-docker --skip-nodejs."
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
# Pinned get_model.sh: commit 45fa231a (microservices/model-download/scripts/
# get_model.sh, unchanged on main as of this writing) and its SHA-256, so the
# default configuration verifies out of the box. A custom ref needs its own
# HARNESS_MODEL_DOWNLOAD_SCRIPT_SHA256 (or the explicit unverified opt-out).
_MODEL_DOWNLOAD_PINNED_REF="45fa231a51b63423b3698282aa83ccb1e5b4685a"
_MODEL_DOWNLOAD_PINNED_SHA256="7267ef551f1a4baba560982be7f1b5df33a557dc1849147a978cc00636db46dc"
HARNESS_MODEL_DOWNLOAD_SCRIPT_REF="${HARNESS_MODEL_DOWNLOAD_SCRIPT_REF:-$_MODEL_DOWNLOAD_PINNED_REF}"
HARNESS_MODEL_DOWNLOAD_IMAGE_TAG="${HARNESS_MODEL_DOWNLOAD_IMAGE_TAG:-}"
# get_model.sh converts with its own OVMS release (default v2025.4.1), which
# can differ from the OVMS image this installer serves with; set this to pass
# --ovms-release-tag explicitly. Unset leaves get_model.sh's default.
HARNESS_MODEL_DOWNLOAD_OVMS_RELEASE_TAG="${HARNESS_MODEL_DOWNLOAD_OVMS_RELEASE_TAG:-}"
# Model Download pulls from several hubs (see its own docs:
# microservices/model-download/docs/user-guide/get-started.md). --model-hub
# accepts all of them; "openvino" (the default) means "pull from Hugging Face
# and convert to OpenVINO IR" (--is-ovms). A downloaded model is registered
# with OVMS (and wired to the Inference Router) only when it contains a
# graph.pbtxt -- the openvino hub always produces one, and a pre-converted
# Hugging Face repo or a remote-url tarball may. Everything else is
# downloaded and tracked for `models list/remove`, with a note that agents
# will not use it.
HARNESS_MODEL_HUB_WAS_SET="${HARNESS_MODEL_HUB:+1}"
HARNESS_MODEL_HUB="${HARNESS_MODEL_HUB:-openvino}"
HARNESS_MODEL_TYPE="${HARNESS_MODEL_TYPE:-}"
HARNESS_MODEL_DOWNLOAD_REVISION="${HARNESS_MODEL_DOWNLOAD_REVISION:-}"
HARNESS_MODEL_PRECISION="${HARNESS_MODEL_PRECISION:-int8}"
HARNESS_MODEL_DEVICE="${HARNESS_MODEL_DEVICE:-CPU}"
HARNESS_MODEL_CONFIG_JSON="${HARNESS_MODEL_CONFIG_JSON:-}"
HARNESS_MODEL_PLUGINS="${HARNESS_MODEL_PLUGINS:-}"
# Space-separated list of model options given on the command line
# (type, device, revision, config, precision), so options an exporter ignores
# can be reported instead of silently dropped.
HARNESS_MODEL_OPTS_GIVEN="${HARNESS_MODEL_OPTS_GIVEN:-}"

_MODEL_HUBS="openvino huggingface ollama remote-url ultralytics geti pipeline-zoo-models omz hls"

# model_hub_is_known HUB -- true for a hub Model Download supports.
model_hub_is_known() {
  [[ " $_MODEL_HUBS " == *" $1 "* ]]
}

# model_hub_unserved_reason HUB -- the one place that says whether OVMS can
# serve what a hub produces. Prints nothing (and returns 0) for hubs that may
# produce a servable graph.pbtxt (checked after the download); otherwise
# prints why not and returns 1. Flip a hub here when OVMS gains support
# (e.g. Ollama).
model_hub_unserved_reason() {
  case "$1" in
    openvino | huggingface | remote-url) return 0 ;;
    ollama)
      printf 'Ollama-format models are not loadable by OVMS (yet)'
      return 1 ;;
    ultralytics | geti | pipeline-zoo-models | omz | hls)
      printf 'it is a vision/other-runtime model, not something an agent can use'
      return 1 ;;
    *)
      printf 'unknown hub'
      return 1 ;;
  esac
}

# model_dir_name MODEL_ID -- the on-disk/registry name for a model id: the
# last path component with anything outside [A-Za-z0-9._-] replaced by '-'.
model_dir_name() {
  local id="${1##*/}"
  printf '%s' "${id//[^A-Za-z0-9._-]/-}"
}

# validate_model_for_hub HUB MODEL_ID -- per-hub shape check of --model, run
# before anything touches disk (the exporters build rm -rf cleanup paths from
# it). Prints the reason on failure.
validate_model_for_hub() {
  local hub="$1" id="$2"
  case "$hub" in
    openvino | huggingface)
      validate_hf_model_id "$id" \
        || { printf "expected a Hugging Face id like 'org/name' (letters, digits, '.', '_', '-'; no empty parts, '..' or trailing '/')"; return 1; } ;;
    ollama)
      # name[:tag], optionally namespaced (e.g. hf.co/user/Repo-GGUF:Q4_K_M)
      local ollama_re='^[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*){0,2}(:[A-Za-z0-9._-]+)?$'
      [[ "$id" =~ $ollama_re && "$id" != *".."* ]] \
        || { printf "expected an Ollama name like 'name' or 'name:tag'"; return 1; } ;;
    remote-url)
      [[ "$id" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ && "$id" != *".."* ]] \
        || { printf "expected a plain model name (letters, digits, '.', '_', '-'), substituted for {name} in the URL"; return 1; }
      [[ "$HARNESS_MODEL_CONFIG_JSON" == *'"url"'* ]] \
        || { printf "remote-url needs the archive URL: --model-config '{\"url\":\"https://…/{name}.tar\"}'"; return 1; } ;;
    ultralytics | pipeline-zoo-models | omz)
      [[ "$id" =~ ^[A-Za-z0-9][A-Za-z0-9._,-]*$ && "$id" != *".."* ]] \
        || { printf "expected a model name (or a comma-separated list) of letters, digits, '.', '_', '-'"; return 1; } ;;
    geti)
      local geti_re='^[A-Za-z0-9][A-Za-z0-9 ._-]*$'
      [[ "$id" =~ $geti_re && "$id" != *".."* ]] \
        || { printf "expected a Geti project name"; return 1; }
      [[ -n "${GETI_HOST:-}" && -n "${GETI_TOKEN:-}" && -n "${GETI_WORKSPACE_ID:-}" ]] \
        || { printf "geti needs GETI_HOST, GETI_TOKEN and GETI_WORKSPACE_ID in the environment"; return 1; } ;;
    hls)
      [[ "$id" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ && "$id" != *".."* ]] \
        || { printf "expected a plain label (letters, digits, '.', '_', '-')"; return 1; }
      case "$HARNESS_MODEL_TYPE" in
        3d-pose | rppg | ai-ecg) ;;
        *) printf "hls needs --model-type 3d-pose, rppg or ai-ecg"; return 1 ;;
      esac ;;
    *)
      printf "unknown hub '%s' (supported: %s)" "$hub" "$_MODEL_HUBS"
      return 1 ;;
  esac
}

# apply_model_source_defaults -- called once after option parsing. Validates
# --model-hub, makes an explicit non-default hub select the Model Download
# exporter on its own, and reports model options the chosen exporter ignores.
apply_model_source_defaults() {
  local hub="$HARNESS_MODEL_HUB" opt
  model_hub_is_known "$hub" \
    || error "Unknown model hub '${hub}'. Supported hubs: ${_MODEL_HUBS}."
  case "$HARNESS_MODEL_PRECISION" in
    int4 | int8 | fp16 | fp32) ;;
    *) error "Invalid model precision '${HARNESS_MODEL_PRECISION}' (expected int4, int8, fp16 or fp32)." ;;
  esac

  if [[ -n "$HARNESS_MODEL_HUB_WAS_SET" && "$hub" != "openvino" ]]; then
    if [[ -z "$HARNESS_OVMS_EXPORTER_WAS_SET" ]]; then
      HARNESS_OVMS_EXPORTER=model-download
    elif [[ "$HARNESS_OVMS_EXPORTER" != "model-download" ]]; then
      error "Model hub '${hub}' needs the model-download exporter, but HARNESS_OVMS_EXPORTER=${HARNESS_OVMS_EXPORTER}.
Unset HARNESS_OVMS_EXPORTER (or set it to model-download), or drop --model-hub."
    fi
  fi
  [[ -n "${HARNESS_HF_MODEL:-}" ]] || return 0

  # Fail fast, before startup.sh installs anything. With an external router
  # the name is the external endpoint's own model name, so it is not checked.
  if [[ -z "${HARNESS_LLM_ROUTER_ENDPOINT:-}" ]]; then
    local validation_hub="openvino" invalid_reason
    [[ "$HARNESS_OVMS_EXPORTER" != "model-download" ]] || validation_hub="$hub"
    invalid_reason="$(validate_model_for_hub "$validation_hub" "$HARNESS_HF_MODEL")" \
      || error "Invalid --model '${HARNESS_HF_MODEL}' for hub '${validation_hub}': ${invalid_reason}."
  fi

  local applies_to
  for opt in $HARNESS_MODEL_OPTS_GIVEN; do
    case "${opt}:${HARNESS_OVMS_EXPORTER}" in
      *:model-download | precision:docker-pull | revision:hf-snapshot) continue ;;
    esac
    case "$opt" in
      precision) applies_to="model-download and docker-pull" ;;
      revision) applies_to="model-download and hf-snapshot" ;;
      *) applies_to="model-download" ;;
    esac
    warn "--model-${opt} is ignored by the '${HARNESS_OVMS_EXPORTER}' exporter (it applies to: ${applies_to})."
  done
}

# There is deliberately no default model: a full install needs one named
# explicitly. model_selection_satisfied reports whether it has one -- --model
# / HARNESS_HF_MODEL, or (external router) HARNESS_LLM_MODEL, or (local OVMS
# re-run) at least one model already registered in config.json. The latter is
# a plain grep rather than ovms_has_exported_models since this runs before
# Node.js is guaranteed to be installed.
model_selection_satisfied() {
  [[ -z "${HARNESS_HF_MODEL:-}" ]] || return 0
  if [[ -n "${HARNESS_LLM_ROUTER_ENDPOINT:-}" ]]; then
    [[ -n "${HARNESS_LLM_MODEL:-}" ]]
    return
  fi
  grep -q '"base_path"' "${HARNESS_MODELS_DIR}/config.json" 2>/dev/null
}

can_prompt_for_model() {
  [[ "${NON_INTERACTIVE:-}" != "1" ]] || return 1
  [[ -t 0 ]] && return 0
  { exec 3</dev/tty; } 2>/dev/null || return 1
  exec 3<&-
}

# require_model_selection -- fail-fast check run before startup.sh installs
# anything: errors out when no model is selected and the user can't be asked.
require_model_selection() {
  model_selection_satisfied && return 0
  can_prompt_for_model && return 0
  error "No model selected. Re-run with --model <model-name> (default hub: a Hugging Face
id such as org/name; add --model-hub <hub> for another source). With
HARNESS_LLM_ROUTER_ENDPOINT set, --model (or HARNESS_LLM_MODEL) names the model that
endpoint serves."
}

# prompt_for_model_if_missing -- asks for the model on a TTY, then validates it
# like a --model given up front. Called after startup.sh (which may re-exec the
# installer under a new group and would otherwise ask twice).
prompt_for_model_if_missing() {
  model_selection_satisfied && return 0
  local reply=""
  if [[ -t 0 ]]; then
    printf "  Model to serve (e.g. a Hugging Face id such as org/name): "
    IFS= read -r reply || reply=""
  elif { exec 3</dev/tty; } 2>/dev/null; then
    printf "  Model to serve (e.g. a Hugging Face id such as org/name): "
    IFS= read -r reply <&3 || reply=""
    exec 3<&-
  fi
  [[ -n "$reply" ]] || error "No model selected. Re-run with --model <model-name>."
  HARNESS_HF_MODEL="$reply"
  export HARNESS_HF_MODEL
  apply_model_source_defaults
}

# model_download_docker_config -- get_model.sh starts its container with a
# fixed `docker run` that forwards no HTTP(S)_PROXY, so behind a proxy the
# service's own start-up (uv/pip fetching plugin dependencies) times out and
# the container exits. The Docker client injects the proxy settings from
# its config.json "proxies" section into every container it creates, so give
# get_model.sh a private copy of the user's Docker client config with those
# settings added (via DOCKER_CONFIG) rather than touching ~/.docker.
# Prints the config directory, or nothing when no proxy is set. The copy is
# owner-only (it can hold proxy credentials); contexts and CLI plugins are
# linked in so a non-default context keeps working.
model_download_docker_config() {
  local http="${HTTP_PROXY:-${http_proxy:-}}" https="${HTTPS_PROXY:-${https_proxy:-}}" no="${NO_PROXY:-${no_proxy:-}}"
  [[ -n "${http}${https}" ]] || return 0
  local src_dir="${DOCKER_CONFIG:-$HOME/.docker}" dir entry
  dir="$(ensure_state_dir)/model-download/docker-config"
  (umask 077 && mkdir -p "$dir")
  node -e '
    const fs = require("node:fs");
    const [src, dst, http, https, no] = process.argv.slice(1);
    let cfg = {};
    try { cfg = JSON.parse(fs.readFileSync(src, "utf8")); } catch {}
    const prev = (cfg.proxies && cfg.proxies.default) || {};
    cfg.proxies = { ...(cfg.proxies || {}), default: {
      ...prev,
      ...(http ? { httpProxy: http } : {}),
      ...(https ? { httpsProxy: https } : {}),
      ...(no ? { noProxy: no } : {}),
    } };
    fs.writeFileSync(dst, JSON.stringify(cfg, null, 2), { mode: 0o600 });
  ' "${src_dir}/config.json" "${dir}/config.json" "$http" "$https" "$no" || return 1
  chmod 600 "${dir}/config.json"
  for entry in contexts cli-plugins; do
    [[ -e "${src_dir}/${entry}" && ! -e "${dir}/${entry}" ]] && ln -s "${src_dir}/${entry}" "${dir}/${entry}"
  done
  printf '%s' "$dir"
}

export_model_via_model_download() {
  local hf_model_id="$1" model_name="${2:-$(model_dir_name "$1")}" script_url script out result_line
  local hub="$HARNESS_MODEL_HUB" plugins="$HARNESS_MODEL_PLUGINS"
  command_exists docker || error "Docker is required by the Model Download microservice's ephemeral container."
  command_exists python3 || error "python3 is required by get_model.sh (builds/parses its
request payloads) -- was it skipped via SKIP_PYTHON=1? Run ./startup.sh --skip-docker --skip-nodejs."
  assert_proxy_scheme_supported
  mkdir -p "$HARNESS_MODELS_DIR"
  script="$(harness_state_root)/model-download/get_model.sh"
  mkdir -p "$(dirname "$script")"
  script_url="https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/${HARNESS_MODEL_DOWNLOAD_SCRIPT_REF}/microservices/model-download/scripts/get_model.sh"
  # Same fail-closed stance as the other downloaded installers: the default
  # ref is pinned above; any other ref needs a caller-supplied digest.
  local script_sha256="${HARNESS_MODEL_DOWNLOAD_SCRIPT_SHA256:-}"
  if [[ -z "$script_sha256" && "$HARNESS_MODEL_DOWNLOAD_SCRIPT_REF" == "$_MODEL_DOWNLOAD_PINNED_REF" ]]; then
    script_sha256="$_MODEL_DOWNLOAD_PINNED_SHA256"
  fi
  if [[ -z "$script_sha256" && "${HARNESS_ALLOW_UNVERIFIED_MODEL_DOWNLOAD_SCRIPT:-}" != "1" ]]; then
    error "HARNESS_MODEL_DOWNLOAD_SCRIPT_REF is set to a non-default ref
(${HARNESS_MODEL_DOWNLOAD_SCRIPT_REF}) with no known-good checksum. Download and
review ${script_url} yourself, then set
HARNESS_MODEL_DOWNLOAD_SCRIPT_SHA256=<sha256> to pin it (or
HARNESS_ALLOW_UNVERIFIED_MODEL_DOWNLOAD_SCRIPT=1 to accept the risk)."
  fi
  info "Fetching the Model Download microservice's get_model.sh (ref: ${HARNESS_MODEL_DOWNLOAD_SCRIPT_REF})…"
  fetch_and_verify "$script_url" "$script" "get_model.sh" "$script_sha256"
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

  [[ -n "$HARNESS_MODEL_DOWNLOAD_OVMS_RELEASE_TAG" ]] \
    && image_tag_args+=(--ovms-release-tag "$HARNESS_MODEL_DOWNLOAD_OVMS_RELEASE_TAG")

  # get_model.sh rejects a --hub it wasn't told to activate via --plugins
  # ("Plugin 'X' was not activated during container startup"). Default to
  # activating just the requested hub, plus huggingface for the "openvino"
  # hub specifically (its HF->OpenVINO conversion depends on the
  # huggingface plugin too -- confirmed against get_model.sh's own quickstart
  # examples), unless HARNESS_MODEL_PLUGINS already overrides this.
  if [[ -z "$plugins" ]]; then
    case "$hub" in
      openvino) plugins="huggingface,openvino" ;;
      *) plugins="$hub" ;;
    esac
  fi

  local -a model_args=(--model-name "$hf_model_id" --hub "$hub")
  # --type isn't universal across hubs (llm/vlm/embeddings/rerank apply to
  # huggingface/openvino; vision/3d-pose/rppg/ai-ecg to ultralytics/hls,
  # etc.) -- only default it for the hubs this installer actually targets
  # (HF-sourced, LLM chat serving); leave it unset for anything else so
  # get_model.sh falls back to its own per-hub default instead of silently
  # getting a wrong/inapplicable --type llm.
  local model_type="$HARNESS_MODEL_TYPE"
  if [[ -z "$model_type" ]]; then
    case "$hub" in
      openvino | huggingface) model_type="llm" ;;
    esac
  fi
  [[ -n "$model_type" ]] && model_args+=(--type "$model_type")
  [[ -n "$HARNESS_MODEL_DOWNLOAD_REVISION" ]] && model_args+=(--revision "$HARNESS_MODEL_DOWNLOAD_REVISION")
  [[ -n "$HARNESS_MODEL_CONFIG_JSON" ]] && model_args+=(--config-json "$HARNESS_MODEL_CONFIG_JSON")
  # --is-ovms (conversion to an OVMS-servable graph.pbtxt) only applies to
  # the "openvino" hub -- the other hubs download models in formats their
  # own runtimes consume directly (Ollama, vision pipelines, etc.), not
  # something OVMS can load.
  if [[ "$hub" == "openvino" ]]; then
    model_args+=(--is-ovms --precision "$HARNESS_MODEL_PRECISION" --device "$HARNESS_MODEL_DEVICE")
  fi

  out="$(mktemp)"
  info "Downloading '${hf_model_id}' via the Model Download microservice (hub: ${hub}, ephemeral, experimental)…"
  # PIPESTATUS, not `if ! ... | tee`, because the pipeline's own exit status
  # is tee's (always 0) unless the caller's shell happens to have pipefail
  # set -- true for scripts/install.sh, but not guaranteed for anyone
  # sourcing this function directly, so don't rely on an external shell
  # option for correctness here.
  # get_model.sh writes .model_download_logs/ into its working directory, so
  # run it from this installer's own state directory (removed on uninstall)
  # instead of wherever install.sh was started -- often a git checkout.
  local docker_config
  local -a docker_env=()
  docker_config="$(model_download_docker_config)" || error "Could not prepare the Docker client config used to forward proxy settings."
  if [[ -n "$docker_config" ]]; then
    info "Forwarding the proxy settings into the Model Download container (temporary Docker client config)."
    docker_env=(env "DOCKER_CONFIG=${docker_config}")
  fi
  ( cd "$(dirname "$script")" && "${docker_env[@]}" bash "$script" "${model_args[@]}" \
      --model-path "$HARNESS_MODELS_DIR" --download-path "$model_name" \
      --plugins "$plugins" "${image_tag_args[@]}" ) 2>&1 | tee "$out"
  if [[ "${PIPESTATUS[0]}" -ne 0 ]]; then
    rm -f "$out"
    error "get_model.sh failed to download '${hf_model_id}' (hub: ${hub}). See its output above."
  fi
  result_line="$(grep -o 'output: .*' "$out" | tail -1)"
  rm -f "$out"
  ok "Downloaded '${hf_model_id}' via the Model Download microservice${result_line:+ (${result_line})}."

  # get_model.sh reports the *container's* view of the output dir (it
  # bind-mounts $HARNESS_MODELS_DIR at /opt/models); translate back to the
  # host path.
  local container_output_dir host_output_dir
  container_output_dir="${result_line#output: }"
  host_output_dir="${HARNESS_MODELS_DIR}${container_output_dir#/opt/models}"
  [[ -n "$host_output_dir" && "$host_output_dir" != "$HARNESS_MODELS_DIR" ]] \
    || host_output_dir="${HARNESS_MODELS_DIR}/${model_name}"
  _finish_model_download "$hub" "$hf_model_id" "$model_name" "$host_output_dir"
}

# _finish_model_download HUB MODEL_ID MODEL_NAME OUTPUT_DIR -- decides what a
# finished Model Download run means for OVMS. Sets HARNESS_LAST_MODEL_REGISTERED
# to 1 when the download was registered with OVMS (and so can be wired to the
# Inference Router), 0 when it was only downloaded and tracked.
_finish_model_download() {
  local hub="$1" hf_model_id="$2" model_name="$3" host_output_dir="$4"
  local graph_file="" relative_base_path reason
  HARNESS_LAST_MODEL_REGISTERED=0

  # A download is served by OVMS iff it contains a graph.pbtxt: OVMS
  # auto-detects that file within base_path, and registration is the same
  # model_config_list entry every exporter writes. The openvino hub's output
  # sits directly under <output_dir>/<hf_model_id>/ (confirmed by running both
  # exporters side by side); for other hubs that may produce one (a
  # pre-converted Hugging Face repo, a remote-url tarball) search the
  # download. Hubs OVMS can never serve are not searched.
  if reason="$(model_hub_unserved_reason "$hub")"; then
    if [[ "$hub" == "openvino" && -f "${host_output_dir}/${hf_model_id}/graph.pbtxt" ]]; then
      graph_file="${host_output_dir}/${hf_model_id}/graph.pbtxt"
    else
      graph_file="$(find "$host_output_dir" -maxdepth 4 -name graph.pbtxt -print -quit 2>/dev/null || true)"
    fi
  fi

  if [[ -n "$graph_file" ]]; then
    relative_base_path="$(dirname "$graph_file")"
    relative_base_path="${relative_base_path#"${HARNESS_MODELS_DIR}"/}"
    if with_state_lock ovms-config _add_model_config_entry_locked \
        "${HARNESS_MODELS_DIR}/config.json" "$model_name" "$relative_base_path"; then
      ok "Registered '${model_name}' with OVMS (base_path: ${relative_base_path})."
      HARNESS_LAST_MODEL_REGISTERED=1
    else
      warn "Downloaded ${hf_model_id} but could not update OVMS's config.json --
add a model_config_list entry for base_path '${relative_base_path}' manually."
    fi
    return 0
  fi

  if [[ "$hub" == "openvino" ]]; then
    warn "No graph.pbtxt found under ${host_output_dir} -- OVMS will not serve chat
completions for '${model_name}' until this is resolved (check the Model
Download microservice's logs above)."
    return 0
  fi

  [[ -n "$reason" ]] || reason="the download contains no graph.pbtxt (OVMS serving definition)"
  # Tracked separately from config.json (which only ever holds
  # OVMS-servable models) so this download isn't simply invisible to
  # ./install.sh models list/remove -- see list_exported_models/
  # remove_exported_model.
  if with_state_lock model-download-registry _add_unregistered_download_entry_locked \
      "$model_name" "$hub" "$host_output_dir"; then
    info "Downloaded '${hf_model_id}' (hub: ${hub}) to ${host_output_dir}, but agents will
not use it: ${reason}. It is not registered with OVMS. Tracked for
'./install.sh models list' / 'models remove ${model_name}'."
  else
    warn "Downloaded '${hf_model_id}' (hub: ${hub}) to ${host_output_dir}, but agents will
not use it: ${reason}. It is not registered with OVMS and could not be tracked
for './install.sh models list/remove' -- remove it manually if needed."
  fi
}

# unregistered_downloads_file — tracks model-download fetches that were
# deliberately not registered with OVMS (HARNESS_MODEL_HUB != openvino --
# see export_model_via_model_download above), so they aren't simply
# invisible to ./install.sh models list/remove once config.json already
# has entries (list_exported_models' directory-scan fallback only runs
# when config.json has none at all).
unregistered_downloads_file() {
  printf '%s/unregistered-downloads.json' "$HARNESS_MODELS_DIR"
}

_add_unregistered_download_entry_locked() {
  local name="$1" hub="$2" path="$3" reg_file tmp
  reg_file="$(unregistered_downloads_file)"
  tmp="$(mktemp)"
  node -e '
    const fs = require("node:fs");
    const [regFile, name, hub, modelPath] = process.argv.slice(1);
    let data = {};
    try { data = JSON.parse(fs.readFileSync(regFile, "utf8")); } catch {}
    data[name] = { hub, path: modelPath };
    process.stdout.write(JSON.stringify(data, null, 2));
  ' "$reg_file" "$name" "$hub" "$path" >"$tmp" || { rm -f "$tmp"; return 1; }
  chmod 644 "$tmp"
  mv -f "$tmp" "$reg_file"
}

# _unregistered_download_field name field — prints one field ("hub" or
# "path") for a tracked unregistered download, empty if not found/no
# registry file yet.
_unregistered_download_field() {
  local name="$1" field="$2" reg_file
  reg_file="$(unregistered_downloads_file)"
  [[ -f "$reg_file" ]] || return 0
  node -e '
    try {
      const data = JSON.parse(require("node:fs").readFileSync(process.argv[1], "utf8"));
      const v = data[process.argv[2]]?.[process.argv[3]];
      if (v) process.stdout.write(String(v));
    } catch {}
  ' "$reg_file" "$name" "$field"
}

_remove_unregistered_download_entry_locked() {
  local name="$1" reg_file tmp
  reg_file="$(unregistered_downloads_file)"
  [[ -f "$reg_file" ]] || return 0
  tmp="$(mktemp)"
  node -e '
    const fs = require("node:fs");
    const [regFile, name] = process.argv.slice(1);
    let data = {};
    try { data = JSON.parse(fs.readFileSync(regFile, "utf8")); } catch {}
    delete data[name];
    process.stdout.write(JSON.stringify(data, null, 2));
  ' "$reg_file" "$name" >"$tmp" || { rm -f "$tmp"; return 1; }
  chmod 644 "$tmp"
  mv -f "$tmp" "$reg_file"
}

# export_model_via_hf_snapshot hf_model_id [model_name] — exporter
# (HARNESS_OVMS_EXPORTER=hf-snapshot) for HF repos that are already
# published as ready-to-serve OpenVINO IR + an OVMS MediaPipe graph.pbtxt
# (e.g. the OpenVINO organization's own pre-converted model repos) -- a
# plain huggingface_hub.snapshot_download, unlike the other three exporters
# which all run an optimum-cli-based conversion step. Set
# HARNESS_HF_MODEL_REVISION to pin an exact commit/tag for reproducible
# deployments.
export_model_via_hf_snapshot() {
  local hf_model_id="$1" model_name="${2:-${1##*/}}" out_dir venv revision_desc
  out_dir="${HARNESS_MODELS_DIR}/${model_name}"
  revision_desc="${HARNESS_HF_MODEL_REVISION:-main}"
  if [[ -f "${out_dir}/graph.pbtxt" ]]; then
    info "Model '${model_name}' is already downloaded."
    ensure_ovms_config
    with_state_lock ovms-config _add_model_config_entry_locked \
      "${HARNESS_MODELS_DIR}/config.json" "$model_name" "$model_name" \
      || warn "Model '${model_name}' is already downloaded but could not confirm its
OVMS config.json registration -- add a model_config_list entry for base_path
'${model_name}' manually if it doesn't serve requests."
    return 0
  fi
  command_exists python3 || error "python3 is required to download a pre-converted
model via huggingface_hub -- was it skipped via SKIP_PYTHON=1? Run ./startup.sh
--skip-docker --skip-nodejs."
  python_venv_usable || error "python3's venv module is not usable (python3 -m venv
--help fails) -- Debian/Ubuntu ship this as the separate python3-venv package.
Run ./startup.sh --skip-docker --skip-nodejs."
  assert_proxy_scheme_supported
  ensure_ovms_config
  venv="${HARNESS_MODELS_DIR}/.hf-snapshot-venv"
  [[ -d "$venv" ]] || python3 -m venv "$venv"
  # shellcheck disable=SC1091
  . "${venv}/bin/activate"
  spin "Installing huggingface_hub in the download venv" pip install --quiet --upgrade pip huggingface_hub
  if ! spin "Downloading pre-converted ${hf_model_id} (revision: ${revision_desc})" \
    python3 - "$hf_model_id" "$out_dir" "${HARNESS_HF_MODEL_REVISION:-}" <<'PY'
import sys

from huggingface_hub import snapshot_download

repo_id, local_dir, revision = sys.argv[1], sys.argv[2], (sys.argv[3] or None)
snapshot_download(repo_id=repo_id, local_dir=local_dir, revision=revision)
PY
  then
    rm -rf -- "$out_dir"
    deactivate
    error "Downloading ${hf_model_id} via huggingface_hub failed. Check network
access to huggingface.co, and that '${hf_model_id}' (revision: ${revision_desc})
exists."
  fi
  deactivate
  if [[ ! -f "${out_dir}/graph.pbtxt" ]]; then
    rm -rf -- "$out_dir"
    error "Downloaded ${hf_model_id} to ${out_dir} but it has no graph.pbtxt -- this
exporter only supports HF repos already published as ready-to-serve OpenVINO
IR + an OVMS MediaPipe graph. Use
HARNESS_OVMS_EXPORTER=docker-pull or export-model-py to convert a plain
(non-OpenVINO-IR) HF model instead."
  fi
  if with_state_lock ovms-config _add_model_config_entry_locked \
      "${HARNESS_MODELS_DIR}/config.json" "$model_name" "$model_name"; then
    ok "Downloaded ${hf_model_id} -> ${out_dir} (registered with OVMS)"
  else
    error "Downloaded ${hf_model_id} but could not update OVMS's config.json --
add a model_config_list entry for base_path '${model_name}' manually."
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

# ensure_backend_network — idempotent create of the user-defined network
# joining OVMS and the Inference Router, so they can resolve each other by
# container name (the default bridge network gives containers no DNS-by-name
# resolution between each other).
ensure_backend_network() {
  docker network inspect "$HARNESS_BACKEND_NETWORK" >/dev/null 2>&1 \
    || docker network create "$HARNESS_BACKEND_NETWORK" >/dev/null \
    || error "Could not create backend network '${HARNESS_BACKEND_NETWORK}'."
}

ensure_openvino_model_server() {
  local gpu_args group_add_args bind_host
  local -a proxy_args=()
  ensure_ovms_config
  ensure_backend_network
  if docker inspect "$HARNESS_OVMS_CONTAINER" >/dev/null 2>&1; then
    # Recreated, not just restarted -- a plain `docker restart` keeps
    # whatever GPU/proxy/network/port args the container was first created
    # with, silently ignoring any change to those in the current run (e.g.
    # a GPU that's now present, a newly-set HTTP_PROXY, or a changed
    # HARNESS_OVMS_REST_PORT/HARNESS_BIND_HOST). Every run already forces a
    # full OVMS restart (and model reload) either way, so recreating costs
    # nothing extra over the restart this replaces.
    docker rm -f "$HARNESS_OVMS_CONTAINER" >/dev/null 2>&1 || true
  fi
  gpu_args="$(intel_gpu_docker_device_args)"
  # --device alone doesn't grant GPU access -- the server runs as the
  # image's own fixed non-root user (see the config.json permission fix
  # above for the same root cause), which needs the render node's own
  # group added as a supplementary group too (OVMS's own docs require this
  # exact extra flag for GPU-targeted containers).
  group_add_args="$(intel_gpu_docker_group_add_args)"
  docker_proxy_env_args_into proxy_args
  bind_host="$(resolve_bind_host)" && [[ -n "$bind_host" ]] \
    || error "Could not resolve the address to publish OpenVINO Model Server on; refusing to publish on all interfaces."
  info "Starting OpenVINO Model Server on port ${HARNESS_OVMS_REST_PORT}…"
  local docker_run_output
  # shellcheck disable=SC2086
  if ! docker_run_output="$(docker run -d --name "$HARNESS_OVMS_CONTAINER" --restart unless-stopped \
    --network "$HARNESS_BACKEND_NETWORK" \
    -p "${bind_host}:${HARNESS_OVMS_REST_PORT}:8000" $gpu_args $group_add_args \
    "${proxy_args[@]}" \
    -v "${HARNESS_MODELS_DIR}:/models" \
    "$HARNESS_OVMS_IMAGE" \
    --rest_port 8000 --config_path /models/config.json $HARNESS_OVMS_EXTRA_ARGS 2>&1)"; then
    printf '%s\n' "$docker_run_output" >&2
    case "$docker_run_output" in
      *"429"* | *"Too Many Requests"* | *toomanyrequests*)
        error "Could not start OpenVINO Model Server -- Docker Hub rate-limited the
image pull (429 Too Many Requests), common on a shared/proxied IP. Try
'docker login' (raises the anonymous pull limit) or wait and retry." ;;
      *)
        error "Could not start OpenVINO Model Server -- a common cause is another
process already using port ${HARNESS_OVMS_REST_PORT} (check with 'docker ps -a'
and 'ss -tlnp | grep :${HARNESS_OVMS_REST_PORT}')." ;;
    esac
  fi
  ok "OpenVINO Model Server is running on port ${HARNESS_OVMS_REST_PORT}"
}

# wait_for_ovms_model_ready model_name -- polls OVMS's KServe v2 readiness
# endpoint for the given model. A restarted/started container is running as
# soon as `docker restart`/`docker run` returns, but OVMS itself can take a
# few seconds longer to actually load the model into memory -- without this,
# an immediate request (e.g. the onboarding smoke test) can race a model
# that's still loading and get a spurious "graph definition not found".
wait_for_ovms_model_ready() {
  local model_name="$1" endpoint probe_host _
  command_exists curl || return 0
  probe_host="$(resolve_probe_host)" || probe_host="127.0.0.1"
  endpoint="http://${probe_host}:${HARNESS_OVMS_REST_PORT}/v2/models/${model_name}/ready"
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
# Either way, every request goes through the Inference Router: with an
# external endpoint, IR just has that endpoint as its provider instead of OVMS.
ensure_inference_backend() {
  if [[ -n "$HARNESS_LLM_ROUTER_ENDPOINT" ]]; then
    record_ovms_managed 0
    info "Routing through the Inference Router to external endpoint: ${HARNESS_LLM_ROUTER_ENDPOINT}"
    info "This installer will not start, stop, or health-check that endpoint itself."
    # Same precedence as run_agent_onboard's model_hint, so the model the
    # agent asks IR for matches IR's provider `model` literally.
    local external_ir_model
    external_ir_model="${HARNESS_LLM_MODEL:-$(resolve_onboarding_model_hint)}"
    ensure_inference_router "$external_ir_model"
    return 0
  fi
  case "$HARNESS_LLM_PROVIDER" in
    ovms)
      # Validated before anything touches disk: the exporters build rm -rf
      # cleanup paths from this value. Every exporter other than
      # model-download takes a Hugging Face id.
      if [[ -n "${HARNESS_HF_MODEL:-}" ]]; then
        local model_hub_for_validation="openvino" model_invalid_reason
        [[ "$HARNESS_OVMS_EXPORTER" != "model-download" ]] || model_hub_for_validation="$HARNESS_MODEL_HUB"
        model_invalid_reason="$(validate_model_for_hub "$model_hub_for_validation" "$HARNESS_HF_MODEL")" \
          || error "Invalid --model '${HARNESS_HF_MODEL}' for hub '${model_hub_for_validation}': ${model_invalid_reason}."
      fi
      record_ovms_managed 1
      ensure_openvino_model_server
      # Exporters other than model-download always register what they
      # export; model-download reports whether the download was served by
      # OVMS (it contains a graph.pbtxt) via HARNESS_LAST_MODEL_REGISTERED.
      # When it wasn't, HARNESS_HF_MODEL is not an OVMS-registered model
      # name, so it must not be treated as one below (readiness poll,
      # Router provider wiring).
      HARNESS_LAST_MODEL_REGISTERED=1
      local model_download_unregistered=0
      if [[ -n "${HARNESS_HF_MODEL:-}" ]]; then
        case "$HARNESS_OVMS_EXPORTER" in
          docker-pull) export_model_via_docker_pull "$HARNESS_HF_MODEL" ;;
          export-model-py) export_model_to_openvino "$HARNESS_HF_MODEL" ;;
          model-download) export_model_via_model_download "$HARNESS_HF_MODEL" ;;
          hf-snapshot) export_model_via_hf_snapshot "$HARNESS_HF_MODEL" ;;
          *) error "Unknown HARNESS_OVMS_EXPORTER: ${HARNESS_OVMS_EXPORTER} (expected
docker-pull, export-model-py, model-download, or hf-snapshot)." ;;
        esac
        [[ "$HARNESS_LAST_MODEL_REGISTERED" -eq 1 ]] || model_download_unregistered=1
        ensure_openvino_model_server
        # wait_for_ovms_model_ready returning 1 means "still loading, not
        # confirmed ready yet" -- its own warn() message is the complete,
        # intended signal for that ("retry if the next step fails"), not a
        # fatal condition. Without `|| true`, that bare return 1 was
        # silently killing the *entire* installer right here under set -e
        # (no [ERROR], the script just exited) whenever a model took longer
        # than 60s to report ready, well before reaching the "next step" the
        # warning itself refers to. Skipped entirely when nothing was
        # actually registered with OVMS (see model_download_unregistered).
        [[ "$model_download_unregistered" -eq 1 ]] \
          || wait_for_ovms_model_ready "$(model_dir_name "$HARNESS_HF_MODEL")" || true
      elif ! ovms_has_exported_models; then
        error "No model is exported yet and no --model was given. Re-run with
--model <model-name> (and --model-hub <hub> for a non-default source)."
      fi
      # The Inference Router always sits in front of OVMS -- agents are
      # wired to its endpoint (see harness_llm_endpoint above), never
      # directly to OVMS's. Resolves the model name with the exact same
      # precedence as run_agent_onboard's own model_hint (including the
      # HARNESS_LLM_MODEL override) -- the two values must agree, since IR
      # matches a client's request.model against this provider's `model`
      # field literally; a mismatch would make IR reject every request.
      # HARNESS_HF_MODEL is skipped here when model_download_unregistered
      # (it names a download that was never registered with OVMS), so this
      # falls through to whatever's actually registered instead.
      local ir_model_name=""
      [[ "$model_download_unregistered" -eq 1 ]] || { [[ -n "${HARNESS_HF_MODEL:-}" ]] && ir_model_name="$(model_dir_name "$HARNESS_HF_MODEL")"; }
      [[ -n "$ir_model_name" ]] || ir_model_name="$(ovms_sole_registered_model_name 2>/dev/null || true)"
      [[ -n "$ir_model_name" ]] || ir_model_name="default"
      ir_model_name="${HARNESS_LLM_MODEL:-$ir_model_name}"
      if [[ "$model_download_unregistered" -eq 1 && -z "${HARNESS_LLM_MODEL:-}" ]]; then
        warn "'${HARNESS_HF_MODEL}' (hub: ${HARNESS_MODEL_HUB}) was downloaded but is not
served by OVMS -- the Inference Router is wired to '${ir_model_name}' instead
(whatever's already registered, or 'default'). Set HARNESS_LLM_MODEL
explicitly if you want the Router to target a different model."
      fi
      ensure_inference_router "$ir_model_name"
      ;;
    *)
      error "Unknown HARNESS_LLM_PROVIDER: ${HARNESS_LLM_PROVIDER} (expected: ovms).
Set HARNESS_LLM_ROUTER_ENDPOINT instead to route to an existing external
OpenAI-compatible endpoint without this installer managing a backend."
      ;;
  esac
}

# ovms_has_exported_models — true if config.json already lists at least one
# exported servable, so a fresh install without --model can tell "nothing
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
# neither --model nor HARNESS_LLM_MODEL given -- "default" never matches
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

# ovms_model_registered NAME -- true if config.json's model_config_list has an
# entry with exactly this name, i.e. OVMS actually serves a model under it
# (as opposed to a download that was only tracked, not registered).
ovms_model_registered() {
  local config_file="${HARNESS_MODELS_DIR}/config.json" name="$1"
  [[ -n "$name" && -f "$config_file" ]] || return 1
  node -e '
    try {
      const d = JSON.parse(require("node:fs").readFileSync(process.argv[1], "utf8"));
      const list = Array.isArray(d.model_config_list) ? d.model_config_list : [];
      process.exit(list.some((e) => e?.config?.name === process.argv[2]) ? 0 : 1);
    } catch { process.exit(1); }
  ' "$config_file" "$name"
}

harness_llm_endpoint() {
  # Agents are always wired to the Inference Router's endpoint, never
  # directly to OVMS's or to an external endpoint -- the Router is a
  # mandatory part of the backend (see ensure_inference_router in
  # inference-router.sh), whichever provider sits behind it. Delegates to
  # inference_router_endpoint (inference-router.sh)
  # rather than re-deriving the same host:port/v1 URL here, so there is one
  # place that can go stale if HARNESS_IR_PORT's meaning ever changes.
  inference_router_endpoint
}

# ovms_endpoint — this installer's own OVMS container's URL, as reachable
# from the install host (not from inside another container -- see
# ovms_internal_endpoint for that). Distinct from harness_llm_endpoint()
# (what agents are actually wired to, i.e. the Inference Router sitting in
# front of OVMS) -- used for status/diagnostics.
ovms_endpoint() {
  local host
  host="$(resolve_advertised_host)" || return 1
  printf 'http://%s:%s/v3' "$host" "$HARNESS_OVMS_REST_PORT"
}

# ovms_internal_endpoint — OVMS's URL as reachable from another container on
# HARNESS_BACKEND_NETWORK (container name as hostname, OVMS's own internal
# --rest_port, not the host-published HARNESS_OVMS_REST_PORT/resolve_bind_host
# mapping). This is what the Inference Router's provider config must use --
# a container cannot reach another container via the host's loopback or a
# host-only-bound published port (see ensure_backend_network).
ovms_internal_endpoint() {
  printf 'http://%s:8000/v3' "$HARNESS_OVMS_CONTAINER"
}

# Rejects path-traversal/empty/current-dir/hidden names before any
# model_dir/config.json touch — the leading-dot check also keeps this from
# targeting internal dirs like the export venv (.export-venv).
validate_model_name() {
  local name="$1"
  [[ -n "$name" && "$name" != .* && "$name" != *"/"* && "$name" != *".."* ]]
}

# Hugging Face model id: "name" or "org/name", each part starting with an
# alphanumeric and containing no "..".
validate_hf_model_id() {
  local id="$1"
  [[ "$id" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)?$ && "$id" != *".."* ]]
}

# Reads registered models from config.json (the same authoritative source
# remove_exported_model now consults) rather than only scanning top-level
# directories -- some exporters nest an export's files one level deeper
# than the user-facing model name (see export_model_via_docker_pull's
# comment), which a raw directory scan would otherwise misreport (e.g.
# showing "org" instead of "name" for a model nested under "org/...").
# Also lists model-download downloads tracked in
# unregistered_downloads_file (hub != openvino fetches, never registered
# with OVMS -- see export_model_via_model_download) unconditionally, not
# just as part of the directory-scan fallback below, so they stay visible
# even once config.json already has other, real entries. Falls back to a
# directory scan only when both of those are empty, so models from an
# exporter/version that registered nothing anywhere are still visible.
list_exported_models() {
  local dir="$HARNESS_MODELS_DIR" entry name found=0 line config_file reg_file
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
  fi
  reg_file="$(unregistered_downloads_file)"
  if [[ -f "$reg_file" ]]; then
    while IFS= read -r line; do
      [[ -n "$line" ]] || continue
      found=1
      printf '  %s\n' "$line"
    done < <(node -e '
      try {
        const data = JSON.parse(require("node:fs").readFileSync(process.argv[1], "utf8"));
        for (const name of Object.keys(data)) {
          const hub = data[name]?.hub || "?";
          console.log(`${name}\t(hub: ${hub}, not served by OVMS)`);
        }
      } catch {}
    ' "$reg_file")
  fi
  [[ "$found" -eq 1 ]] && return 0
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
# wiping every other exported model. Also handles models tracked in
# unregistered_downloads_file (model-download with a non-openvino hub --
# never touched config.json/OVMS, so just removes the directory + entry).
remove_exported_model() {
  local name="$1" dir="$HARNESS_MODELS_DIR" model_dir config_file base_path
  [[ -n "$name" ]] || error "Usage: ./install.sh models remove <name>"
  validate_model_name "$name" || error "Invalid model name: ${name}"

  local unregistered_path
  unregistered_path="$(_unregistered_download_field "$name" "path")"
  if [[ -n "$unregistered_path" ]]; then
    [[ -d "$unregistered_path" ]] || error "Model '${name}' is tracked but its directory
is missing (${unregistered_path}) -- edit $(unregistered_downloads_file) to drop
the stale entry."
    rm -rf -- "$unregistered_path"
    with_state_lock model-download-registry _remove_unregistered_download_entry_locked "$name" \
      || warn "Removed ${unregistered_path} but could not update
$(unregistered_downloads_file) -- it may still list '${name}'."
    ok "Removed downloaded model '${name}' (${unregistered_path}, was not served by OVMS)"
    return 0
  fi

  config_file="${dir}/config.json"
  # Prefer the base_path OVMS was actually registered with over assuming a
  # flat <models-dir>/<name> layout -- some exporters (docker-pull, at
  # least on OVMS 2026.1-py, and model-download) nest the export under the
  # full HF source_model path (e.g. "org/name") instead
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
  # A nested base_path (e.g. "org/name") leaves an empty
  # parent directory ("org/") behind after removing just the leaf -- clean
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
      let data;
      try { data = JSON.parse(fs.readFileSync(configFile, "utf8")); } catch { process.exit(1); }
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
  # Only succeeds once no container is still attached (IR is removed first
  # by uninstall.sh's call order) -- a no-op/failure otherwise is fine,
  # since a stale empty network left behind is harmless and
  # ensure_backend_network recreates it idempotently on the next install.
  docker network rm "$HARNESS_BACKEND_NETWORK" >/dev/null 2>&1 || true
}
