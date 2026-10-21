#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Intel-platform installer payload — the actual install flow, invoked by the
# thin bootstrap at the repo root (../install.sh). Automatically runs
# ../startup.sh first to install/verify Docker/Node.js/Python, so there is
# only one script for the user to run. Staged install flow: host prep (GPU),
# inference routing, agent install, onboarding
# (no CDI needed; Intel render nodes pass through to containers via --device).
set -euo pipefail

# Repo root is one level up from this payload script.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
for lib in colors verify state sudo shim gpu-intel docker-setup nodejs python-setup openvino inference-router agents harness-mcp; do
  # shellcheck disable=SC1090
  . "${SCRIPT_DIR}/scripts/lib/${lib}.sh"
done

TOTAL_STEPS=3
NON_INTERACTIVE="${NON_INTERACTIVE:-}"
SKIP_GPU_CHECK="${SKIP_GPU_CHECK:-}"

usage() {
  cat <<EOF

  ${C_BOLD}agent-harness-install${C_RESET}

  Usage:
    ./install.sh [options]                      Run the full install + onboarding (requires --model)
    ./install.sh models <list|remove> [name]     List or delete exported OpenVINO models
    ./install.sh mcp register <name> <url> [agent]  Register an arbitrary MCP endpoint URL
    ./install.sh skill <install|list|remove> [path|name]  Manage Hermes skills
    ./install.sh status                          Show agent-harness-install/OVMS/agent health
    ./install.sh onboard                         Re-run onboarding only

  ./install.sh automatically runs startup.sh first to install/verify Docker,
  Node.js/npm, and Python -- no separate setup step needed. Run
  ./startup.sh --help for finer-grained control (e.g. --skip-docker) if
  you want to run just that step on its own.

  Options:
    --non-interactive                Skip prompts (uses env vars / defaults)
    --skip-gpu-check                  Skip Intel GPU detection/driver checks
    --harness <openclaw|deepagents-code|hermes>  Agent harness to install (sets HARNESS_AGENT)
    --model <model-name>              Model to serve (required; prompted for on a terminal, an error otherwise), named as its hub
                                       names it (default hub: Hugging Face id such as org/name, exported to OpenVINO IR).
                                       Sets HARNESS_HF_MODEL.
    --model-hub <hub>                  Source hub (default: openvino = Hugging Face + conversion). Any other hub selects the
                                       Model Download exporter automatically. Hubs: openvino, huggingface, ollama, remote-url,
                                       ultralytics, geti, pipeline-zoo-models, omz, hls. Only results with an OVMS graph.pbtxt
                                       are served to agents; the rest are downloaded and tracked (sets HARNESS_MODEL_HUB)
    --model-config <json>              Hub-specific settings as JSON, e.g. '{"url":"https://…/{name}.tar"}' for remote-url
                                       (sets HARNESS_MODEL_CONFIG_JSON)
    --model-revision <rev>             Branch, tag or commit (model-download and hf-snapshot exporters)
    --model-type <type>                Model type, e.g. llm (model-download exporter; hls needs 3d-pose|rppg|ai-ecg)
    --model-precision <int4|int8|fp16|fp32>  Weight precision (default: int8; model-download and docker-pull exporters)
    --model-device <CPU|GPU|NPU|HETERO:…>    Conversion target device (model-download exporter; default: CPU)
    --help, -h                        Show this help message and exit

  Environment:
    HARNESS_AGENT               openclaw | deepagents-code | hermes (default: openclaw)
    HERMES_INSTALL_URL            Custom Hermes installer URL (default: scripts/install.sh at a pinned hermes-agent commit, checksum built in)
    HERMES_INSTALL_SHA256         Expected SHA-256 of the Hermes installer (required with HERMES_INSTALL_URL unless HERMES_ALLOW_UNVERIFIED_INSTALL=1)
    HERMES_ALLOW_UNVERIFIED_INSTALL  Run a custom Hermes installer without a pinned checksum (not recommended)
    DCODE_INSTALL_URL             Custom dcode installer URL (default: libs/code/scripts/install.sh at a pinned deepagents commit, checksum built in)
    DCODE_INSTALL_SHA256          Expected SHA-256 of the dcode installer (required with DCODE_INSTALL_URL unless HARNESS_ALLOW_UNVERIFIED_DCODE_INSTALL=1)
    HARNESS_ALLOW_UNVERIFIED_DCODE_INSTALL  Run a custom dcode installer without a pinned checksum (not recommended)
    DEEPAGENTS_CODE_VERSION       Exact dcode version to install (default: the pinned version)
    DEEPAGENTS_HOME               Path to dcode's profile dir (default: ~/.deepagents)
    HARNESS_LLM_ENDPOINT         OpenAI-compatible endpoint (default: local OpenVINO Model Server)
    HARNESS_LLM_PROVIDER         ovms (default) — the only backend this installer manages itself
    HARNESS_LLM_ROUTER_ENDPOINT  Point the Inference Router at an existing external OpenAI-compatible endpoint instead of OVMS
                                  (inference still goes through the Router; --model names the model that endpoint serves)
    HARNESS_LLM_ROUTER_API_KEY   Bearer token the Router sends to HARNESS_LLM_ROUTER_ENDPOINT (optional; passed to the container by name, never written to disk)
    HARNESS_HF_MODEL                Same as --model: the model to serve, named as its hub names it
                                    (default hub: a Hugging Face id such as org/name)
    HARNESS_OVMS_REST_PORT, HARNESS_MODELS_DIR
    HARNESS_OVMS_IMAGE            OVMS serving image (default: openvino/model_server:2026.4.1-gpu)
    HARNESS_OVMS_EXPORT_IMAGE     OVMS "-py" image used by the docker-pull exporter (default: openvino/model_server:2026.1-py)
    HARNESS_BACKEND_NETWORK      Docker network joining OVMS + the Inference Router so they can reach each other by name (default: agent-harness-install-backend)
    MIN_NODE_VERSION
    HARNESS_OVMS_EXTRA_ARGS       Extra OVMS server flags (e.g. --tool_parser <parser>)
    HARNESS_OVMS_EXPORTER         docker-pull (default) | export-model-py | model-download | hf-snapshot (see Known limitations)
    HARNESS_HF_MODEL_REVISION     Pin an exact HF revision (commit/tag/branch) for the hf-snapshot exporter
    HARNESS_OVMS_EXPORT_MODEL_PY_SHA256, HARNESS_OVMS_EXPORT_MODEL_REQUIREMENTS_SHA256  Pin export_model.py/requirements.txt (export-model-py exporter only)
    HARNESS_ALLOW_UNVERIFIED_OVMS_EXPORTER  Skip pinning for a custom HARNESS_OVMS_EXPORT_MODEL_REF (export-model-py exporter only, not recommended)
    HARNESS_MODEL_DOWNLOAD_SCRIPT_REF, HARNESS_MODEL_DOWNLOAD_SCRIPT_SHA256, HARNESS_MODEL_DOWNLOAD_IMAGE_TAG, HARNESS_MODEL_DOWNLOAD_OVMS_RELEASE_TAG
    HARNESS_ALLOW_UNVERIFIED_MODEL_DOWNLOAD_SCRIPT  Skip pinning get_model.sh's checksum (not recommended)
    HARNESS_MODEL_HUB             Same as --model-hub: openvino (default, HF+convert) | huggingface | ollama | remote-url |
                                  ultralytics | geti | pipeline-zoo-models | omz | hls. A non-default hub selects the
                                  model-download exporter unless HARNESS_OVMS_EXPORTER is set; only downloads that contain an
                                  OVMS graph.pbtxt are served, the rest are downloaded and tracked (see Known limitations)
    HARNESS_MODEL_TYPE             Same as --model-type (default: llm for the openvino/huggingface hubs, unset otherwise)
    HARNESS_MODEL_DOWNLOAD_REVISION, HARNESS_MODEL_PRECISION, HARNESS_MODEL_DEVICE, HARNESS_MODEL_CONFIG_JSON  Same as the matching --model-* options
    HARNESS_MODEL_PLUGINS          Model Download plugins to enable (default: the hub, plus huggingface for openvino)
    GETI_HOST, GETI_TOKEN, GETI_WORKSPACE_ID  Required by --model-hub geti
    HF_TOKEN                       Hugging Face token for gated models (forwarded to the exporters)
    HARNESS_IR_SOURCE_REPO, HARNESS_IR_SOURCE_REF  Inference Router source repo/pinned commit SHA (only with HARNESS_IR_BUILD_FROM_SOURCE=1)
    HARNESS_IR_BUILD_FROM_SOURCE   1 = build the Inference Router from source instead of pulling the published image
    HARNESS_ALLOW_UNVERIFIED_IR_SOURCE  Build the Inference Router from a branch/tag instead of a pinned commit SHA (not recommended)
    HARNESS_IR_IMAGE               Inference Router image (default: intel/inference-router:2026.2.0)
    HARNESS_IR_CONTAINER, HARNESS_IR_PORT, HARNESS_IR_WORKSPACE_DIR
    HARNESS_IR_PROVIDER_TYPE       LiteLLM provider-type prefix for the Router's provider entry (default: hosted_vllm)
    HARNESS_IR_ROUTING_POLICY      Balanced (default, only supported value today) | Intelligent — see Known limitations (Intelligent needs a classifier model this installer does not yet provision)
    HERMES_CONFIG                  Path to Hermes's config.yaml (default: ~/.hermes/config.yaml)
    HARNESS_MCP_REGISTER_CMD       Script to register an MCP endpoint with a non-Hermes agent
    HARNESS_ADVERTISED_HOST       Host/IP printed in endpoint URLs (default: 127.0.0.1)
    HARNESS_BIND_HOST             Address Docker binds published ports to (default: same as HARNESS_ADVERTISED_HOST)
    HTTP_PROXY, HTTPS_PROXY, ALL_PROXY, NO_PROXY  (either case) Forwarded into
                                   OVMS/Inference Router containers, and into
                                   the Docker daemon's own config so it can
                                   pull images through the same proxy
    NON_INTERACTIVE=1, SKIP_GPU_CHECK=1

EOF
}

