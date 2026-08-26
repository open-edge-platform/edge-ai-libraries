# Quick Start Guide

- **Time to Complete:** 10 mins
- **Programming Language:** Python

Get the Inference Router running with one configured backend and verify the
OpenAI-compatible API.

## Get Started

### Prerequisites

- Install Docker Engine version 25.0 or higher:
  [Installation Guide](https://docs.docker.com/engine/install/ubuntu/).
- Python programming language version 3.10 or higher for local development.
- An OpenAI-compatible inference backend such as vLLM that is reachable from this
  host, or an API key for a cloud provider supported by LiteLLM tool.

The router itself is lightweight. Local model serving requirements depend on
the backend you connect to.

If you are cloning from the larger monorepo and only need this service, you
can use sparse checkout:

```bash
git clone --filter=blob:none --sparse https://github.com/open-edge-platform/edge-ai-libraries.git
cd edge-ai-libraries
git sparse-checkout set microservices/inference-router
cd microservices/inference-router
```

### Step 1: Configure

Copy the example configuration and edit it to point at your backend.
Note that the backend service **must be alive beforehand**. If your provider
needs API keys, copy `.env.example` to `workspace/.env` and fill in the
applicable values:

```bash
mkdir -p workspace
cp config.example.yaml workspace/config.yaml
cp .env.example workspace/.env
```

An example of a minimal `workspace/config.yaml` with one local vLLM model:

```yaml
providers:
  - name: "local"
    type: "hosted_vllm"
    model: "Qwen/Qwen3.5-9B"
    enabled: true
    metadata:
      labels:
        - "local"
      cost: 0
      performance: 0.85
      capability:
        complexity: 0.75
    settings:
      endpoint: "http://localhost:8088/v1"
      timeout: 300.0
      auth:
        scheme: "none"
        api_key: null
        custom_headers: {}
```

The router uses [LiteLLM tool](https://docs.litellm.ai/docs/#litellm-python-sdk) to
support different provider backends. `type` is passed to LiteLLM tool as the prefix
in `type/model`. Use `hosted_vllm` for a self-hosted vLLM server, or any other
[LiteLLM tool-supported provider](https://docs.litellm.ai/docs/providers).

When `workspace/config.yaml` references values such as `${OPENAI_API_KEY}` or
`${ANTHROPIC_API_KEY}`, Docker Compose tool forwards them from `workspace/.env`
into the container.


#### Model Preparation
Docker Compose deployments require the OpenVINO model prepared
**before starting the router**. The currently supported intelligent routing
classifier model is `Qwen3.5-2B-FP16`.

Download the supported Qwen3.5 2B OpenVINO model. If your
environment uses an internal model mirror or an approved local checkpoint,
replace `Qwen/Qwen3.5-2B` with that equivalent source:

```bash
# install huggingface CLI
pip install -U huggingface_hub
```

> **Note**: if you encounter an `externally-managed-environment` error,
either run the install command with `--break-system-packages`, or create
a Python virtual environment first.

```bash
hf download OpenVINO/Qwen3.5-2B-fp16-ov --local-dir /opt/models/Qwen2.5-2B-FP16
```

> **Note**: **`/opt` permissions:** the default `/opt/models` is typically root-owned.
> Grant your user access
> (`sudo mkdir -p /opt/models && sudo chown "$USER:$USER" /opt/models`).

> For users based in PRC, you might need to set `export HF_ENDPOINT=https://hf-mirror.com`.

For Docker Compose deployments, export the model path on this host with
`IR_OV_MODEL`; the compose file mounts it into the container automatically.

```bash
export IR_OV_MODEL=/opt/models/Qwen3.5-2B-FP16
```

### Step 2: Deploy

By default the deploy starts **both** the router and its web UI. The router
image resolves to `${REGISTRY}inference-router:${TAG}` and the UI image to
`${REGISTRY}inference-router-ui:${TAG}` — they share the same `REGISTRY` prefix
and `TAG`. With `REGISTRY` empty (the default), **locally built** images are
used. Choose one of the following.

To deploy the router **without** the UI, add `--standalone` to any of the
commands below.

#### Option 1: build from source (default)

With no `REGISTRY` set, build the images locally and deploy:

```bash
bash scripts/deploy_docker.sh --build
```

`--build` forces a build of both the router and UI images. If the images
already exist, run `bash scripts/deploy_docker.sh`.

#### Option 2: use a remote prebuilt image

Set a remote registry by exporting environment variables. The deploy then
**pulls** the prebuilt images instead of building:

```bash
export REGISTRY="intel/"
export TAG="latest"
```

`REGISTRY` is a prefix — include the trailing `/` (e.g. `intel/` or
`myregistry.example.com:5000/`). Leave it unset/empty to use the local images
from Option 1.

Deploy:

```bash
bash scripts/deploy_docker.sh
```

Check that the containers are running:

```bash
docker ps --filter name=inference-router
```

To stop everything:

```bash
bash scripts/deploy_docker.sh --down
```

To use a different host port:

```bash
ROUTER_PORT=9000 bash scripts/deploy_docker.sh
```

#### Web UI

With the UI enabled (the default), open it in a browser at
`http://<host-ip>:7010`. Because the router runs on the host network while the
UI runs in a bridge network, the deploy script automatically detects the host's
LAN IP, binds the router to it, and points the UI there — so the router is
reachable from other machines on your network in this mode. Use a different UI
port with `--ui-port`:

```bash
bash scripts/deploy_docker.sh --ui-port 8080
```

To skip the UI and deploy only the router (local-only by default, see
[Enable Remote Access](#enable-remote-access)):

```bash
bash scripts/deploy_docker.sh --standalone
```

#### Enable Remote Access

In `--standalone` mode the router binds to `127.0.0.1` (loopback) by default, so
it is only reachable from the host it runs on. To allow access from **other
machines**, export `IR_BIND_HOST=0.0.0.0` (or a specific interface IP) before
deploying:

```bash
IR_BIND_HOST=0.0.0.0 bash scripts/deploy_docker.sh --standalone
```

(When the UI is enabled the router is already bound to the host's LAN IP, so it
is reachable remotely without this step. Export `IR_BIND_HOST` to override the
detected address.)

Clients on other machines will then reach the router at `http://<host-ip>:8000`
(substitute your `ROUTER_PORT` if you changed it).

### Step 3: Verify

List available models. The response includes `router` plus your configured
providers:

```bash
curl http://localhost:8000/v1/models
```

Send a request to a specific model from `/v1/models`:

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3.5-9B",
    "messages": [{"role": "user", "content": "hello"}]
  }'
```

To get a quicker response, disable the `thinking` mode. Different model serving
backends may require different ways to do that. As an example, for vLLM with
the Qwen3 model, disable `thinking` with:

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3.5-9B",
    "messages": [{"role": "user", "content": "hello"}],
    "chat_template_kwargs": {
        "enable_thinking": false
    }
  }'
```

Let the router pick the provider based on the configured policy:

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "hello"}]
  }'
```

When two providers expose the same model name, `request.model` resolves to
the first one in `config.yaml`. To target the other, pass the provider name
(the `owned_by` field in `/v1/models`) as `model`:

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "cloud",
    "messages": [{"role": "user", "content": "hello"}]
  }'
```

Stream a chat completion:

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3.5-9B",
    "messages": [{"role": "user", "content": "hello"}],
    "stream": true
  }'
