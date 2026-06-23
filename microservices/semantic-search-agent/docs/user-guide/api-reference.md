# API Reference

Base URL: `http://localhost:8080/api/v1` (default).

---

## `GET /health`

Checks the liveness status of the service and reports the current VLM backend state.

### Response

```json
{
  "status": "healthy",
  "service": "semantic-search-agent",
  "version": "2026.1.0",
  "vlm_backend": "ovms",
  "vlm_status": "connected",
  "uptime_seconds": 42.5
}
```

| Field            | Type    | Description                                             |
| ---------------- | ------- | ------------------------------------------------------- |
| `status`         | string  | Always `"healthy"` when the service is running.         |
| `service`        | string  | Service name.                                           |
| `version`        | string  | Service version.                                        |
| `vlm_backend`    | string  | Configured VLM backend (`ovms`, `openvino_local`, `openai`). |
| `vlm_status`     | string  | `"connected"` if the backend is available, otherwise `"unavailable"`. |
| `uptime_seconds` | float   | Seconds since the service started.                      |

---

## `POST /compare/order`

Compares a list of expected items against detected items to identify missing, extra, and quantity-mismatched products. Uses the configured matching strategy (exact, semantic, or hybrid).

### Request Body (JSON)

| Parameter        | Type                   | Required | Description                                               |
| ---------------- | ---------------------- | -------- | --------------------------------------------------------- |
| `expected_items` | array of `ItemModel`   | Yes      | Items that should be present with their expected quantities. |
| `detected_items` | array of `ItemModel`   | Yes      | Items detected by the vision pipeline.                    |
| `options`        | `ComparisonOptions`    | No       | Optional matching behavior overrides.                     |

**`ItemModel`**

| Field      | Type    | Required | Description              |
| ---------- | ------- | -------- | ------------------------ |
| `name`     | string  | Yes      | Item name.               |
| `quantity` | integer | Yes      | Item quantity (≥ 1).     |

**`ComparisonOptions`**

| Field               | Type    | Default | Description                                            |
| ------------------- | ------- | ------- | ------------------------------------------------------ |
| `use_semantic`      | boolean | `true`  | Enable semantic matching for items not matched exactly. |
| `exact_match_first` | boolean | `true`  | Try exact match before semantic (always true in engine). |
| `case_insensitive`  | boolean | `true`  | Case-insensitive text normalization.                   |

### Examples

**Basic Order Validation:**

```bash
curl -X POST http://localhost:8080/api/v1/compare/order \
  -H "Content-Type: application/json" \
  -d '{
    "expected_items": [
      {"name": "apple", "quantity": 3},
      {"name": "milk", "quantity": 2},
      {"name": "bread", "quantity": 1}
    ],
    "detected_items": [
      {"name": "apple", "quantity": 3},
      {"name": "whole milk", "quantity": 2},
      {"name": "orange juice", "quantity": 1}
    ]
  }'
```

### Response

```json
{
  "status": "mismatch",
  "validation": {
    "missing": [
      {"name": "bread", "quantity": 1}
    ],
    "extra": [
      {"name": "orange juice", "quantity": 1}
    ],
    "quantity_mismatch": [],
    "matched": [
      {
        "expected": {"name": "apple", "quantity": 3},
        "detected": {"name": "apple", "quantity": 3},
        "match_type": "exact",
        "confidence": 1.0
      },
      {
        "expected": {"name": "milk", "quantity": 2},
        "detected": {"name": "whole milk", "quantity": 2},
        "match_type": "hybrid_semantic",
        "confidence": 0.92
      }
    ]
  },
  "metrics": {
    "total_expected": 3,
    "total_detected": 3,
    "exact_matches": 1,
    "semantic_matches": 1,
    "processing_time_ms": 245.3
  }
}
```

| Field                        | Type    | Description                                                    |
| ---------------------------- | ------- | -------------------------------------------------------------- |
| `status`                     | string  | `"validated"` if all items matched, `"mismatch"` otherwise.   |
| `validation.missing`         | array   | Expected items with no detected match.                         |
| `validation.extra`           | array   | Detected items with no expected match.                         |
| `validation.quantity_mismatch` | array | Items where names matched but quantities differ.               |
| `validation.matched`         | array   | Successfully matched item pairs with match type and confidence. |
| `metrics.exact_matches`      | integer | Count of items resolved by exact string matching.              |
| `metrics.semantic_matches`   | integer | Count of items resolved by semantic VLM matching.              |
| `metrics.processing_time_ms` | float   | Total processing time in milliseconds.                         |

