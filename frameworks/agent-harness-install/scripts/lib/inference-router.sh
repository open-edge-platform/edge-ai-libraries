# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=bash
# Inference Router (IR) — a pluggable FastAPI/LiteLLM-backed routing service
# that every inference request goes through, exposing the single
# OpenAI-compatible endpoint agents are actually wired to (see
# harness_llm_endpoint in openvino.sh). Its one configured provider is either
# this installer's own OpenVINO Model Server (OVMS) or, when
# HARNESS_LLM_ROUTER_ENDPOINT is set, that external OpenAI-compatible endpoint.
# By default the published intel/inference-router release image is pulled;
# HARNESS_IR_BUILD_FROM_SOURCE=1 builds it instead from a pinned commit of
# github.com/open-edge-platform/edge-ai-libraries (microservices/inference-router)
# -- see fetch_inference_router_source for why a pinned commit SHA is the
# integrity check for that path.

# Only used when HARNESS_IR_BUILD_FROM_SOURCE=1. Pinned to a commit on
# open-edge-platform/edge-ai-libraries main; re-pin deliberately.
HARNESS_IR_SOURCE_REPO="${HARNESS_IR_SOURCE_REPO:-https://github.com/open-edge-platform/edge-ai-libraries.git}"
HARNESS_IR_SOURCE_REF="${HARNESS_IR_SOURCE_REF:-af603af031e91cba44e6cb8b1164ed2308b6e8d1}"
HARNESS_IR_BUILD_FROM_SOURCE="${HARNESS_IR_BUILD_FROM_SOURCE:-}"
if [[ "$HARNESS_IR_BUILD_FROM_SOURCE" == "1" ]]; then
  HARNESS_IR_IMAGE="${HARNESS_IR_IMAGE:-agent-harness-install-ir:local}"
else
  HARNESS_IR_IMAGE="${HARNESS_IR_IMAGE:-intel/inference-router:2026.2.0}"
fi
HARNESS_IR_CONTAINER="${HARNESS_IR_CONTAINER:-agent-harness-install-ir}"
# 8010, not IR's own upstream default of 8000 -- this installer's OVMS
# already claims 8000 (HARNESS_OVMS_REST_PORT), and the two containers run
# side by side on the same host.
HARNESS_IR_PORT="${HARNESS_IR_PORT:-8010}"
HARNESS_IR_WORKSPACE_DIR="${HARNESS_IR_WORKSPACE_DIR:-$HOME/.agent-harness-install/inference-router/workspace}"
# IR's own config schema passes `type` straight through to LiteLLM as the
# `type/model` provider prefix (confirmed against its config loader: no
# allowlist is enforced at the config layer). "hosted_vllm" is the type IR's
# own documented examples use for a self-hosted OpenAI-compatible backend,
# and it works with auth scheme "none": confirmed on a real run that
# "openai" instead fails every request with "Missing credentials" (LiteLLM's
# openai provider insists on an api_key, which OVMS never needs). Override
# via this var if OVMS's provider entry needs a different LiteLLM prefix.
HARNESS_IR_PROVIDER_TYPE="${HARNESS_IR_PROVIDER_TYPE:-hosted_vllm}"
# "Balanced" (single-provider passthrough) rather than "Intelligent" by
# default -- the latter loads its own OpenVINO classifier model onto the
# GPU purely to choose between providers, which is pointless overhead when
# OVMS is the only provider configured.
HARNESS_IR_ROUTING_POLICY="${HARNESS_IR_ROUTING_POLICY:-Balanced}"

inference_router_workspace_dir() {
  printf '%s' "$HARNESS_IR_WORKSPACE_DIR"
}

