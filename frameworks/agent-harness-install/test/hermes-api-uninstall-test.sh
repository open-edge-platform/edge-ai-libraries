#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Offline test for remove_hermes_api_gateway: stub hermes/systemctl on PATH, throwaway HOME.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for lib in colors state agents hermes-api; do
  # shellcheck disable=SC1090
  . "$SCRIPT_DIR/scripts/lib/$lib.sh"
done
ROOT="$(mktemp -d)"
trap 'rm -rf -- "$ROOT"' EXIT
export NO_COLOR=1
HARNESS_SHIM_DIR="$ROOT/shim"
mkdir -p "$ROOT/bin" "$HARNESS_SHIM_DIR"
for stub in hermes systemctl node; do
  printf '#!/bin/sh\necho "%s $*" >> "$CALLS"\n' "$stub" > "$ROOT/bin/$stub"
  chmod +x "$ROOT/bin/$stub"
done
# RESTART_FAILS makes 'hermes gateway restart' fail; ACTIVE_STATE is what 'systemctl is-active' prints.
printf '[ "$2" = restart ] && [ -n "${RESTART_FAILS:-}" ] && exit 1\nexit 0\n' >> "$ROOT/bin/hermes"
printf '[ "$2" = is-active ] && [ -n "${ACTIVE_STATE:-}" ] && echo "$ACTIVE_STATE"\nexit 0\n' >> "$ROOT/bin/systemctl"
export PATH="$ROOT/bin:$PATH"
MARKER='# BEGIN agent-harness-install hermes-api -- do not edit between markers'
GATEWAY_EXEC='"/home/u/.hermes/venv/bin/python" "-m" "hermes_cli.main" "gateway" "run"'

# unit_file <path> <exec-start> <hermes-home>: writes a user unit the way 'hermes gateway install' does.
unit_file() {
  printf '[Service]\nExecStart=%s\nEnvironment="HERMES_HOME=%s"\n' "$2" "$3" > "$1"
}

# fixture <name> <state:yes|marker|no>: sets HOME, XDG_CONFIG_HOME, CALLS and UNIT for one case.
# yes = installer API block in .env; marker = gateway marker only (after 'disable'); no = neither.
fixture() {
  export HOME="$ROOT/$1/home" CALLS="$ROOT/$1/calls"
  export XDG_CONFIG_HOME="$HOME/.config"
  UNIT="$XDG_CONFIG_HOME/systemd/user/hermes-gateway.service"
  mkdir -p "$HOME/.hermes" "$(dirname "$UNIT")"
  : > "$CALLS"
  : > "$HOME/.hermes/.env"
  if [[ "$2" == yes ]]; then printf '%s\nAPI_SERVER_ENABLED=true\n' "$MARKER" > "$HOME/.hermes/.env"; fi
  if [[ "$2" == marker ]]; then : > "$HOME/.hermes/.agent-harness-install-gateway"; fi
  unit_file "$UNIT" "$GATEWAY_EXEC" "$HOME/.hermes"
  unset HERMES_HOME KEEP_AGENT_DATA
}
fail() { echo "FAIL: $*" >&2; exit 1; }

fixture enabled yes
remove_hermes_api_gateway 2>/dev/null
grep -Fxq 'hermes gateway stop' "$CALLS" || fail "gateway was not stopped"
grep -Fxq 'systemctl --user disable --now hermes-gateway' "$CALLS" || fail "unit was not disabled"
grep -Fxq 'systemctl --user daemon-reload' "$CALLS" || fail "systemd was not reloaded"
[[ ! -e "$UNIT" ]] || fail "unit file was not removed"

fixture disabled marker
remove_hermes_api_gateway 2>/dev/null
grep -Fxq 'hermes gateway stop' "$CALLS" || fail "after disable: gateway was not stopped"
[[ ! -e "$UNIT" ]] || fail "after disable: unit file was not removed"

