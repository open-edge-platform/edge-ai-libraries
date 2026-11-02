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
Docker Compose deployments require the OpenVINO classifier model prepared
**before starting the router**, even if you do not enable model-based routing
yet: the compose file mounts it into the container. The default model-based
routing classifier model is `Qwen3.5-2B` in OpenVINO FP16 format.

Download the Qwen3.5 2B OpenVINO model. If your environment uses an internal
model mirror, download the same `OpenVINO/Qwen3.5-2B-fp16-ov` repository from
it:

```bash
# install huggingface CLI
pip install -U huggingface_hub
```

> **Note**: if you encounter an `externally-managed-environment` error,
either run the install command with `--break-system-packages`, or create
a Python virtual environment first.

```bash
hf download OpenVINO/Qwen3.5-2B-fp16-ov --local-dir /opt/models/Qwen3.5-2B-FP16
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

## Optional: Model-Based Routing

With model-based routing, a small classifier model on this host reads each
request and decides whether a local model can handle it or it should go to a
cloud model. The router ships a ready-to-use classifier for the model prepared
in [Model Preparation](#model-preparation); no training is needed.

1. Give the two providers the labels `local` and `cloud` in
   `workspace/config.yaml`:

   ```yaml
   providers:
     - name: "local"
       type: "hosted_vllm"
       model: "Qwen/Qwen3.5-9B"
       fallback: true
       metadata:
         labels: ["local"]
       settings:
         endpoint: "http://localhost:8088/v1"
     - name: "cloud"
       type: "openai"
       model: "gpt-4o"
       metadata:
         labels: ["cloud"]
       settings:
         endpoint: "https://api.openai.com/v1"
         auth:
           scheme: "bearer"
           api_key: "${OPENAI_API_KEY}"
   ```

2. Select the built-in `ModelBased` policy in the same file:

   ```yaml
   routing:
     policy: "ModelBased"
   ```

3. Redeploy with `IR_OV_MODEL` still exported, then check the router log for
   the classifier:

   ```bash
   export IR_OV_MODEL=/opt/models/Qwen3.5-2B-FP16
   bash scripts/deploy_docker.sh
   docker logs inference-router 2>&1 | grep -E "Compiled backbone|Preloaded"
   ```

   `Preloaded 1 ModelBasedRule classifier(s) for the active policy` means
   model-based routing is active.

4. Send requests with `"model": "auto"`. A simple question goes to `local`, a
   hard one to `cloud`:

   ```bash
   curl http://localhost:8000/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "auto",
       "messages": [{"role": "user", "content": "What is the capital of France?"}]
     }'
   ```

The classifier runs on the Intel GPU by default and falls back to the CPU when
no GPU is available. Choose the device with `IR_DEVICE=CPU` or
`IR_DEVICE=GPU.1` before deploying.

See [Model-Based Routing](./routing.md#model-based-routing) for the other
supported model, custom classifier versions, your own categories, and
troubleshooting.

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
  **tool predictor** (an OpenAI-compatible LLM endpoint, or a reranker endpoint
  for the small-model option).
- `harness` — compresses system or developer messages using a **compress server**.
- `context` — compresses the conversation context.

>  **Caution:** The context compressor is experimental and is disabled by default.

The compress server and tool predictor are **not** part of the router.
For deployment instructions, see the
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
(`tool`, `harness`, or `context`). `name` is only an instance identifier and can be any
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
        placement: "schema"
        accumulate: true
  postrouting:
    - name: "compressor_harness"
      node: "compressor"
      enabled: true
      settings:
        type: "harness"
        profile: "openclaw"
        compress_server_url: "http://localhost:8001/compress"
        compress_rate: 0.5
        compress_min_chars: 200
        timeout: 60.0
        enable_quantum_lock: false
    - name: "compressor_context"
      node: "compressor"
      enabled: false
      settings:
        type: "context"
        protect_recent_tool_turns: 1
        large_result_stub: true
        large_result_stub_guidance: "legacy"
        large_result_min_tokens: 4000
        large_result_keep_tool_turns: 1
        compression_mode: "none"
  postresponse: []
```

