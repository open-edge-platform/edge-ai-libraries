# Inference Router

A pluggable FastAPI service for routing chat completion requests to multiple
inference providers. Backed by [LiteLLM](https://docs.litellm.ai/), it can talk
to any provider LiteLLM supports, including self-hosted vLLM/OpenVINO, OpenAI,
Anthropic, MiniMax, Ollama, and more, through a single OpenAI-compatible
endpoint.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![License](https://img.shields.io/badge/license-Apache--2.0-green)]()

## Features

- OpenAI-compatible `/v1/chat/completions` API with streaming and non-streaming responses.
- LiteLLM-backed provider support for local, hosted, and cloud inference backends.
- Policy-based routing through strategies and policies in [src/rsd](src/rsd).
- Pre-routing, post-routing and post-response plugin hooks.
- Optional prompt-compression plugins (tool-schema filtering and system-prompt
  compression) backed by [adaptive-token-compressor](https://github.com/open-edge-platform/edge-ai-libraries/tree/main/libraries/adaptive-token-compressor).
- Per-provider telemetry for requests, tokens, latency, TTFT, and TPOT.
- Environment variable expansion in configuration values.

## Quick Start

This is the minimal path to a running router. For prerequisites, model
preparation, verification, pass-through services, and compression plugins, see
the full [Quick Start Guide](docs/user-guide/get-started.md).

If you are cloning from the larger monorepo and only need this service, you
can use sparse checkout:

```bash
git clone --filter=blob:none --sparse https://github.com/open-edge-platform/edge-ai-libraries.git
cd edge-ai-libraries
git sparse-checkout set microservices/inference-router
cd microservices/inference-router
```

### Prerequisites

- Docker 25.0 or higher ([Installation Guide](https://docs.docker.com/engine/install/ubuntu/)).
- An OpenAI-compatible inference backend (such as vLLM) reachable from this
  host, or an API key for a cloud provider supported by LiteLLM. The backend
  **must be alive before you start the router.**

### Step 1: Configure

Create the runtime workspace folder, copy the example configuration into it,
and edit it to point at your backend. If your provider needs API keys, also
copy `.env.example` to `workspace/.env` and fill in the applicable values:

```bash
mkdir -p workspace
cp config.example.yaml workspace/config.yaml
cp .env.example workspace/.env
```

Docker Compose deployments also require the OpenVINO classifier model (used by
intelligent routing) prepared **before starting the router**. Download the
supported `Qwen3.5-2B-FP16` model and export its path — see
[Model preparation](docs/user-guide/get-started.md#model-preparation) for the
full steps:

```bash
export IR_OV_MODEL=/opt/models/Qwen3.5-2B-FP16
```

### Step 2: Build the Image

Build the Docker image:

```bash
bash scripts/deploy_docker.sh --build
```

### Step 3: Deploy

Start the router on port `8000` by default:

```bash
bash scripts/deploy_docker.sh
```

To use a different host port, or to stop the service:

```bash
ROUTER_PORT=9000 bash scripts/deploy_docker.sh
bash scripts/deploy_docker.sh --down
```

The intelligent-routing classifier **defaults to GPU** and automatically falls
back to CPU when no Intel GPU is available. Override the device with `IR_DEVICE`
(e.g. `export IR_DEVICE=CPU` or `IR_DEVICE=GPU.1`) before starting.

### Step 4: Verify

List available models (the response includes `router` plus your configured
providers), then send a request:

```bash
curl http://localhost:8000/v1/models

curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "hello"}]
  }'
```

Use `"model": "auto"` to let the router pick the provider by policy, or pass a
specific model name from `/v1/models`. See
[Step 4: Verify](docs/user-guide/get-started.md#step-4-verify) for streaming,
provider targeting, and metrics.

### Setup UI (optional)

Build and start the UI container with Docker Compose:

```bash
cd ui/docker

# Set environment variables
export SERVER_HOST=<your-server-ip>
export SERVER_PORT=<your-server-port>

# Build and start
docker compose -f build.yaml build
docker compose -f compose.yaml up -d
```

By default the UI is available at `http://<SERVER_HOST>:7010`. Stop it with
`docker compose -f compose.yaml down`.

## Optional Compression Plugins

Optional compression plugins (`tool` and `harness`) can cut prompt tokens
before requests reach the backend. They need a Lingua server and a tool
predictor started separately, then enabled under `plugins` in your config. See
[Optional: Compression Plugins](docs/user-guide/get-started.md#optional-compression-plugins)
for setup and the
[adaptive-token-compressor](https://github.com/open-edge-platform/edge-ai-libraries/tree/main/libraries/adaptive-token-compressor)
repository for those services.

## Learn More

- [Quick Start Guide](docs/user-guide/get-started.md) — full walkthrough,
  pass-through services, and compression plugins.
- [Plugins guide](docs/user-guide/plugin.md) — the plugin system and built-in plugins.
- [API Reference](docs/user-guide/api-reference.md) — endpoint details.