# maybe_prompt_advertised_host — offers to advertise endpoint URLs under a
# non-loopback host/IP (e.g. this machine's LAN address) instead of the
# 127.0.0.1 default, for setups accessed from another machine. Skipped
# non-interactively or without a TTY; the chosen value is persisted so later
# invocations (status) keep showing it.
maybe_prompt_advertised_host() {
  # An explicit env value is saved too, so later `status` runs (without the
  # variable) print the address the ports were actually published on.
  if [[ -n "$HARNESS_ADVERTISED_HOST_WAS_SET" && "$HARNESS_ADVERTISED_HOST" =~ ^[A-Za-z0-9.:-]+$ ]]; then
    persist_advertised_host "$HARNESS_ADVERTISED_HOST"
  fi
  [[ "${NON_INTERACTIVE:-}" != "1" ]] || return 0
  local reply=""
  if [[ -t 0 ]]; then
    printf "  Host/IP to advertise in printed endpoint URLs [%s]: " "$(resolve_advertised_host)"
    IFS= read -r reply || reply=""
  elif { exec 3</dev/tty; } 2>/dev/null; then
    printf "  Host/IP to advertise in printed endpoint URLs [%s]: " "$(resolve_advertised_host)"
    IFS= read -r reply <&3 || reply=""
    exec 3<&-
  else
    return 0
  fi
  [[ -n "$reply" ]] || return 0
  # This value now also doubles as the literal docker -p bind address (via
  # resolve_bind_host) unless HARNESS_BIND_HOST overrides it separately, so
  # reject anything that isn't a plausible IPv4/IPv6/hostname literal before
  # persisting it -- a typo here would otherwise surface later as a much
  # more confusing "docker run" failure instead of just wrong display text.
  if [[ ! "$reply" =~ ^[A-Za-z0-9.:-]+$ ]]; then
    warn "'${reply}' doesn't look like a valid host/IP; keeping the previous value."
    return 0
  fi
  HARNESS_ADVERTISED_HOST="$reply"
  HARNESS_ADVERTISED_HOST_WAS_SET=1
  persist_advertised_host "$reply"
}

