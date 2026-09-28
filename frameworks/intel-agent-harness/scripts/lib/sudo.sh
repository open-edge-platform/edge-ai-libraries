# shellcheck shell=bash
# Non-interactive-safe sudo authorization: probe passwordless sudo first,
# else validate credentials through a TTY (stdin or /dev/tty for piped
# `curl | bash` installs).

authorize_sudo() {
  if sudo -n true >/dev/null 2>&1; then
    return 0
  fi
  if [[ "${NON_INTERACTIVE:-}" == "1" ]]; then
    return 1
  fi
  if [[ -t 0 ]]; then
    sudo -v >&2 || return 1
    return 0
  fi
  if { exec 3</dev/tty; } 2>/dev/null; then
    info "Installer stdin is piped; validating sudo credentials through /dev/tty…" >&2
    if ! sudo -v <&3 >&2; then
      exec 3<&-
      return 1
    fi
    exec 3<&-
    return 0
  fi
  return 1
}

require_sudo_or_fail() {
  authorize_sudo || error "This step needs sudo. Re-run in a terminal, or grant
passwordless sudo and set NON_INTERACTIVE=1, for: $*"
}
