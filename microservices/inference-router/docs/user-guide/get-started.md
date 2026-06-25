# Quick Start Guide

- **Time to Complete:** 10 mins
- **Programming Language:** Python

Get the Inference Router running with one configured backend and verify the
OpenAI-compatible API.

## Get Started

### Prerequisites

- Install Docker 25.0 or higher: [Installation Guide](https://docs.docker.com/engine/install/ubuntu/).
- Python 3.10+ for local development.
- An OpenAI-compatible inference backend, such as vLLM, reachable from this
  host, or an API key for a cloud provider supported by LiteLLM.

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

Copy the example config and edit it to point at your backend. If your provider
needs API keys, also copy `.env.example` to `workspace/.env` and fill in the
applicable values:

```bash
mkdir -p workspace
cp config.example.yaml workspace/config.yaml
cp .env.example workspace/.env
```

A minimal `workspace/config.yaml` with one local vLLM model:

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

The router uses [LiteLLM](https://docs.litellm.ai/docs/#litellm-python-sdk) to
support different provider backends. `type` is passed to LiteLLM as the prefix
in `type/model`. Use `hosted_vllm` for a self-hosted vLLM server, or any other
[LiteLLM-supported provider](https://docs.litellm.ai/docs/providers).

When `workspace/config.yaml` references values such as `${OPENAI_API_KEY}` or
`${ANTHROPIC_API_KEY}`, Docker Compose forwards them from `workspace/.env`
into the container.

### Step 2: Build Image

Build the Docker image:

```bash
bash scripts/deploy_docker.sh --build
```

### Step 3: Deploy

Start the router on port `8000` by default:

```bash
bash scripts/deploy_docker.sh
```

Check that the container is running:

```bash
docker ps --filter name=inference-router
```

To stop the router:

```bash
bash scripts/deploy_docker.sh --down
```

To use a different host port:

```bash
ROUTER_PORT=9000 bash scripts/deploy_docker.sh
```

### Step 4: Verify

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

<details>
<summary>Tips</summary>

To get a quicker response, you can try to disable `thinking` mode. Different model serving backends may require different way to do that. As an example, for vLLM with Qwen3 model, disable `thinking` with

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

</details>

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

## Learn More

- Check the [API Reference](./api-reference.md) for endpoint details.
- See the [Release Notes](./release-notes.md) for version history.