prepare_installer_host() {
  # Docker/Node.js/Python prerequisites live in startup.sh (so the
  # install/prereq logic stays separated in its own file), but invoked
  # automatically here so the user only ever has to run ./install.sh --
  # never a separate setup step first. Safe/fast to re-run: every check
  # short-circuits immediately once a prerequisite is already satisfied.
  # Run before any of the prompts below: if this needs to grant the
  # current user docker-group access, it transparently restarts this
  # whole script under the new group (see ensure_docker_group_active) --
  # doing that *after* an interactive prompt had already run would ask it
  # again on the restart.
  local startup_script="${SCRIPT_DIR}/startup.sh" startup_rc=0
  [[ -f "$startup_script" ]] || error "Could not find startup.sh at ${startup_script}."
  bash "$startup_script" || startup_rc=$?
  if [[ "$startup_rc" -eq 2 ]]; then
    # ensure_docker_group_active (docker-setup.sh) already tried to
    # self-heal this via sg/sudo re-exec inside that subprocess and
    # couldn't (neither available/working) -- its own warning explains
    # this needs a new login shell. Stop here cleanly instead of
    # continuing straight into docker commands that would fail with
    # permission-denied against a group that isn't active in this shell.
    exit 0
  elif [[ "$startup_rc" -ne 0 ]]; then
    error "Prerequisite setup failed (see output above).
Re-run ./install.sh once resolved, or run ./startup.sh directly for finer-
grained control (--skip-docker/--skip-nodejs/--skip-python)."
  fi
  # startup.sh runs as a *subprocess* -- if it just granted this user
  # docker-group access, it already restarted *itself* to pick that up,
  # but that only refreshes that subprocess's own credentials, not this
  # (install.sh's own) process's. Check/self-heal the same way here too,
  # so this process's own later docker commands (ensure_backend_network,
  # docker run for OVMS/IR, etc.) don't fail with permission-denied
  # against a group that isn't active in this process yet.
  ensure_docker_group_active "$0" "${original_args[@]}"

  prompt_for_model_if_missing
  maybe_prompt_advertised_host

  info "Checking Intel GPU…"
  if [[ -n "$SKIP_GPU_CHECK" ]]; then
    info "Skipping GPU check (--skip-gpu-check)."
  elif ! detect_intel_gpu; then
    warn "No Intel display/GPU PCI device detected. Continuing in CPU-only mode."
  else
    ok "Intel GPU detected"
    describe_intel_gpu | sed 's/^/    /'
    intel_gpu_kernel_driver_loaded || warn "Neither the i915 nor xe kernel driver appears
loaded. GPU acceleration may be unavailable."
    intel_gpu_render_nodes_available || warn "No /dev/dri render nodes found; containers
will not get GPU passthrough."
    if intel_compute_runtime_installed; then
      ok "Intel compute runtime already installed"
    else
      warn "Intel compute runtime (Level Zero + OpenCL) not detected. This installer
assumes GPU drivers/compute-runtime are already provisioned on the host (e.g.
via Edge Pack: github.com/open-edge-platform/edge-pack) rather than
installing them itself -- GPU acceleration may be unavailable until that's
done."
    fi
  fi

  # Node.js itself (not just npm -- that's only needed to install openclaw,
  # checked separately before the agent-install step below) is a runtime
  # dependency of this installer's own state/config JSON handling
  # (atomic_write_file's fast path, OVMS's config.json management in
  # openvino.sh) regardless of which agent
  # is selected -- ensure_inference_backend (the very next step) already
  # exercises some of these. startup.sh just ensured this above unless
  # SKIP_NODEJS=1 was set, so this is a safety net for that case, not the
  # common path -- checked here (not just at the agent-install step) so a
  # missing Node fails fast with clear guidance instead of a confusing raw
  # "node: command not found" partway through inference setup.
  #
  # startup.sh's Node.js install (via nvm) runs in a *subprocess* -- nvm's
  # PATH change only takes effect there, not in this (install.sh's own)
  # process, the same class of gap ensure_docker_group_active fixes for
  # Docker's group. Unlike that one, this doesn't need a process re-exec:
  # just load nvm and select the just-installed default version here too.
  # nvm.sh and its functions aren't `set -u` safe.
  set +u
  ensure_nvm_loaded
  if ! node_meets_requirements && command -v nvm >/dev/null 2>&1; then
    nvm use "$HARNESS_NODE_VERSION" --silent 2>/dev/null \
      || nvm use default --silent 2>/dev/null || true
  fi
  set -u
  command_exists node \
    || error "Node.js is required (used internally for state/config JSON
handling, independent of which agent is selected) but not found -- was it
skipped via SKIP_NODEJS=1? Run ./startup.sh --skip-docker --skip-python to
install just Node.js, then re-run ./install.sh."
}