```

View router metrics:

```bash
curl http://localhost:8000/v1/metrics
```

## Optional: Pass-through Services

Besides chat completions, the router can expose additional OpenAI-compatible
and/or Cohere-compatible endpoints that **forward the request body verbatim**
to a backing service and return the response untouched. These are configured
as **providers** — the same `providers:` list as chat backends — so they are
listed, enabled or disabled, and updated through the same
[provider configuration API](./api-reference.md).

Currently supported services (the provider `type` selects the service and the
endpoint it exposes):

| Provider `type` | Endpoint Exposed              | Typical Backend                  |
| --------------- | ----------------------------- | -------------------------------- |
| `transcription` | `POST /v1/audio/transcriptions` | Speech-to-text service (e.g. Whisper)  |
| `tts`           | `POST /v1/audio/speech`         | Text-to-speech                 |
| `embeddings`    | `POST /v1/embeddings`           | Embedding model                |
| `rerank`        | `POST /v1/rerank`               | Reranker (Cohere-compatible)   |
| `ocr`           | `POST /v1/ocr`                  | OCR / document understanding   |

> **Note**: Optical Character Recognition (OCR)

### Enable a pass-through service

Add a provider whose `type` is one of the values above. The request is forwarded
to `settings.endpoint`; if the endpoint is a base URL, the service subpath (e.g.
`/v1/ocr`) is appended automatically. `model` is a nominal identifier used for
display. There is no `enabled` field to add — a provider present in the configuration
is enabled (set `enabled: false` to keep it in the file but turn it off).

```yaml
providers:
  # ... your chat providers ...

  - name: "ocr-backend"
    type: "ocr"                       # exposes POST /v1/ocr
    model: "ocr"
    settings:
      endpoint: "http://localhost:8002"
      timeout: 600                    # OCR cold-start + multi-page docs can be slow
      auth:                           # optional; same shape as chat providers
        scheme: "none"

  - name: "embeddings-backend"
    type: "embeddings"                # exposes POST /v1/embeddings
    model: "bge-m3"
    settings:
      endpoint: "http://localhost:9002"
      timeout: 30
