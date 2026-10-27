# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=bash
# Real agent catalog — installs actual open-source agent projects, verified
# against their public npm registry entries. HARNESS_AGENT selects one.
#
# Verified real, public, MIT-licensed packages:
#   openclaw        -> npm package "openclaw" (github.com/openclaw/openclaw)
#   deepagents-code -> LangChain's official "Deep Agents Code" CLI (dcode),
#                      installed via its own official installer
#                      (github.com/langchain-ai/deepagents) -- not a runner
#                      this installer scaffolds itself.
#   hermes          -> Nous Research's Hermes Agent, installed via its own
#                      official shell installer (not npm) from
#                      hermes-agent.nousresearch.com/install.sh.

canonical_agent_name() {
  local lowered
  lowered="$(printf '%s' "${1:-openclaw}" | tr '[:upper:]' '[:lower:]')"
  case "$lowered" in
    openclaw | open-claw) printf 'openclaw' ;;
    deepagents | deep-agents | deepagents-code | dcode | langgraph | langchain-deepagents) printf 'deepagents-code' ;;
    hermes) printf 'hermes' ;;
    # Returns the lowercased (not raw) input so downstream case matches stay
    # consistent with the patterns above, and so the caller's own "unknown
    # agent" error echoes back the same string it just failed to match.
    *) printf '%s' "$lowered" ;;
  esac
}

agent_display_name() {
  case "$1" in
    openclaw) printf 'OpenClaw' ;;
    deepagents-code) printf 'Deep Agents Code' ;;
    hermes) printf 'Hermes' ;;
    *) printf '%s' "$1" ;;
  esac
}

agent_cli_bin() {
  case "$1" in
    openclaw) printf 'openclaw' ;;
    deepagents-code) printf 'dcode' ;;
    hermes) printf 'hermes' ;;
    # Returns 1 (not error()'s exit) for an unrecognized name -- callers that
    # assign this straight into a variable via `cli_bin="$(agent_cli_bin ..)"`
    # run under `set -e` in a context where the substitution IS the entire
    # command, so a bare `exit` here would abort the whole script before an
    # outer `|| ...` fallback (e.g. print_status's graceful degrade) ever
    # got a chance to run. Callers that want a hard failure instead do
    # `cli_bin="$(agent_cli_bin "$agent")" || error "..."` themselves.
    *) return 1 ;;
  esac
}

# Refuses to trust a CLI that resolves outside the npm global bin or our own
# shim dir — catches PATH-hijack impersonation by an unrelated earlier entry.
agent_cli_is_trusted_path() {
  local cli_bin="$1" resolved npm_bin
  resolved="$(command -v "$cli_bin" 2>/dev/null)" || return 1
  npm_bin="$(resolve_npm_bin 2>/dev/null || true)"
  [[ "$resolved" == "${HARNESS_SHIM_DIR}/"* ]] && return 0
  [[ -n "$npm_bin" && "$resolved" == "${npm_bin}/"* ]] && return 0
  # dcode's own upstream installer (https://langch.in/dcode, a uv-based
  # installer with no knowledge of this project's HARNESS_SHIM_DIR) always
  # installs to this fixed location regardless -- trusted the same way
  # npm's resolved global bin is, independent of this installer's own
  # (user-configurable, e.g. test-isolated) shim dir.
  [[ "$resolved" == "$HOME/.local/bin/"* ]] && return 0
  return 1
}

# Confirms the installed binary actually runs, not just that a file exists
# with the expected name (an install can silently fail and leave a stub).
verify_agent_cli() {
  local cli_bin="$1"
  command_exists "$cli_bin" || return 1
  agent_cli_is_trusted_path "$cli_bin" || error "'${cli_bin}' resolves to an untrusted
location ($(command -v "$cli_bin")); refusing to treat it as the installed agent."
  "$cli_bin" --version >/dev/null 2>&1 || "$cli_bin" --help >/dev/null 2>&1 \
    || { warn "'${cli_bin}' was installed but does not respond to --version/--help."; return 1; }
}

# Reads the version npm actually has installed globally for a package, empty
# if not installed — used to avoid downgrading a newer install to the pin.
installed_npm_global_version() {
  local pkg="$1" json
  command_exists npm || return 1
  json="$(npm list -g "$pkg" --depth=0 --json 2>/dev/null)" || return 1
  node -e '
    try {
      const data = JSON.parse(process.argv[1]);
      const v = data.dependencies?.[process.argv[2]]?.version;
      if (v) process.stdout.write(v);
    } catch {}
  ' "$json" "$pkg" 2>/dev/null
}

