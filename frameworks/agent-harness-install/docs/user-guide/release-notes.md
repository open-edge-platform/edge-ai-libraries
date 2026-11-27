<!--
  Copyright (C) 2026 Intel Corporation
  SPDX-License-Identifier: Apache-2.0
-->

# Release Notes: Agent Harness Installer

## Version 2026.3.0

**December 2026**

This is the first release of Agent Harness Installer (AHI), the recommended
reference Agent runtime installer for autonomous agents on Intel hardware. It
introduces **one-command deployment of OpenClaw, Hermes, or Deep Agents Code**,
the **Inference Router** in front of local or external inference, **Agent
Sandboxing with OpenShell**, and **Observability** for the Router and the
installed harness.

**New**

- **Agent Harness Deployment**: installs one of three open-source Agentic
  frameworks, [OpenClaw](https://github.com/openclaw/openclaw),
  [Hermes](https://github.com/nousresearch/hermes-agent), or
  [Deep Agents Code](https://github.com/langchain-ai/deepagents), and applies
  the recommended default configuration to maximize performance and security.
  Hermes and Deep Agents Code are installed from pinned, checksum-verified
  installer scripts. `./startup.sh` sets up the prerequisites (Docker, Node.js,
  and Python), and runs automatically as the first step of `./install.sh`.
- **Inference Router**: every agent is wired to the Inference Router endpoint,
  never directly to a model server. By default, the Router sits in front of a
  local OpenVINO™ Model Server (OVMS) on Intel® Core™ Ultra iGPU and Intel®
  Arc™ GPUs. Set `HARNESS_LLM_ROUTER_ENDPOINT` to point it at any existing
  OpenAI-compatible endpoint instead. The Router integrates with KV
  Quantization and Token compression for KV-cache and prompt optimization.
- **Model Sources**: models are exported or downloaded from Hugging Face,
  Ollama, remote URLs, and the other Model Download hubs. `./install.sh models`
  lists and removes them.
- **Agent Sandboxing**: select `--runtime openshell` to deploy OpenClaw,
  Hermes, or Deep Agents Code in an OpenShell sandbox with restricted
  filesystem and network access. The installer supplies default sandbox
  policies and agent/provider configuration as a functional starting point,
  and defaults fresh managed deployments to `OpenVINO/Qwen3.5-9B-int8-ov`. Host
  mode remains the default runtime.
- **Observability**: `./install.sh observability enable|disable|show` manages
  telemetry for the Inference Router and the installed harness. The Router
  persists request counters and latencies, and Hermes and OpenClaw record
  per-turn traces into a local SQLite store, with optional export to a managed
  or external Jaeger. Harness telemetry is unavailable in OpenShell sandboxes.
- **MCP and Skills**: registers an MCP endpoint with the installed agent
  (`mcp register`), and ships an install skill that lets an agent drive the
  installation.
- **Run Without a Checkout**: a standalone `curl | bash` bootstrap, and an
  `uninstall.sh` that removes the Router, OVMS, the installed agent, and the
  state directory, keeping downloaded models on request (`--keep-models`).
- **Documentation**: overview, get started, how it works, agentic AI security,
  and known limitations pages.
