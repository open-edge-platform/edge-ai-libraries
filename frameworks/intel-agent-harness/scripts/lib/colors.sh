# shellcheck shell=bash
# Color / logging helpers — disabled when NO_COLOR is set or stdout is not a TTY.
if [[ -z "${NO_COLOR:-}" && -t 1 ]]; then
  C_BOLD=$'\033[1m'
  C_DIM=$'\033[2m'
  C_RED=$'\033[1;31m'
  C_GREEN=$'\033[1;32m'
  C_YELLOW=$'\033[1;33m'
  C_CYAN=$'\033[1;36m'
  C_RESET=$'\033[0m'
else
  C_BOLD='' C_DIM='' C_RED='' C_GREEN='' C_YELLOW='' C_CYAN='' C_RESET=''
fi

info()  { printf "${C_CYAN}[INFO]${C_RESET}  %s\n" "$*"; }
warn()  { printf "${C_YELLOW}[WARN]${C_RESET}  %s\n" "$*"; }
ok()    { printf "  ${C_GREEN}✓${C_RESET}  %s\n" "$*"; }
error() { printf "${C_RED}[ERROR]${C_RESET} %s\n" "$*" >&2; exit 1; }

# step N total "Description" — numbered section header
step() {
  local n="$1" total="$2" msg="$3"
  printf "\n${C_GREEN}[%s/%s]${C_RESET} ${C_BOLD}%s${C_RESET}\n" "$n" "$total" "$msg"
  printf "  ${C_DIM}──────────────────────────────────────────────────${C_RESET}\n"
}

# spin "label" cmd [args...] — runs a command, showing a spinner until it exits.
# Falls back to plain output when stdout is not a TTY (CI / piped installs).
spin() {
  local msg="$1"
  shift
  if [[ ! -t 1 ]]; then
    info "$msg"
    "$@"
    return
  fi
  local log pid i=0 status
  local frames=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
  log=$(mktemp)
  "$@" >"$log" 2>&1 &
  pid=$!
  while kill -0 "$pid" 2>/dev/null; do
    printf "\r  ${C_GREEN}%s${C_RESET}  %s" "${frames[$((i++ % 10))]}" "$msg"
    sleep 0.08
  done
  wait "$pid" && status=0 || status=$?
  if [[ $status -eq 0 ]]; then
    printf "\r  ${C_GREEN}✓${C_RESET}  %s\n" "$msg"
  else
    printf "\r  ${C_RED}✗${C_RESET}  %s\n\n" "$msg"
    cat "$log" >&2
  fi
  rm -f "$log"
  return "$status"
}

command_exists() { command -v "$1" &>/dev/null; }
