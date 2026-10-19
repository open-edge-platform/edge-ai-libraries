<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Deployment Architecture Reference

Covers the Docker Compose topology, config load order, volumes, and GPU
passthrough for the Text To Speech microservice.

---

## Table of Contents

1. [Config Load Order](#config-load-order)
2. [Docker Compose Service Topology](#docker-compose-service-topology)
3. [Volumes and Storage Layout](#volumes-and-storage-layout)
4. [GPU Device Passthrough](#gpu-device-passthrough)
5. [Image Build vs. Pull](#image-build-vs-pull)

---

## Config Load Order

1. `config.yaml` — single source of truth, identical file for standalone and
   container runs. In Compose it is bind-mounted read-only
   (`./config.yaml:/app/text-to-speech/config.yaml:ro`), so host edits apply
   on `docker compose restart text-to-speech` — no rebuild needed.
2. `TEXT_TO_SPEECH__<SECTION>__<KEY>` environment variables — targeted
   overrides layered on top of the file, e.g.
   `TEXT_TO_SPEECH__MODELS__TTS__DEVICE=GPU`.

Two additional env vars affect only the standalone entry point:
`TEXT_TO_SPEECH_SERVER_HOST` / `TEXT_TO_SPEECH_SERVER_PORT` (used by
`python main.py`, not by `uvicorn main:app` directly).
`TEXT_TO_SPEECH_CONFIG_PATH` points at an alternate base config file.

---

## Docker Compose Service Topology

Single service, `text-to-speech`, defined in `docker-compose.yml`:

```yaml
services:
  text-to-speech:
    build: { context: ., dockerfile: Dockerfile }
    image: ${REGISTRY:-intel}/text-to-speech:${RELEASE_TAG:-latest}
    container_name: text-to-speech
    user: "1000:1000"            # fixed — matches the image's baked-in app user
    ports: ["8011:8011"]
    devices: ["/dev/dri:/dev/dri"]
    group_add: ["video", "${RENDER_GID:-992}"]
    environment:
      HF_HOME: /app/text-to-speech/.cache/huggingface
    volumes:
      - ./config.yaml:/app/text-to-speech/config.yaml:ro
      - text_to_speech_models:/app/text-to-speech/models
      - text_to_speech_storage:/app/text-to-speech/storage
      - text_to_speech_cache:/app/text-to-speech/.cache
    healthcheck:
      test: ["CMD", "python3", "-c", "..."]   # GET /health
      start_period: 240s   # model warmup on GPU can take a while
```

Key points:
- `user: "1000:1000"` is **hardcoded** to match both the image's baked-in app
  user and the ownership of the named volumes. Do not change it.
- `group_add` adds the `video` group and `RENDER_GID` so the non-root app
  user can access `/dev/dri` for GPU.
- `container_name: text-to-speech` is explicit (not Compose-generated), which
  is why a leftover container from a previous run produces a name-conflict
  error rather than Compose silently reusing/renaming it.
- `healthcheck.start_period` is intentionally long (240s) to absorb model
  warmup time on GPU; a tighter window would flap the container to
  `unhealthy` during normal boot.
- No `depends_on` — this is a single-service deployment.

---

## Volumes and Storage Layout

Three named volumes, nothing written into the source tree:

| Volume | Container path | Contents |
|--------|-----------------|----------|
| `text_to_speech_models` | `/app/text-to-speech/models` | Downloaded/exported model assets (ONNX for Kokoro, OpenVINO IR for SpeechT5/Qwen) |
| `text_to_speech_storage` | `/app/text-to-speech/storage` | Per-session directories (only populated when `pipeline.persist_outputs: true`): `storage/<session_id>/` with the synthesized WAV and metadata |
| `text_to_speech_cache` | `/app/text-to-speech/.cache` | Hugging Face cache (`HF_HOME`) |

All three are initialized with UID/GID `1000:1000` ownership on first start —
this is why permission errors are rare on a fresh install but common when
reusing volumes created by an earlier root-run (see the troubleshooting
reference).

`app.clear_storage_on_startup: true` (default in `config.yaml`) deletes all
session folders under `storage/` every time the process starts — set this to
`false` if you need session persistence across restarts.

---

## GPU Device Passthrough

`/dev/dri` is passed through unconditionally in `docker-compose.yml` — no
conditional mapping like the NPU pattern used by other services in this
repository. `models.tts.device` accepts `CPU`, `GPU`, or `NPU`, but `NPU`
is not currently functional for any model — see
[model-and-device-config.md](./model-and-device-config.md#npu-accepted-but-universally-non-functional)
for the exact per-model failure behavior before telling a developer this
service simply "has no NPU support."

Requirements for the GPU path to actually work:
- Host has a working Intel iGPU/dGPU with the Intel/OpenVINO host GPU
  runtime installed (`intel-opencl-icd`, `level-zero`) — separate from the
  Python `openvino` package.
- `RENDER_GID` in `.env` matches the host's actual `render` group GID for
  `/dev/dri/renderD*` — this is host-specific; determine it with
  `stat -c '%g' /dev/dri/renderD128` (or the first matching
  `/dev/dri/render*` node) rather than assuming the `992` default.
- Not every model that works on GPU is validated the same way — SpeechT5 on
  GPU and Qwen on GPU are independent validation paths; see
  [model-and-device-config.md](./model-and-device-config.md).

---

## Image Build vs. Pull

`docker-compose.yml` declares both `image:` and `build:` for the same
service:

- `docker compose pull && docker compose up -d` — runs the prebuilt image
  from Docker Hub (`${REGISTRY:-intel}/text-to-speech:${RELEASE_TAG}`).
- `docker compose build && docker compose up -d` — rebuilds from source and
  tags the result with the **same** image reference, so later `docker
  compose up` calls reuse the local build without re-pulling.
- `docker build -t text-to-speech:local .` — direct build outside Compose.

`.env` controls `REGISTRY` (default `intel`) and `RELEASE_TAG` (pinned to the
current release, e.g. `2026.2.0`). Never leave an image reference on
`:latest` in a committed Compose override meant for production use.
