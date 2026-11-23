# Configuration Guide

The Semantic Search Agent is configured with environment variables, the `.env` file at the project root folder, and the bundled `config/service_config.yaml` file. Data sources are JSON files under the `config/` folder.

## Load Order

The service loads the configuration in the following order:

1. **Environment variables**: Highest precedence.
2. **`.env` file**: Loaded from the working directory (the project root folder) through Pydantic Settings on startup. Values here are overridden by real environment variables.
3. **`config/service_config.yaml`**: Bundled with the service and loaded automatically when present. Its values are used only for settings that are not set in the environment or the `.env` file.
4. **Built-in defaults**: Used for any setting that none of the sources above defines.
5. **Configuration JSON Files**: The ComparisonEngine loads `config/inventory.json` and `config/orders.json` lazily on the first use and caches them in memory for the lifetime of the process.

---

## Environment Variables

You can set all variables as real environment variables or place them in the `.env` file at the project root folder. A value set in either place overrides the same setting in `config/service_config.yaml`.

When you run with Docker Compose, the `.env` file at the project root folder is passed to the container, so every variable in it takes effect.

### Service Settings

| Variable           | Default                  | Description                                            |
| ------------------ | ------------------------ | ------------------------------------------------------ |
| `SERVICE_NAME`     | `semantic-search-agent`  | Service name reported in health and logs.              |
| `SERVICE_VERSION`  | `2026.3.0-rc1`           | Service version reported in health responses.          |
| `LOG_LEVEL`        | `INFO`                   | Logging level: `DEBUG`, `INFO`, `WARNING`, or `ERROR`. |
| `API_PORT`         | `8080`                   | Port the FastAPI server listens on.                    |
| `METRICS_PORT`     | `9090`                   | Port for the Prometheus `/metrics` endpoint.           |
| `PROMETHEUS_ENABLED` | `true`                 | Enable or disable the Prometheus metrics mount.        |

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

### OpenVINO Model Server Backend Settings

Required when `VLM_BACKEND=ovms` and strategy is `semantic` or `hybrid`.

| Variable          | Default   | Description                                                                                           |
| ----------------- | --------- | ----------------------------------------------------------------------------------------------------- |
| `OVMS_ENDPOINT`   | *(empty)* | Full base URL of the OpenVINO model server (e.g. `http://your-ovms-host:8000`). ⚠️ Required.          |
| `OVMS_MODEL_NAME` | *(empty)* | Model name served by OpenVINO model server (e.g. `Qwen/Qwen2.5-VL-7B-Instruct-ov-int8`). ⚠️ Required. |
| `OVMS_TIMEOUT`    | `30`      | HTTP request timeout in seconds for OpenVINO model server calls.                                      |

### OpenVINO Toolkit Local Backend Settings

Required when `VLM_BACKEND=openvino_local` and strategy is `semantic` or `hybrid`.

| Variable                    | Default   | Description                                                                 |
| --------------------------- | --------- | --------------------------------------------------------------------------- |
| `OPENVINO_MODEL_PATH`       | *(empty)* | Path to the OpenVINO IR model directory on disk. ⚠️ Required.               |
| `OPENVINO_DEVICE`           | `GPU`     | Inference device: `GPU`, `CPU`, or `AUTO`.                                  |
| `OPENVINO_MAX_NEW_TOKENS`   | `512`     | Maximum tokens to generate per inference call.                              |
| `OPENVINO_TEMPERATURE`      | `0.0`     | Sampling temperature (0.0 = deterministic).                                 |

### OpenAI Backend Settings

Required when `VLM_BACKEND=openai` and strategy is `semantic` or `hybrid`.

| Variable             | Default        | Description                                                 |
| -------------------- | -------------- | ----------------------------------------------------------- |
| `OPENAI_API_KEY`     | *(empty)*      | OpenAI API key. ⚠️ Required.                                |
| `OPENAI_MODEL`       | `gpt-4o-mini`  | OpenAI model identifier to use for inference.               |
| `OPENAI_MAX_TOKENS`  | `100`          | Maximum tokens to generate per API call.                    |

The `openai` Python package is included in `requirements.txt` and in the Docker image.

### Cache Settings

| Variable         | Default   | Description                                                                    |
| ---------------- | --------- | ------------------------------------------------------------------------------ |
| `CACHE_ENABLED`  | `true`    | Enable or disable response caching for semantic match results.                 |
| `CACHE_BACKEND`  | `memory`  | Cache backend: `memory` (in-process) or `redis` (external).                    |
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

> [!NOTE]
> The OpenVINO model server backend sets `trust_env=False` on its HTTP client to bypass proxy settings for internal OpenVINO model server communication. This is intentional because OpenVINO model server hosts are typically on the same internal network.

---

## Configuration JSON Files

Two JSON data files drive the comparison engine's data sources. Their paths can be overridden via environment variables; defaults point to the `config/` directory in the project root.

### `config/inventory.json`

A flat JSON array of item name strings that represent the available inventory:

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

A JSON object that maps order IDs to lists of expected items with names and quantities:

```json
{
  "order_001": [
    {"name": "apple", "quantity": 3},
    {"name": "milk", "quantity": 2}
  ]
}
```

### Path Override Variables

| Variable          | Default                       | Description                                  |
| ----------------- | ----------------------------- | -------------------------------------------- |
| `CONFIG_DIR`      | `./config`                    | Base directory for configuration files.      |
| `ORDERS_FILE`     | `{CONFIG_DIR}/orders.json`    | Path to the orders JSON file.                |
| `INVENTORY_FILE`  | `{CONFIG_DIR}/inventory.json` | Path to the inventory JSON file.             |

## Matching Strategy Reference

| Strategy  | VLM Required | Behavior                                                                                                                    |
| --------- | ------------ | --------------------------------------------------------------------------------------------------------------------------- |
| `exact`   | No           | Normalizes both strings by converting to lowercase, trimming, and stripping special characters, and compares them directly. |
| `semantic`| Yes          | Sends a structured YES/NO prompt to the VLM backend for every comparison. Result is cached.                                 |
| `hybrid`  | Yes          | Tries exact match first. If exact confidence ≥ `0.9`, returns immediately. Otherwise falls back to semantic.                |
