---
name: agent-harness-install
description: >
  Install, check, re-onboard and uninstall an AI agent harness (OpenClaw, Deep
  Agents Code `dcode`, or Hermes) on an Intel Linux host, wired to a local
  OpenAI-compatible endpoint served by OpenVINO Model Server behind the Intel
  Inference Router. USE FOR: running the install.sh script, picking a --model and
  --model-hub, pointing the router at an external endpoint (Ollama, vLLM),
  Intel Core Ultra iGPU or Arc setups, registering an MCP endpoint, checking
  status, uninstalling, fixing install failures behind a proxy. DO NOT USE FOR:
  Windows or macOS hosts, installing Intel GPU drivers or the compute runtime
  (the installer only detects them), tuning model quality, or general questions
  about OpenClaw, dcode or Hermes themselves.
license: Apache-2.0
compatibility: Linux with bash, sudo or root for Docker setup, and network access to Docker Hub and the model hub. Intel GPU optional (CPU-only fallback).
metadata:
  author: open-edge-platform
  tags: "agents openvino inference-router installer intel-gpu"
---

# Agent Harness Install

`./install.sh` prepares an Intel Linux host, starts an inference backend, installs one agent, and wires the agent to the backend. The agent only ever talks to the Inference Router (default `http://127.0.0.1:8010/v1`), never directly to the model server.

## When to Use

- The user wants an agent (OpenClaw, `dcode`, Hermes) running against a local model on Intel hardware.
- The user wants to reuse an existing OpenAI-compatible server (Ollama, vLLM, an internal gateway) behind the Router.
- The user needs to check health, re-run onboarding, list or remove models, register an MCP endpoint, or uninstall.

Do not use this skill to install Intel GPU drivers or the compute runtime (it only detects them), or to configure the agents beyond the endpoint wiring. Questions about writing tools, skills or prompts for an agent are out of scope. Do not answer them with installer commands, including `mcp register`. It covers the default `--runtime host`. For the OpenShell sandbox runtime, point the user to the [Agent Sandboxing guide](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/frameworks/agent-harness-install/docs/agentic-ai-security/agent-sandboxing.md).

## Instructions

### 1. Gather the inputs

Ask for anything missing before running the installer:

1. **Agent**: `openclaw` (default), `deepagents-code`, or `hermes`.
2. **Model name** (required). There is no default, and the installer fails without one in a non-interactive run. A Hugging Face id such as `Qwen/Qwen2.5-0.5B-Instruct` works with the default hub. For an external endpoint, ask for the exact id that endpoint serves, including any `org/` prefix.
3. **Backend**: the local OVMS (default) or an external endpoint via `HARNESS_LLM_ROUTER_ENDPOINT`.
4. **Exposure**: ports bind to `127.0.0.1` unless the user sets `HARNESS_ADVERTISED_HOST` or `HARNESS_BIND_HOST`. Neither service authenticates requests, so warn before widening access.

### 2. Run the installer

From a source checkout:

```bash
./install.sh --harness <openclaw|deepagents-code|hermes> --model <org/name>
```

For automation, add `--non-interactive`, or set `HARNESS_AGENT` and `HARNESS_HF_MODEL` and run `./install.sh --non-interactive`.

For an external endpoint, the Router is the only component that sees it, and OVMS is not started:

```bash
export HARNESS_LLM_ROUTER_ENDPOINT=http://<host>:<port>/v1
export HARNESS_LLM_ROUTER_API_KEY=<token>   # only if the endpoint needs one
export HARNESS_LLM_MODEL=<exact-id-the-endpoint-serves>
./install.sh --harness openclaw
```

Do not pass `--model` here. It strips an `org/` prefix and clears `HARNESS_LLM_MODEL`, so `meta-llama/Llama-3.2-3B-Instruct` would be sent to the endpoint as `Llama-3.2-3B-Instruct`.

`install.sh` runs `startup.sh` first (curl/git, Docker, Node.js via nvm, Python venv). Both are idempotent, so re-running after a failure is safe. If `startup.sh` exits with code `2`, the user was just added to the `docker` group: open a new terminal or run `newgrp docker`, then re-run.

Without a checkout, `install.sh` needs `HARNESS_INSTALL_REPO` and a pinned `HARNESS_INSTALL_REF` (a tag or commit). It refuses to guess either one, so ask the user for them. Pass installer flags after `bash -s --`.

### 3. Choose the model source

`--model-hub` selects where `--model` is fetched from. When the user names a hub and a model, give them that exact command first (for example `./install.sh --harness deepagents-code --model-hub ollama --model qwen2.5:7b`), then say whether the model will be served. The default `openvino` hub converts a Hugging Face id to OpenVINO IR and is the only common path that produces a model agents can use. Hubs other than `openvino` use the Model Download container automatically.

A model is served to agents only when the download contains an OVMS `graph.pbtxt`. The `openvino` hub always does; a pre-converted `huggingface` repo or a `remote-url` tarball may. Ollama, Ultralytics, Geti, the zoos and HLS are downloaded and tracked but never served, so tell the user plainly when they pick one. Only one model is served at a time.

