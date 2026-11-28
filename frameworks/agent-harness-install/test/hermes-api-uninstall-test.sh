#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Offline test for remove_hermes_api_gateway: stub hermes/systemctl on PATH, throwaway HOME.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for lib in colors state agents; do
  # shellcheck disable=SC1090
  . "$SCRIPT_DIR/scripts/lib/$lib.sh"
done
ROOT="$(mktemp -d)"
trap 'rm -rf -- "$ROOT"' EXIT
export NO_COLOR=1
HARNESS_SHIM_DIR="$ROOT/shim"
mkdir -p "$ROOT/bin" "$HARNESS_SHIM_DIR"
for stub in hermes systemctl; do
  printf '#!/bin/sh\necho "%s $*" >> "$CALLS"\n' "$stub" > "$ROOT/bin/$stub"
  chmod +x "$ROOT/bin/$stub"
done
export PATH="$ROOT/bin:$PATH"
MARKER='# BEGIN agent-harness-install hermes-api -- do not edit between markers'

# fixture <name> <with-marker:yes|no>: sets HOME, CALLS and UNIT for one case.
fixture() {
  export HOME="$ROOT/$1/home" CALLS="$ROOT/$1/calls"
  UNIT="$HOME/.config/systemd/user/hermes-gateway.service"
  mkdir -p "$HOME/.hermes" "$(dirname "$UNIT")"
  : > "$CALLS"
  if [[ "$2" == yes ]]; then printf '%s\nAPI_SERVER_ENABLED=true\n' "$MARKER" > "$HOME/.hermes/.env"; else : > "$HOME/.hermes/.env"; fi
  printf '[Service]\nExecStart=/home/u/.hermes/venv/bin/python -m hermes_cli.main gateway run --replace\n' > "$UNIT"
  unset HERMES_HOME KEEP_AGENT_DATA
}
fail() { echo "FAIL: $*" >&2; exit 1; }

fixture enabled yes
remove_hermes_api_gateway 2>/dev/null
grep -Fxq 'hermes gateway stop' "$CALLS" || fail "gateway was not stopped"
grep -Fxq 'systemctl --user disable --now hermes-gateway' "$CALLS" || fail "unit was not disabled"
grep -Fxq 'systemctl --user daemon-reload' "$CALLS" || fail "systemd was not reloaded"
[[ ! -e "$UNIT" ]] || fail "unit file was not removed"

fixture plain no
remove_hermes_api_gateway 2>/dev/null
[[ ! -s "$CALLS" ]] || fail "acted without the installer's API block: $(cat "$CALLS")"
[[ -f "$UNIT" ]] || fail "removed a unit it did not start"

fixture keep yes
KEEP_AGENT_DATA=1 remove_hermes_api_gateway 2>/dev/null
grep -Fxq 'hermes gateway stop' "$CALLS" || fail "KEEP_AGENT_DATA: gateway was not stopped"
[[ -f "$UNIT" ]] || fail "KEEP_AGENT_DATA: unit was removed"

fixture custom yes
mkdir -p "$HOME/custom"; cp "$HOME/.hermes/.env" "$HOME/custom/.env"
HERMES_HOME="$HOME/custom" remove_hermes_api_gateway 2>/dev/null
grep -Fxq 'hermes gateway stop' "$CALLS" || fail "custom HERMES_HOME: gateway was not stopped"
[[ -f "$UNIT" ]] || fail "custom HERMES_HOME: default unit was removed"

fixture symlink yes
mv "$UNIT" "$HOME/real.service"; ln -s "$HOME/real.service" "$UNIT"
remove_hermes_api_gateway 2>/dev/null
[[ -L "$UNIT" && -f "$HOME/real.service" ]] || fail "followed a symlinked unit"

fixture foreign yes
printf '[Service]\nExecStart=/usr/bin/other-daemon\n' > "$UNIT"
remove_hermes_api_gateway 2>/dev/null
[[ -f "$UNIT" ]] || fail "removed a unit that does not run the gateway"

fixture package yes
remove_hermes_package 2>/dev/null
[[ ! -e "$UNIT" && ! -d "$HOME/.hermes" ]] || fail "uninstall left the unit or data behind"
echo "remove_hermes_api_gateway: all cases passed"
