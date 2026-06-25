# Inference Router Microservice

<!--hide_directive
<div class="component_card_widget">
  <a class="icon_github" href="https://github.com/open-edge-platform/edge-ai-libraries/tree/release-2026.1.0/microservices/inference-router">
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
[LiteLLM](https://docs.litellm.ai/). It exposes an OpenAI-compatible
`/v1/chat/completions` endpoint and forwards each request to a configured
provider — self-hosted vLLM/OpenVINO, OpenAI, Anthropic, MiniMax, Ollama, and
any other backend LiteLLM supports.

Key Features:

- OpenAI-Compatible API:

  Drop-in replacement for OpenAI's `/v1/chat/completions` endpoint with both
  streaming and non-streaming responses. Standard parameters such as
  `temperature`, `max_tokens`, `tools`, and `response_format` pass through to
  the backend.

- Multi-Provider Routing:

  Define multiple providers in `config.yaml` and pin a backend by model ID,
  by provider name, or let the router pick automatically by setting
  `model: "auto"`. Routing strategies and policies live in `src/rsd` and are
  pluggable.

- Pluggable Hooks:

  Pre-routing, post-routing, and post-response plugin hooks allow custom
  logic such as request rewriting, header injection, or response filtering.

- Per-Provider Telemetry:

  Built-in metrics for request count, token usage, end-to-end latency, TTFT
  (time-to-first-token), and TPOT (time-per-output-token) — bucketed by
  `(model, provider)` pair and exposed at `/v1/metrics`.

**Programming Language:** Python

## How It Works

1. Request Ingress:

   A client sends an OpenAI-format chat completion request to the router's
   `/v1/chat/completions` endpoint. The `model` field selects a concrete
   backend, picks a provider by name, or triggers smart routing with
   `"auto"`.

2. Routing Decision:

   The router orchestrator applies the configured routing strategy and
   policy to choose a provider, then dispatches the request through the
   matching `ProviderAdapter`.

3. Backend Inference:

   LiteLLM forwards the request to the selected backend (vLLM, OpenAI,
   etc.) and returns the response — streamed as SSE or buffered as JSON.

4. Telemetry:

   Every request, token, and latency measurement is recorded per
   `(model, provider)` bucket and is observable through `/v1/metrics`.

## Workflow

1. Configure one or more providers in `workspace/config.yaml` with their
   endpoint, credentials, and routing metadata.
2. The client sends an OpenAI-compatible request; the router picks a
   provider based on the requested model or the active routing policy.
3. The selected backend serves the inference; the router streams or returns
   the response and updates per-provider telemetry.

## Learn More

- Begin with the [Quick Start Guide](./get-started.md).
- See the [API Reference](./api-reference.md) for endpoint details.