print_done() {
  printf "\n${C_GREEN}${C_BOLD}=== Installation complete ===${C_RESET}\n\n"
}

# print_status — combined health view: host/GPU, OVMS, the Inference Router,
# and the installed agent. Read-only; touches nothing.
print_status() {
  local agent cli_bin

  printf "\n${C_BOLD}Host${C_RESET}\n"
  if command_exists docker && docker info >/dev/null 2>&1; then
    ok "Docker is running"
  else
    warn "Docker is not running or not installed"
  fi
  if detect_intel_gpu; then
    ok "Intel GPU detected"
  else
    info "No Intel GPU detected (CPU-only)"
  fi

  printf "\n${C_BOLD}Inference backend${C_RESET}\n"
  if [[ -n "${HARNESS_LLM_ROUTER_ENDPOINT:-}" ]]; then
    ok "Upstream routed externally — ${HARNESS_LLM_ROUTER_ENDPOINT} (not managed by this installer)"
  fi
  if ! command_exists docker; then
    info "Docker not installed"
  else
    # OVMS and the Inference Router are reported separately: OVMS's own
    # health uses its own URL (ovms_endpoint), while the endpoint agents are
    # actually wired to is the Router's (harness_llm_endpoint) — printing
    # only one of the two under a single "Running" line would otherwise
    # conflate "OVMS is up" with "the agent's endpoint is reachable",
    # which are only the same thing when the Router is also healthy.
    # OVMS is skipped when routing externally (the Router is still checked).
    if [[ -n "${HARNESS_LLM_ROUTER_ENDPOINT:-}" ]]; then
      :
    elif docker inspect "$HARNESS_OVMS_CONTAINER" >/dev/null 2>&1; then
      if [[ "$(docker inspect -f '{{.State.Running}}' "$HARNESS_OVMS_CONTAINER" 2>/dev/null)" == "true" ]]; then
        # Assigned via `if endpoint=$(...); then` (not inlined into ok's
        # argument list) so a failure inside ovms_endpoint (e.g. its
        # resolve_advertised_host's tamper checks on the advertised-host
        # state file) is actually detected here -- status is read-only and
        # must degrade gracefully (still show the rest of the sections
        # below) rather than either aborting outright or silently printing
        # "Running — " with a blank endpoint.
        local ovms_url
        if ovms_url="$(ovms_endpoint)"; then
          ok "OpenVINO Model Server running — ${ovms_url}"
        else
          warn "OVMS container is running, but its endpoint could not be resolved (see error above)."
        fi
      else
        warn "OpenVINO Model Server container exists but is not running (${HARNESS_OVMS_CONTAINER})"
      fi
    else
      info "OpenVINO Model Server not installed"
    fi

    if docker inspect "$HARNESS_IR_CONTAINER" >/dev/null 2>&1; then
      if [[ "$(docker inspect -f '{{.State.Running}}' "$HARNESS_IR_CONTAINER" 2>/dev/null)" == "true" ]]; then
        # Assigned via `if endpoint=$(harness_llm_endpoint)` (not inlined
        # into ok's argument list) so a failure inside harness_llm_endpoint
        # (e.g. its resolve_advertised_host's tamper checks on the
        # advertised-host state file) is actually detected here -- status
        # is read-only and must degrade gracefully rather than either
        # aborting outright or silently printing "Running — " with a blank
        # endpoint.
        local endpoint
        if endpoint="$(harness_llm_endpoint)"; then
          ok "Inference Router running — ${endpoint} (what the agent is wired to)"
        else
          warn "Inference Router container is running, but its endpoint could not be resolved (see error above)."
        fi
      else
        warn "Inference Router container exists but is not running (${HARNESS_IR_CONTAINER})"
      fi
    else
      info "Inference Router not installed"
    fi
  fi

  printf "\n${C_BOLD}Agent${C_RESET}\n"
  local display
  agent="$(resolve_installed_agent)"
  # agent_cli_bin returns 1 on an unrecognized name -- status is read-only
  # and must never hard-fail just because a stale/corrupted installed-agent
  # marker holds something unknown, so degrade to "not installed" instead.
  # The fallback must be outside the substitution (not `... || true` inside
  # it) -- see agent_cli_bin's comment for why that distinction matters here.
  cli_bin="$(agent_cli_bin "$agent")" || cli_bin=""
  display="$(agent_display_name "$agent")"
  if [[ -n "$cli_bin" ]] && command_exists "$cli_bin"; then
    ok "${display} installed ($(command -v "$cli_bin"))"
  elif [[ -n "$cli_bin" && -x "${HARNESS_SHIM_DIR}/${cli_bin}" ]]; then
    # Shim exists but isn't resolvable via this shell's current PATH yet
    # (e.g. .bashrc was updated after this terminal started) — command -v
    # alone would wrongly report it as not installed.
    warn "${display} installed (${HARNESS_SHIM_DIR}/${cli_bin}) but not on this
shell's PATH yet — open a new terminal, or re-source your shell profile."
  else
    info "${display} not installed"
  fi
  printf "\n"
}

