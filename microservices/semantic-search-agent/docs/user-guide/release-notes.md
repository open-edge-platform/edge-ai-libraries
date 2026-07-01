# Release Notes: Semantic Search Agent

This page tracks releases of the Semantic Search Agent microservice. The most recent release is listed first.

## Version 2026.1.0

First release of the Semantic Search Agent as a production-ready, multi-strategy AI comparison microservice.

**June 17, 2026**

**New**

- **REST Comparison API** with three endpoints:
  - `POST /api/v1/compare/order` — Two-pass order validation (exact then semantic) returning missing, extra, quantity-mismatch, and matched item sets.
  - `POST /api/v1/compare/inventory` — Per-item inventory lookup with exact and semantic fallback against a configurable JSON inventory.
  - `POST /api/v1/compare/semantic` — Generic pairwise semantic comparison returning match boolean, confidence score, and VLM reasoning.
- **Three Matching Strategies** (`exact`, `semantic`, `hybrid`) selectable via `DEFAULT_MATCHING_STRATEGY` environment variable.
- **Two-Pass Comparison Engine** — Exact matching resolved first without VLM calls; semantic matching applied only to unmatched items to minimize inference cost.
- **Pluggable VLM Backends** built-in:
  - **OVMS** — OpenVINO Model Server via OpenAI-compatible `/v3/chat/completions` endpoint. Proxy bypass for internal OVMS hosts.
  - **OpenVINO Local** — In-process inference using `openvino-genai` library with configurable device (`GPU`, `CPU`, `AUTO`).
  - **OpenAI** — Cloud API fallback for development and testing.
- **VLMBackendFactory** — Singleton factory with instance caching to avoid re-initializing backends on each request.
- **Response Caching** — In-memory (`MemoryCache`) and Redis-backed (`RedisCache`) caches for semantic match results, keyed by MD5 hash of the input pair and context. Configurable TTL.
- **Prometheus Metrics** — `api_requests_total`, `matches_total`, `request_duration_seconds`, `vlm_inference_duration_seconds`, `cache_hits_total`, `cache_misses_total`, and `vlm_backend_available` gauges.
- **Pydantic Settings** — Full environment variable and `.env` file configuration with type validation and clear startup errors on missing required variables.
- **Health Check Endpoint** (`GET /api/v1/health`) reporting service version, VLM backend type, VLM availability status, and uptime.
- **New User Guide documentation set** including Overview, Get Started, How It Works, Configuration, API Reference, Troubleshooting, and Release Notes.
- Containerization running as non-root user (UID 1000) with built-in Docker health check.
- Redis optional sidecar in Docker Compose for persistent semantic match caching.
- Modular matcher and VLM backend design allowing extension with new strategies or inference backends.