install_openclaw() {
  local version="${OPENCLAW_VERSION:-2026.9.5}" installed npm_ver
  local -a npm_args=(-g "openclaw@${version}")
  # Not wrapping this in `|| true` would let a failure here (package not
  # yet installed — the normal fresh-install case) silently kill the whole
  # `set -e` script via the plain assignment's own exit status.
  installed="$(installed_npm_global_version openclaw || true)"
  if [[ -n "$installed" ]] && version_gte "$installed" "$version"; then
    info "OpenClaw already installed (openclaw@${installed}) — not downgrading to ${version}."
    return 0
  fi
  # npm 11.16+/12+ blocks a package's install-time lifecycle scripts unless
  # explicitly allow-listed; OpenClaw's own install docs require this flag
  # on those npm versions, and skipping it silently leaves the CLI broken.
  npm_ver="$(command_exists npm && npm --version 2>/dev/null || true)"
  if [[ -n "$npm_ver" ]] && version_gte "$npm_ver" "11.16.0"; then
    npm_args+=(--allow-scripts=openclaw)
  fi
  info "Installing OpenClaw (openclaw@${version}) from the public npm registry…"
  spin "npm install -g openclaw" npm install "${npm_args[@]}"
}

# Registers this installer's OpenAI-compatible endpoint as a custom OpenClaw
# model provider named "ovms", using OpenClaw's own documented, non-fabricated
# mechanism (`models.providers` — see docs/gateway/config-tools/
# custom-providers.md in github.com/openclaw/openclaw) and selects it as the
# default model. Mirrors configure_dcode_provider's role for dcode.
# `openclaw config set` requires the local Gateway to be stopped (it refuses
# to write otherwise, leaving any existing config untouched) -- callers
# should treat a non-zero return as "configure it manually instead".
configure_openclaw_provider() {
  local endpoint="$1" model_name="$2" endpoint_esc model_name_esc provider_json
  # Escape backslashes/quotes before interpolating into JSON string literals
  # -- same reasoning as configure_dcode_provider's TOML escaping.
  endpoint_esc="$(printf '%s' "$endpoint" | sed 's/\\/\\\\/g; s/"/\\"/g')"
  model_name_esc="$(printf '%s' "$model_name" | sed 's/\\/\\\\/g; s/"/\\"/g')"
  # contextWindow/maxTokens are required-ish catalog fields with no per-model
  # value this installer can verify for an arbitrary --model; these are
  # conservative generic defaults the operator can override afterward with
  # another `openclaw config set models.providers.ovms.models ...`.
  provider_json="{\"baseUrl\":\"${endpoint_esc}\",\"api\":\"openai-completions\",\"apiKey\":\"not-needed\",\"models\":[{\"id\":\"${model_name_esc}\",\"name\":\"${model_name_esc}\",\"reasoning\":false,\"input\":[\"text\"],\"cost\":{\"input\":0,\"output\":0,\"cacheRead\":0,\"cacheWrite\":0},\"contextWindow\":32768,\"maxTokens\":4096}]}"
  openclaw config set models.providers.ovms "$provider_json" --strict-json --merge \
    || { warn "'openclaw config set' failed -- if the OpenClaw Gateway daemon is running,
stop it first ('openclaw gateway stop'), then re-run: ./install.sh onboard."; return 1; }
  openclaw models set "ovms/${model_name}" \
    || { warn "Registered the 'ovms' provider but could not set it as the default model."; return 1; }
}

# dcode ("Deep Agents Code") is LangChain's own official terminal coding
# agent CLI (github.com/langchain-ai/deepagents) -- installed via its
# official installer rather than this installer scaffolding a runner around
# the bare deepagents library itself. Supports pointing at an arbitrary
# OpenAI-compatible endpoint out of the box (see configure_dcode_provider),
# so no Intel-specific code is needed beyond that wiring.

# Default dcode installer: libs/code/scripts/install.sh at the commit tagged
# deepagents-code==0.1.86 (byte-identical to what https://langch.in/dcode
# served for that release), with its SHA-256. Bump all three together.
DCODE_PINNED_VERSION="0.1.86"
DCODE_PINNED_COMMIT="577e3f1f2376f8522c47aedc9423de3805e9deb8"
DCODE_PINNED_SHA256="1961f5eb8d338e668b3f5afc34ad15e87e6602bdec56cfe261265462228d8639"

install_dcode() {
  local installer_url installer_sha256="${DCODE_INSTALL_SHA256:-}"
  local installer_tmp
  installer_tmp="$(mktemp)"
  if [[ -n "${DCODE_INSTALL_URL:-}" ]]; then
    installer_url="$DCODE_INSTALL_URL"
  else
    installer_url="https://raw.githubusercontent.com/langchain-ai/deepagents/${DCODE_PINNED_COMMIT}/libs/code/scripts/install.sh"
    installer_sha256="${installer_sha256:-$DCODE_PINNED_SHA256}"
    export DEEPAGENTS_CODE_VERSION="${DEEPAGENTS_CODE_VERSION:-$DCODE_PINNED_VERSION}"
  fi
  info "Installing Deep Agents Code (dcode) from ${installer_url}…"
  # A custom DCODE_INSTALL_URL has no built-in digest: fail closed unless the
  # caller pins DCODE_INSTALL_SHA256 or opts out explicitly.
  if [[ -z "$installer_sha256" && "${HARNESS_ALLOW_UNVERIFIED_DCODE_INSTALL:-}" != "1" ]]; then
    error "DCODE_INSTALL_SHA256 is not set, so refusing to run dcode's installer
unverified. Download and review ${installer_url} yourself, then set
DCODE_INSTALL_SHA256=<sha256> to pin it (or HARNESS_ALLOW_UNVERIFIED_DCODE_INSTALL=1
to accept the risk and proceed without pinning)."
  fi
  fetch_and_verify "$installer_url" "$installer_tmp" "dcode installer" "$installer_sha256"
  assert_shell_script "$installer_tmp" "dcode installer"
  spin "Installing dcode" bash "$installer_tmp"
  rm -f "$installer_tmp"
  export PATH="$HOME/.local/bin:$PATH"
}

# Writes dcode's [models.providers.openai] section (its "Compatible APIs"
# mechanism) to point at this installer's OpenAI-compatible endpoint, inside
# BEGIN/END markers so a re-run replaces only this block and leaves any
# other provider config/preferences the operator has in config.toml alone.
# api_key_env names a harness-owned var (not OPENAI_API_KEY) so this never
# reads/collides with a real OpenAI key the operator may have set for
# something else -- OVMS itself doesn't check it, it just needs *a* value.
configure_dcode_provider() {
  local endpoint="$1" model_name="$2" config_dir config_file tmp
  local endpoint_esc model_name_esc
  # Escape backslashes/quotes before interpolating into a TOML basic string
  # ("...") -- an unescaped quote in $endpoint/$model_name (e.g. a stray
  # character in a misconfigured HARNESS_LLM_ROUTER_ENDPOINT) would otherwise
  # break out of the string literal and corrupt the rest of config.toml.
  endpoint_esc="$(printf '%s' "$endpoint" | sed 's/\\/\\\\/g; s/"/\\"/g')"
  model_name_esc="$(printf '%s' "$model_name" | sed 's/\\/\\\\/g; s/"/\\"/g')"
  config_dir="${DEEPAGENTS_HOME:-$HOME/.deepagents}"
  config_file="${config_dir}/config.toml"
  mkdir -p "$config_dir"
  tmp="$(mktemp)"
  if [[ -f "$config_file" ]]; then
    awk '
      /# BEGIN agent-harness-install managed provider/ { skip=1 }
      /# END agent-harness-install managed provider/ { skip=0; next }
      !skip
    ' "$config_file" >"$tmp"
  fi
  # A second [models] (or provider) table would make the whole file invalid
  # TOML, so leave the operator's own tables alone and say what to add.
  if grep -qE '^[[:space:]]*\[models(\.providers\.openai(\.params)?)?\][[:space:]]*(#.*)?$' "$tmp"; then
    rm -f "$tmp"
    warn "${config_file} already defines [models] or [models.providers.openai] outside this
installer's managed block; leaving it untouched. To point dcode at this endpoint, merge into
those tables yourself:
  default = \"openai:${model_name_esc}\"
  [models.providers.openai]
  base_url = \"${endpoint_esc}\"
  api_key_env = \"HARNESS_DCODE_API_KEY\"
  models = [\"${model_name_esc}\"]
  [models.providers.openai.params]
  use_responses_api = false"
    return 1
  fi
  {
    cat "$tmp"
    cat <<EOF
# BEGIN agent-harness-install managed provider -- do not edit between markers
[models]
default = "openai:${model_name_esc}"

[models.providers.openai]
base_url = "${endpoint_esc}"
api_key_env = "HARNESS_DCODE_API_KEY"
models = ["${model_name_esc}"]

[models.providers.openai.params]
use_responses_api = false
# END agent-harness-install managed provider
EOF
  } >"${tmp}.new"
  mv -f "${tmp}.new" "$config_file"
  rm -f "$tmp"
}

# Default Hermes installer: scripts/install.sh at the commit tagged v0.22.2,
# with its SHA-256; --commit makes the installer check out that same commit.
# The hermes-agent.nousresearch.com URL serves a moving target, so it is not
# used by default. Bump all three together.
HERMES_PINNED_COMMIT="d923a5eb487a17c0a68801bba9ef0f56c81040a8"
HERMES_PINNED_SHA256="f4cdb0e20f1aca2c3871a76b962fd4db61510f549cf973759c753ac13349beb5"

install_hermes() {
  local installer_url installer_sha256="${HERMES_INSTALL_SHA256:-}"
  local -a installer_args=(--skip-setup --non-interactive)
  local installer_tmp
  installer_tmp="$(mktemp)"
  if [[ -n "${HERMES_INSTALL_URL:-}" ]]; then
    installer_url="$HERMES_INSTALL_URL"
  else
    installer_url="https://raw.githubusercontent.com/NousResearch/hermes-agent/${HERMES_PINNED_COMMIT}/scripts/install.sh"
    installer_sha256="${installer_sha256:-$HERMES_PINNED_SHA256}"
    installer_args+=(--commit "$HERMES_PINNED_COMMIT")
  fi
  info "Installing Hermes Agent from ${installer_url}…"
  # A custom HERMES_INSTALL_URL has no built-in digest: fail closed unless the
  # caller pins HERMES_INSTALL_SHA256 or opts out explicitly.
  if [[ -z "$installer_sha256" && "${HERMES_ALLOW_UNVERIFIED_INSTALL:-}" != "1" ]]; then
    error "HERMES_INSTALL_SHA256 is not set, so refusing to run the Hermes installer
unverified. Download and review ${installer_url} yourself, then set
HERMES_INSTALL_SHA256=<sha256> to pin it (or HERMES_ALLOW_UNVERIFIED_INSTALL=1
to accept the risk and proceed without pinning)."
  fi
  fetch_and_verify "$installer_url" "$installer_tmp" "Hermes installer" "$installer_sha256"
  assert_shell_script "$installer_tmp" "Hermes installer"
  # Hermes's own installer bootstraps a standalone Python build via plain
  # urllib (unlike uv's own downloader moments earlier in the same install,
  # which already trusts the system CA store fine) -- on a host with a
  # corporate TLS-inspecting proxy, Python's ssl module needs an explicit
  # nudge towards the system CA bundle rather than whatever it defaults to.
  # Only set if the caller hasn't already pointed Python at a bundle
  # themselves.
  local system_ca_bundle="/etc/ssl/certs/ca-certificates.crt"
  if [[ -z "${SSL_CERT_FILE:-}" && -r "$system_ca_bundle" ]]; then
    export SSL_CERT_FILE="$system_ca_bundle"
  fi
  # Observed in practice: Hermes's own downloads (ffmpeg/node/python/ripgrep/
  # uv, fetched independently of each other) intermittently hit a transient
  # TLS verification blip on a corporate-proxied network -- which *specific*
  # download hits it varies run to run, consistent with an occasional
  # network/proxy hiccup rather than a deterministic missing-CA problem.
  # Hermes's own installer is incremental (already-downloaded components are
  # skipped on a re-run), and its own error message suggests retrying -- so
  # retry the whole install a few times -- but only when the failure output
  # actually looks like a network/TLS problem; anything else (bad args,
  # missing deps, a real installer bug) fails immediately instead of being
  # masked behind retries.
  local hermes_attempt hermes_installed="" hermes_log
  local transient_re='SSL|TLS|certificate|timed out|timeout|Connection (reset|refused|aborted)|Temporary failure|Could not resolve|Name or service not known|curl: \([0-9]+\)|URLError'
  hermes_log="$(mktemp)"
  for hermes_attempt in 1 2 3; do
    : >"$hermes_log"
    # tee into hermes_log so the failure can be classified; spin still
    # shows/prints the output as before.
    if spin "Installing Hermes" bash -c \
      'bash "$1" "${@:3}" 2>&1 | tee "$2"; exit "${PIPESTATUS[0]}"' \
      _ "$installer_tmp" "$hermes_log" "${installer_args[@]}"; then
      hermes_installed=1
      break
    fi
    if ! grep -Eqi "$transient_re" "$hermes_log"; then
      rm -f "$hermes_log" "$installer_tmp"
      error "Hermes install failed with a non-network error (see output above); not retrying."
    fi
    [[ "$hermes_attempt" -lt 3 ]] || break
    warn "Hermes install failed (attempt ${hermes_attempt}/3) -- retrying after a
transient-looking network/TLS blip…"
    sleep 5
  done
  rm -f "$installer_tmp" "$hermes_log"
  [[ -n "$hermes_installed" ]] || error "Hermes install failed after 3 attempts (see output above)."
  export PATH="$HOME/.local/bin:$PATH"
}

# resolve_installed_agent — the agent to operate on when the caller didn't
# pin one explicitly via HARNESS_AGENT: whatever install_selected_agent last
# recorded as actually installed (~/.agent-harness-install/installed-agent),
# falling back to openclaw only if nothing was ever recorded. Without this,
# run_agent_onboard/print_status defaulted straight to "openclaw" whenever
# HARNESS_AGENT wasn't re-exported in the current shell -- silently
# onboarding/reporting the wrong agent after e.g. `--harness hermes` in an
# earlier session. Shared with uninstall.sh so all four read paths
# (install/onboard/status/uninstall) agree on the same installed agent.
resolve_installed_agent() {
  local installed_agent
  if [[ -n "${HARNESS_AGENT:-}" ]]; then
    canonical_agent_name "$HARNESS_AGENT"
    return
  fi
  installed_agent="$(cat "$(harness_state_root)/installed-agent" 2>/dev/null || true)"
  canonical_agent_name "${installed_agent:-openclaw}"
}

install_selected_agent() {
  local agent
  agent="$(canonical_agent_name "${HARNESS_AGENT:-openclaw}")"
  export HARNESS_AGENT="$agent"
  case "$agent" in
    openclaw) install_openclaw ;;
    deepagents-code) install_dcode ;;
    hermes) install_hermes ;;
    *) error "Unknown HARNESS_AGENT: $agent (expected openclaw, deepagents-code, or hermes)" ;;
  esac
  ensure_cli_shim "$(agent_cli_bin "$agent")" || true
  verify_agent_cli "$(agent_cli_bin "$agent")" \
    || error "$(agent_display_name "$agent") did not verify as runnable after install."
  atomic_write_file "$(ensure_state_dir)/installed-agent" "$agent"
  ok "$(agent_display_name "$agent") installed"
}

