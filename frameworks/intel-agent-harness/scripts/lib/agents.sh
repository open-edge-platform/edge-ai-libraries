# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# shellcheck shell=bash
# Real agent catalog — installs actual open-source agent projects, verified
# against their public npm registry entries. HARNESS_AGENT selects one.
#
# Verified real, public, MIT-licensed packages:
#   openclaw        -> npm package "openclaw" (github.com/openclaw/openclaw)
#   deepagents-code -> npm package "deepagents" (github.com/langchain-ai/deepagentsjs),
#                      a LangGraph library with no CLI bin — this installer
#                      scaffolds a thin runner around it.
#   hermes          -> Nous Research's Hermes Agent, installed via its own
#                      official shell installer (not npm) from
#                      hermes-agent.nousresearch.com/install.sh.

canonical_agent_name() {
  case "$(printf '%s' "${1:-openclaw}" | tr '[:upper:]' '[:lower:]')" in
    openclaw | open-claw) printf 'openclaw' ;;
    deepagents | deep-agents | deepagents-code | langgraph | langchain-deepagents) printf 'deepagents-code' ;;
    hermes) printf 'hermes' ;;
    *) printf '%s' "$1" ;;
  esac
}

agent_display_name() {
  case "$1" in
    openclaw) printf 'OpenClaw' ;;
    deepagents-code) printf 'LangGraph Deep Agents' ;;
    hermes) printf 'Hermes' ;;
    *) printf '%s' "$1" ;;
  esac
}

agent_cli_bin() {
  case "$1" in
    openclaw) printf 'openclaw' ;;
    deepagents-code) printf 'deepagents-runner' ;;
    hermes) printf 'hermes' ;;
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

# Reads the version already resolved into a project's node_modules, empty if
# not installed — used to avoid downgrading a newer install to the pin.
installed_project_dep_version() {
  local dir="$1" pkg="$2"
  [[ -f "${dir}/node_modules/${pkg}/package.json" ]] || return 1
  node -e '
    try {
      const data = require(process.argv[1]);
      if (data.version) process.stdout.write(data.version);
    } catch {}
  ' "${dir}/node_modules/${pkg}/package.json" 2>/dev/null
}

# deepagents is a library, not a CLI. Scaffold a minimal runner project that
# depends on it + langgraph, configured against HARNESS_LLM_ENDPOINT (the
# OpenVINO Model Server's OpenAI-compatible endpoint).
install_deepagents_runner() {
  local runner_dir="${HOME}/.local/share/deepagents-runner"
  local version="${DEEPAGENTS_VERSION:-1.14.0}" installed
  # Same set -e footgun as install_openclaw above: guard against the normal
  # not-installed-yet case (exit 1) killing the whole script silently.
  installed="$(installed_project_dep_version "$runner_dir" deepagents || true)"
  if [[ -n "$installed" ]] && version_gte "$installed" "$version"; then
    info "deepagents-runner already has deepagents@${installed} — not downgrading to ${version}."
    return 0
  fi
  mkdir -p "$runner_dir"
  cat >"${runner_dir}/package.json" <<EOF
{
  "name": "deepagents-runner",
  "private": true,
  "type": "module",
  "bin": { "deepagents-runner": "./index.mjs" },
  "dependencies": {
    "deepagents": "${version}",
    "@langchain/langgraph": "^1.4.18",
    "@langchain/openai": "^1.6.0"
  }
}
EOF
  cat >"${runner_dir}/index.mjs" <<'EOF'
#!/usr/bin/env node
// Minimal LangGraph Deep Agents runner wired to an OpenAI-compatible endpoint
// (e.g. OpenVINO Model Server on Intel GPU) via HARNESS_LLM_ENDPOINT.
import { createDeepAgent } from "deepagents";
import { ChatOpenAI } from "@langchain/openai";

// Handled before touching the model/endpoint: the installer's verify step
// calls --version/--help and must not depend on a live inference call.
const args = process.argv.slice(2);
if (args.includes("--version") || args.includes("-v")) {
  console.log("deepagents-runner v1.0.0");
  process.exit(0);
}
if (args.includes("--help") || args.includes("-h")) {
  console.log("Usage: deepagents-runner [prompt...]");
  console.log("Runs a LangGraph Deep Agents prompt against HARNESS_LLM_ENDPOINT.");
  process.exit(0);
}

const endpoint = process.env.HARNESS_LLM_ENDPOINT || "http://127.0.0.1:8000/v3";
const model = new ChatOpenAI({
  model: process.env.HARNESS_LLM_MODEL || "default",
  configuration: { baseURL: endpoint },
  apiKey: process.env.HARNESS_LLM_API_KEY || "unused",
});

const agent = createDeepAgent({ model });
const prompt = args.join(" ") || "Say hello and describe your tools.";
try {
  const result = await agent.invoke({ messages: [{ role: "user", content: prompt }] });
  console.log(JSON.stringify(result, null, 2));
} catch (err) {
  console.error(`deepagents-runner: request to ${endpoint} failed: ${err.message || err}`);
  process.exit(1);
}
EOF
  chmod +x "${runner_dir}/index.mjs"
  spin "Installing deepagents-runner dependencies" bash -c "cd \"$runner_dir\" && npm install"
  spin "Linking deepagents-runner CLI" bash -c "cd \"$runner_dir\" && npm link"
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

install_selected_agent() {
  local agent
  agent="$(canonical_agent_name "${HARNESS_AGENT:-openclaw}")"
  export HARNESS_AGENT="$agent"
  case "$agent" in
    openclaw) install_openclaw ;;
    deepagents-code) install_deepagents_runner ;;
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
    deepagents-code) remove_deepagents_runner_package ;;
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

