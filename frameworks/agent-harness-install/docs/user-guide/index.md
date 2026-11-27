<!--hide_directive
```{eval-rst}
.. meta::
   :description: The Agent Harness Installer deploys the OpenClaw, Deep Agents Code, or Hermes agent harness on Intel hardware and wires it to a local OpenAI-compatible inference endpoint through the Inference Router.
   :keywords: Agent Harness Installer, OpenClaw, Deep Agents Code, Hermes, OpenVINO Model Server, Inference Router, OpenShell, agent sandboxing
```
hide_directive-->

# Agent Harness Installer

<!--hide_directive
<div class="component_card_widget">
  <a class="icon_github" href="https://github.com/open-edge-platform/edge-ai-libraries/tree/main/frameworks/agent-harness-install">
     GitHub
  </a>
  <a class="icon_document" href="https://github.com/open-edge-platform/edge-ai-libraries/blob/main/frameworks/agent-harness-install/README.md">
     Readme
  </a>
</div>
hide_directive-->

Agent Harness Installer (AHI) is the recommended reference Agent runtime
installer which sets up an optimized execution environment for autonomous
agents on Intel hardware. AHI installs the chosen Agent harness, sets up
the Routing capability, provides Observability options, and the configured
Security capabilities. AHI is used across all Agentic blueprint applications
in Open Edge Platform, with notable examples being
[Virtual Security Guard Agent](https://docs.openedgeplatform.intel.com/dev/edge-ai-suites/virtual-security-guard-agent/index.html)
in **Metro Suite**,
[QSR Store Agent](https://docs.openedgeplatform.intel.com/dev/edge-ai-suites/ai-suite-retail/qsr-store-agent/index.html)
in **Retail Suite**, and
[Factory Defects Inspector Agent](https://docs.openedgeplatform.intel.com/dev/edge-ai-suites/ai-suite-manufacturing/factory-defects-inspector-agent/index.html)
in **Manufacturing Suite**.

The following sections provide overview of the major features offered. In
addition to the listed features, AHI provides mechanisms to register MCP
tools backed with relevant Skills.

## Install the chosen Agent Harness

AHI offers ease-of-deployment by providing support to deploy one of the
following open-source Agentic frameworks:

| Agent Framework | Verified package |
| --- | --- |
| [`openclaw`](https://github.com/openclaw/openclaw) | npm `openclaw` |
| [`hermes`](https://github.com/nousresearch/hermes-agent) | Nous Research's official installer from its repo (pinned installer script from the repo, not npm) |
| [`deepagents-code`](https://github.com/langchain-ai/deepagents) | `dcode` (Deep Agents Code) in its repo |

The installation ensures the default configuration for the installed Agent
framework is the recommended configuration to maximize performance and
security.

## Inference Router

The inference backend is **configurable**, but every request goes through the
[**Inference Router** (IR)](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/inference-router/index.html).
The agents are wired to the router's endpoint, never directly to a model
server. By default the Router sits in front of a local **OpenVINO™ Model
Server** (OVMS) serving an OpenAI-compatible `/v3/chat/completions` endpoint
on Intel® Core™ Ultra iGPU and Intel® Arc™ (CRI) GPUs; the Router itself is
the published `intel/inference-router` image.

Setting `HARNESS_LLM_ROUTER_ENDPOINT` instead points the Router at any
existing OpenAI-compatible endpoint you already operate (e.g., Ollama, vLLM,
an internal gateway), with `HARNESS_LLM_ROUTER_API_KEY` as an optional bearer
token. OVMS is not started in that case, and this installer never starts,
stops, or health-checks that endpoint (`status` reports it as "routed
externally"). Host mode has no fresh-install default model: name it with
`--model` or the model environment variables. The installer can reuse a
previously exported model; otherwise it prompts on a terminal and fails
non-interactively without a selection.

The Inference Router provides integration with
[KV Quantization](https://github.com/open-edge-platform/edge-ai-libraries/tree/main/libraries/kv-quant-offload)
and
[Token compression](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/adaptive-token-compressor/index.html)
to offer KV-cache and Prompt optimization capabilities.

## Agentic AI Security

Explore [Agentic AI Security](./agentic-ai-security.md) for security
controls for agent deployments, starting with
[Agent Sandboxing using OpenShell](./agentic-ai-security/agent-sandboxing.md).

The `--runtime` option is **optional**. Interactive installation offers a choice
of `host` or `openshell`; pressing Enter selects `host`. Non-interactive
installation also defaults to host mode unless a runtime is explicitly selected
with `--runtime` or `HARNESS_RUNTIME`.

Select `--runtime openshell` to deploy OpenClaw, Hermes, or Deep Agents Code in
a sandbox. The installer supplies default sandbox policies and agent/provider
configuration as a functional starting point. Fresh managed OpenShell deployments
default to `OpenVINO/Qwen3.5-9B-int8-ov` when no explicit or reusable model
selection exists, with model-tuning defaults for OpenClaw and Hermes. These
sandbox defaults do not change host-mode model selection. See the
[sandbox setup and policy boundaries](./agentic-ai-security/agent-sandboxing.md#getting-started)
for prerequisites and limitations.

## Observability

`./install.sh observability enable|disable|show` manages telemetry for the
Inference Router and Hermes harness. `enable` takes the collection and storage
options (`--backend`, `--endpoint`, `--content`); `disable` can delete collected
data (`--clean`) or keep the managed Jaeger (`--keep-jaeger`); `show` prints a
CLI summary, with Jaeger providing the full trace view. The Router persists
request counters and latencies to a JSONL file and serves them on `/v1/metrics`.
Hermes records per-turn traces through the `hermes-otel` plugin in a local
SQLite store and optionally exports them to a managed or external Jaeger.
Harness telemetry is Hermes-only and unavailable in OpenShell sandboxes.
Settings are kept in `~/.agent-harness-install/metrics.json`, so Router config
regeneration preserves them. See [Observability](./get-started.md#observability)
for details.

## Documentation

- [Agent Harness Installer, Overview](./overview.md): a
  plain-language overview of what AHI does and why it matters, for
  non-technical readers.
- [Get Started](./get-started.md): install flow, usage, and
  [model sources](./get-started.md#model-sources) (Hugging Face,
  Ollama, remote URL, and the other Model Download hubs).
- [Run Without a Checkout](./get-started/run-without-a-checkout.md):
  the standalone `curl | bash` bootstrap path.
- [Uninstall](./get-started/uninstall.md) Agent Harness Installer.
- [Known Limitations](./known-limitations.md) in current version.
- [Release Notes](./release-notes.md).

<!--hide_directive
:::{toctree}
:hidden:

Overview (non-technical) <./overview.md>
./get-started.md
./how-it-works.md
./agentic-ai-security.md
./known-limitations.md
Release Notes <./release-notes.md>

:::
hide_directive-->