See [Compressor plugin](./plugin.md#compressor-plugin) for more configuration details.

The `tool` example above uses the large-model predictor (`Qwen/Qwen3.6-35B-A3B`).
To use the small-model predictor instead, point the `tool` compressor at a
reranker endpoint and select tools with `top_k`:

```yaml
plugins:
  prerouting:
    - name: "compressor_tool"
      node: "compressor"
      enabled: true
      settings:
        type: "tool"
        predictor_url: "http://localhost:8091/v1/rerank"
        predictor_model: "Qwen/Qwen3-Reranker-0.6B"
        predictor_backend: "reranker"
        top_k: 10
        placement: "schema"
        accumulate: true
```

The small model is faster but saves fewer tool tokens. Size `top_k` to the
number of tools per request. For measured results and how to choose `top_k`,
see the ToolCompressor configuration guide in the
[adaptive-token-compressor](https://github.com/open-edge-platform/edge-ai-libraries/tree/main/libraries/adaptive-token-compressor)
repository.

#### Selecting per-compressor metrics

Each compressor instance records the metrics listed in `settings.metrics`,
reported as `<plugin_name>.<metric>`. If `metrics` is omitted or empty, the
default set below is used. A non-empty list replaces the default set, **so
include the default metrics you still want**:

```yaml
  postrouting:
    - name: "compressor_harness"
      node: "compressor"
      enabled: true
      settings:
        type: "harness"
        compress_server_url: "http://localhost:8001/compress"
        metrics: [total_input, total_output, call_count, compression_ratio,
                  avg_duration_per_call, total_saved, avg_saved_per_call]
```

| Metric | Default | Description |
| -------- | -------- | -------- |
| `total_input` | Yes | Sum of input tokens before compression |
| `total_output` | Yes | Sum of output tokens after compression |
| `call_count` | Yes | Number of times the compressor ran |
| `compression_ratio` | Yes | `total_output / total_input`; lower means stronger compression |
| `avg_duration_per_call` | Yes | Average compression latency per call, in milliseconds |
| `total_saved` | No | Sum of saved tokens (`total_input - total_output`) |
| `total_duration` | No | Sum of compression latency, in milliseconds |
| `avg_saved_per_call` | No | Average saved tokens per call |
| `avg_input_per_call` | No | Average input tokens per call |
| `avg_output_per_call` | No | Average output tokens per call |

Unknown metric names are skipped with a warning in the router log. The
cross-compressor `overall.*` fields are always recorded.
### Metrics Checking

After sending chat requests, choose the view that matches what you want to
inspect:

| Endpoint | Purpose |
| -------- | ------- |
| `/v1/plugins/compressor` | Aggregated metrics across compressor instances. |
| `/v1/plugins/compressor/<name>` | Configuration and runtime metrics for one compressor instance. |
| `/v1/metrics` | Token usage before and after router plugin processing for the whole request. |

Replace `<name>` with a configured plugin instance name, such as
`compressor_harness` in the configuration above.

#### Node-level compression metrics

View metrics across all compressor instances:

```bash
curl http://localhost:8000/v1/plugins/compressor
```

This endpoint returns the `compressor` node view, including metrics aggregated
by the shared `CompressionManager`:

- `metrics`: numeric aggregates.
- `metrics_by_keys`: the same aggregates split by key, currently only by
  `provider`, the provider that served the request (see
  [Metrics by key](#metrics-by-key)).
- `cache_stats`: per-compressor cache usage.

The `metrics` object contains each instance's selected metrics (see
[Selecting per-compressor metrics](#selecting-per-compressor-metrics)). With
the default set, these are:

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

> **Note**:
> `overall.*` fields only count the request parts the compressors cover, and
> count a part twice when two compressors of the same type run in series. For
> the whole-request saving, use
> [`/v1/metrics`](#whole-request-token-usage).

The `cache_stats` object contains:

- `<plugin_name>.currsize`: current cache entry count.
- `<plugin_name>.maxsize`: configured cache capacity.

This endpoint returns the node metadata plus empty metrics when no compressor
plugin is configured, or when compressor metrics are not available yet (for
example before any request flows through the compressor pipeline).

##### Metrics by key

`metrics_by_keys` maps each key to its values, and each value to a snapshot
with the same field names as `metrics`. The only key is currently `provider`,
whose values are provider names, for example:

```json
{
  "metrics_by_keys": {
    "provider": {
      "openai-gpt": {
        "compressor_harness.total_input": 800,
        "overall.total_requests": 2
      },
      "vllm-qwen": {
        "compressor_harness.total_input": 1200,
        "overall.total_requests": 3
      }
    }
  }
}
```

The example shows selected fields. Read per-provider metrics with the following
in mind:

- Only `postrouting` compressors are counted. A `prerouting` compressor runs
  before the provider is chosen, so its fields never appear here, and the
  per-provider `overall.*` fields cover `postrouting` compressors only. They
  therefore do not add up to the global `overall.*` fields when a `prerouting`
  compressor is configured.
- Token counts are `cl100k_base` estimates, not counts from each provider's own
  tokenizer.
- The compression cache is shared across providers. A cache hit is fast no matter
  which provider it is recorded under, so durations are not comparable across
  providers; saved token counts are.
- Sum fields (`total_input`, `total_output`, `call_count`, ...) add up across
  providers to the corresponding global values for `postrouting` compressors.
  Ratio and average fields (`compression_ratio`, `avg_*`) do not; recompute them
  from the summed totals.

#### Per-instance compression metrics

View one compressor instance using `/v1/plugins/compressor/<name>`. For example,
to inspect the `compressor_harness` instance configured above:

```bash
curl http://localhost:8000/v1/plugins/compressor/compressor_harness
```

The response includes the instance configuration and, for a live instance, its
runtime metrics:

- `metrics`: only this compressor's fields, using the
  `<plugin_name>.*` names described above.
- `metrics_by_keys`: for a `postrouting` compressor, the same per-instance
  fields split by key (`provider`). The
  [per-provider accounting notes](#metrics-by-key) also apply here.
  An empty object (`{}`) means no request has been recorded yet. For a compressor
  at any other stage, this field is `null` because metrics are not split by
  key.

A configured-but-disabled instance that is not loaded returns its static
configuration rather than live runtime metrics.

To reset this instance's metrics, or the shared node-level metrics:

```bash
curl -X POST http://localhost:8000/v1/plugins/compressor/compressor_harness/reset
curl -X POST http://localhost:8000/v1/plugins/compressor/reset
```

For the general plugin inspection and reset API contract, see the
[API Reference](./api-reference.md#get-plugin).

#### Whole-request token usage

Compare token usage before and after router plugin processing:

```bash
curl http://localhost:8000/v1/metrics
```

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

## Learn More

- See the [Plugins guide](./plugin.md) for the plugin system, built-in plugins,
  and how to register a new one.
- Check the [API Reference](./api-reference.md) for endpoint details.
- See the [Release Notes](./release-notes.md) for version history.
