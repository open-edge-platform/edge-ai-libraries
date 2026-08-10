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

If you are cloning from the larger monorepo and only need this service, you
can use sparse checkout:

```bash
git clone --filter=blob:none --sparse https://github.com/open-edge-platform/edge-ai-libraries.git
cd edge-ai-libraries
git sparse-checkout set microservices/inference-router
cd microservices/inference-router
```

### 1. Configure

Create the runtime workspace folder, copy the example configuration into it,
and edit it to point at your backend. If your provider needs API keys, also
copy `.env.example` to `workspace/.env` and fill in the applicable values:

```bash
mkdir -p workspace
cp config.example.yaml workspace/config.yaml
cp .env.example workspace/.env
```

### 2. Build the Image

Build the Docker image (default without compressor):

```bash
bash scripts/deploy_docker.sh --build
```

To build with compressor support in one command:

```bash
bash scripts/deploy_docker.sh --build --with-compressor
```

`--with-compressor` vendors and installs
`adaptive-token-compressor` into the router image (claw-compactor comes in
as a regular dependency), so compression plugins are available in the
container runtime.

### 3. Start the Service

Before starting with Docker Compose, export the path to the OpenVINO classifier
model on this host (used by intelligent routing).

```bash
export IR_OV_MODEL=/opt/models/Qwen3.5-2B-FP16
```

Start the router on port `8000` by default:

```bash
bash scripts/deploy_docker.sh
```

To stop the service:

```bash
bash scripts/deploy_docker.sh --down
```

#### Select the classifier device (Intel GPU / CPU)

Image ships with the Intel GPU runtime built in and the
intelligent-routing classifier **defaults to GPU**. If no Intel GPU is available
(or `/dev/dri` is not present on the host), it automatically falls back to CPU.

Override the device with the `IR_DEVICE` environment variable — export it before
starting the router:

```bash
export IR_DEVICE=CPU
bash scripts/deploy_docker.sh
```

To pick a specific device (e.g. a second GPU), set the full device string:

```bash
export IR_DEVICE=GPU.1
bash scripts/deploy_docker.sh
```

Requirements on the host when using a GPU:

- Intel GPU drivers installed and `/dev/dri/renderD*` present (`ls /dev/dri`).
- Your user in the `render` group, or run the script with the needed privileges.

### 4. Setup UI

Build and start the UI container with Docker Compose:

```bash
cd ui/docker

# Set environment variables:

export SERVER_HOST=<your-server-ip>
export SERVER_PORT=<your-server-port>

# Build UI image
docker compose -f build.yaml build

# Start UI container
docker compose -f compose.yaml up -d
```

By default, the UI will be available at:

```text
http://<SERVER_HOST>:7010
```

To stop the UI container:

```bash
docker compose -f compose.yaml down
```

## Optional Compression Plugins

Optional compression plugins (tool + harness) can cut
prompt tokens before requests reach the backend.
They need a Lingua server and
a tool predictor, start those services separately before enabling the
compression plugins in config. — see [get-started.md](docs/user-guide/get-started.md#optional-compression-plugins)
for setup and the [adaptive-token-compressor](https://github.com/open-edge-platform/edge-ai-libraries/tree/main/libraries/adaptive-token-compressor)
repository for those services.

See [get-started.md](docs/user-guide/get-started.md) for more information.
