#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
umask 077
if [[ "${HARNESS_AGENT:-}" == openclaw ]]; then
  # SQLite chooses its temp directory before the first Node process starts.
  export SQLITE_TMPDIR="$HOME/.openclaw/tmp/sqlite"
  mkdir -p "$SQLITE_TMPDIR"
  chmod 700 "$SQLITE_TMPDIR"
fi
if [[ -f "$HOME/.harness-model.json" ]]; then
  selection="$(node <<'JS'
    const fs = require("node:fs");
    const s = JSON.parse(fs.readFileSync(`${process.env.HOME}/.harness-model.json`, "utf8"));
    if (typeof s.model !== "string" || !s.model || /[\x00-\x1f]/.test(s.model) ||
        typeof s.endpoint !== "string" || /[\x00-\x1f]/.test(s.endpoint))
      throw Error("Invalid persisted sandbox model");
    console.log(s.model); console.log(s.endpoint);
JS
  )"
  mapfile -t fields <<<"$selection"
  export HARNESS_SANDBOX_MODEL="${fields[0]}"
  export HARNESS_SANDBOX_ENDPOINT="${fields[1]}"
fi
: "${HARNESS_SANDBOX_ENDPOINT:?Missing inference endpoint}"
: "${HARNESS_SANDBOX_MODEL:?Missing inference model}"

# OpenShell replaces the image PATH and omits npm's global executable directory.
export PATH="/home/node/.local/bin:$PATH"

configure_dcode_qwen_defaults() {
  [[ "$HARNESS_SANDBOX_MODEL" == "Qwen3.5-9B-int8-ov" ]] || return 0
  node - "$HOME/.deepagents/config.toml" <<'JS'
const fs = require("node:fs");
const file = process.argv[2];
const config = fs.readFileSync(file, "utf8");
const begin = "# BEGIN agent-harness-install managed provider -- do not edit between markers";
const end = "# END agent-harness-install managed provider";
const start = config.indexOf(begin);
const finish = config.indexOf(end, start + begin.length);
if (start < 0 || finish < 0 || config.indexOf(begin, start + begin.length) >= 0)
  throw Error("Missing or invalid installer-managed Deep Agents Code provider block");
const unmanagedConfig = config.slice(0, start) + config.slice(finish + end.length);
const userQwenParams = /^[ \t]*\[models\.providers\.openai\.params\.(?:"Qwen3\.5-9B-int8-ov"|'Qwen3\.5-9B-int8-ov')\][ \t]*(?:#.*)?$/m;
if (userQwenParams.test(unmanagedConfig))
  throw Error("config.toml already defines Qwen3.5-9B-int8-ov model-specific params outside the installer-managed block; leaving it untouched to avoid a duplicate TOML table");
const block = config.slice(start, finish);
const setting = "use_responses_api = false";
if (block.split(setting).length !== 2)
  throw Error("Missing or duplicate Deep Agents Code provider options");
const tuned = block.replace(setting, `${setting}\ntemperature = 0.2\nmax_tokens = 4096\n[models.providers.openai.params."Qwen3.5-9B-int8-ov"]\nextra_body = { chat_template_kwargs = { enable_thinking = false } }`);
fs.writeFileSync(file, config.slice(0, start) + tuned + config.slice(finish));
JS
}

configure_hermes_config() (
  local hermes_home="$1" staged_home state_dir
  mkdir -p "$hermes_home"
  staged_home="$(mktemp -d "${hermes_home}/.harness-config.XXXXXX")"
  state_dir="$(mktemp -d "${HOME}/.harness-config-state.XXXXXX")"
  trap 'rm -rf -- "$staged_home" "$state_dir"' EXIT
  if [[ -f "${hermes_home}/config.yaml" ]]; then
    cp -- "${hermes_home}/config.yaml" "${staged_home}/config.yaml"
  fi
  HERMES_HOME="$hermes_home" \
    HARNESS_HERMES_CONFIG_FILE="${staged_home}/config.yaml" \
    HARNESS_MODEL_CONFIG_STAGE_DIR="$state_dir" \
    node "${HARNESS_MODEL_CONFIG_SCRIPT:-/opt/harness/model-config.mjs}" \
    hermes "$HARNESS_SANDBOX_MODEL" "$HARNESS_SANDBOX_ENDPOINT" stage
  [[ -s "${staged_home}/config.yaml" ]] \
    || { printf 'Hermes configuration was not created.\n' >&2; return 1; }
  chmod 600 "${staged_home}/config.yaml"
  # Invalidate readiness first; publish config and defaults before marking it applied.
  mv -f -- "${state_dir}/.harness-model.pending.json" "$HOME/.harness-model.json"
  mv -f -- "${staged_home}/config.yaml" "${hermes_home}/config.yaml"
  mv -f -- "${state_dir}/.harness-local-defaults.json" "$HOME/.harness-local-defaults.json"
  mv -f -- "${state_dir}/.harness-model.json" "$HOME/.harness-model.json"
)
case "${HARNESS_AGENT:?Missing agent}" in
  openclaw)
    # Preserve the gateway token and user configuration when the sandbox process restarts.
    if [[ ! -f "$HOME/.openclaw/openclaw.json" ]]; then
      node <<'JS'
