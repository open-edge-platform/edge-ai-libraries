# Release Notes: Inference Router

## Version 2026.2.0

**August, 2026**

**New**

- Policy-Based and Intelligent Routing:

  - Three-layer routing model: Rules, Strategies, and Policies that are configurable
    in these YAML files: `src/rsd/strategy.yaml` and `src/rsd/policy.yaml`.
  - Built-in rules for model name, message content, tool calls, metadata,
    query-complexity score and zone, and context length.
  - Provider metadata (`labels`, `cost`, `performance`, and `capability`) drives
    the `provider_selector` matching, including zone-mapped selectors.
  - Built-in `Balanced` and `CostFirst` policies with `FirstMatch` or `AllMatch`
    criteria, plus a first-available-provider fallback.
  - `IntelligentRule`: a model-based classifier (bundled OpenVINO Qwen3.5)
    maps the last user message to an index and routes accordingly (e.g.
    `0 -> local`, `1 -> cloud`). Configure the model with `IR_OV_MODEL`.
  - See the [Routing Guide](./routing-guide.md) and
    [Policy Based Router Usage](./policy-based-router.md).

- Plugin System:

  - Pluggable `prerouting`, `postrouting`, and `postresponse` hooks with
    auto-discovery of every module under `src/plugins/` — no central registry
    to edit. Plugins can also contribute their own HTTP routes under `/v1`.
  - Built-in `compressor` plugin: prompt compression (`tool`, `harness`, and
    `context` types) backed by the [adaptive-token-compressor](https://github.com/open-edge-platform/edge-ai-libraries/tree/main/libraries/adaptive-token-compressor)
    library to cut token usage, with per-instance and node-level metrics.
  - Built-in `provider_management` plugin: start and stop backends on demand via an
    external Local Provider Manager, updating the running configuration.
  - Built-in `dummy_logger` reference plugin.
  - See the [Plugins](./plugin.md) section.

- Pass-through Services:

  - New OpenAI- and Cohere-compatible endpoints that forward the request body
    verbatim to a backing service: `POST /v1/audio/transcriptions` (`transcription`),
    `POST /v1/audio/speech` (`tts`), `POST /v1/embeddings` (`embeddings`),
    `POST /v1/rerank` (`rerank`), and `POST /v1/ocr` (`ocr`).
  - Enabled and managed dynamically by adding a provider of the matching `type`.

- Runtime Management API:

  - Providers: `GET/POST/DELETE /v1/providers` and `/v1/providers/{name}`.
  - Plugins: list instances and node types, inspect, create or update, delete, and
    reset via `/v1/plugins` (see the [API Reference](./api-reference.md#list-plugins)).
  - Policies: `/v1/policies` Create, Read, Update, Delete (CRUD).
  - Strategies: `/v1/strategies` CRUD.
  - Configuration and routing: `GET /v1/config` and `GET/PUT /v1/routing`.
  - Changes persist to the on-disk configuration and take effect immediately.

- Web UI Dashboard:

  - A Vue-based dashboard for managing providers and monitoring telemetry,
    including latency and token metrics. Supports light and dark themes, and English
	and Chinese locales.
  - Build and run with Docker Compose tool from `ui/docker`.

- Intel® GPU Support:

  - The Docker image ships with the Intel GPU runtime built in; the
    intelligent-routing classifier defaults to GPU. Override with `IR_DEVICE`
    (e.g. `IR_DEVICE=CPU`, `IR_DEVICE=GPU.1`).

- Observability:

  - Detailed health check and service information endpoints.
  - Token accounting integrated with telemetry; router processing time is
    excluded from the Time To First Token (TTFT) statistics.


## Version 2026.1.0

**June 17, 2026**

**New**

- Initial release of the Inference Router microservice.

- OpenAI-Compatible API:

  - `/v1/chat/completions` supports both streaming responses via
    Server-Sent Events (SSE) and non-streaming responses.
  - `/v1/models` endpoint lists every configured provider plus the virtual
    `"auto"` model for smart routing.

- Multi-Provider Routing:

  - LiteLLM-backed provider support for self-hosted vLLM and OpenVINO™, OpenAI,
    Anthropic, MiniMax, Ollama, and any other LiteLLM-supported backend.
  - Pin a backend by model ID, by provider name, or use `"auto"` to let the
    router pick based on the configured policy.

- Telemetry:

  - The `/v1/metrics` endpoint breaks down request counts by each unique
    (model, provider) pair, token usage, end-to-end latency, TTFT, and
	Time Per Output Token (TPOT).
  - The `POST /v1/metrics/reset` endpoint clears accumulated counters.

- Configuration:

  - YAML-based configuration with environment-variable expansion.
  - Concurrency limit and per-provider authentication settings.

*Validated configuration*:

- *Intel® Core™ Ultra processor X7 358H*
