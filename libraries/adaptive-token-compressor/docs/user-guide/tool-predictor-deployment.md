# Tool Predictor — Bring Your Own vLLM Docker Compose

The `ToolCompressor` in `adaptive_token_compressor.tool` uses an external model
to score tool relevance. Two predictor backends are supported, each needing a different endpoint:

| `predictor_backend` | Validated model | Endpoint |
| ------------------- | ----------------- | ---------- |
| `"generative"` (default) | `Qwen/Qwen3.6-35B-A3B` | OpenAI-compatible `/v1/chat/completions` |
| `"reranker"` | `Qwen/Qwen3-Reranker-0.6B` | Jina/Cohere-style `/v1/rerank` |

See [Predictor configurations](./get-started.md#predictor-configurations) for how to choose between them.

This library does **not** provide or maintain a vLLM deployment yaml anymore.
Please start your own model service with Docker Compose and expose the endpoint
for the backend you chose.

## Experiment Baseline

Internal validation was run with:

| `predictor_backend` | Model | Image | Endpoint |
| ------------------- | ------- | ------- | ---------- |
| `"generative"` | `Qwen/Qwen3.6-35B-A3B` | `intel/llm-scaler-vllm:0.21.0-b1` | `/v1/chat/completions` |
| `"reranker"` | `Qwen/Qwen3-Reranker-0.6B` | `intel/llm-scaler-vllm:0.21.0-b1` | `/v1/rerank` |

You may use different models/images as long as the endpoint matches the contract below.

## Setup (Bring Your Own Compose)

1. Prepare your own Docker Compose yaml for vLLM.
2. Mount your model weights path in that yaml.
3. Start your service, for example:

   ```bash
   docker compose -f /path/to/your-vllm-compose.yaml up -d
   ```

4. Confirm the service endpoint is reachable.

If needed, adjust your system GPU group GIDs (typical Debian/Ubuntu values are `44` for `video`
and `992` for `render`):

```bash
getent group video  | cut -d: -f3
getent group render | cut -d: -f3
```

## Endpoint

Use the host/port exposed by your own Docker Compose service.

### Generative backend

OpenAI-compatible chat completions:

```
http://<your-host>:<your-port>/v1/chat/completions
```

Wire into the tool compressor:

```python
from adaptive_token_compressor.tool import ToolCompressor

compressor = ToolCompressor(
    predictor_url="http://<your-host>:<your-port>/v1/chat/completions",
    predictor_model="Qwen/Qwen3.6-35B-A3B",
    predictor_backend="generative",
    score_threshold=2.0,
)
```

### Reranker backend

Jina/Cohere-style rerank API, as served by vLLM for reranker models:

```
http://<your-host>:<your-port>/v1/rerank
```

The compressor sends one request per turn that scores every tool:

```json
{"model": "Qwen/Qwen3-Reranker-0.6B", "query": "<task and agent context>", "documents": ["<tool 1>", "..."], "top_n": <number of tools>}
```

The response must contain a `results` array with one entry per document, each
with its `index` and a `relevance_score` in [0, 1]. A missing or out-of-range
score fails the prediction, and the request is passed through uncompressed.
Health checks use `/v1/models` on the same host/port, which must list the
model name.

Wire into the tool compressor:

```python
from adaptive_token_compressor.tool import ToolCompressor

compressor = ToolCompressor(
    predictor_url="http://<your-host>:<your-port>/v1/rerank",
    predictor_model="Qwen/Qwen3-Reranker-0.6B",
    predictor_backend="reranker",
    top_k=20,
)
```

Size `top_k` to the number of tools per request; see
[Predictor configurations](./get-started.md#predictor-configurations).

## Override the port

Use any host port you prefer by changing the port mapping in your own
Docker Compose yaml, then restart the service.

```bash
docker compose -f /path/to/your-vllm-compose.yaml up -d
```

## Stop

```bash
docker compose -f /path/to/your-vllm-compose.yaml down
```

## Alternative

You're not locked into one exact deployment. Any endpoint that matches the
contract above for your chosen backend works.

## See also

- Library usage and configuration: [get-started.md](./get-started.md)
- Companion compress server: [compress-server-deployment.md](./compress-server-deployment.md)