```

Then call the endpoint directly (the body and response are passed through as-is):

```bash
curl http://localhost:8000/v1/ocr \
  -H "Content-Type: application/json" \
  -d '{"image_path": "/data/page.png"}'

curl http://localhost:8000/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model": "bge-m3", "input": "hello world"}'
```

Notes:

- **Not listed in `/v1/models`.** Pass-through backends are not chat-capable
  models, so they are omitted from `/v1/models`. They still appear in
  `/v1/providers` and can be managed there.
- **Concurrency.** Requests to these endpoints count against `max-concurrency`,
  shared with `/v1/chat/completions` — when the limit is reached the router
  returns `429`. Status and configuration endpoints
  (`/health`, `/v1/models`, `/v1/config`) are never limited.
- **Dynamic control.** Because they are ordinary providers, you can enable,
  disable, update, or delete them at runtime through the `/v1/providers` API; the
  change takes effect immediately. Disabling or removing the provider makes its
  endpoint return `503`.
- The backing services are **not** part of the router. Deploy them separately.

## Optional: Compression Plugins

The router can compress prompts before they reach the backend to cut token
usage, via plugins based on the
[adaptive-token-compressor](https://github.com/open-edge-platform/edge-ai-libraries/tree/main/libraries/adaptive-token-compressor).
Use the unified `compressor` node and select the compressor type with
`settings.type`:


- `tool` — filters the request `tools` schema to a relevant subset using a
  **tool predictor** (an OpenAI-compatible LLM endpoint).
- `harness` — compresses system or developer messages using a **Lingua server**.

These backend services are **not** part of the router. To deploy
the Lingua server and the tool predictor,
see the
[adaptive-token-compressor](https://github.com/open-edge-platform/edge-ai-libraries/tree/main/libraries/adaptive-token-compressor)
repository. 
For detailed purpose and behavior of each compressor, see the
[adaptive-token-compressor](https://github.com/open-edge-platform/edge-ai-libraries/tree/main/libraries/adaptive-token-compressor) repository documentation.


### Configuration

Enable the plugins under `plugins` in `workspace/config.yaml`, pointing each at
your running services:

Plugin stages:

- `prerouting`: When the plugin instance runs before provider selection, i.e.,
  before the routing decision is made.
- `postrouting`: When the plugin instance runs after provider selection and
  before the backend call.
- `postresponse`: When the plugin instance runs on the response after backend
  inference.

For compressor plugins, define them only in the `prerouting` or `postrouting` stage.
The `postresponse` stage is not for request compression.

In each plugin entry, `node` must be one of the supported fixed values
(currently `compressor`). `settings.type` selects the compressor type
(`tool` or `harness`). `name` is only an instance identifier and can be any
unique string.

```yaml
plugins:
  prerouting:
    - name: "compressor_tool"
      node: "compressor"
      enabled: true
      settings:
        type: "tool"
        predictor_url: "http://localhost:8088/v1/chat/completions"
        predictor_model: "Qwen/Qwen3.6-35B-A3B"
        score_threshold: 2.0
        prompt_mode: "dynamic"
        tool_descriptions_mode: "dynamic"
        placement: "schema"
  postrouting:
    - name: "compressor_harness"
      node: "compressor"
      enabled: true
      settings:
        type: "harness"
        profile: "openclaw"
        lingua_url: "http://localhost:8001/compress"
        compress_rate: 0.5
        compress_min_chars: 200
        timeout: 60.0
        enable_quantum_lock: false
  postresponse: []
