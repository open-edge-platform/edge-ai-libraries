# Release Notes: Inference Router

## Version 2026.2.0

**August, 2026**

**New**

- Policy-Based & Intelligent Routing:

  - Three-layer routing model — Rules, Strategies, and Policies — configurable
    in YAML (`src/rsd/strategy.yaml`, `src/rsd/policy.yaml`).
  - Built-in rules for model name, message content, tool calls, metadata,
    query-complexity score/zone, and context length.
  - Provider metadata (`labels`, `cost`, `performance`, `capability`) drives
    `provider_selector` matching, including zone-mapped selectors.
  - Built-in `Balanced` and `CostFirst` policies with `FirstMatch` / `AllMatch`
    criteria, plus a first-available-provider fallback.
  - `IntelligentRule`: a model-based classifier (vendored OpenVINO Qwen3.5)
    maps the last user message to an index and routes accordingly (e.g.
    `0 -> local`, `1 -> cloud`). Configure the model with `IR_OV_MODEL`.
  - See the [Routing Guide](./routing-guide.md) and
    [Policy Based Router Usage](./policy-based-router.md).

- Plugin System:

  - Pluggable `prerouting` / `postrouting` / `postresponse` hooks with
    auto-discovery of every module under `src/plugins/` — no central registry
    to edit. Plugins can also contribute their own HTTP routes under `/v1`.
  - Built-in `compressor` plugin: prompt compression (`tool`, `harness`, and
    `context` kinds) backed by the
    [adaptive-token-compressor](https://github.com/open-edge-platform/edge-ai-libraries/tree/main/libraries/adaptive-token-compressor)
    library to cut token usage, with per-instance and node-level metrics.
  - Built-in `provider_management` plugin: start/stop backends on demand via an
    external Local Provider Manager, updating the running config.
  - Built-in `dummy_logger` reference plugin.
  - See the [Plugins Guide](./plugin.md).

- Pass-through Services:

  - New OpenAI/Cohere-compatible endpoints that forward the request body
    verbatim to a backing service: `POST /v1/audio/transcriptions` (`transcription`),
    `POST /v1/audio/speech` (`tts`), `POST /v1/embeddings` (`embeddings`),
    `POST /v1/rerank` (`rerank`), and `POST /v1/ocr` (`ocr`).
  - Enabled and managed dynamically by adding a provider of the matching `type`.

- Runtime Management API:

  - Providers: `GET/POST/DELETE /v1/providers` and `/v1/providers/{name}`.
  - Plugins: list instances and node types, inspect, create/update, delete, and
    reset via `/v1/plugins` (see the [API Reference](./api-reference.md#list-plugins)).
  - Policies: `/v1/policies` CRUD.
  - Strategies: `/v1/strategies` CRUD.
  - Configuration & routing: `GET /v1/config`, `GET/PUT /v1/routing`.
  - Changes persist to the on-disk config and take effect immediately.

- Web UI Dashboard:

  - A Vue-based dashboard for managing providers and viewing overview, latency,
    and token telemetry, with light/dark themes and English/Chinese locales.
  - Build and run with Docker Compose from `ui/docker`.

- Intel GPU Support:

  - The Docker image ships with the Intel GPU runtime built in; the
    intelligent-routing classifier defaults to GPU. Override with `IR_DEVICE`
    (e.g. `IR_DEVICE=CPU`, `IR_DEVICE=GPU.1`).

- Observability:

  - Detailed health check and service info endpoints.
  - Token accounting integrated with telemetry; router processing time is
    excluded from TTFT statistics.


## Version 2026.1.0

**June 17, 2026**

**New**

- Initial release of the Inference Router microservice.

- OpenAI-Compatible API:

  - `/v1/chat/completions` with streaming (SSE) and non-streaming responses.
  - `/v1/models` endpoint listing every configured provider plus the virtual
    `"auto"` model for smart routing.

- Multi-Provider Routing:

  - LiteLLM-backed provider support for self-hosted vLLM/OpenVINO, OpenAI,
    Anthropic, MiniMax, Ollama, and any other LiteLLM-supported backend.
  - Pin a backend by model ID, by provider name, or use `"auto"` to let the
    router pick based on the configured policy.

- Telemetry:

  - `/v1/metrics` exposes per-`(model, provider)` request counts, token
    usage, end-to-end latency, TTFT, and TPOT.
  - `POST /v1/metrics/reset` clears accumulated counters.

- Configuration:

  - YAML-based configuration with environment variable expansion.
  - Concurrency limit and per-provider authentication settings.

*Validated configuration*:

- *Intel(R) Core(TM) Ultra X7 358H*
