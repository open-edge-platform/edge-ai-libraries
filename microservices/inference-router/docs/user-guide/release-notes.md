# Release Notes: Inference Router

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