```

### Metrics Checking

Compressor-related metrics are exposed from the following two endpoints.

After sending chat requests, view the aggregated compression metrics:

```bash
curl http://localhost:8000/v1/plugins/compressor
```

To compare token usage before and after router plugin processing (overall
compressor effect):

```bash
curl http://localhost:8000/v1/metrics
```


#### 1. `/v1/plugins/compressor` (node-level compression metrics)

This endpoint returns the `compressor` node view, including metrics aggregated
by the shared `CompressionManager`:

- `metrics`: numeric aggregates.
- `cache_stats`: per-compressor cache usage.

The `metrics` object usually contains:

- `<plugin_name>.total_input`: sum of input tokens before this plugin's compression.
- `<plugin_name>.total_output`: sum of output tokens after this plugin's compression.
- `<plugin_name>.call_count`: number of times this plugin ran.
- `<plugin_name>.compression_ratio`: `total_output / total_input` for this plugin.
  Lower value means a stronger compression.
- `<plugin_name>.avg_duration_per_call`: average plugin latency in milliseconds.

It also includes cross-plugin overall fields:

- `overall.total_requests`: unique request count across compressor plugins.
- `overall.total_input`: summed input tokens across all compressor plugins.
- `overall.total_output`: summed output tokens across all compressor plugins.
- `overall.compression_ratio`: `overall.total_output / overall.total_input`.
- `overall.avg_duration_per_request`: average end-to-end compression time per request.

The `cache_stats` object contains:

- `<plugin_name>.currsize`: current cache entry count.
- `<plugin_name>.maxsize`: configured cache capacity.

This endpoint returns the node metadata plus empty metrics when no compressor
plugin is configured, or when compressor metrics are not available yet (for
example before any request flows through the compressor pipeline).

#### 2. `/v1/metrics` (router telemetry with compression effect)

This endpoint includes compressor effect under `token_metrics`:

- `token_metrics.before_router`: token counts before plugin processing.
- `token_metrics.after_router`: token counts after plugin processing.

> **Note**:
> `after_router` is measured after the `prerouting` and `postrouting` stages are both
> completed (it is the request that will be forwarded to the backend).

`token_metrics.before_router` and `token_metrics.after_router` each contains the
following fields:

- `system_prompt_tokens`: system and developer message tokens.
- `tool_schema_tokens`: `request.tools` schema tokens.
- `context_tokens`: all other message tokens (user, assistant, or tool).
- `overall_tokens`: sum of the tokens in `system_prompt_tokens`, `tool_schema_tokens`,
  and `context_tokens`.

How to interpret compression savings:

- Per category saving = `before_router.<x> - after_router.<x>`.
- Overall saving = `before_router.overall_tokens - after_router.overall_tokens`.
- Overall remaining ratio = `after_router.overall_tokens / before_router.overall_tokens`.

Unlike provider-reported prompt tokens, `before_router` and `after_router`
tokens here are counted with the same token accounting method, so they are directly
comparable.

#### 3. `/v1/plugins/{node}/{name}` (per-instance view)

Beyond the group-aggregated compression view above, any plugin may fold its
**own** runtime information (including metrics) into its instance view. Fetch it with:

```bash
curl http://localhost:8000/v1/plugins/<node>/<name>
```

The response is whatever the plugin's `describe()` hook returns — the instance
configuration plus any plugin-defined fields (e.g. a `metrics` object). Plugins that
support it can reset their per-instance state:

```bash
curl -X POST http://localhost:8000/v1/plugins/<node>/<name>/reset
```

There is also a node-level pair: `GET /v1/plugins/<node>` (the type's
`describe_node()` payload, which may carry cross-instance aggregates) and
`POST /v1/plugins/<node>/reset`. See the
[API Reference](./api-reference.md#get-plugin) for the full contract.

Registering your own plugin type and the full list of built-in plugins are
covered in the [Plugins guide](./plugin.md).

## Learn More

- See the [Plugins guide](./plugin.md) for the plugin system, built-in plugins,
  and how to register a new one.
- Check the [API Reference](./api-reference.md) for endpoint details.
- See the [Release Notes](./release-notes.md) for version history.
