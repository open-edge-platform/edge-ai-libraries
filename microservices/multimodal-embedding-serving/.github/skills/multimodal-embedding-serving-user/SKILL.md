---
name: multimodal-embedding-serving-user
description: >
  Deploy and consume the Multimodal Embedding Serving microservice — bring it
  up with setup.sh + docker compose (from a repo clone, or by fetching those
  same files from GitHub when no clone exists) using the prebuilt
  intel/multimodal-embedding-serving image, embed text/images/videos over REST
  on port 9777, choose among 19 models (CLIP/SigLIP/MobileCLIP/CN-CLIP/Blip2/
  QwenText), or integrate in-process via the Python SDK wheel. Use when an app
  needs embeddings for similarity search or retrieval. Not for modifying the
  service's source — that is multimodal-embedding-serving-dev.
---

# Multimodal Embedding Serving — User

Run and call the embedding service. **Run commands yourself** and relay
output. REST base URL: `http://localhost:9777` (host port hardcoded by
setup.sh; container 8000).

## When to Use

- Deploy the embedding service (Docker Compose or standalone) and confirm health
- Embed text, images, or videos over REST on port 9777
- Choose or switch among the CLIP/SigLIP/MobileCLIP/CN-CLIP/Blip2/QwenText models
- Integrate embeddings in-process via the Python SDK wheel
- Diagnose 400/422 errors or model-capability mismatches

## Example Prompts

Sample Problem-solving scenarios this skill handles end-to-end:

| Example | Problem it solves |
|---|---|
| [image-similarity-finder.md](./example-prompts/image-similarity-finder.md) | Find visually/semantically similar images in a local folder |
| [text-to-image-search.md](./example-prompts/text-to-image-search.md) | Search an image folder with natural-language queries ("Google Lens" for local media) |
| [image-duplicate-detector.md](./example-prompts/image-duplicate-detector.md) | Flag duplicate / near-duplicate images in a folder for cleanup, QC, and dataset deduplication |

## Docs & deploy files — with or without a clone

All paths below are relative to `microservices/multimodal-embedding-serving/`
in the
[edge-ai-libraries](https://github.com/open-edge-platform/edge-ai-libraries)
repo. **No clone?** Fetch any of them from GitHub raw:

```
https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/main/microservices/multimodal-embedding-serving/<path>
```

Load these existing docs only when needed:

| Resource | Load when… |
|---|---|
| `docs/user-guide/api-reference.md` + `docs/user-guide/api-docs/openapi.yaml` | building non-text payloads (image/video, base64, `segment_config`) or parsing responses/errors |
| `docs/user-guide/supported-models.md` | choosing or switching models (dimensions, modalities, language, size) |
| `docs/user-guide/sdk-usage.md` + `docs/user-guide/wheel-installation.md` | integrating in-process via the Python SDK wheel |
| `docs/user-guide/get-started.md` | more curl examples and env-var tables |
| `setup.sh`, `docker/compose.yaml` | the deploy artifacts used below |

## 1. Context routing — repo clone or standalone? REST or SDK?

- **In-process Python integration wanted** (no separate server): the service
  doubles as an SDK — build the wheel with `poetry build` (needs the repo) and
  use `get_model_handler(...)` + `EmbeddingModel`; see
  `docs/user-guide/sdk-usage.md`. Rule of thumb: default to REST; pick the SDK
  when a Python process embeds heavily and an HTTP hop per item would
  dominate. Note: MobileCLIP/Blip2 extras exist only in the Docker image, and
  the wheel is not on PyPI.
- Otherwise detect a clone:
  ```bash
  [ -f setup.sh ] && grep -q 'name = "multimodal-embedding-serving"' pyproject.toml 2>/dev/null \
    && echo REPO || echo STANDALONE
  ```
  **REPO** → Step 2 from the microservice root. **STANDALONE** → fetch the two
  deploy files, then the exact same Step 2:
  ```bash
  RAW=https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/main/microservices/multimodal-embedding-serving
  mkdir -p embedding-serving/docker && cd embedding-serving
  curl -fsSL $RAW/setup.sh -o setup.sh
  curl -fsSL $RAW/docker/compose.yaml -o docker/compose.yaml
  ```
  Already running (`curl -sf localhost:9777/health`) → Step 3.

## 2. Bring-up (identical in both contexts)

1. Pick a model — default `CLIP/clip-vit-b-32` (512-dim, text+image+video).
   Trade-offs: `docs/user-guide/supported-models.md`.
2. `setup.sh` must be **sourced** and hard-fails without
   `EMBEDDING_MODEL_NAME`. `REGISTRY_URL=intel` selects the prebuilt image;
   `--no-build` prevents a source build. Run in the background — first start
   downloads the model:
   ```bash
   bash -c 'export EMBEDDING_MODEL_NAME="CLIP/clip-vit-b-32" REGISTRY_URL=intel TAG=latest \
     && source setup.sh && docker compose -f docker/compose.yaml up -d --no-build'
   ```
   Intel GPU: also `export EMBEDDING_DEVICE=GPU` (setup.sh then auto-enables
   OpenVINO + THROUGHPUT mode).
3. Wait for readiness:
   ```bash
   until curl -sf http://localhost:9777/health; do sleep 5; done
   ```

## 3. Capability check (mandatory before non-text inputs)

```bash
curl -s http://localhost:9777/model/capabilities
```

QwenText models are **text-only** — image/video requests return 400. `GET
/model/current` shows the exact loaded model id to use in requests.

## 4. Embed

Text (single string or list of strings):

```bash
curl -s http://localhost:9777/embeddings -H 'Content-Type: application/json' -d '{
  "model": "CLIP/clip-vit-b-32",
  "input": {"type": "text", "text": "a red truck at a loading dock"},
  "encoding_format": "float"
}'
```

Response: `{"embedding": [...]}` — a flat vector for text/image; a **list of
per-frame vectors** for video inputs.

- `model` must equal the loaded model (else 400).
- Image: `{"type":"image_url","image_url":"https://…"}` (plain string, not a
  nested object) or `image_base64`. Video: `video_url`/`video_base64`/
  `video_frames` with `segment_config` (`num_frames` default 64,
  `extraction_fps`, `frame_indexes`) — full shapes and examples:
  `docs/user-guide/api-reference.md`.

## 5. Stop / clean

- `docker compose -f docker/compose.yaml down`
- Volumes `ov-models` (model caches) and `data-prep` persist; removing them
  forces re-downloads — **confirm with the user first**.

## Troubleshooting

| Symptom | Likely cause → action |
|---|---|
| `source setup.sh` prints ERROR and stops | `EMBEDDING_MODEL_NAME` not exported → export it first |
| No response on 9777 | still starting/downloading → `docker logs -f multimodal-embedding-serving` |
| 400 "model mismatch" | request `model` ≠ loaded model → `GET /model/current` |
| 400 unsupported modality on image/video | text-only model (QwenText) → switch model or send text |
| First non-text request slow | lazy OpenVINO conversion/compile → expected once |
| 422 on `/embeddings` | malformed `input` union → check shapes in `docs/user-guide/api-reference.md` |
| Port 9777 busy | stop the conflicting service (`EMBEDDING_SERVER_PORT` is hardcoded by setup.sh) |
