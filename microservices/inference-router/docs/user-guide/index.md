# Inference Router Microservice

<!--hide_directive
<div class="component_card_widget">
  <a class="icon_github" href="https://github.com/open-edge-platform/edge-ai-libraries/tree/release-2026.2.0/microservices/inference-router">
     GitHub
  </a>
</div>
hide_directive-->

Routes OpenAI-compatible chat completion requests to one or more inference
backends through a single endpoint. Useful when an application needs to mix
local and cloud models, or pick a backend dynamically based on a routing
policy.

## Overview

The Inference Router is a pluggable FastAPI service backed by
[LiteLLM](https://docs.litellm.ai/) tool. It exposes an OpenAI-compatible
`/v1/chat/completions` endpoint and forwards each request to a configured
model-serving backend or provider, including self-hosted vLLM and
OpenVINO™, OpenAI, Anthropic, MiniMax, Ollama, and any other backend or
provider that LiteLLM tool supports.

Key Features:

- OpenAI-Compatible API:
  
  This endpoint substitutes the OpenAI `/v1/chat/completions` endpoint,
  and supports both streaming and non-streaming responses. It forwards
  standard request parameters, including `temperature`, `max_tokens`,
  `tools`, and `response_format`, to the selected backend.

- Multi-Provider Routing:

  Define multiple providers in `config.yaml` and pin a backend by model ID,
  by provider name, or let the router pick automatically by setting
  `model: "auto"`. Routing strategies and policies live in `src/rsd` and
  are pluggable.
  
- Pluggable Hooks:

  Pre-routing, post-routing, and post-response plugin hooks allow custom
  logic such as request rewriting, header injection, or response filtering.

- Per-Provider Telemetry:

  Built-in metrics for request count, token usage, end-to-end latency,
  time-to-first-token (TTFT), and time-per-output-token (TPOT). These
  metrics are bucketed by the `(model, provider)` pair and exposed at the
  `/v1/metrics` endpoint.

**Programming Language:** Python

## How It Works

1. Request Ingress:
   
   A client sends an OpenAI-format chat completion request to the router's
   /v1/chat/completions endpoint. The router uses the `model` value to
   route to a specific backend or configured provider target. If `model`
   is "auto", the router triggers smart routing.

2. Routing Decision:

   The router orchestrator applies the configured routing strategy and
   policy to choose a provider, then dispatches the request through the
   matching `ProviderAdapter` layer.

3. Backend Inference:

   LiteLLM tool forwards the request to the selected backend, e.g. vLLM and
   OpenAI, and returns the response streamed as Server-Sent Events (SSE) or
   buffered as JSON.

4. Telemetry:

   Every request, token, and latency measurement is recorded per the
   `(model, provider)` bucket and is observable through the `/v1/metrics`
   endpoint.

## Workflow

1. Configure one or more providers in `workspace/config.yaml` with their
   endpoint, credentials, and routing metadata.
2. The client sends an OpenAI-compatible request; the router picks a
   provider based on the requested model or the active routing policy.
3. The selected backend serves the inference; the router streams or returns
   the response and updates the per-provider telemetry.

## Learn More

- Begin with the [Quick Start Guide](./get-started.md).
- Read the [Plugins guide](./plugin.md) for the plugin system and built-in plugins.
- See the [API Reference](./api-reference.md) for endpoint details.

<!--hide_directive
:::{toctree}
:hidden:

./get-started.md
./policy-based-router.md
./plugin.md
./api-reference.md
Release Notes <./release-notes.md>

:::
hide_directive-->