# fetch_inference_router_source — clones just microservices/inference-router
# out of the pinned commit, without a full repo clone: `git fetch --depth 1
# origin <sha>` followed by `git checkout <sha> -- <path>` populates only
# that path in the working tree, the same single-path-extraction trick used
# elsewhere for a single file (fetch_and_verify) but for a whole directory.
# Requires a full 40-character commit SHA by default (not a branch/tag,
# which can move underneath you) -- HARNESS_ALLOW_UNVERIFIED_IR_SOURCE=1
# opts out for local development against a moving branch.
fetch_inference_router_source() {
  local tmp
  if [[ ! "$HARNESS_IR_SOURCE_REF" =~ ^[0-9a-f]{40}$ ]] \
    && [[ "${HARNESS_ALLOW_UNVERIFIED_IR_SOURCE:-}" != "1" ]]; then
    error "HARNESS_IR_SOURCE_REF ('${HARNESS_IR_SOURCE_REF}') is not a full
40-character commit SHA, so refusing to build the Inference Router from it
unverified -- a branch/tag name can move underneath you. Pin an exact commit
SHA, or set HARNESS_ALLOW_UNVERIFIED_IR_SOURCE=1 to accept the risk (e.g.
for local development against a moving branch)."
  fi
  tmp="$(mktemp -d)"
  local attempt fetched=""
  # Corporate TLS-inspecting proxies intermittently fail a single git fetch
  # ("certificate signer not trusted"); a retry on a fresh repo usually succeeds.
  for attempt in 1 2 3; do
    rm -rf -- "${tmp:?}"/.git "${tmp:?}"/microservices
    if (
      cd "$tmp" \
        && git init -q \
        && git remote add origin "$HARNESS_IR_SOURCE_REPO" \
        && git fetch -q --depth 1 origin "$HARNESS_IR_SOURCE_REF" \
        && git checkout -q FETCH_HEAD -- microservices/inference-router
    ); then
      fetched=1
      break
    fi
    [[ "$attempt" -lt 3 ]] || break
    warn "Fetching the Inference Router source failed (attempt ${attempt}/3); retrying…"
    sleep 5
  done
  [[ -n "$fetched" ]] || { rm -rf -- "$tmp"; error "Could not fetch microservices/inference-router at
'${HARNESS_IR_SOURCE_REF}' from ${HARNESS_IR_SOURCE_REPO} -- check network
access and that the ref/path exist."; }
  [[ -d "${tmp}/microservices/inference-router" ]] \
    || { rm -rf -- "$tmp"; error "microservices/inference-router not found at
'${HARNESS_IR_SOURCE_REF}' in ${HARNESS_IR_SOURCE_REPO}."; }
  printf '%s' "${tmp}/microservices/inference-router"
}

# ensure_inference_router_image — pulls the published image once (later runs
# reuse it), or with HARNESS_IR_BUILD_FROM_SOURCE=1 builds it from the
# pinned source commit.
ensure_inference_router_image() {
  if [[ "$HARNESS_IR_BUILD_FROM_SOURCE" != "1" ]]; then
    docker image inspect "$HARNESS_IR_IMAGE" >/dev/null 2>&1 && return 0
    spin "Pulling Inference Router image ${HARNESS_IR_IMAGE}" docker pull "$HARNESS_IR_IMAGE" \
      || error "Could not pull the Inference Router image '${HARNESS_IR_IMAGE}' -- check network
access and Docker Hub rate limits, or set HARNESS_IR_BUILD_FROM_SOURCE=1 to build it
from the pinned source commit instead."
    return 0
  fi
  local source_label="${HARNESS_IR_SOURCE_REPO}@${HARNESS_IR_SOURCE_REF}" built_from=""
  # Rebuild when the image was built from a different (or unrecorded) source
  # than the one currently configured, so re-pinning actually takes effect.
  if built_from="$(docker image inspect -f '{{ index .Config.Labels "agent-harness-install.ir-source" }}' "$HARNESS_IR_IMAGE" 2>/dev/null)"; then
    [[ "$built_from" != "$source_label" ]] || return 0
    info "Inference Router image ${HARNESS_IR_IMAGE} was built from '${built_from:-an unrecorded source}',
not ${source_label} -- rebuilding."
  fi
  local src_dir tmp_root
  src_dir="$(fetch_inference_router_source)" || return 1
  tmp_root="${src_dir%/microservices/inference-router}"
  local -a proxy_build_args=()
  local var
  for var in HTTP_PROXY HTTPS_PROXY NO_PROXY http_proxy https_proxy no_proxy; do
    [[ -n "${!var:-}" ]] && proxy_build_args+=(--build-arg "${var}=${!var}")
  done
  info "Building the Inference Router image (${HARNESS_IR_IMAGE}) from
${source_label}…"
  if ! spin "Building Inference Router image" \
    docker build -t "$HARNESS_IR_IMAGE" --label "agent-harness-install.ir-source=${source_label}" \
    "${proxy_build_args[@]}" "$src_dir"; then
    rm -rf -- "$tmp_root"
    error "Docker build of the Inference Router image failed."
  fi
  rm -rf -- "$tmp_root"
}

# write_inference_router_config model_name — regenerates IR's
# workspace/config.yaml with a single provider pointed at either this
# installer's own OVMS (ovms_internal_endpoint, from openvino.sh) or, when
# HARNESS_LLM_ROUTER_ENDPOINT is set, that external OpenAI-compatible
# endpoint (with HARNESS_LLM_ROUTER_API_KEY as a bearer token if given) —
# overwritten on every run, so manual edits here don't persist;
# HARNESS_IR_PROVIDER_TYPE/HARNESS_IR_ROUTING_POLICY are the supported
# override points instead.
# Lock-protected, atomic mktemp+mv write (mirrors
# _add_model_config_entry_locked's pattern in openvino.sh) -- a plain `cat >
# config_file` would follow a symlink planted at that path (TOCTOU) instead
# of refusing or replacing it safely.
write_inference_router_config() {
  with_state_lock inference-router-config _write_inference_router_config_locked "$@"
}

_write_inference_router_config_locked() {
  local model_name="$1" workspace_dir config_file tmp ovms_url ovms_url_esc model_esc
  local provider_name="ovms" auth_scheme="none" auth_key_line=""
  workspace_dir="$(inference_router_workspace_dir)"
  mkdir -p "$workspace_dir"
  config_file="${workspace_dir}/config.yaml"
  if [[ -n "${HARNESS_LLM_ROUTER_ENDPOINT:-}" ]]; then
    provider_name="external"
    ovms_url="$HARNESS_LLM_ROUTER_ENDPOINT"
    if [[ -n "${HARNESS_LLM_ROUTER_API_KEY:-}" ]]; then
      # The key itself never touches config.yaml: IR expands ${VAR} in its
      # config values from its own environment (the container gets
      # HARNESS_LLM_ROUTER_API_KEY via a by-name -e, see ensure_inference_router).
      auth_scheme="bearer"
      auth_key_line=$'\n        api_key: "${HARNESS_LLM_ROUTER_API_KEY}"'
    fi
  else
    # Container-to-container URL (container name + OVMS's internal port), not
    # ovms_endpoint()'s host-facing one -- IR is a separate container and
    # can't reach OVMS via the install host's loopback/advertised address or
    # its host-published (often loopback-only) port. Both containers must be
    # joined to HARNESS_BACKEND_NETWORK for this name to resolve (see
    # ensure_backend_network in openvino.sh and this file's docker run below).
    ovms_url="$(ovms_internal_endpoint)" || return 1
  fi
  ovms_url_esc="$(printf '%s' "$ovms_url" | sed 's/\\/\\\\/g; s/"/\\"/g')"
  model_esc="$(printf '%s' "${model_name:-default}" | sed 's/\\/\\\\/g; s/"/\\"/g')"
  tmp="$(mktemp)"
  cat >"$tmp" <<EOF
# Managed by agent-harness-install -- regenerated on every run; manual edits
# here are overwritten. Routes IR's single provider at this installer's own
# OVMS, or at HARNESS_LLM_ROUTER_ENDPOINT when set. See
# HARNESS_IR_PROVIDER_TYPE/HARNESS_IR_ROUTING_POLICY to override.
log_level: "INFO"
providers:
  - name: "${provider_name}"
    type: "${HARNESS_IR_PROVIDER_TYPE}"
    model: "${model_esc}"
    enabled: true
    settings:
      endpoint: "${ovms_url_esc}"
      auth:
        scheme: "${auth_scheme}"${auth_key_line}
plugins:
  prerouting: []
  postrouting: []
  postresponse: []
routing:
  policy: "${HARNESS_IR_ROUTING_POLICY}"
telemetry:
  backend: "memory"
  enabled: true
EOF
  # mktemp creates its file mode 0600, owned by whichever host user runs
  # the installer -- but IR runs as its image's own fixed internal user
  # (its Dockerfile's `useradd -m -u 1000 user`), which essentially never
  # matches the host user. A bind-mounted file's permissions are the
  # host's, not the image's build-time chown, so without this chmod IR
  # cannot read its own config.yaml at startup -- same root cause, and
  # same fix, as _add_model_config_entry_locked's chmod 644 for OVMS's
  # config.json.
  chmod 644 "$tmp"
  mv -f "$tmp" "$config_file"
}

# ensure_inference_router model_name — starts/restarts IR, pointed at OVMS (or
# at HARNESS_LLM_ROUTER_ENDPOINT when set, in which case no OVMS is involved
# and the backend network is not used).
# Shares the GPU with OVMS via the same device/group-add helpers
# docker-setup.sh already provides (confirmed acceptable to run both on one
# GPU).
ensure_inference_router() {
  local model_name="${1:-}" gpu_args group_add_args no_proxy_combined bind_host external_host=""
  local -a proxy_args=() network_args=() external_args=()
  ensure_inference_router_image
  if [[ -n "${HARNESS_LLM_ROUTER_ENDPOINT:-}" ]]; then
    external_host="${HARNESS_LLM_ROUTER_ENDPOINT#*://}"
    external_host="${external_host%%/*}"
    case "${external_host%%:*}" in
      localhost|127.*|"[::1]")
        warn "HARNESS_LLM_ROUTER_ENDPOINT points at ${external_host}, which from inside the
Inference Router container is the container itself, not this host. Use this host's
LAN address or host.docker.internal instead." ;;
    esac
    external_args=(--add-host=host.docker.internal:host-gateway)
    if [[ -n "${HARNESS_LLM_ROUTER_API_KEY:-}" ]]; then
      # A by-name -e only forwards exported variables; keeps the key out of argv.
      export HARNESS_LLM_ROUTER_API_KEY
      external_args+=(-e HARNESS_LLM_ROUTER_API_KEY)
    fi
  else
    ensure_backend_network
    network_args=(--network "$HARNESS_BACKEND_NETWORK")
  fi
  write_inference_router_config "$model_name" || error "Could not write
${HARNESS_IR_WORKSPACE_DIR}/config.yaml."
  if docker inspect "$HARNESS_IR_CONTAINER" >/dev/null 2>&1; then
    # Recreated, not just restarted -- see the matching comment in
    # ensure_openvino_model_server; every run already forces a full IR
    # restart either way, so this costs nothing extra while actually
    # picking up a changed GPU/proxy/network/port configuration.
    docker rm -f "$HARNESS_IR_CONTAINER" >/dev/null 2>&1 || true
  fi
  gpu_args="$(intel_gpu_docker_device_args)"
  group_add_args=""
  [[ -n "$gpu_args" ]] && group_add_args="$(intel_gpu_docker_group_add_args)"
  docker_proxy_env_args_into proxy_args
  # docker_proxy_env_args_into forwards the host's NO_PROXY/no_proxy
  # verbatim, which won't mention HARNESS_OVMS_CONTAINER -- so with
  # HTTP(S)_PROXY also set, IR's own outbound call to OVMS by container
  # name (see _write_inference_router_config_locked) would otherwise get
  # routed through the corporate proxy instead of reaching OVMS directly
  # (the proxy has no way to resolve/reach an internal container
  # hostname). Appended after docker_proxy_env_args_into's own -e
  # NO_PROXY/-e no_proxy so these win (docker run uses the last -e for a
  # given key). Skipped when routing externally: there is no OVMS container,
  # and the external endpoint should follow the host's proxy settings.
  if [[ -z "${HARNESS_LLM_ROUTER_ENDPOINT:-}" ]]; then
    no_proxy_combined="${NO_PROXY:-${no_proxy:-}}"
    no_proxy_combined="${no_proxy_combined:+${no_proxy_combined},}${HARNESS_OVMS_CONTAINER}"
    proxy_args+=(-e "NO_PROXY=${no_proxy_combined}" -e "no_proxy=${no_proxy_combined}")
  fi
  info "Starting Inference Router on port ${HARNESS_IR_PORT}…"
  bind_host="$(resolve_bind_host)" && [[ -n "$bind_host" ]] \
    || error "Could not resolve the address to publish the Inference Router on; refusing to publish on all interfaces."
  # shellcheck disable=SC2086
  docker run -d --name "$HARNESS_IR_CONTAINER" --restart unless-stopped \
    "${network_args[@]}" \
    -p "${bind_host}:${HARNESS_IR_PORT}:8000" $gpu_args $group_add_args \
    -v "$(inference_router_workspace_dir):/app" \
    -e "GATEWAY_CONFIG=/app/config.yaml" \
    -e "IR_DEVICE=$([[ -n "$gpu_args" ]] && printf GPU || printf CPU)" \
    "${proxy_args[@]}" \
    "${external_args[@]}" \
    "$HARNESS_IR_IMAGE" \
    || error "Could not start the Inference Router -- a common cause is another
process already using port ${HARNESS_IR_PORT}."
  wait_for_inference_router_ready || true
  ok "Inference Router is running on port ${HARNESS_IR_PORT}"
}

# wait_for_inference_router_ready — polls IR's own /health endpoint, same
# non-fatal "still starting" pattern as wait_for_ovms_model_ready.
wait_for_inference_router_ready() {
  local endpoint probe_host _
  command_exists curl || return 0
  probe_host="$(resolve_probe_host)" || probe_host="127.0.0.1"
  endpoint="http://${probe_host}:${HARNESS_IR_PORT}/health"
  for _ in $(seq 1 30); do
    curl -sf "$endpoint" >/dev/null 2>&1 && return 0
    sleep 2
  done
  warn "Inference Router did not report healthy within 60s (checked
${endpoint}); it may still be starting. Retry if the next step fails."
  return 1
}

# inference_router_endpoint — the OpenAI-compatible URL agents are actually
# wired to (see harness_llm_endpoint in openvino.sh, which calls this).
inference_router_endpoint() {
  local host
  host="$(resolve_advertised_host)" || return 1
  printf 'http://%s:%s/v1' "$host" "$HARNESS_IR_PORT"
}

# remove_inference_router — used by the uninstaller. Not gated on
# ovms_is_managed: IR is always started by this installer (in front of OVMS,
# or in front of an external endpoint), so the container is always ours.
remove_inference_router() {
  command_exists docker || return 0
  docker rm -f "$HARNESS_IR_CONTAINER" >/dev/null 2>&1 || true
  # Only an image built locally from source goes with the container; the
  # published image is left in place, same as the OVMS image.
  if [[ "$HARNESS_IR_BUILD_FROM_SOURCE" == "1" ]]; then
    docker rmi "$HARNESS_IR_IMAGE" >/dev/null 2>&1 || true
  fi
  # Earlier versions always built this tag locally; clean up the leftover.
  if [[ "$HARNESS_IR_IMAGE" != "agent-harness-install-ir:local" ]]; then
    docker rmi agent-harness-install-ir:local >/dev/null 2>&1 || true
  fi
}
