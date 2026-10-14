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
  # value this installer can verify for an arbitrary --hf-model; these are
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
install_dcode() {
  local installer_url="https://langch.in/dcode"
  local installer_tmp
  installer_tmp="$(mktemp)"
  info "Installing Deep Agents Code (dcode) from ${installer_url}…"
  # LangChain does not publish a static checksum for this installer either.
  # Same fail-closed-by-default stance as Hermes/Docker: set
  # DCODE_INSTALL_SHA256 once you've reviewed a known-good copy, or
  # HARNESS_ALLOW_UNVERIFIED_DCODE_INSTALL=1 to accept the risk.
  if [[ -z "${DCODE_INSTALL_SHA256:-}" && "${HARNESS_ALLOW_UNVERIFIED_DCODE_INSTALL:-}" != "1" ]]; then
    error "DCODE_INSTALL_SHA256 is not set, so refusing to run dcode's installer
unverified. Download and review ${installer_url} yourself, then set
DCODE_INSTALL_SHA256=<sha256> to pin it (or HARNESS_ALLOW_UNVERIFIED_DCODE_INSTALL=1
to accept the risk and proceed without pinning)."
  fi
  fetch_and_verify "$installer_url" "$installer_tmp" "dcode installer" "${DCODE_INSTALL_SHA256:-}"
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
      /# BEGIN intel-agent-harness managed provider/ { skip=1 }
      /# END intel-agent-harness managed provider/ { skip=0; next }
      !skip
    ' "$config_file" >"$tmp"
  fi
  {
    cat "$tmp"
    cat <<EOF
# BEGIN intel-agent-harness managed provider -- do not edit between markers
[models]
default = "openai:${model_name_esc}"

[models.providers.openai]
base_url = "${endpoint_esc}"
api_key_env = "HARNESS_DCODE_API_KEY"
models = ["${model_name_esc}"]

[models.providers.openai.params]
use_responses_api = false
# END intel-agent-harness managed provider
EOF
  } >"${tmp}.new"
  mv -f "${tmp}.new" "$config_file"
  rm -f "$tmp"
}

install_hermes() {
  local installer_url="${HERMES_INSTALL_URL:-https://hermes-agent.nousresearch.com/install.sh}"
  local installer_tmp
  installer_tmp="$(mktemp)"
  info "Installing Hermes Agent from ${installer_url}…"
  # Nous Research does not publish a static checksum for this installer.
  # Refuse to run it unverified by default -- HTTPS + a shebang check alone
  # don't establish artifact integrity. Set HERMES_INSTALL_SHA256 once you've
  # reviewed a known-good copy, or HERMES_ALLOW_UNVERIFIED_INSTALL=1 to
  # accept the risk and proceed without pinning.
  if [[ -z "${HERMES_INSTALL_SHA256:-}" && "${HERMES_ALLOW_UNVERIFIED_INSTALL:-}" != "1" ]]; then
    error "HERMES_INSTALL_SHA256 is not set, so refusing to run the Hermes installer
unverified. Download and review ${installer_url} yourself, then set
HERMES_INSTALL_SHA256=<sha256> to pin it (or HERMES_ALLOW_UNVERIFIED_INSTALL=1
to accept the risk and proceed without pinning)."
  fi
  fetch_and_verify "$installer_url" "$installer_tmp" "Hermes installer" "${HERMES_INSTALL_SHA256:-}"
  assert_shell_script "$installer_tmp" "Hermes installer"
  spin "Installing Hermes" bash "$installer_tmp" --skip-setup --non-interactive
  rm -f "$installer_tmp"
  export PATH="$HOME/.local/bin:$PATH"
}

# resolve_installed_agent — the agent to operate on when the caller didn't
# pin one explicitly via HARNESS_AGENT: whatever install_selected_agent last
# recorded as actually installed (~/.intel-agent/installed-agent), falling
# back to openclaw only if nothing was ever recorded. Without this,
# run_agent_onboard/print_status defaulted straight to "openclaw" whenever
# HARNESS_AGENT wasn't re-exported in the current shell -- silently
# onboarding/reporting the wrong agent after e.g. `--agent hermes` in an
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

# run_agent_onboard — wires the installed agent to HARNESS_LLM_ENDPOINT and
# verifies it runs.
run_agent_onboard() {
  local agent endpoint cli_bin
  agent="$(resolve_installed_agent)"
  endpoint="${HARNESS_LLM_ENDPOINT:-$(harness_llm_endpoint)}"
  cli_bin="$(agent_cli_bin "$agent")" \
    || error "Unknown agent: '${agent}' (expected openclaw, deepagents-code, or hermes).
Check HARNESS_AGENT, or re-install with --agent <name>."

  case "$agent" in
    openclaw)
      command_exists "$cli_bin" || error "openclaw CLI not found after install."
      local model_hint="default"
      [[ -n "${HARNESS_HF_MODEL:-}" ]] && model_hint="${HARNESS_HF_MODEL##*/}"
      model_hint="${HARNESS_LLM_MODEL:-$model_hint}"
      if configure_openclaw_provider "$endpoint" "$model_hint"; then
        info "Smoke-testing OpenClaw against ${endpoint} (model: ovms/${model_hint})…"
        "$cli_bin" infer model run --prompt "Say hello." --model "ovms/${model_hint}" --json >/dev/null \
          || warn "Smoke test failed — check that the model server at ${endpoint} is reachable and that
'${model_hint}' matches a model name registered with it."
      else
        warn "Could not configure OpenClaw's 'ovms' provider automatically. Configure it
manually instead: openclaw config set models.providers.ovms '{\"baseUrl\":\"${endpoint}\",
\"api\":\"openai-completions\",\"models\":[{\"id\":\"${model_hint}\", ...}]}' --strict-json --merge
(see github.com/openclaw/openclaw docs/gateway/config-tools/custom-providers.md)."
      fi
      ;;
    deepagents-code)
      command_exists "$cli_bin" || error "dcode not found after install."
      local model_hint="default"
      [[ -n "${HARNESS_HF_MODEL:-}" ]] && model_hint="${HARNESS_HF_MODEL##*/}"
      model_hint="${HARNESS_LLM_MODEL:-$model_hint}"
      configure_dcode_provider "$endpoint" "$model_hint"
      info "Smoke-testing dcode against ${endpoint} (model: ${model_hint})…"
      HARNESS_DCODE_API_KEY="${HARNESS_DCODE_API_KEY:-not-needed}" DEEPAGENTS_CODE_NO_UPDATE_CHECK=1 \
        "$cli_bin" -n "Say hello." --model "openai:${model_hint}" \
        || warn "Smoke test failed — check that the model server at ${endpoint} is reachable and that
'${model_hint}' matches a model name registered with it."
      ;;
    hermes)
      command_exists "$cli_bin" || warn "'${cli_bin}' was not found on PATH after install."
      info "Hermes is installed. Its own config lives at $(hermes_config_path)
(providers.<name>.base_url) — point a provider at ${endpoint}, or run 'hermes setup'
for the interactive wizard. See github.com/NousResearch/hermes-agent for details."
      ;;
    *) error "Unknown agent: $agent (expected openclaw, deepagents-code, or hermes)" ;;
  esac
}
