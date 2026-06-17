# How It Works

This page describes the architecture and internal request flow of a comparison request through the microservice.

## Architecture

At a high level, the Semantic Search Agent accepts item comparison payloads via REST, passes them through a configured matching strategy, and returns structured results. The matching pipeline uses a two-pass approach — fast exact normalization first, followed by VLM-based semantic reasoning for any remaining unmatched items — to minimize latency and inference costs.

```mermaid
%%{init: {
  'theme': 'base',
  'themeVariables': {
    'fontFamily': '"IntelOne Display", "Intel Clear", "Inter", "Segoe UI", Arial, sans-serif',
    'fontSize': '14px',
    'primaryColor': '#0068B5',
    'primaryTextColor': '#FFFFFF',
    'primaryBorderColor': '#00377C',
    'lineColor': '#00377C',
    'secondaryColor': '#EEF3F8',
    'tertiaryColor': '#F7F8FA',
    'background': '#FFFFFF',
    'mainBkg': '#FFFFFF',
    'clusterBkg': '#F7F8FA',
    'clusterBorder': '#0068B5',
    'edgeLabelBackground': '#FFFFFF',
    'noteBkgColor': '#F7F8FA',
    'noteTextColor': '#3A3A3A'
  }
}}%%
flowchart TD
    Client([Client])

    subgraph Service["Semantic Search Agent (:8080)"]
        API["API Layer<br/>(REST Endpoints)"]

        subgraph Engine["Comparison Engine"]
            ExactPass["Pass 1: Exact Matcher<br/>(Normalize → Compare)"]
            SemanticPass["Pass 2: Semantic Matcher<br/>(VLM Prompt → YES/NO)"]
            Cache[("Result Cache<br/>(Memory / Redis)")]
        end

        subgraph VLM["VLM Backend"]
            Factory["VLMBackendFactory"]
            OVMS["OVMS Backend<br/>(OpenAI-compat API)"]
            OVLocal["OpenVINO Local<br/>(In-process GenAI)"]
            OAI["OpenAI Backend<br/>(Cloud API)"]
        end

        Config["Settings & Config Files<br/>(inventory.json / orders.json)"]
        Metrics["Prometheus Metrics<br/>(:9090/metrics)"]
    end

    Client -- "POST /api/v1/compare/order" --> API
    Client -- "POST /api/v1/compare/inventory" --> API
    Client -- "POST /api/v1/compare/semantic" --> API
    API --> ExactPass
    ExactPass -->|Unmatched items| SemanticPass
    SemanticPass <--> Cache
    SemanticPass --> Factory
    Factory --> OVMS
    Factory --> OVLocal
    Factory --> OAI
    API <--> Config
    API --> Metrics

    classDef client fill:#FFFFFF,stroke:#0068B5,stroke-width:2px,color:#3A3A3A;
    classDef core fill:#0068B5,stroke:#00377C,stroke-width:1.5px,color:#FFFFFF;
    classDef backend fill:#00A3F4,stroke:#00377C,stroke-width:1.5px,color:#FFFFFF;
    classDef store fill:#6C6C6C,stroke:#0068B5,stroke-width:1.5px,color:#FFFFFF;

    class Client client;
    class API,ExactPass,SemanticPass,Factory core;
    class OVMS,OVLocal,OAI backend;
    class Cache,Config,Metrics store;

    style Service fill:#F7F8FA,stroke:#0068B5,stroke-width:1.5px,color:#3A3A3A;
    style Engine fill:#EEF3F8,stroke:#0068B5,stroke-width:1.0px,color:#3A3A3A;
    style VLM fill:#EEF3F8,stroke:#0068B5,stroke-width:1.0px,color:#3A3A3A;
```

**Key components:**