# remove_agent_package agent — undoes install_selected_agent's actual package
# install (not just the CLI shim, which uninstall.sh removes separately).
# Used by the uninstaller; each branch is best-effort so a missing tool
# (e.g. no npm) doesn't abort the rest of the uninstall.
remove_agent_package() {
  local agent
  agent="$(canonical_agent_name "$1")"
  case "$agent" in
    openclaw) remove_openclaw_package ;;
    deepagents-code) remove_dcode_package ;;
    hermes) remove_hermes_package ;;
    *) warn "No package-removal step known for agent '${agent}'; only its CLI shim (if any) was removed." ;;
  esac
}

remove_openclaw_package() {
  command_exists npm || return 0
  npm ls -g openclaw >/dev/null 2>&1 || return 0
  info "Removing OpenClaw (npm uninstall -g)…"
  if npm uninstall -g openclaw >/dev/null 2>&1; then
    ok "OpenClaw removed"
  else
    warn "Could not npm-uninstall openclaw; remove it manually if needed."
  fi
}

# safe_agent_data_dir PATH -- true only for an absolute, non-symlink path that
# is not "/", $HOME, or an ancestor of $HOME. Guards the rm -rf of an agent
# data directory against a mistyped or hostile DEEPAGENTS_HOME/HERMES_HOME.
safe_agent_data_dir() {
  local dir="${1%/}"
  [[ "$dir" == /* && -n "$dir" && ! -L "$dir" ]] || return 1
  [[ "$dir" != "${HOME%/}" ]] || return 1
  [[ "${HOME%/}/" != "${dir}/"* ]] || return 1
  return 0
}

remove_dcode_package() {
  if command_exists uv; then
    if uv tool uninstall deepagents-code >/dev/null 2>&1; then
      ok "dcode removed"
    else
      warn "Could not uv-uninstall deepagents-code; remove it manually if needed."
    fi
  else
    warn "uv not found on PATH; could not uninstall dcode automatically."
  fi
  if [[ -n "${KEEP_AGENT_DATA:-}" ]]; then
    info "Keeping dcode data directory (KEEP_AGENT_DATA=1)."
    return 0
  fi
  local dcode_home="${DEEPAGENTS_HOME:-$HOME/.deepagents}"
  if [[ -d "$dcode_home" ]] && ! safe_agent_data_dir "$dcode_home"; then
    warn "Refusing to delete '${dcode_home}' (not an absolute, non-symlink path distinct
from \$HOME and its parents) -- remove it manually if intended."
    return 0
  fi
  if [[ -d "$dcode_home" && ! -L "$dcode_home" ]]; then
    info "Removing dcode data directory (${dcode_home})…"
    rm -rf -- "$dcode_home"
    ok "Removed dcode data directory (${dcode_home})"
  fi
}

# Removes Hermes's own command links and, unless KEEP_AGENT_DATA=1, its
# entire data directory (config, sessions, memories, skills) — matching the
# default behavior of Hermes-based reference projects' own uninstallers,
# which also wipe this dir unless told to keep it.
remove_hermes_package() {
  local link_dir="${HARNESS_SHIM_DIR}" bin hermes_home
  for bin in hermes hermes-agent hermes-acp; do
    if [[ -f "${link_dir}/${bin}" && ! -L "${link_dir}/${bin}" ]]; then
      rm -f -- "${link_dir}/${bin}"
    fi
  done
  if [[ -n "${KEEP_AGENT_DATA:-}" ]]; then
    info "Keeping Hermes data directory (KEEP_AGENT_DATA=1)."
    return 0
  fi
  hermes_home="${HERMES_HOME:-$HOME/.hermes}"
  if [[ -d "$hermes_home" ]] && ! safe_agent_data_dir "$hermes_home"; then
    warn "Refusing to delete '${hermes_home}' (not an absolute, non-symlink path distinct
from \$HOME and its parents) -- remove it manually if intended."
    return 0
  fi
  if [[ -d "$hermes_home" && ! -L "$hermes_home" ]]; then
    info "Removing Hermes data directory (${hermes_home})…"
    rm -rf -- "$hermes_home"
    ok "Removed Hermes data directory (${hermes_home})"
  fi
}

# Hermes runs directly on the host (not in a Docker sandbox), so "installing
# a skill" is just placing a SKILL.md directory under its native skills root
# — Hermes owns discovery/loading from there, same bring-your-own stance as
# HARNESS_MCP_REGISTER_CMD. Not implemented for openclaw/deepagents-code:
# their own plugin/skill mechanisms differ and aren't reproduced here.
hermes_skills_dir() {
  printf '%s/skills' "${HERMES_HOME:-$HOME/.hermes}"
}

# Rejects path-traversal/empty/current-dir names before any skills_dir touch.
validate_skill_name() {
  local name="$1"
  [[ -n "$name" && "$name" != "." && "$name" != *"/"* && "$name" != *".."* ]]
}

hermes_skill_install() {
  local local_path="$1" skills_dir skill_name dest
  [[ -n "$local_path" ]] || error "Usage: ./install.sh skill install <path>"
  [[ -d "$local_path" ]] || error "Skill path must be a directory containing SKILL.md
(got: ${local_path}) — Hermes discovers skills by directory, not a bare file."
  command_exists hermes || warn "Hermes CLI not found on PATH — installing a skill for
an agent that isn't installed yet."
  skill_name="$(basename "$local_path")"
  validate_skill_name "$skill_name" || error "Invalid skill name derived from '${local_path}'
(basename: '${skill_name}'). Pass a path that doesn't end in '.', '..', or '/'."
  skills_dir="$(hermes_skills_dir)"
  mkdir -p "$skills_dir" || error "Could not create ${skills_dir}."
  dest="${skills_dir}/${skill_name}"
  [[ -e "$dest" ]] && error "A skill named '${skill_name}' already exists at ${dest}; remove it first."
  cp -R "$local_path" "$dest" || error "Could not copy '${local_path}' to ${dest}."
  ok "Installed Hermes skill '${skill_name}' (${dest})"
  info "Hermes discovers skills natively — check 'hermes skills list', or restart
Hermes if it doesn't appear."
}

hermes_skill_list() {
  local skills_dir entry found=0
  skills_dir="$(hermes_skills_dir)"
  [[ -d "$skills_dir" ]] || { info "No Hermes skills installed yet (${skills_dir})."; return 0; }
  for entry in "$skills_dir"/*/; do
    [[ -d "$entry" ]] || continue
    found=1
    printf '  %s\n' "$(basename "$entry")"
  done
  [[ "$found" -eq 1 ]] || info "No Hermes skills installed yet (${skills_dir})."
}

hermes_skill_remove() {
  local name="$1" dest
  [[ -n "$name" ]] || error "Usage: ./install.sh skill remove <name>"
  validate_skill_name "$name" || error "Invalid skill name: ${name}"
  dest="$(hermes_skills_dir)/${name}"
  [[ -e "$dest" ]] || error "No skill named '${name}' at ${dest}."
  rm -rf -- "$dest"
  ok "Removed Hermes skill '${name}'"
}

# resolve_onboarding_model_hint -- the model name onboarding wires an agent to
# (before the HARNESS_LLM_MODEL override). With an external router the name
# belongs to that endpoint, so it is used exactly as given (minus any
# leading "org/"): sanitising it would break names such as "name:tag".
# With OVMS, HARNESS_HF_MODEL counts only if OVMS actually serves it under
# its on-disk name (model_dir_name); otherwise fall back to the one model
# OVMS has registered, else "default".
resolve_onboarding_model_hint() {
  local hint=""
  if [[ -n "${HARNESS_HF_MODEL:-}" ]]; then
    if [[ -n "${HARNESS_LLM_ROUTER_ENDPOINT:-}" ]]; then
      hint="${HARNESS_HF_MODEL##*/}"
    elif ovms_model_registered "$(model_dir_name "$HARNESS_HF_MODEL")"; then
      hint="$(model_dir_name "$HARNESS_HF_MODEL")"
    fi
  fi
  [[ -n "$hint" ]] || hint="$(ovms_sole_registered_model_name 2>/dev/null || true)"
  [[ -n "$hint" ]] || hint="default"
  printf '%s' "$hint"
}

# run_agent_onboard — wires the installed agent to HARNESS_LLM_ENDPOINT and
# verifies it runs.
run_agent_onboard() {
  local agent endpoint cli_bin model_hint
  agent="$(resolve_installed_agent)"
  endpoint="${HARNESS_LLM_ENDPOINT:-$(harness_llm_endpoint)}"
  cli_bin="$(agent_cli_bin "$agent")" \
    || error "Unknown agent: '${agent}' (expected openclaw, deepagents-code, or hermes).
Check HARNESS_AGENT, or re-install with --harness <name>."

  # Resolved once, shared by both the openclaw and dcode branches below.
  # Precedence: an explicit --model/HARNESS_HF_MODEL always wins; then,
  # if nothing was given (e.g. a standalone "./install.sh onboard" run after
  # an earlier --model install), fall back to whatever single model is
  # already registered with OVMS rather than the literal string "default"
  # (which never matches a real registered model name and always 404s);
  # HARNESS_LLM_MODEL overrides all of the above when set explicitly.
  # HARNESS_HF_MODEL is only used as the model name when OVMS actually
  # serves it (a download that wasn't registered -- see
  # export_model_via_model_download in openvino.sh -- is not a real model
  # name and must not be guessed as one), or when routing to an external
  # endpoint, where the caller names the model. Must stay in sync with
  # ensure_inference_backend's ir_model_name.
  model_hint="$(resolve_onboarding_model_hint)"
  model_hint="${HARNESS_LLM_MODEL:-$model_hint}"

  case "$agent" in
    openclaw)
      command_exists "$cli_bin" || error "openclaw CLI not found after install."
      if configure_openclaw_provider "$endpoint" "$model_hint"; then
        info "Smoke-testing OpenClaw against ${endpoint} (model: ovms/${model_hint})…"
        # The CLI can exit 0 with no output when the upstream call fails
        # after the HTTP 200 (e.g. a streaming error), so require output too.
        local openclaw_out=""
        if openclaw_out="$("$cli_bin" infer model run --prompt "Say hello." --model "ovms/${model_hint}" --json 2>/dev/null)" \
          && [[ -n "${openclaw_out//[[:space:]]/}" ]]; then
          ok "OpenClaw smoke test passed"
        else
          warn "Smoke test failed — check that the model server at ${endpoint} is reachable and that
'${model_hint}' matches a model name registered with it."
        fi
      else
        warn "Could not configure OpenClaw's 'ovms' provider automatically. Configure it
manually instead: openclaw config set models.providers.ovms '{\"baseUrl\":\"${endpoint}\",
\"api\":\"openai-completions\",\"models\":[{\"id\":\"${model_hint}\", ...}]}' --strict-json --merge
(see github.com/openclaw/openclaw docs/gateway/config-tools/custom-providers.md)."
      fi
      ;;
    deepagents-code)
      command_exists "$cli_bin" || error "dcode not found after install."
      configure_dcode_provider "$endpoint" "$model_hint" || {
        info "Skipping the dcode smoke test: its config.toml was not updated (see the warning above)."
        return 0
      }
      info "Smoke-testing dcode against ${endpoint} (model: ${model_hint})…"
      # dcode starts its own local LangGraph dev server as part of this
      # invocation and health-checks it over plain HTTP before running the
      # prompt. Behind a corporate proxy (HTTP_PROXY/HTTPS_PROXY set),
      # that purely-local health check gets routed through the proxy
      # instead of hitting the server directly; the proxy then rejects it
      # (403), and dcode times out after 60s waiting for a health check
      # that was never going to succeed. Neither that health check nor the
      # actual OVMS call dcode makes afterward (http://127.0.0.1:...) ever
      # needs external network access, so stripping the proxy vars just
      # for this one invocation is safe and fixes the smoke test outright
      # instead of always failing behind a proxy -- confirmed empirically
      # (reproduced the 403/60s-timeout with proxy vars set, confirmed
      # clean success within ~1-2s with them unset).
      # dcode exits 0 even when its model call fails (it just prints "[ERROR]"
      # and reports 0 requests), so the exit status alone can't be trusted.
      local dcode_log dcode_ok=1
      dcode_log="$(mktemp)"
      HARNESS_DCODE_API_KEY="${HARNESS_DCODE_API_KEY:-not-needed}" DEEPAGENTS_CODE_NO_UPDATE_CHECK=1 \
        env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy -u ALL_PROXY -u all_proxy \
        "$cli_bin" -n "Say hello." --model "openai:${model_hint}" 2>&1 | tee "$dcode_log" || dcode_ok=""
      grep -q '^\[ERROR\]' "$dcode_log" && dcode_ok=""
      rm -f "$dcode_log"
      [[ -n "$dcode_ok" ]] \
        || warn "Smoke test failed — check that the model server at ${endpoint} is reachable and that
'${model_hint}' matches a model name registered with it."
      info "To run dcode yourself, export HARNESS_DCODE_API_KEY=not-needed first (any non-empty value).
Behind a proxy, also run it as: env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY dcode …"
      ;;
    hermes)
      command_exists "$cli_bin" || warn "'${cli_bin}' was not found on PATH after install."
      info "Hermes is installed. Its own config lives at $(hermes_config_path).
Point it at ${endpoint} with:
  hermes config set model.provider custom
  hermes config set model.base_url ${endpoint}
  hermes config set model.default ${model_hint}
or choose 'Custom endpoint' in 'hermes model'. See github.com/NousResearch/hermes-agent for details."
      ;;
    *) error "Unknown agent: $agent (expected openclaw, deepagents-code, or hermes)" ;;
  esac
}