const fs = require("node:fs");
const crypto = require("node:crypto");
const id = process.env.HARNESS_SANDBOX_MODEL;
const config = {
  models: {providers: {ovms: {
    baseUrl: process.env.HARNESS_SANDBOX_ENDPOINT, api: "openai-completions", apiKey: "not-needed",
    models: [{id, name: id, reasoning: false, input: ["text"]}]
  }}},
  agents: {defaults: {model: {primary: `ovms/${id}`}, workspace: "/sandbox"}},
  gateway: {mode: "local", bind: "loopback", auth: {mode: "token", token: crypto.randomBytes(32).toString("hex")}}
};
fs.writeFileSync(`${process.env.HOME}/.openclaw/openclaw.json`, JSON.stringify(config), {mode: 0o600, flag: "wx"});
JS
    fi
    node "${HARNESS_MODEL_CONFIG_SCRIPT:-/opt/harness/model-config.mjs}" \
      openclaw "$HARNESS_SANDBOX_MODEL" "$HARNESS_SANDBOX_ENDPOINT"
    # The installer's first sandbox exec can hold OpenClaw's state lifecycle lock while the
    # gateway starts. Retry briefly on that race, then replace this shell with the final attempt.
    for _ in 1 2 3 4 5 6 7 8; do
      openclaw gateway run && exit 0
      sleep 3
    done
    exec openclaw gateway run
    ;;
  hermes)
    # OpenShell sets HOME independently; Hermes must still find its image-installed environment.
    export HERMES_HOME="${HERMES_HOME:-/home/node/.hermes}"
    configure_hermes_config "$HERMES_HOME"
    # Hermes is launched interactively by the connect command; no messaging service is enabled.
    exec sleep infinity
    ;;
  deepagents-code)
    agent_lib_dir="${HARNESS_AGENT_LIB_DIR:-/opt/harness/lib}"
    # Reuse the host installer’s provider writer so TOML escaping and user settings stay consistent.
    # Analyze the same repository libraries copied into the runtime image.
    # shellcheck source=../scripts/lib/colors.sh
    source "$agent_lib_dir/colors.sh"
    # shellcheck source=../scripts/lib/agents.sh
    source "$agent_lib_dir/agents.sh"
    configure_dcode_provider "$HARNESS_SANDBOX_ENDPOINT" "$HARNESS_SANDBOX_MODEL"
    configure_dcode_qwen_defaults
    node "${HARNESS_MODEL_CONFIG_SCRIPT:-/opt/harness/model-config.mjs}" \
      deepagents-code "$HARNESS_SANDBOX_MODEL" "$HARNESS_SANDBOX_ENDPOINT"
    exec sleep infinity
    ;;
  *) printf 'Unsupported sandbox agent: %s\n' "$HARNESS_AGENT" >&2; exit 1 ;;
esac