Gated Hugging Face models need `HF_TOKEN` exported before the run.

See the [model sources table](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/frameworks/agent-harness-install/docs/user-guide/get-started.md#model-sources) for per-hub inputs.

### 4. Verify

```bash
./install.sh status
```

`status` is read-only. It reports host, OVMS, Router and agent health, and shows an external upstream as "routed externally" because the installer never health-checks it.

### 5. Maintain and remove

```bash
./install.sh onboard                               # re-run onboarding only
./install.sh models list                           # shows "not served by OVMS" entries
./install.sh models remove <name>
./install.sh mcp register <name> <url> <agent>     # Hermes and OpenClaw built in; others need HARNESS_MCP_REGISTER_CMD
./install.sh skill <install|list|remove> [path|name]   # Hermes skills only
./uninstall.sh --yes --harness <agent> [--keep-models] [--keep-agent-data]
```

Always pass the agent to `mcp register`. Without it the command uses `HARNESS_AGENT` and falls back to Hermes, not the agent that was installed, so it can edit the wrong agent's configuration.

Uninstall deletes the downloaded models unless `--keep-models` is passed. For Hermes and `dcode` it also deletes the agent's data directory (`~/.hermes`, or `~/.deepagents` with config and sessions) unless `--keep-agent-data` is passed. `--yes` skips the confirmation, so ask whether the user wants the models and the agent data kept before running it. It leaves Docker, Node.js/nvm, the Intel compute runtime, the pulled images, the shell-profile PATH block and OpenClaw's `~/.openclaw` in place. Tell the user so they can remove those if wanted.

## Agent-specific behavior

| Agent | Installed via | Onboarding result |
|---|---|---|
| `openclaw` | `npm install -g openclaw` | Registers a custom `ovms` provider, sets it as the default model, runs a smoke test |
| `deepagents-code` | Pinned upstream `dcode` installer | Writes a managed `[models.providers.openai]` block in `~/.deepagents/config.toml` and runs a smoke test |
| `hermes` | Pinned upstream installer | Prints the endpoint only. The user points a provider at it in `~/.hermes/config.yaml`; no smoke test |

Third-party installers are fetched over HTTPS and checked against a built-in SHA-256, so no flags are needed. Override URLs only with a matching digest. Avoid the `*_ALLOW_UNVERIFIED_*` opt-outs unless the user explicitly accepts the risk.

## Common Issues

| Symptom | Cause and fix |
|---|---|
| `No model selected` error | No `--model` in a non-interactive run. Pass `--model` or set `HARNESS_HF_MODEL`. |
| Image pulls fail behind a proxy | Export `HTTP_PROXY`, `HTTPS_PROXY` and `NO_PROXY`. `startup.sh` writes them into the Docker daemon's systemd drop-in, which needs sudo. |
| Syntax errors such as `unexpected token` on a Linux host | CRLF line endings from a Windows checkout. Convert the scripts to LF (`sed -i 's/\r$//'`) or re-clone with `core.autocrlf=input`. |
| OpenClaw `config set` refuses to write on re-onboard | Its Gateway daemon is running. Stop it, or run the manual command the installer prints. |
| `dcode` fails with `MissingCredentialsError` | Run `export HARNESS_DCODE_API_KEY=not-needed`. Only the installer's smoke test sets it. |
| `dcode` health check returns `403` behind a proxy | Run it with the proxy variables unset: `env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY dcode ...`. |
| Model downloaded but agents cannot use it | The hub does not produce a `graph.pbtxt`. Use the default `openvino` hub or a pre-converted OVMS repo. |
| `Unknown model` from the Router, often with HTTP 200 on streamed requests | The served name drops the Hugging Face organisation, so `org/name` is served as `name`. Configure the client with the name `curl http://127.0.0.1:8010/v1/models` returns. |
| No GPU detected | The installer continues CPU-only. It does not install drivers, so provision the Intel compute runtime separately (for example with Edge Pack). Use `--skip-gpu-check` to silence the check. |
| Reachable from other machines unexpectedly | `HARNESS_ADVERTISED_HOST` or `HARNESS_BIND_HOST` is set. Docker-published ports bypass `ufw`, so restrict them through the `DOCKER-USER` iptables chain. |

## References

- [Get Started](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/frameworks/agent-harness-install/docs/user-guide/get-started.md): full option list, model hubs, command reference.
- [Running Without a Checkout](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/frameworks/agent-harness-install/docs/user-guide/running-without-a-checkout.md): the standalone bootstrap path.
- [Known Limitations](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/frameworks/agent-harness-install/docs/user-guide/known-limitations.md): exporters, pinned installers, proxy caveats.
- [Uninstall](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/frameworks/agent-harness-install/docs/user-guide/uninstall.md): what is and is not removed.
- Run `./install.sh --help` for every flag and `HARNESS_*` variable.
