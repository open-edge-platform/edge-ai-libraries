---
name: vlm-openvino-serving-user
description: >
  Deploy and consume the OpenAI-compatible VLM OpenVINO Serving microservice —
  bring it up with setup.sh + docker compose (from a repo clone, or by
  fetching those same files from GitHub when no clone exists) using the
  prebuilt intel/vlm-openvino-serving image, send chat completions with text,
  images, or video, stream responses, and read telemetry. Use when the user
  wants to run or call the VLM service from their app. Not for modifying the
  service's source — that is vlm-openvino-serving-dev.
---

# VLM OpenVINO Serving — User

Run and call the VLM service. **Run commands yourself** and relay output. The
service speaks the OpenAI chat-completions dialect on host port **9764**
(container 8000), so any OpenAI client works against
`http://localhost:9764/v1` with a dummy API key.

## When to Use

- Deploy the VLM service (Docker Compose or standalone) and confirm health
- Send text/image/video chat completions (OpenAI-compatible) on port 9764
- Stream responses or drive the service with the `openai` Python client
- Read telemetry, queue status, or available devices
- Diagnose 404/503 errors, GPU OOM restarts, or gated-model download failures

## Example Prompts

Sample Problem-solving scenarios this skill handles end-to-end:

| Example | Problem it solves |
|---|---|
| [safety-inspection-assistant.md](./example-prompts/safety-inspection-assistant.md) | Check camera frames for PPE and unsafe scenes against stated rules |
| [retail-shelf-assistant.md](./example-prompts/retail-shelf-assistant.md) | Report empty/misplaced stock from shelf and aisle images |
| [screenshot-understanding.md](./example-prompts/screenshot-understanding.md) | Answer questions about UI screenshots, forms, charts, dashboards |
| [compliance-checker.md](./example-prompts/compliance-checker.md) | Grade an image against a checklist with pass/fail + evidence JSON |
| [image-to-json-extractor.md](./example-prompts/image-to-json-extractor.md) | Turn a visual scene into structured JSON (objects, counts, text, risks) |
| [smart-camera-operator-console.md](./example-prompts/smart-camera-operator-console.md) | Ask live-frame questions like "is the loading bay clear?" |

## Docs & deploy files — with or without a clone

All paths below are relative to `microservices/vlm-openvino-serving/` in the
[edge-ai-libraries](https://github.com/open-edge-platform/edge-ai-libraries)
repo. **No clone?** Fetch any of them from GitHub raw:

```
https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/main/microservices/vlm-openvino-serving/<path>
```

Load these existing docs only when needed:

| Resource | Load when… |
|---|---|
| `docs/user-guide/api-reference.md` + `docs/user-guide/api-docs/openapi.yaml` | building non-trivial payloads (multi-image, video, base64, streaming) or parsing responses |
| `docs/user-guide/get-started.md` | you want ready-made curl examples (base64 image/video, telemetry, device) |
| `docs/user-guide/environment-variables.md` | tuning: device/GPU, ports, compression, log levels, proxies, gated models |
| `docs/user-guide/Overview.md` | choosing a model (capability matrix: image/video per model) |
| `setup.sh`, `docker/compose.yaml` | the deploy artifacts used below |

## 1. Context routing — repo clone or standalone?

```bash
[ -f setup.sh ] && grep -q 'vlm-openvino-serving' pyproject.toml 2>/dev/null \
  && echo REPO || echo STANDALONE
```

- **REPO** → run Step 2 from the microservice root.
- **STANDALONE** → fetch the two deploy files into a fresh directory, then run
  the exact same Step 2 from there:
  ```bash
  RAW=https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/main/microservices/vlm-openvino-serving
  mkdir -p vlm-serving/docker && cd vlm-serving
  curl -fsSL $RAW/setup.sh -o setup.sh
  curl -fsSL $RAW/docker/compose.yaml -o docker/compose.yaml
  ```
- Service already running (`curl -sf http://localhost:9764/health`) → skip to
  Step 3.

## 2. Bring-up (identical in both contexts)

1. Pick a model — default `Qwen/Qwen2.5-VL-3B-Instruct` (image + multi-image +
   video). Full list: `docs/user-guide/Overview.md`.
2. `setup.sh` must be **sourced** (it exports env and uses `return`) and
   requires `VLM_MODEL_NAME`. `REGISTRY_URL=intel` selects the prebuilt Docker
   Hub image and `--no-build` prevents a source build (that's the `-dev`
   skill's job). Run in the background — the first start downloads and
   converts the model, which can take many minutes:
   ```bash
   bash -c 'export VLM_MODEL_NAME="Qwen/Qwen2.5-VL-3B-Instruct" REGISTRY_URL=intel TAG=latest \
     && source setup.sh && docker compose -f docker/compose.yaml up -d --no-build'
   ```
   For Intel GPU: also `export VLM_DEVICE=GPU` (setup.sh then forces int4
   weights and 1 worker). Everything else:
   `docs/user-guide/environment-variables.md`.
3. Wait for health before any request:
   ```bash
   until curl -sf http://localhost:9764/health; do sleep 10; done
   ```
   Watch progress with `docker logs -f vlm-openvino-serving` if it takes long.

## 3. Query the service

Basic text + image chat completion:

```bash
curl -s http://localhost:9764/v1/chat/completions -H 'Content-Type: application/json' -d '{
  "model": "Qwen/Qwen2.5-VL-3B-Instruct",
  "messages": [{"role": "user", "content": [
    {"type": "text", "text": "Describe this image in one sentence."},
    {"type": "image_url", "image_url": {"url": "https://example.com/dock.jpg"}}
  ]}],
  "max_completion_tokens": 100
}'
```

- `model` must equal the configured `VLM_MODEL_NAME` (check `GET /v1/models`),
  otherwise 404.
- Python: use the `openai` package with
  `OpenAI(base_url="http://localhost:9764/v1", api_key="EMPTY")`.
- Streaming: add `"stream": true` (SSE chunks). Video (`video` frame lists /
  `video_url` mp4, Qwen models only), base64 inputs, and full schemas:
  `docs/user-guide/api-reference.md`; worked examples:
  `docs/user-guide/get-started.md`.

## 4. Observe

- `GET /v1/telemetry?limit=5` — per-request latency/token metrics (none for
  SmolVLM).
- `GET /v1/queue-status` — active vs queued requests.
- `GET /device` — OpenVINO devices visible in the container.

## 5. Stop / clean

- `docker compose -f docker/compose.yaml down`
- The `ov-models` volume keeps model caches so restarts are fast. Removing it
  (`docker volume rm ov-models`) forces a full re-download — **confirm with
  the user first**.

## Troubleshooting

| Symptom | Likely cause → action |
|---|---|
| `curl` exit 7 / no response on 9764 | not started or still pulling → `docker ps`, `docker logs -f vlm-openvino-serving` |
| `/health` returns 503 | model still downloading/converting → keep waiting, watch logs |
| 404 on chat completions | `model` mismatch → `GET /v1/models` and use that exact id |
| `error code: -5` on GPU | GPU OOM; the service **intentionally restarts itself** (`os.execv`) to recover — not a crash loop → smaller model, int4 weights, fewer concurrent requests |
| First request very slow | model compile on first inference → expected once per start |
| Port 9764 busy | `export VLM_SERVICE_PORT=<other>` before bring-up |
| Gated model download fails | `export HUGGINGFACE_TOKEN=...` — see `docs/user-guide/environment-variables.md` |
