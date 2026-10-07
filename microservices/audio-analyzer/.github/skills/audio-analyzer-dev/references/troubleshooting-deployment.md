<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Troubleshooting Deployment Reference

Deployment and operations failures, in the order a developer is likely to
hit them.

---

## Service Will Not Start

- Confirm port `8010` is free: `ss -ltnp | grep 8010`.
- Confirm `config.yaml` is valid YAML — the service loads it, then applies
  `AUDIO_ANALYZER__...` overrides. Same file for standalone and container.

## `health` Endpoint Fails / Container Shows `unhealthy`

- `docker compose ps` and `docker compose logs -f audio-analyzer`.
- First startup is expected to be slow — model assets may be downloaded or
  exported to `models/` and the Hugging Face cache on first run. The
  built-in healthcheck has a 240s `start_period` specifically to absorb
  Whisper GPU warmup (~120s); do not shorten it without understanding why.
- Behind a corporate proxy, pass `--noproxy '*'` to `curl` against
  `127.0.0.1`.

## GPU Path Is Not Used

- OpenVINO `GPU` requires the Intel/OpenVINO host GPU runtime installed on
  the host — a separate prerequisite from the Python `openvino` package.
- For containers, `/dev/dri` must be exposed (default in
  `docker-compose.yml`).
- **Docker vs. host `.venv`:** Docker Compose is the verified configuration
  for GPU/NPU acceleration. A host `.venv` without the full Intel GPU/NPU
  runtime stack typically reports only `CPU` in
  `ov.Core().available_devices` and fails fast at startup:
  ```text
  RuntimeError: Configured OpenVINO ASR device 'GPU' is not visible in this runtime.
  ```
  This is a host runtime environment limitation, not an application bug —
  switch to Docker Compose rather than trying to patch the host venv.

## NPU Path Is Not Used

Recommended verification sequence:

```bash
# 1. Host NPU node exists
ls -l /dev/accel/

# 2. Resolved Compose device mapping
docker compose config    # check services.audio-analyzer.devices

# 3. Container sees the mapped node
docker compose exec audio-analyzer ls -l /dev/accel/

# 4. OpenVINO runtime sees NPU inside the container
docker compose exec audio-analyzer python3 -c \
  "import openvino as ov; print([str(d).upper() for d in ov.Core().available_devices])"

# 5. Service is healthy
docker compose logs -f audio-analyzer
curl --noproxy '*' http://127.0.0.1:8010/health
```

Checklist if NPU is still not visible:
- `ACCEL_MOUNT_PATH` set in `.env` (or exported) to the correct host device
  node before `docker compose up`.
- `ZE_ENABLE_ALT_DRIVERS=libze_intel_npu.so` present in the container
  environment (default in Compose — do not remove it).
- Container runs with the host `render` group via `RENDER_GID` so the
  non-root app user can access the device node.
- Host Intel NPU driver stack is installed and loaded; re-check after any
  driver update.

When `device: NPU` is configured but not visible, startup fails fast with:

```text
RuntimeError: Configured OpenVINO ASR device 'NPU' is not visible in this runtime.
OpenVINO available_devices=['CPU', 'GPU'].
For NPU, ensure ACCEL_MOUNT_PATH maps the host NPU node into /dev/accel/accel0
and ZE_ENABLE_ALT_DRIVERS=libze_intel_npu.so is set.
```

## `whisper-large` Rejected or Fails at Startup on NPU

This is a **confirmed NPU driver/firmware limitation**, not an application
bug. `whisper-large` (1.55B params) compiles on NPU (~200s) but fails at the
Level Zero `pfnAppendGraphExecute` call during inference with
`ZE_RESULT_ERROR_UNINITIALIZED`. `whisper-tiny`/`base`/`small`/`medium` all
pass NPU inference validation on the same hardware.

**Fix:** set `device: CPU` or `device: GPU` for `whisper-large`, or choose a
smaller model for NPU deployments. See
[model-and-device-config.md](./model-and-device-config.md) for the model
selection matrix.

## Invalid ASR Provider/Device Combination

Startup fails with a validation error naming `models.asr.provider` /
`models.asr.device`. Check against the matrix: `openai` and `whispercpp` are
CPU-only; only `openvino` supports GPU/NPU. Restart after correcting
`config.yaml` or the equivalent `AUDIO_ANALYZER__MODELS__ASR__*` override.

## Permission Errors on Mounted Volumes

```text
PermissionError: [Errno 13] Permission denied: '/app/audio_analyzer/storage/...'
```

The container runs as UID/GID `1000:1000`, and fresh named volumes are
initialized with that ownership — this rarely fails on a clean install. It
usually means the volumes were initialized by an earlier root-only run.
Reset them:

```bash
docker compose down
docker volume rm \
  audio-analyzer_audio_analyzer_models \
  audio-analyzer_audio_analyzer_chunks \
  audio-analyzer_audio_analyzer_storage \
  audio-analyzer_audio_analyzer_cache
docker compose up -d
```

This deletes cached models and session data — confirm with the user before
running it, since it can force a slow re-export/re-download on next start.

## Speaker Diarization Silently Disabled

If `models.asr.diarization: true` but diarization does not appear in
output, check the logs for a warning rather than assuming a crash — this is
soft-fail behavior. Causes: `HF_TOKEN` not set, or the Pyannote model
license not accepted on Hugging Face (one-time gate acceptance per
account). The rest of the service keeps running normally.

## Microphone / `GET /devices` Returns Empty

- Confirm ALSA capture devices exist on the host: `arecord -l`.
- For containers, uncomment the `/dev/snd` device mapping in
  `docker-compose.yml` (commented out by default).

## FFmpeg or `libsndfile` Errors (Standalone Only)

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg alsa-utils libsndfile1
```

## Port 8010 Already in Use

```bash
ss -ltnp | grep 8010
docker compose down
```
