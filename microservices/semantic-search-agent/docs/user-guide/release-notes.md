# Release Notes: Semantic Search Agent

This section tracks releases of the Semantic Search Agent microservice. The most recent release is listed first.

<!--## Version 2026.2.0-->

<!--date TBD-->

## Version 2026.1.0

First release of the Semantic Search Agent as a production-ready, multi-strategy AI comparison microservice.

**Release Date:** June 17, 2026

**New:**

- **REST Comparison API** with three endpoints:
  - `POST /api/v1/compare/order` — Two-pass order validation (exact, then semantic) that returns missing, extra, quantity-mismatch, and matched item sets.
  - `POST /api/v1/compare/inventory` — Per-item inventory lookup with the exact and semantic fallback against a configurable JSON inventory.
  - `POST /api/v1/compare/semantic` — Generic pairwise semantic comparison that returns boolean match, confidence score, and VLM reasoning.
- **Three Matching Strategies** (`exact`, `semantic`, or `hybrid`) that are selectable via the `DEFAULT_MATCHING_STRATEGY` environment variable.
- **Two-Pass Comparison Engine** — The engine resolves exact matches first without VLM calls and applies semantic matching only to unmatched items to minimize inference cost.
- **Pluggable VLM Backends** built-in:
  - **OVMS** — OpenVINO model server via OpenAI-compatible `/v3/chat/completions` endpoint. Proxy bypass for internal OpenVINO model server hosts.
  - **OpenVINO Local** — In-process inference that uses the `openvino-genai` library with configurable device (`GPU`, `CPU`, or `AUTO`).
  - **OpenAI API** — Cloud API fallback for development and testing.
- **VLMBackendFactory** — Singleton factory with instance caching to avoid re-initializing backends on each request.
- **Response Caching** — In-memory (`MemoryCache`) and Redis-backed (`RedisCache`) caches for semantic match results, keyed by Message Digest Algorithm 5 (MD5) hash of the input pair and context. Configurable time-to-live (TTL).
- **Prometheus Metrics** — `api_requests_total`, `matches_total`, `request_duration_seconds`, `vlm_inference_duration_seconds`, `cache_hits_total`, `cache_misses_total`, and `vlm_backend_available` gauges.
- **Pydantic Settings** — Full environment variable and `.env` file configuration with type validation and clear startup errors on missing required variables.
- **Health Check Endpoint** (`GET /api/v1/health`) reports service version, VLM backend type, VLM availability status, and uptime.
- **New User Guide documentation set** that includes the Overview, Get Started, How It Works, Configuration, API Reference, Troubleshooting, and Release Notes sections.
- Containers run as a non-root user with UID 1000, and include a built-in Docker health check.
- An optional Redis service in the Docker Compose configuration, which provides persistent caching for semantic match results.
- Modular matcher and VLM backend design, which allow for extension with new strategies or inference backends.