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

An installer that deploys an agent harness onto Intel hardware and wires it
to a local, OpenAI-compatible inference endpoint.

The installer deploys one of three open-source agent projects, each
published independently:

| Agent | Verified package |
| --- | --- |
| `openclaw` | npm `openclaw` — github.com/openclaw/openclaw |
| `deepagents-code` | `dcode` (Deep Agents Code) — github.com/langchain-ai/deepagents |
| `hermes` | Nous Research's official installer — github.com/NousResearch/hermes-agent (pinned installer script from the repo, not npm) |

The inference backend is **configurable**, but every request goes through the
**Inference Router** (IR): agents are wired to the Router's endpoint, never
directly to a model server. By default the Router sits in front of a local
**OpenVINO Model Server** (OVMS) serving an OpenAI-compatible
`/v3/chat/completions` endpoint on Intel Core Ultra iGPU and Arc (CRI)
GPUs; the Router itself is the published `intel/inference-router` image.
Setting `HARNESS_LLM_ROUTER_ENDPOINT` instead points the Router at any
existing OpenAI-compatible endpoint you already operate (e.g., Ollama, vLLM,
an internal gateway), with `HARNESS_LLM_ROUTER_API_KEY` as an optional bearer
token. OVMS is not started in that case, and this installer never starts,
stops, or health-checks that endpoint (`status` reports it as "routed
externally"). Host mode has no fresh-install default model: name it with
`--model` or the model environment variables. The installer can reuse a
previously exported model; otherwise it prompts on a terminal and fails
non-interactively without a selection.

## Agentic AI Security

Explore [Agentic AI Security](./agentic-ai-security.md) for security
controls for agent deployments, starting with
[Agent Sandboxing using OpenShell](./agentic-ai-security/agent-sandboxing.md).

The `--runtime` option is **optional**. Interactive installation offers a choice
of `host` or `openshell`; pressing Enter selects `host`. Non-interactive
installation also defaults to host mode unless a runtime is explicitly selected
with `--runtime` or `HARNESS_RUNTIME`.

Select `--runtime openshell` to deploy OpenClaw, Hermes or Deep Agents Code in
a sandbox. The installer supplies default sandbox policies and agent/provider
configuration as a functional starting point. Fresh managed OpenShell deployments
default to `OpenVINO/Qwen3.5-9B-int8-ov` when no explicit or reusable model
selection exists, with model-tuning defaults for OpenClaw and Hermes. These
sandbox defaults do not change host-mode model selection. See the
[sandbox setup and policy boundaries](./agentic-ai-security/agent-sandboxing.md#getting-started)
for prerequisites and limitations.

## Documentation

- [Get Started](./get-started.md): install flow, usage and
  [model sources](./get-started.md#model-sources) (Hugging Face,
  Ollama, remote URL and the other Model Download hubs).
- [Run Without a Checkout](./get-started/run-without-a-checkout.md):
  the standalone `curl | bash` bootstrap path.
- [Uninstall](./get-started/uninstall.md).
- [Known Limitations](./known-limitations.md).

<!--hide_directive
:::{toctree}
:hidden:

./get-started.md
./how-it-works.md
./agentic-ai-security.md
./known-limitations.md

:::
hide_directive-->