fixture plain no
remove_hermes_api_gateway 2>/dev/null
[[ ! -s "$CALLS" ]] || fail "acted without the installer's API block or marker: $(cat "$CALLS")"
[[ -f "$UNIT" ]] || fail "removed a unit it did not start"

fixture keep yes
KEEP_AGENT_DATA=1 remove_hermes_api_gateway 2>/dev/null
grep -Fxq 'hermes gateway stop' "$CALLS" || fail "KEEP_AGENT_DATA: gateway was not stopped"
[[ -f "$UNIT" ]] || fail "KEEP_AGENT_DATA: unit was removed"

fixture custom yes
mkdir -p "$HOME/custom"; cp "$HOME/.hermes/.env" "$HOME/custom/.env"
CUSTOM_UNIT="$(dirname "$UNIT")/hermes-gateway-abc12345.service"
unit_file "$CUSTOM_UNIT" "$GATEWAY_EXEC" "$HOME/custom"
HERMES_HOME="$HOME/custom" remove_hermes_api_gateway 2>/dev/null
grep -Fxq 'hermes gateway stop' "$CALLS" || fail "custom HERMES_HOME: gateway was not stopped"
grep -Fxq 'systemctl --user disable --now hermes-gateway-abc12345' "$CALLS" || fail "custom HERMES_HOME: its unit was not disabled"
[[ ! -e "$CUSTOM_UNIT" ]] || fail "custom HERMES_HOME: its unit was not removed"
[[ -f "$UNIT" ]] || fail "custom HERMES_HOME: default unit was removed"

fixture symlink yes
mv "$UNIT" "$HOME/real.service"; ln -s "$HOME/real.service" "$UNIT"
remove_hermes_api_gateway 2>/dev/null
[[ -L "$UNIT" && -f "$HOME/real.service" ]] || fail "followed a symlinked unit"

fixture foreign yes
unit_file "$UNIT" '"/usr/bin/other-daemon"' "$HOME/.hermes"
remove_hermes_api_gateway 2>/dev/null
[[ -f "$UNIT" ]] || fail "removed a unit that does not run the gateway"

fixture lookalike yes
unit_file "$UNIT" '"/usr/bin/api-gateway" "run"' "$HOME/.hermes"
remove_hermes_api_gateway 2>/dev/null
[[ -f "$UNIT" ]] || fail "removed a foreign unit whose command only contains 'gateway'"

fixture otherhome yes
unit_file "$UNIT" "$GATEWAY_EXEC" "$HOME/elsewhere"
remove_hermes_api_gateway 2>/dev/null
[[ -f "$UNIT" ]] || fail "removed a Hermes unit that pins another HERMES_HOME"

fixture package yes
remove_hermes_package 2>/dev/null
[[ ! -e "$UNIT" && ! -d "$HOME/.hermes" ]] || fail "uninstall left the unit or data behind"
echo "remove_hermes_api_gateway: all cases passed"

# hermes_api_disable_host restarts the gateway unless systemd reports it down.
for state in active activating ""; do
  fixture "disable-${state:-nobus}" no
  ACTIVE_STATE="$state" hermes_api_disable_host >/dev/null 2>&1
  grep -Fxq 'hermes gateway restart' "$CALLS" || fail "disable: no restart for state '${state}'"
done
for state in inactive failed; do
  fixture "disable-$state" no
  ACTIVE_STATE="$state" hermes_api_disable_host >/dev/null 2>&1
  ! grep -Fxq 'hermes gateway restart' "$CALLS" || fail "disable: restarted a $state gateway"
done
fixture disable-nounit no
rm -f "$UNIT"
ACTIVE_STATE=active hermes_api_disable_host >/dev/null 2>&1
! grep -Fxq 'hermes gateway restart' "$CALLS" || fail "disable: restarted without a unit"
fixture disable-restartfail no
if (ACTIVE_STATE=active RESTART_FAILS=1 hermes_api_disable_host) >/dev/null 2>&1; then
  fail "disable: a failed restart was not reported"
fi
echo "hermes_api_disable_host: all cases passed"