- **API Router** — Accepts and validates incoming comparison requests using Pydantic models. Routes to the appropriate ComparisonEngine method and returns structured JSON responses.
- **ComparisonEngine** — Orchestrates the two-pass matching pipeline. Loads order and inventory data from config JSON files. Coordinates exact and semantic matchers, aggregates results (missing, extra, quantity mismatch, matched), and records Prometheus metrics.
- **ExactMatcher** — Normalizes both input strings (lowercase, whitespace trimming, special character removal) and performs direct string equality. Returns confidence `1.0` on match, `0.0` otherwise.
- **SemanticMatcher** — Constructs a structured prompt from the input pair and a context string, submits it to the configured VLM backend, and interprets the YES/NO response as a boolean match. Checks an in-memory or Redis cache before invoking the VLM to avoid redundant inference calls.
- **HybridMatcher** — Runs ExactMatcher first as a fast path. If the exact confidence meets the configured threshold (default `0.9`), returns the exact result immediately. Otherwise, delegates to SemanticMatcher and returns the semantic result.
- **VLMBackendFactory** — Singleton factory that creates and caches one VLM backend instance per backend type. Supports `ovms`, `openvino_local`, and `openai` backends.
- **OVMS Backend** — Sends requests to an OpenVINO Model Server using the OpenAI-compatible `/v3/chat/completions` endpoint. Bypasses system proxy to communicate with internal OVMS hosts.
- **OpenVINO Local Backend** — Loads an OpenVINO IR model in-process using the `openvino-genai` library. Suitable for GPU-accelerated edge deployments without a separate model server.
- **OpenAI Backend** — Delegates to the OpenAI API for cloud-based inference. Used as a development or fallback option.
- **Cache** — Keyed by MD5 hash of the normalized input pair and context string. Supports configurable TTL. Backed by either an in-process `MemoryCache` or an external `RedisCache`.

## Request Flow

### Order Validation (`POST /api/v1/compare/order`)

1. **Validate** — FastAPI validates the request body against `OrderValidationRequest`. Each item must have a `name` (string) and `quantity` (integer ≥ 1).
2. **Pass 1 — Exact Matching** — For every expected item, the engine normalizes its name and searches detected items for an exact normalized match. On a match, the item is added to `matched` and the detected slot is reserved. If quantities differ, the item is added to `quantity_mismatch`.
3. **Pass 2 — Semantic Matching** — For each expected item still unmatched after Pass 1, the engine iterates over unreserved detected items and calls `matcher.match(expected_name, detected_name)`. If `MatchResult.match` is `True`, the item pair is added to `matched` with the semantic confidence. Unmatched expected items become `missing`; unreserved detected items become `extra`.
4. **Respond** — Returns a `OrderValidationResponse` containing `status` (`validated` or `mismatch`), a full `validation` breakdown, and `metrics` (exact/semantic match counts, processing time).

### Inventory Validation (`POST /api/v1/compare/inventory`)

1. **Validate** — FastAPI validates the request body against `InventoryValidationRequest`. Accepts a list of item name strings and an optional inventory list (uses `config/inventory.json` if omitted).
2. **Per-Item Matching** — For each input item, exact match is attempted against all inventory entries. If no exact match is found and semantic matching is enabled, the engine iterates inventory entries and picks the highest-confidence semantic match above the threshold.
3. **Respond** — Returns `InventoryValidationResponse` with per-item results (matched item, match type, confidence) and a summary (total, matched, unmatched, processing time ms).

### Semantic Match (`POST /api/v1/compare/semantic`)

1. **Validate** — FastAPI validates the request body against `SemanticMatchRequest` with `text1`, `text2`, and an optional `context` string.
2. **Match** — Directly calls `SemanticMatcher.match()`, which checks the cache first, then invokes the VLM backend with a structured prompt.
3. **Respond** — Returns `SemanticMatchResponse` with `match` (boolean), `confidence` (float), `reasoning` (VLM response), and `match_type`.

## Configuration Surface

All runtime settings are parsed and validated via Pydantic Settings on startup. Environment variables or a `.env` file at the project root override defaults. See the [Configuration Guide](./get-started/configuration.md) for a comprehensive list of parameters.
