# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=bash
# Registers an arbitrary MCP endpoint URL with the installed agent.
# Hermes's real, documented config.yaml shape and OpenClaw's own `mcp set`
# command are built in; any other agent can be wired up via
# HARNESS_MCP_REGISTER_CMD (bring your own registration script) instead of
# this installer guessing its config format, same stance this installer
# already takes with the Hermes install itself before it was verified.

hermes_config_path() {
  printf '%s' "${HERMES_CONFIG:-$HOME/.hermes/config.yaml}"
}

# Merges a remote MCP server entry into Hermes's config.yaml. Requires
# python3 with PyYAML: this project has no other YAML tooling, and
# hand-editing YAML with sed/awk is too fragile to trust for a config file a
# running agent depends on. Lock-protected so two concurrent registrations
# can't clobber each other.
hermes_register_mcp_endpoint() {
  local name="$1" url="$2"
  with_state_lock hermes-config _hermes_register_mcp_endpoint_locked "$name" "$url"
}

_hermes_register_mcp_endpoint_locked() {
  local name="$1" url="$2" config
  config="$(hermes_config_path)"
  command_exists python3 || error "python3 is required to register MCP endpoints
with Hermes (edit ${config} manually instead)."
  mkdir -p "$(dirname "$config")"
  python3 - "$config" "$name" "$url" <<'PY' || error "Could not update the Hermes
config (install PyYAML: pip install pyyaml — or edit the file manually)."
import sys

try:
    import yaml
except ImportError:
    sys.exit(1)

config_path, name, url = sys.argv[1:4]
try:
    with open(config_path) as f:
        data = yaml.safe_load(f) or {}
except FileNotFoundError:
    data = {}

data.setdefault("mcp_servers", {})[name] = {
    "url": url,
    "transport": "streamable-http",
    "enabled": True,
    "connect_timeout": 15,
    "timeout": 120,
}

# Hermes's config can carry provider API keys, so write it 0600 -- plain
# open(..., "w") would use the process umask (commonly 0644) -- and refuse
# to follow a symlink swapped in at the destination path.
import os

flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
fd = os.open(config_path, flags, 0o600)
with os.fdopen(fd, "w") as f:
    yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
PY
  ok "Registered '${name}' with Hermes (${config})"
}

# OpenClaw's own CLI has a real, documented MCP registration command
# (`openclaw mcp set <name> '<json>'`), including remote HTTP/SSE servers via
# a bare `url` field -- no config-file format guessing needed here.
openclaw_register_mcp_endpoint() {
  local name="$1" url="$2" url_esc json
  command_exists openclaw || error "openclaw CLI not found on PATH -- install it first."
  # Escape backslashes/quotes before embedding in the JSON string literal.
  url_esc="$(printf '%s' "$url" | sed 's/\\/\\\\/g; s/"/\\"/g')"
  json="{\"url\": \"${url_esc}\"}"
  openclaw mcp set "$name" "$json" || error "'openclaw mcp set ${name}' failed."
  ok "Registered '${name}' with OpenClaw (openclaw mcp set)"
}

harness_register_mcp_endpoint() {
  local agent name url
  agent="$(canonical_agent_name "$1")" name="$2" url="$3"
  [[ -n "$name" && -n "$url" ]] || error "harness_register_mcp_endpoint requires a
service name and an endpoint URL."

  # Bring-your-own registration: lets any agent be wired up via its own real
  # config format without this installer having to guess or fabricate one.
  # Gets the same canonicalized agent name as the built-in dispatch below.
  if [[ -n "${HARNESS_MCP_REGISTER_CMD:-}" ]]; then
    info "Registering '${name}' via HARNESS_MCP_REGISTER_CMD…"
    "$HARNESS_MCP_REGISTER_CMD" "$agent" "$name" "$url" \
      || error "HARNESS_MCP_REGISTER_CMD failed for '${name}'."
    return
  fi

  case "$agent" in
    hermes) hermes_register_mcp_endpoint "$name" "$url" ;;
    openclaw) openclaw_register_mcp_endpoint "$name" "$url" ;;
    *) warn "MCP registration for '${agent}' isn't implemented here — this installer
hasn't verified its config format. Set HARNESS_MCP_REGISTER_CMD=<script> to plug
in your agent's real registration logic, or point it at ${url} manually." ;;
  esac
}
