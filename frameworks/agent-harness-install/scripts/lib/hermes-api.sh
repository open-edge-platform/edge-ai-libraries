#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# './install.sh hermes-api <enable|disable|status|key|forward>': turns the Hermes
# OpenAI-compatible API server (served by the Hermes gateway) on or off, on the
# host or inside the OpenShell sandbox. The server stays on loopback and is
# protected by a generated key kept in Hermes's .env (0600).
#
# Sourced by install.sh; relies on colors.sh, agents.sh, openshell.sh and
# install.sh helpers (usage, ensure_node_on_path).

HERMES_API_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/hermes-api-config.mjs"
HERMES_API_SANDBOX_SCRIPT=/opt/harness/hermes-api-config.mjs
HERMES_API_SANDBOX_HOME=/home/node/.hermes
HARNESS_HERMES_API_PORT="${HARNESS_HERMES_API_PORT:-}"
HARNESS_HERMES_API_LOCAL_PORT="${HARNESS_HERMES_API_LOCAL_PORT:-18642}"

hermes_api_validate_port() {
  local value="$1" label="$2"
  [[ "$value" =~ ^[1-9][0-9]{0,4}$ ]] && (( value <= 65535 )) \
    || error "${label} must be a port between 1 and 65535 (got '${value}')."
}

hermes_api_port_args() {
  [[ -z "$HARNESS_HERMES_API_PORT" ]] || printf '%s\n' --port "$HARNESS_HERMES_API_PORT"
}

# A freshly restarted sandbox can be Ready before it accepts exec, so retry the whole probe.
hermes_api_probe_sandbox() {
  local _
  for _ in {1..6}; do
    hermes_api_config probe --wait 20 && return 0
    sleep 3
  done
  return 1
}

# Runs the config helper on the host or in the sandbox, per the selected runtime.
hermes_api_config() {
  if [[ "${HARNESS_RUNTIME:-host}" == openshell ]]; then
    # Pass HERMES_HOME explicitly: a sandbox exec does not necessarily inherit the image environment.
    openshell_agent_exec /usr/bin/env "HERMES_HOME=${HERMES_API_SANDBOX_HOME}" \
      /usr/local/bin/node "$HERMES_API_SANDBOX_SCRIPT" "$@"
  else
    node "$HERMES_API_SCRIPT" "$@"
  fi
}

hermes_api_print_access() {
  local port="$1" location="${HERMES_HOME:-$HOME/.hermes}/.env"
  [[ "${HARNESS_RUNTIME:-host}" == openshell ]] && location="${HERMES_API_SANDBOX_HOME}/.env inside sandbox ${OPENSHELL_NAME}"
  printf '\n'
  info "Endpoint:  http://127.0.0.1:${port}/v1  (model name 'hermes-agent'; GET /health is unauthenticated)"
  info "API key:   stored in ${location}; print it with './install.sh hermes-api key' (add --runtime openshell for the sandbox)."
  info "The API gives full Hermes tool access: it stays on loopback. Use an SSH tunnel for remote clients."
}

hermes_api_enable_host() {
  local port
  local -a port_args
  command_exists hermes || error "The hermes CLI is not on PATH. Install it first: ./install.sh --harness hermes"
  if [[ -z "$(hermes_model_setting base_url 2>/dev/null || true)" ]]; then
    warn "Hermes has no custom model endpoint configured; run './install.sh onboard --harness hermes' so the API serves the local model."
  fi
  mapfile -t port_args < <(hermes_api_port_args)
  hermes_api_config enable "${port_args[@]}" >/dev/null \
    || error "Could not write the API server settings."
  port="$(hermes_api_config port)" || error "Could not read back the API server port."
  : > "$(hermes_gateway_marker)" || error "Could not record the gateway for uninstall."
  # The gateway reads .env only at start-up, so install the user service when missing and (re)start it.
  # 'hermes gateway status' exits 0 without a service, so look for the unit itself.
  if ! hermes_gateway_unit >/dev/null; then
    hermes gateway install \
      || error "'hermes gateway install' failed. Fix the error above, or run 'hermes gateway run' yourself; the settings are already written."
  fi
  hermes gateway restart || hermes gateway start \
    || error "Could not start the Hermes gateway. Check 'hermes gateway status'."
  hermes_api_config probe --wait 60 \
    || error "The API server did not become ready. Check 'hermes gateway status' and ${HERMES_HOME:-$HOME/.hermes}/logs."
  ok "Hermes API server enabled."
  hermes_api_print_access "$port"
  info "To keep the gateway running after you log out: sudo loginctl enable-linger \"\$USER\" (the installer never runs sudo)."
}

