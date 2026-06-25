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

Build the Docker image:

```bash
bash scripts/deploy_docker.sh --build
```

### 3. Start the Service

Start the router on port `8000` by default:

```bash
bash scripts/deploy_docker.sh
```

To stop the service:

```bash
bash scripts/deploy_docker.sh --down
```

See [get-started.md](docs/user-guide/get-started.md) for more information.