run_models_command() {
  local verb="${1:-}" name="${2:-}"
  [[ -n "$verb" ]] || { usage; error "models requires a verb (list/remove)."; }
  case "$verb" in
    list) list_exported_models ;;
    remove) remove_exported_model "$name" ;;
    *) usage; error "Unknown models verb: $verb" ;;
  esac
}

# run_mcp_command — registers an arbitrary MCP endpoint URL with an agent.
# Reuses harness_register_mcp_endpoint (Hermes built in;
# HARNESS_MCP_REGISTER_CMD for anything else) — see harness-mcp.sh.
run_mcp_command() {
  local verb="${1:-}" name="${2:-}" url="${3:-}" agent="${4:-${HARNESS_AGENT:-hermes}}"
  [[ -n "$verb" ]] || { usage; error "mcp requires a verb (register)."; }
  case "$verb" in
    register)
      [[ -n "$name" && -n "$url" ]] || error "Usage: ./install.sh mcp register <name> <url> [agent]"
      harness_register_mcp_endpoint "$agent" "$name" "$url"
      ;;
    *) usage; error "Unknown mcp verb: $verb" ;;
  esac
}

# run_skill_command — Hermes-only (see agents.sh hermes_skill_install); the
# other catalog agents own their own plugin/skill mechanisms.
run_skill_command() {
  local verb="${1:-}" arg="${2:-}"
  [[ -n "$verb" ]] || { usage; error "skill requires a verb (install/list/remove)."; }
  case "$verb" in
    install) hermes_skill_install "$arg" ;;
    list) hermes_skill_list ;;
    remove) hermes_skill_remove "$arg" ;;
    *) usage; error "Unknown skill verb: $verb" ;;
  esac
}

