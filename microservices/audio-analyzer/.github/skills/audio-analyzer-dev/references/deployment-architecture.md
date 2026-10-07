<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Deployment Architecture Reference

Covers the Docker Compose topology, config load order, volumes, and device
passthrough for the Audio Analyzer microservice.

---

## Table of Contents

1. [Config Load Order](#config-load-order)
2. [Docker Compose Service Topology](#docker-compose-service-topology)
3. [Volumes and Storage Layout](#volumes-and-storage-layout)
4. [Device Passthrough (GPU/NPU)](#device-passthrough-gpunpu)
5. [Image Build vs. Pull](#image-build-vs-pull)
6. [MinIO as an External Dependency](#minio-as-an-external-dependency)

---

## Config Load Order

1. `config.yaml` — single source of truth, identical file for standalone and
   container runs. In Compose it is bind-mounted read-only
   (`./config.yaml:/app/audio_analyzer/config.yaml:ro`), so host edits apply
   on `docker compose restart audio-analyzer` — no rebuild needed.
2. `AUDIO_ANALYZER__<SECTION>__<KEY>` environment variables — targeted
   overrides layered on top of the file, e.g.
   `AUDIO_ANALYZER__MODELS__ASR__DEVICE=GPU`.

Two additional env vars affect only the standalone entry point:
`AUDIO_ANALYZER_SERVER_HOST` / `AUDIO_ANALYZER_SERVER_PORT` (used by
`python main.py`, not by `uvicorn main:app` directly). `AUDIO_ANALYZER_CONFIG_PATH`
points at an alternate base config file; `AUDIO_ANALYZER_ENV_FILE` preloads a
`.env` file before config parsing.

---

## Docker Compose Service Topology

Single service, `audio-analyzer`, defined in `docker-compose.yml`:

```yaml
services:
  audio-analyzer:
    build: { context: ., dockerfile: docker/Dockerfile }
    image: ${REGISTRY:-intel}/audio-analyzer:${RELEASE_TAG:-latest}
    user: "1000:1000"            # fixed — matches the image's baked-in app user
    ports: ["8010:8010"]
    group_add: ["video", "${RENDER_GID:-992}"]
    environment:
      HF_HOME: /app/audio_analyzer/.cache/huggingface
      ZE_ENABLE_ALT_DRIVERS: libze_intel_npu.so
      HF_TOKEN: ${HF_TOKEN:-}
    volumes:
      - ./config.yaml:/app/audio_analyzer/config.yaml:ro
      - audio_analyzer_models:/app/audio_analyzer/models
      - audio_analyzer_chunks:/app/audio_analyzer/chunks
      - audio_analyzer_storage:/app/audio_analyzer/storage
      - audio_analyzer_cache:/app/audio_analyzer/.cache
    devices:
      - /dev/dri:/dev/dri
      - ${ACCEL_MOUNT_PATH:-/dev/null}:/dev/accel/accel0
    healthcheck:
      test: ["CMD", "python3", "-c", "..."]   # GET /health
      start_period: 240s   # Whisper GPU warmup can take ~120s
```

Key points:
- `user: "1000:1000"` is **hardcoded** to match both the image's baked-in app
  user and the ownership of the named volumes. Do not change it.
- `group_add` adds the `video` group and `RENDER_GID` so the non-root app
  user can access `/dev/dri` for GPU.
- `healthcheck.start_period` is intentionally long (240s) because warming up
  a Whisper model on GPU can take up to ~120s; a tighter window would flap
  the container to `unhealthy` during normal boot.
- No `depends_on` — this is a single-service deployment. MinIO, if used, is
  external (see below).

---

## Volumes and Storage Layout

Four named volumes, nothing written into the source tree:

| Volume | Container path | Contents |
|--------|-----------------|----------|
| `audio_analyzer_models` | `/app/audio_analyzer/models` | Exported OpenVINO IR / whisper.cpp ggml / cached PyTorch weights |
| `audio_analyzer_chunks` | `/app/audio_analyzer/chunks` | Transient FFmpeg-split audio chunks (deleted after use when `pipeline.delete_chunks_after_use: true`) |
| `audio_analyzer_storage` | `/app/audio_analyzer/storage` | Per-session directories: `storage/<session_id>/transcription.txt`, `timestamped_transcription.txt`, `session_state.json` |
| `audio_analyzer_cache` | `/app/audio_analyzer/.cache` | Hugging Face cache (`HF_HOME`) |

All four are initialized with UID/GID `1000:1000` ownership on first start —
this is why permission errors are rare on a fresh install but common when
reusing volumes created by an earlier root-run (see the troubleshooting
reference).

`app.clear_storage_on_startup: true` (default in `config.yaml`) deletes all
session folders under `storage/` every time the process starts — set this to
`false` if you need session persistence across restarts.

---

## Device Passthrough (GPU/NPU)

**GPU (`/dev/dri`)** — passed through unconditionally in `docker-compose.yml`.
No extra host setup beyond having the Intel iGPU/dGPU and its kernel driver
present; the `openvino` provider can then target `device: GPU`.

**NPU (`ACCEL_MOUNT_PATH` → `/dev/accel/accel0`)** — conditional mapping:

```yaml
devices:
  - ${ACCEL_MOUNT_PATH:-/dev/null}:/dev/accel/accel0
```

- Set `ACCEL_MOUNT_PATH` in `.env` (or export before `docker compose up`) to
  the host NPU device node — commonly `/dev/accel/accel0` on Meteor Lake
  systems. The host path is machine-specific; verify with `ls -l /dev/accel/`.
- If `ACCEL_MOUNT_PATH` is unset, Compose maps `/dev/null` into
  `/dev/accel/accel0` so CPU/GPU-only workflows are unaffected.
- `ZE_ENABLE_ALT_DRIVERS=libze_intel_npu.so` must remain set in the container
  environment (already default in Compose) for NPU enumeration.
- `RENDER_GID` must match the host's `render` group GID so the non-root app
  user can access the device node; default fallback is `992`.

Verify the resolved mapping before starting: `docker compose config` and
check `services.audio-analyzer.devices`.

---

## Image Build vs. Pull

`docker-compose.yml` declares both `image:` and `build:` for the same
service:

- `docker compose pull && docker compose up -d` — runs the prebuilt image
  from Docker Hub (`${REGISTRY:-intel}/audio-analyzer:${RELEASE_TAG}`).
- `docker compose build && docker compose up -d` — rebuilds from source and
  tags the result with the **same** image reference, so later `docker
  compose up` calls reuse the local build without re-pulling.
- `docker build -t audio-analyzer:local .` — direct build outside Compose,
  useful for quick iteration without touching the Compose-managed tag.

`.env` controls `REGISTRY` (default `intel`) and `RELEASE_TAG` (pinned to the
current release, e.g. `2026.2.0`). Never leave an image reference on
`:latest` in a committed Compose override meant for production use.

---

## MinIO as an External Dependency

MinIO is **not** a service in `docker-compose.yml` and is never started,
bundled, or managed by Audio Analyzer. It only matters for the
VSS-compatibility endpoint `POST /transcriptions` when the caller supplies a
`minio_bucket`/`video_id`/`video_name` source instead of a direct file
upload.

To wire it up for a deployment:
1. Run MinIO as its own container or use an existing deployment, reachable
   from the Audio Analyzer container's network.
2. Supply `minio.endpoint` / `minio.access_key` / `minio.secret_key` /
   `minio.secure` either by editing the bind-mounted `config.yaml` directly,
   or by adding `AUDIO_ANALYZER__MINIO__*` variables under
   `services.audio-analyzer.environment` in `docker-compose.yml` — values
   placed only in `.env` are **not** auto-forwarded into the container unless
   referenced there explicitly.
3. If `minio.endpoint` is left empty, a MinIO-source request to
   `POST /transcriptions` returns `503`.

See [model-and-device-config.md](./model-and-device-config.md) for the full
config key reference.
