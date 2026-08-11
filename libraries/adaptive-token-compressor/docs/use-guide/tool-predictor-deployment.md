# Tool Predictor — Bring Your Own vLLM Docker Compose

The `ToolCompressor` in `adaptive_token_compressor.tool` uses an external LLM to score tool relevance.

This library does **not** provide or maintain a vLLM deployment yaml anymore.
Please start your own model service with Docker Compose and expose an OpenAI-compatible
chat completions endpoint.

## Experiment Baseline

Internal validation for tool prediction was run with:

- Model: `Qwen/Qwen3.6-35B-A3B`
- Image: `intel/llm-scaler-vllm:0.21.0-b1`

You may use different models/images as long as the endpoint is OpenAI-compatible.

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

OpenAI-compatible chat completions:

```
http://<your-host>:<your-port>/v1/chat/completions
```

Use the host/port exposed by your own Docker Compose service.

Wire into the library's tool predictor:

```python
from adaptive_token_compressor.tool import ToolCompressor, HTTPToolPredictor

predictor = HTTPToolPredictor(
    predictor_url="http://<your-host>:<your-port>/v1/chat/completions",
    predictor_model="Qwen/Qwen3.6-35B-A3B",
)
```

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

You're not locked into one exact deployment. Any OpenAI-compatible endpoint
serving your chosen model works.

## See also

- Companion lingua server: [lingua-deployment.md](lingua-deployment.md)