main() {
  local -a original_args=("$@")
  local -a positional=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --non-interactive) NON_INTERACTIVE=1 ;;
      --skip-gpu-check) SKIP_GPU_CHECK=1 ;;
      --harness)
        [[ -n "${2:-}" ]] || { usage; error "--harness requires a value (openclaw|deepagents-code|hermes)."; }
        HARNESS_AGENT="$2"; shift ;;
      --model)
        [[ -n "${2:-}" ]] || { usage; error "--model requires a value (the model name as its hub names it, e.g. a Hugging Face id)."; }
        HARNESS_HF_MODEL="$2"; shift ;;
      --model-hub)
        [[ -n "${2:-}" ]] || { usage; error "--model-hub requires a value (e.g. openvino, huggingface, ollama)."; }
        HARNESS_MODEL_HUB="$2"; HARNESS_MODEL_HUB_WAS_SET=1; shift ;;
      --model-config)
        [[ -n "${2:-}" ]] || { usage; error "--model-config requires a value (a JSON object)."; }
        HARNESS_MODEL_CONFIG_JSON="$2"; HARNESS_MODEL_OPTS_GIVEN+=" config"; shift ;;
      --model-revision)
        [[ -n "${2:-}" ]] || { usage; error "--model-revision requires a value (branch, tag or commit)."; }
        HARNESS_MODEL_DOWNLOAD_REVISION="$2"; HARNESS_HF_MODEL_REVISION="$2"; HARNESS_MODEL_OPTS_GIVEN+=" revision"; shift ;;
      --model-type)
        [[ -n "${2:-}" ]] || { usage; error "--model-type requires a value (e.g. llm)."; }
        HARNESS_MODEL_TYPE="$2"; HARNESS_MODEL_OPTS_GIVEN+=" type"; shift ;;
      --model-precision)
        [[ -n "${2:-}" ]] || { usage; error "--model-precision requires a value (int4, int8, fp16 or fp32)."; }
        HARNESS_MODEL_PRECISION="$2"; HARNESS_MODEL_OPTS_GIVEN+=" precision"; shift ;;
      --model-device)
        [[ -n "${2:-}" ]] || { usage; error "--model-device requires a value (CPU, GPU, NPU or HETERO:…)."; }
        HARNESS_MODEL_DEVICE="$2"; HARNESS_MODEL_OPTS_GIVEN+=" device"; shift ;;
      --agent) usage; error "--agent was renamed to --harness." ;;
      --hf-model) usage; error "--hf-model was renamed to --model." ;;
      --help | -h) usage; exit 0 ;;
      --) ;;
      *) positional+=("$1") ;;
    esac
    shift
  done
  export NON_INTERACTIVE
  export HARNESS_AGENT HARNESS_HF_MODEL HARNESS_MODEL_HUB HARNESS_MODEL_HUB_WAS_SET HARNESS_MODEL_CONFIG_JSON HARNESS_MODEL_TYPE
  export HARNESS_MODEL_PRECISION HARNESS_MODEL_DEVICE HARNESS_MODEL_DOWNLOAD_REVISION HARNESS_HF_MODEL_REVISION
  apply_model_source_defaults

  if [[ "${positional[0]:-}" == "models" ]]; then
    run_models_command "${positional[@]:1}"
    exit 0
  fi
  if [[ "${positional[0]:-}" == "mcp" ]]; then
    run_mcp_command "${positional[@]:1}"
    exit 0
  fi
  if [[ "${positional[0]:-}" == "skill" ]]; then
    run_skill_command "${positional[@]:1}"
    exit 0
  fi
  if [[ "${positional[0]:-}" == "status" ]]; then
    print_status
    exit 0
  fi
  if [[ "${positional[0]:-}" == "onboard" ]]; then
    run_agent_onboard
    exit 0
  fi
  if [[ -n "${positional[0]:-}" ]]; then
    usage
    error "Unknown command: ${positional[0]}"
  fi

  require_model_selection

  printf "\n${C_GREEN}${C_BOLD}agent-harness-install${C_RESET}\n\n"

  prepare_installer_host

  step 1 "$TOTAL_STEPS" "Inference routing"
  ensure_inference_backend
  # Assigned as its own plain statement before exporting (not
  # `export VAR="$(...)"` combined) -- `export` is a builtin command, so a
  # failing command substitution embedded directly in its argument is NOT
  # checked by set -e (same pitfall as embedding one in printf/ok's
  # argument list): only a bare `VAR=$(cmd)` assignment's own failure is.
  # Without this split, a failure inside harness_llm_endpoint (e.g. its
  # resolve_advertised_host's tamper checks) would silently leave
  # HARNESS_LLM_ENDPOINT empty instead of aborting, and the agent would
  # then get installed/onboarded against a broken empty endpoint.
  HARNESS_LLM_ENDPOINT="${HARNESS_LLM_ENDPOINT:-$(harness_llm_endpoint)}"
  export HARNESS_LLM_ENDPOINT
  ok "LLM endpoint: ${HARNESS_LLM_ENDPOINT}"

  step 2 "$TOTAL_STEPS" "Agent install"
  # Node.js/npm is only actually needed to install openclaw (its CLI ships
  # as an npm package — see install_openclaw in agents.sh); deepagents-code
  # installs via uv and Hermes via its own shell installer, neither of which
  # touches npm. prepare_installer_host already ran startup.sh above, which
  # installs Node.js unconditionally (regardless of agent) unless
  # SKIP_NODEJS=1 -- this is a stronger, openclaw-specific check (version +
  # a writable npm global prefix, not just "node exists on PATH").
  if [[ "$(canonical_agent_name "${HARNESS_AGENT:-openclaw}")" == "openclaw" ]] \
    && { ! node_meets_requirements || ! npm_global_prefix_writable; }; then
    error "Node.js >=${MIN_NODE_VERSION} (with a writable npm global prefix) is
required to install openclaw -- was it skipped via SKIP_NODEJS=1? Run
./startup.sh --skip-docker --skip-python to install just Node.js, then
re-run ./install.sh."
  fi
  install_selected_agent

  step 3 "$TOTAL_STEPS" "Onboarding"
  run_agent_onboard

  print_done
}

main "$@"