hermes_api_disable_host() {
  local unit state
  hermes_api_config disable >/dev/null || error "Could not remove the API server settings."
  if command_exists hermes && unit="$(hermes_gateway_unit)"; then
    # Skip the restart only when systemd says the service is down; an unreachable user bus prints nothing.
    state="$(systemctl --user is-active "$(basename "$unit" .service)" 2>/dev/null || true)"
    case "$state" in
      inactive | failed | unknown) ;;
      *)
        hermes gateway restart \
          || error "Could not restart the Hermes gateway, so the API server may still be answering with its old settings. Run 'hermes gateway restart', then check './install.sh hermes-api status'."
        ;;
    esac
  fi
  ok "Hermes API server disabled."
  info "The Hermes gateway service itself is left installed; manage it with 'hermes gateway stop' if you no longer need it."
}

hermes_api_prepare_openshell() {
  HARNESS_AGENT=hermes
  export HARNESS_AGENT
  openshell_load_profile
  openshell_assert_owned
  openshell_ensure_ready
  openshell_agent_exec /usr/bin/test -f "$HERMES_API_SANDBOX_SCRIPT" \
    || error "Sandbox ${OPENSHELL_NAME} was built before Hermes API server support. Recreate it: ./install.sh --runtime openshell --harness hermes"
}

hermes_api_enable_openshell() {
  local port
  local -a port_args
  hermes_api_prepare_openshell
  mapfile -t port_args < <(hermes_api_port_args)
  hermes_api_config enable "${port_args[@]}" >/dev/null \
    || error "Could not write the API server settings in the sandbox."
  port="$(hermes_api_config port)" || error "Could not read back the API server port."
  warn "Restarting sandbox ${OPENSHELL_NAME}; open Hermes sessions in it will end."
  openshell_restart_sandbox
  hermes_api_probe_sandbox \
    || error "The API server did not become ready inside the sandbox."
  ok "Hermes API server enabled in sandbox ${OPENSHELL_NAME}."
  hermes_api_print_access "$port"
  info "Reach it from the host with: ./install.sh hermes-api forward --runtime openshell"
}

hermes_api_disable_openshell() {
  hermes_api_prepare_openshell
  hermes_api_config disable >/dev/null || error "Could not remove the API server settings in the sandbox."
  warn "Restarting sandbox ${OPENSHELL_NAME}; open Hermes sessions in it will end."
  openshell_restart_sandbox
  ok "Hermes API server disabled in sandbox ${OPENSHELL_NAME}."
}

hermes_api_forward() {
  local port
  [[ "${HARNESS_RUNTIME:-host}" == openshell ]] \
    || error "'hermes-api forward' is only for --runtime openshell; the host API server is already on 127.0.0.1."
  hermes_api_prepare_openshell
  port="$(hermes_api_config port)" || error "The API server is not enabled in the sandbox. Run: ./install.sh hermes-api enable --runtime openshell"
  hermes_api_validate_port "$HARNESS_HERMES_API_LOCAL_PORT" "--forward-port"
  info "Forwarding http://127.0.0.1:${HARNESS_HERMES_API_LOCAL_PORT}/v1 to sandbox ${OPENSHELL_NAME}:${port}. Press Ctrl-C to stop."
  openshell forward service "$OPENSHELL_NAME" --target-port "$port" \
    --local "127.0.0.1:${HARNESS_HERMES_API_LOCAL_PORT}" -g "$OPENSHELL_GATEWAY"
}

hermes_api_status() {
  local state
  [[ "${HARNESS_RUNTIME:-host}" != openshell ]] || hermes_api_prepare_openshell
  state="$(hermes_api_config status)" || error "Could not read the API server settings."
  printf '%s\n' "$state"
  if [[ "$state" == *'"enabled":true'* ]]; then
    hermes_api_config probe || warn "The API server is configured but not answering; the gateway may be stopped."
  fi
}

run_hermes_api_command() {
  local verb="${1:-}"
  [[ -n "$verb" ]] || { usage; error "hermes-api requires a verb (enable/disable/status/key/forward)."; }
  [[ -z "$HARNESS_HERMES_API_PORT" ]] || hermes_api_validate_port "$HARNESS_HERMES_API_PORT" "--api-port"
  if [[ "${HARNESS_RUNTIME:-host}" != openshell ]]; then
    ensure_node_on_path
    command_exists node || error "Node.js was not found. Run ./startup.sh --skip-docker --skip-python to install it."
  fi
  case "$verb" in
    enable)
      if [[ "${HARNESS_RUNTIME:-host}" == openshell ]]; then hermes_api_enable_openshell; else hermes_api_enable_host; fi
      ;;
    disable)
      if [[ "${HARNESS_RUNTIME:-host}" == openshell ]]; then hermes_api_disable_openshell; else hermes_api_disable_host; fi
      ;;
    status) hermes_api_status ;;
    key)
      [[ "${HARNESS_RUNTIME:-host}" != openshell ]] || hermes_api_prepare_openshell
      hermes_api_config key || error "The Hermes API server is not enabled."
      ;;
    forward) hermes_api_forward ;;
    *) usage; error "Unknown hermes-api verb: ${verb}" ;;
  esac
}
