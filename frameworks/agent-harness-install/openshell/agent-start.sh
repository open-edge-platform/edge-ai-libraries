#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
umask 077
: "${HARNESS_SANDBOX_ENDPOINT:?Missing inference endpoint}"
: "${HARNESS_SANDBOX_MODEL:?Missing inference model}"

case "${HARNESS_AGENT:?Missing agent}" in
  openclaw)
    mkdir -p "$HOME/.openclaw"
    # Preserve the gateway token and user configuration when the sandbox process restarts.
    if [[ ! -f "$HOME/.openclaw/openclaw.json" ]]; then
      node <<'JS'
const fs = require("node:fs");
const crypto = require("node:crypto");
const id = process.env.HARNESS_SANDBOX_MODEL;
const config = {
  models: {providers: {ovms: {
    baseUrl: process.env.HARNESS_SANDBOX_ENDPOINT, api: "openai-completions", apiKey: "not-needed",
    models: [{id, name: id, reasoning: false, input: ["text"], contextWindow: 32768, maxTokens: 4096}]
  }}},
  agents: {defaults: {model: {primary: `ovms/${id}`}, workspace: "/sandbox"}},
  gateway: {mode: "local", bind: "loopback", auth: {mode: "token", token: crypto.randomBytes(32).toString("hex")}}
};
fs.writeFileSync(`${process.env.HOME}/.openclaw/openclaw.json`, JSON.stringify(config), {mode: 0o600, flag: "wx"});
JS
    fi
    exec openclaw gateway run
    ;;
  hermes)
    # OpenShell sets HOME independently; Hermes must still find its image-installed environment.
    export HERMES_HOME=/home/node/.hermes
    /home/node/.local/bin/hermes config set model.provider custom
    /home/node/.local/bin/hermes config set model.base_url "$HARNESS_SANDBOX_ENDPOINT"
    /home/node/.local/bin/hermes config set model.default "$HARNESS_SANDBOX_MODEL"
    # Hermes is launched interactively by the connect command; no messaging service is enabled.
    exec sleep infinity
    ;;
  *) printf 'Unsupported sandbox agent: %s\n' "$HARNESS_AGENT" >&2; exit 1 ;;
esac