remove_deepagents_runner_package() {
  local runner_dir="${HOME}/.local/share/deepagents-runner"
  if command_exists npm; then
    npm rm -g deepagents-runner >/dev/null 2>&1 || true
  fi
  if [[ -d "$runner_dir" && ! -L "$runner_dir" ]]; then
    info "Removing deepagents-runner scaffold (${runner_dir})…"
    rm -rf -- "$runner_dir"
    ok "deepagents-runner scaffold removed"
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
# verifies it runs. Configuration specifics for OpenClaw's own provider setup
# are intentionally not fabricated here — its exact CLI/config surface isn't
# something this installer has verified beyond its published package.json.
run_agent_onboard() {
  require_third_party_notice_acceptance
  local agent endpoint cli_bin
  agent="$(canonical_agent_name "${HARNESS_AGENT:-openclaw}")"
  endpoint="${HARNESS_LLM_ENDPOINT:-$(harness_llm_endpoint)}"
  cli_bin="$(agent_cli_bin "$agent")"

  case "$agent" in
    openclaw)
      command_exists "$cli_bin" || error "openclaw CLI not found after install."
      ok "OpenClaw is installed. Endpoint to configure: ${endpoint}"
      info "Run 'openclaw' interactively and add a custom OpenAI-compatible provider
pointed at ${endpoint} — see github.com/openclaw/openclaw for its exact
provider-setup steps; this installer does not assume flags it hasn't verified."
      ;;
    deepagents-code)
      command_exists "$cli_bin" || error "deepagents-runner not found after install."
      local model_hint=""
      [[ -n "${HARNESS_HF_MODEL:-}" ]] && model_hint="${HARNESS_HF_MODEL##*/}"
      info "Smoke-testing deepagents-runner against ${endpoint}…"
      HARNESS_LLM_ENDPOINT="$endpoint" HARNESS_LLM_MODEL="${HARNESS_LLM_MODEL:-$model_hint}" "$cli_bin" "Say hello." \
        || warn "Smoke test failed — check that the model server at ${endpoint} is reachable and that
HARNESS_LLM_MODEL matches a model name registered with it."
      ;;
    hermes)
      command_exists "$cli_bin" || warn "'${cli_bin}' was not found on PATH after install."
      info "Hermes is installed. Its own config lives at $(hermes_config_path)
(providers.<name>.base_url) — point a provider at ${endpoint}, or run 'hermes setup'
for the interactive wizard. See github.com/NousResearch/hermes-agent for details."
      ;;
  esac
}