---

## `POST /compare/inventory`

Checks whether a list of item names exist in the inventory, using exact or semantic matching.

### Request Body (JSON)

| Parameter   | Type                 | Required | Description                                                                      |
| ----------- | -------------------- | -------- | -------------------------------------------------------------------------------- |
| `items`     | array of strings     | Yes      | Item names to look up in inventory.                                              |
| `inventory` | array of strings     | No       | Explicit inventory list. Uses `config/inventory.json` if omitted.               |
| `options`   | `ComparisonOptions`  | No       | Optional matching behavior overrides (same as `/compare/order`).                |

### Examples

**Inventory Check:**

```bash
curl -X POST http://localhost:8080/api/v1/compare/inventory \
  -H "Content-Type: application/json" \
  -d '{
    "items": ["apple", "cola bottle", "bread loaf"],
    "inventory": ["apple", "coca cola 500ml", "bread", "milk"]
  }'
```

### Response

```json
{
  "results": [
    {
      "item": "apple",
      "match": true,
      "matched_inventory_item": "apple",
      "match_type": "exact",
      "confidence": 1.0
    },
    {
      "item": "cola bottle",
      "match": true,
      "matched_inventory_item": "coca cola 500ml",
      "match_type": "hybrid_semantic",
      "confidence": 0.91
    },
    {
      "item": "bread loaf",
      "match": true,
      "matched_inventory_item": "bread",
      "match_type": "hybrid_semantic",
      "confidence": 0.88
    }
  ],
  "summary": {
    "total_items": 3,
    "matched": 3,
    "unmatched": 0,
    "processing_time_ms": 312.7
  }
}
```

---

## `POST /compare/semantic`

Performs a generic semantic comparison between two arbitrary text strings using the configured VLM backend.

### Request Body (JSON)

| Parameter | Type   | Required | Description                                                      |
| --------- | ------ | -------- | ---------------------------------------------------------------- |
| `text1`   | string | Yes      | First text string (treated as the "expected" item).              |
| `text2`   | string | Yes      | Second text string (treated as the "detected" item).             |
| `context` | string | No       | Domain context passed to the VLM prompt. Default: `"grocery products"`. |

### Examples

**Semantic Comparison:**

```bash
curl -X POST http://localhost:8080/api/v1/compare/semantic \
  -H "Content-Type: application/json" \
  -d '{
    "text1": "green apple",
    "text2": "apple",
    "context": "grocery products"
  }'
```

### Response

```json
{
  "match": true,
  "confidence": 0.92,
  "reasoning": "YES",
  "match_type": "semantic"
}
```

| Field        | Type    | Description                                                             |
| ------------ | ------- | ----------------------------------------------------------------------- |
| `match`      | boolean | `true` if the VLM determined the texts refer to the same item.          |
| `confidence` | float   | Confidence score between 0.0 and 1.0.                                   |
| `reasoning`  | string  | Raw VLM response (`YES` or `NO`) or cache/error details.                |
| `match_type` | string  | Always `"semantic"` for this endpoint.                                  |

---

## `GET /metrics`

Prometheus-compatible metrics endpoint. Available on port `9090` by default (configurable via `METRICS_PORT`).

```bash
curl http://localhost:9090/metrics
```

Key metrics exposed:

| Metric                          | Type      | Description                                              |
| ------------------------------- | --------- | -------------------------------------------------------- |
| `api_requests_total`            | Counter   | Total requests per endpoint, method, and status code.   |
| `matches_total`                 | Counter   | Total match operations per match type and result.        |
| `request_duration_seconds`      | Histogram | Request latency per endpoint and method.                 |
| `vlm_inference_duration_seconds`| Histogram | VLM inference latency per backend.                       |
| `cache_hits_total`              | Counter   | Total cache hits per operation type.                     |
| `cache_misses_total`            | Counter   | Total cache misses per operation type.                   |
| `vlm_backend_available`         | Gauge     | VLM backend availability (1 = available, 0 = unavailable). |
