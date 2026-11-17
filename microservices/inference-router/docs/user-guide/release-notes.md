# Release Notes: Inference Router

## Version 2026.3.0

**November, 2026**

**New**

- Configurable Model-Based Strategies:

  - `ModelBasedRule` runs a small classifier model on the router host against
    the last user message and returns a routing zone index that the strategy's
    index-keyed `provider_selector` maps to a provider (for example
    `0 -> local`, `1 -> cloud`). The built-in `ModelBased` policy runs the
    `ModelBasedRouting` strategy.
  - Choose the classifier for each rule with `param`: a stored `version`,
    prompt `text`, or a multi-class `prompt_file` that routes to your own
    categories (one zone per `provider_selector.label` entry).
  - Configure at runtime with `POST /v1/strategies/{name}`. The router checks
    the classifier before writing anything, loads the new policy's classifiers
    before switching to it (`IR_SWAP_MODE`), and reports what changed in
    `prompt_result` and `reconcile`. `GET /v1/strategies/{name}` lists the
    available models and versions in `classifier_options`.
  - If a classifier version cannot be loaded, the rule falls back to the
    packaged default, or to `-1` (no classifier guidance); requests keep
    being served.
  - See [Model-Based Routing](./routing.md#model-based-routing).

- Soft Prompts:

  - Each backbone ships a trained soft-prompt classifier version (`v1`) in
    `src/rsd/model_based/prompts/<backbone>/v1.rcv`, which works for
    local/cloud routing without any training.
  - A text system prompt posted with `param.text` is packed into a hard-prompt
    version (`<IR_ARTIFACTS_DIR>/<backbone>/vN.rcv`), and you can switch back
    to it by `version` at any time.
  - The router checks each version's format and fingerprint against the loaded
    backbone before using it, so a version built for a different model is
    rejected.

- Provider Probes:

  - A per-provider background task fetches an endpoint on an interval (for
    example a backend's Prometheus `/metrics` endpoint), reads numeric fields
    with `regex` or `json` rules, and reduces them over a sliding window
    (`mean`, `median`, `p90`, `ewma`, `latest`, and more).
  - Values are published to the provider's routing metadata (for example
    `performance.*`), to a capped JSONL history file, or to both. Everything is
    declared under a provider's `settings.probes`; no per-backend code is
    needed.
  - Add, start, and stop probes at runtime through the providers API. Live
    values are returned by `GET /v1/providers` and are never written to
    `config.yaml`.
  - New `PerformanceBased` strategy and `PerformanceFirst` policy route to the
    least-loaded backend, filtering providers by `performance` bounds or
    ranges (for example `[null, 0.9]`) and sorting on a live metric.
  - See [Provider Probes](./probe.md) and
    [Performance-Based Routing](./routing.md#performance-based-routing).

**Changed**

- `IntelligentRule` is replaced by `ModelBasedRule`. Update any custom
  `strategy.yaml` that references the old rule type.


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
  - See the [Routing guide](./routing.md).

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
