# Configuration Guide

The Semantic Search Agent uses environment variables (or a `.env` file at the project root) for all configuration. No YAML subscription file is required; data sources are JSON files under `config/`.

## Load Order

The service loads configuration in the following order:

1. **Environment Variables / `.env`**: Loaded via Pydantic Settings on startup. Environment variables take precedence over `.env` file values.
2. **Config JSON Files**: `config/inventory.json` and `config/orders.json` are loaded lazily on first use by the ComparisonEngine and cached in memory for the lifetime of the process.

---

## Environment Variables

All variables can be set as real environment variables or placed in the `.env` file at the project root.

### Service Settings

| Variable           | Default                  | Description                                      |
| ------------------ | ------------------------ | ------------------------------------------------ |
| `SERVICE_NAME`     | `semantic-search-agent`  | Service name reported in health and logs.        |
| `SERVICE_VERSION`  | `2026.1.0`               | Service version reported in health responses.    |
| `LOG_LEVEL`        | `INFO`                   | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `API_PORT`         | `8080`                   | Port the FastAPI server listens on.              |
| `METRICS_PORT`     | `9090`                   | Port for the Prometheus `/metrics` endpoint.     |
| `PROMETHEUS_ENABLED` | `true`                 | Enable or disable the Prometheus metrics mount.  |

### Matching Configuration

| Variable                      | Default    | Description                                                                          |
| ----------------------------- | ---------- | ------------------------------------------------------------------------------------ |
| `DEFAULT_MATCHING_STRATEGY`   | `exact`    | Matching strategy: `exact`, `semantic`, or `hybrid`.                                 |
| `CONFIDENCE_THRESHOLD`        | `0.85`     | Minimum VLM confidence score to consider a semantic match successful.                |
| `MAX_RETRIES`                 | `2`        | Maximum retries for VLM inference calls on transient failures.                       |

### VLM Backend Selection

| Variable       | Default  | Description                                                                         |
| -------------- | -------- | ----------------------------------------------------------------------------------- |
| `VLM_BACKEND`  | `ovms`   | VLM backend to use: `ovms`, `openvino_local`, or `openai`. Required only when `DEFAULT_MATCHING_STRATEGY` is `semantic` or `hybrid`. |

### OVMS Backend Settings

Required when `VLM_BACKEND=ovms` and strategy is `semantic` or `hybrid`.

| Variable          | Default | Description                                                            |
| ----------------- | ------- | ---------------------------------------------------------------------- |
| `OVMS_ENDPOINT`   | *(empty)* | Full base URL of the OVMS server (e.g. `http://your-ovms-host:8000`). ⚠️ Required. |
| `OVMS_MODEL_NAME` | *(empty)* | Model name served by OVMS (e.g. `Qwen/Qwen2.5-VL-7B-Instruct-ov-int8`). ⚠️ Required. |
| `OVMS_TIMEOUT`    | `30`    | HTTP request timeout in seconds for OVMS calls.                        |

### OpenVINO Local Backend Settings

Required when `VLM_BACKEND=openvino_local` and strategy is `semantic` or `hybrid`.

| Variable                    | Default | Description                                                                 |
| --------------------------- | ------- | --------------------------------------------------------------------------- |
| `OPENVINO_MODEL_PATH`       | *(empty)* | Path to the OpenVINO IR model directory on disk. ⚠️ Required.             |
| `OPENVINO_DEVICE`           | `GPU`   | Inference device: `GPU`, `CPU`, or `AUTO`.                                  |
| `OPENVINO_MAX_NEW_TOKENS`   | `512`   | Maximum tokens to generate per inference call.                              |
| `OPENVINO_TEMPERATURE`      | `0.0`   | Sampling temperature (0.0 = deterministic).                                 |

### OpenAI Backend Settings

Required when `VLM_BACKEND=openai` and strategy is `semantic` or `hybrid`.

| Variable             | Default        | Description                                                 |
| -------------------- | -------------- | ----------------------------------------------------------- |
| `OPENAI_API_KEY`     | *(empty)*      | OpenAI API key. ⚠️ Required.                               |
| `OPENAI_MODEL`       | `gpt-4o-mini`  | OpenAI model identifier to use for inference.               |
| `OPENAI_MAX_TOKENS`  | `100`          | Maximum tokens to generate per API call.                    |

### Cache Settings

| Variable         | Default   | Description                                                                    |
| ---------------- | --------- | ------------------------------------------------------------------------------ |
| `CACHE_ENABLED`  | `true`    | Enable or disable response caching for semantic match results.                 |
| `CACHE_BACKEND`  | `memory`  | Cache backend: `memory` (in-process) or `redis` (external).                   |
| `REDIS_HOST`     | `redis`   | Redis hostname (used when `CACHE_BACKEND=redis`).                              |
| `REDIS_PORT`     | `6379`    | Redis port.                                                                    |
| `REDIS_DB`       | `0`       | Redis database index.                                                          |
| `CACHE_TTL`      | `3600`    | Cache entry time-to-live in seconds.                                           |

### Proxy Settings

Pass these when running the service or building the Docker image behind a corporate proxy:

| Variable       | Default   | Description                                               |
| -------------- | --------- | --------------------------------------------------------- |
| `HTTP_PROXY`   | *(empty)* | HTTP proxy URL (e.g. `http://proxy.company.com:8080`).    |
| `HTTPS_PROXY`  | *(empty)* | HTTPS proxy URL.                                          |
| `NO_PROXY`     | *(empty)* | Comma-separated list of hosts to bypass the proxy.        |

> **Note**: The OVMS backend sets `trust_env=False` on its HTTP client to bypass proxy settings for internal OVMS communication. This is intentional — OVMS hosts are typically on the same internal network.

---

## Config JSON Files

Two JSON data files drive the comparison engine's data sources. Their paths can be overridden via environment variables; defaults point to the `config/` directory in the project root.

### `config/inventory.json`

A flat JSON array of item name strings representing the available inventory:

```json
[
  "apple",
  "banana",
  "milk",
  "bread",
  "eggs",
  "butter"
]
```

### `config/orders.json`

A JSON object mapping order IDs to lists of expected items with names and quantities:

```json
{
  "order_001": [
    {"name": "apple", "quantity": 3},
    {"name": "milk", "quantity": 2}
  ]
}
```

### Path Override Variables

| Variable          | Default                     | Description                                  |
| ----------------- | --------------------------- | -------------------------------------------- |
| `CONFIG_DIR`      | `./config`                  | Base directory for config files.             |
| `ORDERS_FILE`     | `{CONFIG_DIR}/orders.json`  | Path to the orders JSON file.                |
| `INVENTORY_FILE`  | `{CONFIG_DIR}/inventory.json` | Path to the inventory JSON file.           |

---

## Matching Strategy Reference

| Strategy  | VLM Required | Behavior                                                                                      |
| --------- | ------------ | --------------------------------------------------------------------------------------------- |
| `exact`   | No           | Normalizes both strings (lowercase, trim, strip special chars) and compares directly.         |
| `semantic`| Yes          | Sends a structured YES/NO prompt to the VLM backend for every comparison. Result is cached.   |
| `hybrid`  | Yes          | Tries exact match first. If exact confidence ≥ `0.9`, returns immediately. Otherwise falls back to semantic. |
