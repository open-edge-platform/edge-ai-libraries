# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=bash
# Third-party software notice acceptance flow. Edit notice.json to change
# the text/version.

notice_config_path() {
  printf '%s/notice.json' "$SCRIPT_DIR"
}

notice_state_file() {
  local state_dir
  state_dir="$(ensure_state_dir)"
  printf '%s/notice-acceptance.json' "$state_dir"
}

notice_already_accepted() {
  local version="$1" state_file saved
  state_file="$(notice_state_file)"
  [[ -f "$state_file" ]] || return 1
  saved="$(read_json_field "$state_file" acceptedVersion)"
  [[ "$saved" == "$version" ]]
}

save_notice_acceptance() {
  local version="$1" state_file
  state_file="$(notice_state_file)"
  atomic_write_file "$state_file" "{\"acceptedVersion\":\"${version}\"}"
}

print_notice_body() {
  local notice_json="$1"
  if command_exists node; then
    node -e '
      const data = JSON.parse(require("node:fs").readFileSync(process.argv[1], "utf8"));
      for (const line of data.body || []) console.log("  " + line);
    ' "$notice_json" 2>/dev/null && return
  fi
  # Fallback without Node: best-effort extraction of the "body" string array.
  sed -n '/"body"/,/\]/p' "$notice_json" | grep -oE '"[^"]*"' | sed -n '2,$p' | sed 's/^"//; s/"$//; s/^/  /'
}

# Fails closed in non-interactive mode unless explicitly accepted, and prompts
# on a TTY (stdin or /dev/tty) otherwise.
require_third_party_notice_acceptance() {
  local notice_json version title prompt answer
  notice_json="$(notice_config_path)"
  [[ -f "$notice_json" ]] || error "Third-party notice config not found: ${notice_json}.
This installer refuses to skip consent because of a missing/corrupt checkout
— restore notice.json and retry."
  version="$(read_json_field "$notice_json" version)"
  [[ -n "$version" ]] || error "notice.json is missing a 'version' field: ${notice_json}.
Refusing to skip third-party notice consent due to a malformed config."

  if notice_already_accepted "$version"; then
    return 0
  fi
  if [[ "${ACCEPT_THIRD_PARTY_SOFTWARE:-}" == "1" ]]; then
    save_notice_acceptance "$version"
    return 0
  fi
  if [[ "${NON_INTERACTIVE:-}" == "1" ]]; then
    error "Non-interactive installation requires explicit acceptance. Re-run with
--yes-i-accept-third-party-software (or ACCEPT_THIRD_PARTY_SOFTWARE=1)."
  fi

  title="$(read_json_field "$notice_json" title)"
  prompt="$(read_json_field "$notice_json" interactivePrompt)"
  printf "\n  %s\n  ────────────────────────────────────────\n" "${title:-Third-Party Software Notice}"
  print_notice_body "$notice_json"
  printf "\n"

  if [[ -t 0 ]]; then
    printf "  %s" "${prompt:-Type 'yes' to accept and continue [no]: }"
    IFS= read -r answer || answer=""
  elif { exec 3</dev/tty; } 2>/dev/null; then
    printf "  %s" "${prompt:-Type 'yes' to accept and continue [no]: }"
    IFS= read -r answer <&3 || answer=""
    exec 3<&-
  else
    error "Interactive third-party software acceptance requires a TTY. Re-run in a
terminal, or pass --yes-i-accept-third-party-software."
  fi

  [[ "$(printf '%s' "$answer" | tr '[:upper:]' '[:lower:]')" == "yes" ]] \
    || error "Installation cancelled — third-party software notice was not accepted."
  save_notice_acceptance "$version"
}
