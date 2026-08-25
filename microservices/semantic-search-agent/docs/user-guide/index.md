# Semantic Search Agent

<!--hide_directive
<div class="component_card_widget">
  <a class="icon_github" href="https://github.com/open-edge-platform/edge-ai-libraries/tree/main/microservices/semantic-search-agent">
     GitHub
  </a>
  <a class="icon_document" href="https://github.com/open-edge-platform/edge-ai-libraries/blob/main/microservices/semantic-search-agent/README.md">
     Readme
  </a>
</div>
hide_directive-->

Semantic Search Agent is a lightweight, production-ready microservice for AI-powered item matching and validation. Built with FastAPI and asyncio, it accepts item comparison requests via REST, runs them through a configurable multi-strategy matching pipeline (exact string, semantic VLM-based, or hybrid), and returns structured match results with confidence scores. The service consolidates semantic matching logic from multiple edge-AI applications into a single extensible microservice.

## Use Cases

- **Order Validation at the Edge** — Compare a list of expected grocery or retail items against detected items from a vision pipeline and identify missing, extra, or quantity-mismatched products.
- **Inventory Verification** — Check whether detected items exist in a configured inventory database, tolerating name variations, abbreviations, and paraphrases using semantic understanding.
- **Fuzzy Product Matching** — Resolve naming inconsistencies between systems (e.g., "Coca Cola 500ml" vs "cola bottle") using a VLM-backed semantic comparison prompt.
- **Multi-Backend VLM Flexibility** — Run inference against a remote OpenVINO Model Server (OVMS), a local OpenVINO GenAI model, or the OpenAI cloud API without changing business logic.

## Key Capabilities

- **Three Matching Strategies** — `exact` (fast normalized string comparison), `semantic` (VLM-based reasoning), and `hybrid` (exact fast-path with semantic fallback for unmatched items).
- **Pluggable VLM Backends** — Supports OVMS (OpenAI-compatible endpoint), OpenVINO GenAI (in-process), and OpenAI API. Selected via a single environment variable.
- **Two-Pass Comparison Engine** — Runs exact matching first for speed, then applies semantic matching only to unmatched items to minimize VLM inference calls.
- **Response Caching** — In-memory or Redis-backed cache for semantic match results, keyed by normalized input pair and context.
- **Prometheus Metrics** — Exposes `api_requests_total`, `matches_total`, `request_duration_seconds`, `vlm_inference_duration_seconds`, `cache_hits_total`, and `vlm_backend_available` metrics on a dedicated metrics endpoint.
- **Config-Driven Data Sources** — Inventory and order definitions loaded from JSON files; paths configurable via environment variables.

## Next Steps

- [Get Started](./get-started.md) - a step-by-step guide to your first run.
- [Configuration](./get-started/configuration.md) - how to configure matching strategy, VLM backend, and caching.
- [How It Works](./how-it-works.md) - learn about the internal request flow and components.

<!--hide_directive
:::{toctree}
:hidden:

./get-started.md
./how-it-works.md
./api-reference.md
./troubleshooting.md
Release Notes <./release-notes.md>

:::
hide_directive-->
