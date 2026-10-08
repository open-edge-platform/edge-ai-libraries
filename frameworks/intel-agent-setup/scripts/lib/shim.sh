# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=bash
# CLI shim + PATH profile management — puts the installed CLI on PATH for
# future shells even when npm's global bin isn't already there.

HARNESS_SHIM_DIR="${HARNESS_SHIM_DIR:-$HOME/.local/bin}"

detect_shell_profile() {
  local profile="$HOME/.bashrc"
  case "$(basename "${SHELL:-bash}")" in
    zsh) profile="$HOME/.zshrc" ;;
    fish) profile="$HOME/.config/fish/config.fish" ;;
    tcsh) profile="$HOME/.tcshrc" ;;
    csh) profile="$HOME/.cshrc" ;;
    *) [[ ! -f "$HOME/.bashrc" && -f "$HOME/.profile" ]] && profile="$HOME/.profile" ;;
  esac
  printf '%s' "$profile"
}

# Idempotent — skips if the marker comment is already present.
ensure_local_bin_in_profile() {
  local profile shell_name path_line
  profile="$(detect_shell_profile)"
  [[ -n "$profile" ]] || return 0
  if [[ -f "$profile" ]] && grep -qF '# Intel Agent Setup PATH setup' "$profile" 2>/dev/null; then
    return 0
  fi
  shell_name="$(basename "${SHELL:-bash}")"
  case "$shell_name" in
    fish) path_line="$(printf 'set -gx PATH "%s" $PATH' "$HARNESS_SHIM_DIR")" ;;
    csh | tcsh) path_line="$(printf 'setenv PATH "%s:$PATH"' "$HARNESS_SHIM_DIR")" ;;
    *) path_line="$(printf 'export PATH="%s:$PATH"' "$HARNESS_SHIM_DIR")" ;;
  esac
  mkdir -p "$(dirname "$profile")"
  {
    printf '\n# Intel Agent Setup PATH setup\n'
    printf '%s\n' "$path_line"
    printf '# end Intel Agent Setup PATH setup\n'
  } >>"$profile"
}

resolve_npm_bin() {
  command_exists npm || return 1
  local prefix
  prefix="$(npm config get prefix 2>/dev/null)"
  [[ -n "$prefix" ]] || return 1
  printf '%s/bin' "$prefix"
}

# Creates a thin exec shim in HARNESS_SHIM_DIR pointing at the resolved CLI,
# so a stale PATH cache in the current shell doesn't hide a real install.
# Refuses to clobber a shim that isn't a symlink-free file we own — that's
# either an attacker-planted path or a real, unrelated binary.
ensure_cli_shim() {
  local cli_bin="$1" npm_bin cli_path shim_path
  npm_bin="$(resolve_npm_bin)" || return 1
  cli_path="${npm_bin}/${cli_bin}"
  [[ -x "$cli_path" ]] || return 1
  shim_path="${HARNESS_SHIM_DIR}/${cli_bin}"

  # Always (re-)create the shim, even if $cli_bin already resolves via PATH
  # in this process — with nvm-managed Node, that resolution is a
  # version-pinned path (~/.nvm/versions/node/vX.Y.Z/bin) only on PATH
  # because nvm.sh happened to be sourced in *this* run. It won't be
  # resolvable in other shells the same way; the shim is what makes it so.
  if [[ -e "$shim_path" && ! -L "$shim_path" ]] \
    && grep -qF "$cli_path" "$shim_path" 2>/dev/null; then
    return 0
  fi

  if [[ -e "$shim_path" || -L "$shim_path" ]]; then
    [[ ! -L "$shim_path" ]] || error "Refusing to replace symlinked shim: ${shim_path}"
    [[ -f "$shim_path" ]] || error "Refusing to replace non-regular-file shim: ${shim_path}"
    local owner
    owner="$(stat -c '%u' "$shim_path" 2>/dev/null || stat -f '%u' "$shim_path" 2>/dev/null || true)"
    [[ -n "$owner" && "$owner" == "$(id -u)" ]] \
      || error "Refusing to replace shim not owned by the current user: ${shim_path}"
  fi

  mkdir -p "$HARNESS_SHIM_DIR"
  local tmp_shim
  tmp_shim="$(mktemp "${shim_path}.tmp.XXXXXX")"
  cat >"$tmp_shim" <<EOF
#!/usr/bin/env bash
exec "$cli_path" "\$@"
EOF
  chmod 755 "$tmp_shim"
  mv -f "$tmp_shim" "$shim_path"
  [[ ! -L "$shim_path" ]] || error "Shim path became a symlink during publish: ${shim_path}"
  ensure_local_bin_in_profile
  export PATH="${HARNESS_SHIM_DIR}:${PATH}"
  info "Created shim at ${shim_path}"
}

# Removes a shim we created, for the uninstaller. Uses the same ownership
# guards as ensure_cli_shim so it won't touch a file it doesn't recognize.
remove_cli_shim() {
  local cli_bin="$1" shim_path
  [[ -n "$cli_bin" ]] || return 0
  shim_path="${HARNESS_SHIM_DIR}/${cli_bin}"
  [[ -e "$shim_path" || -L "$shim_path" ]] || return 0
  if [[ -L "$shim_path" ]]; then
    warn "Refusing to remove symlinked shim: ${shim_path}"
    return 1
  fi
  local owner
  owner="$(stat -c '%u' "$shim_path" 2>/dev/null || stat -f '%u' "$shim_path" 2>/dev/null || true)"
  if [[ -z "$owner" || "$owner" != "$(id -u)" ]]; then
    warn "Refusing to remove shim not owned by the current user: ${shim_path}"
    return 1
  fi
  rm -f "$shim_path"
}
