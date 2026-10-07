---
name: audio-analyzer-dev
description: >
  Build, configure, deploy, and operate the Audio Analyzer microservice.
  Use this skill when a developer or operator wants to: run the service with
  Docker Compose or on the host; build the image from source; select an ASR
  provider and device (openai/openvino/whispercpp on CPU/GPU/NPU); enable
  speaker diarization or voice sentiment; wire Docker volumes, device
  passthrough (`/dev/dri`, `ACCEL_MOUNT_PATH`); tune `config.yaml` and
  `AUDIO_ANALYZER__...` overrides; run the root-level or tiered test suites;
  validate a Dockerfile/Compose change with the Tier-3 build test suite;
  inspect the active model/device or last-call latency via `/v1/model-info`
  and `/v1/performance`; or debug a startup, permission, GPU/NPU-visibility,
  or stuck-model failure. Trigger on phrases like "deploy audio analyzer",
  "run audio-analyzer in docker", "build audio-analyzer image", "enable
  NPU", "enable diarization", "configure whisper model", "GPU not
  detected", "permission denied storage", "audio analyzer won't start",
  "whisper-large NPU error", "run audio-analyzer tests", "which model is
  active", "check ASR latency", or "validate the docker build".
argument-hint: >
  Describe what you want to deploy or debug (e.g. "deploy audio-analyzer with
  GPU acceleration" or "enable speaker diarization with my HF token")
---

# Audio Analyzer Developer Skill

Help developers and operators build, configure, deploy, and troubleshoot the
Audio Analyzer microservice.

> Codebase root: `microservices/audio-analyzer/`

## When to Use

- Deploying the service with Docker Compose (prebuilt image or local build)
- Running the service directly on the host with a Python virtualenv
- Choosing and validating an ASR provider/device combination
- Enabling speaker diarization (Hugging Face gated model + token) or voice
  sentiment analysis
- Wiring GPU (`/dev/dri`) or NPU (`ACCEL_MOUNT_PATH`) device passthrough
- Debugging a service that will not start, fails health checks, reports the
  wrong devices, or raises permission errors on mounted volumes
- Running the root-level lightweight tests or the tiered functional suite
  (`tier1`/`tier2`/`tier3`), including the Tier-3 Docker build verification
  tests
- Inspecting a running deployment's active model/device or last-call
  latency via the undocumented debug endpoints

## Quick Facts

| Fact | Value |
|------|-------|
| Default port | `8010` (standalone and Docker both bind here; VSS Compose expects `8000` — override via `AUDIO_ANALYZER_SERVER_PORT`) |
| Config file | `config.yaml`, same file for standalone and container runs |
| Config overrides | `AUDIO_ANALYZER__<SECTION>__<KEY>=<value>` environment variables |
| Container user | UID/GID `1000:1000` (baked into the image — do not change) |
| Named volumes | `audio_analyzer_models`, `audio_analyzer_chunks`, `audio_analyzer_storage`, `audio_analyzer_cache` |
| ASR provider/device matrix | `openai`: CPU only · `whispercpp`: CPU only · `openvino`: CPU \| GPU \| NPU |
| Health check | `GET /health` → `{"status": "ok"}` |
| Debug endpoints | `GET /v1/model-info` (active model/provider/device), `GET /v1/performance` (last ASR call latency) — not in the published API reference |
| Test suites | Root-level `tests/*.py` (unmarked, no model weights/GPU needed) **and** tiered `tests/functional/` (`tier1`/`tier2`/`tier3`) — different invocations, see below |

## Reference Lookup

| Reference | When to read |
|-----------|-------------|
| [deployment-architecture.md](./references/deployment-architecture.md) | Compose service topology, volumes, device passthrough, config load order, image build vs. pull |
| [model-and-device-config.md](./references/model-and-device-config.md) | ASR provider/device matrix, precision/weight_format, diarization and sentiment setup, per-request device override |
| [troubleshooting-deployment.md](./references/troubleshooting-deployment.md) | Permission errors, GPU/NPU visibility, whisper-large NPU limitation, slow first startup |
| [testing-and-debugging.md](./references/testing-and-debugging.md) | Both test suites' correct invocations, the Tier-3 Docker build suite, debug endpoints, startup failure diagnosis |

## Example Prompts

| File | Covers |
|------|--------|
| [examples-prompts/docker-compose-deploy.md](./examples-prompts/docker-compose-deploy.md) | Standing up the service with Docker Compose and verifying health |
| [examples-prompts/enable-gpu-npu-acceleration.md](./examples-prompts/enable-gpu-npu-acceleration.md) | Configuring OpenVINO GPU/NPU device passthrough end-to-end |
| [examples-prompts/enable-diarization-and-sentiment.md](./examples-prompts/enable-diarization-and-sentiment.md) | Turning on speaker diarization and voice sentiment analysis |
| [examples-prompts/run-tests-and-debug.md](./examples-prompts/run-tests-and-debug.md) | Running the correct test suite and diagnosing a failing deployment |

---

## Architecture Summary

```
audio-analyzer/
├── api/
│   ├── openai_endpoints.py     ← /v1/audio/transcriptions (+ /stream, SSE)
│   ├── realtime_endpoints.py   ← /v1/realtime WebSocket
│   └── custom_endpoints.py     ← /health, /devices, VSS-compatible routes
├── pipeline.py                 ← orchestrates preprocessing → ASR → sentiment
├── components/
│   ├── asr/                    ← base_asr.py, openai/, openvino/, openvino_genai/, whispercpp/, diarization/
│   ├── asr_component.py
│   ├── sentiment/               ← speechbrain/
│   └── sentiment_component.py
├── utils/
│   ├── config_loader.py        ← config.yaml + AUDIO_ANALYZER__ env merge
│   ├── openvino_runtime_validation.py ← provider/device validation, NPU checks
│   ├── latency_store.py        ← thread-safe last-call latency, backs /v1/performance
│   ├── ensure_model.py / preload_models.py
│   └── session_manager.py / storage_manager.py / session_state_manager.py
├── config.yaml                 ← single source of truth for runtime behavior
├── docker-compose.yml          ← service, volumes, device mounts, healthcheck
├── docker/Dockerfile
└── tests/
    ├── *.py                    ← Suite A: unmarked unittest tests, no model weights/GPU
    └── functional/
        ├── conftest.py          ← stubs heavy ML libs for tier1 imports
        ├── *.py                 ← Suite B: tier1/tier2/tier3 pytest-marked tests
        └── build/
            └── test_build.py    ← tier3 — real `docker compose build` validation
```

---

## Procedure: Deploying with Docker Compose

Read [deployment-architecture.md](./references/deployment-architecture.md) first.

1. From `microservices/audio-analyzer/`, review `config.yaml` and edit the
   `models.asr`, `sentiment`, and `audio_preprocessing` sections as needed —
   this file is bind-mounted, so edits apply on `docker compose restart`.
2. Copy `.env.example` to `.env` and set `REGISTRY`, `RELEASE_TAG`, and (for
   NPU) `ACCEL_MOUNT_PATH`.
3. Start the service:
   ```bash
   docker compose pull   # or: docker compose build
   docker compose up -d
   ```
4. Verify:
   ```bash
   curl --noproxy '*' http://127.0.0.1:8010/health
   ```

> [!IMPORTANT]
> The container always runs as UID/GID `1000:1000`. Named volumes are
> initialized with that ownership on first run — do not override `user:` in
> Compose, and do not reuse volumes created by an older root-only run (see
> the troubleshooting reference for the reset procedure).

---

## Procedure: Choosing and Validating an ASR Provider/Device

Read [model-and-device-config.md](./references/model-and-device-config.md) first.

The supported provider/device matrix is fixed:

| Provider | CPU | GPU | NPU |
|----------|-----|-----|-----|
| `openai` | ✅ | ❌ | ❌ |
| `whispercpp` | ✅ | ❌ | ❌ |
| `openvino` | ✅ | ✅ | ✅ |

Set `models.asr.provider` and `models.asr.device` in `config.yaml`. For GPU
or NPU, use the Docker Compose path — it is the verified configuration for
accelerator visibility (`/dev/dri` is passed through by default; NPU needs
`ACCEL_MOUNT_PATH`). Running directly from a host `.venv` without the full
Intel GPU/NPU runtime stack typically reports only `CPU` in
`ov.Core().available_devices` and fails fast at startup instead of silently
falling back.

> [!IMPORTANT]
> `whisper-large` is confirmed unsupported for inference on NPU (Level Zero
> `pfnAppendGraphExecute` failure on current driver/firmware) even though it
> loads and compiles. Use `whisper-tiny`/`base`/`small`/`medium` on NPU, or
> move `whisper-large` to `CPU`/`GPU`.

---

## Procedure: Building From Source or Running Standalone

1. Docker build: `docker compose build && docker compose up -d` (tags the
   same `${REGISTRY}/audio-analyzer:${RELEASE_TAG}` so later `up` calls reuse
   the local build), or `docker build -t audio-analyzer:local .` directly.
2. Standalone: install host packages (`ffmpeg`, `alsa-utils`, `libsndfile1`),
   create a venv, `pip install -r requirements.txt`, then `python main.py`
   (default bind `127.0.0.1:8010`; override with `AUDIO_ANALYZER_SERVER_HOST`
   / `AUDIO_ANALYZER_SERVER_PORT`).

---

## Procedure: Running Tests and Debugging the Codebase

Read [testing-and-debugging.md](./references/testing-and-debugging.md) first
— this codebase has **two independently organized test suites**, and using
the wrong invocation silently runs zero tests.

```bash
# Suite A — root-level, unmarked, no model weights/GPU needed
pip install pytest httpx
pytest tests/test_streaming_endpoints.py tests/test_vss_endpoints.py -v

# Suite B — tiered functional tests (explicit path required; testpaths
# in pytest.ini only auto-discovers tests/functional/build on its own)
pytest tests/functional -v -m tier1    # CI-safe, no model weights/Docker/GPU
pytest tests/functional -v -m tier2    # needs HF_TOKEN
pytest tests/functional -v -m tier3    # needs Docker daemon / full ML stack / live server

# Tier-3 Docker build verification — validates Dockerfile/Compose changes
# against a live Docker daemon without deploying the service
pytest tests/functional/build/test_build.py -m tier3 -v -s
```

> [!IMPORTANT]
> Suite A's tests have no `tier1`/`tier2`/`tier3` markers at all — never add
> a `-m` filter when running them, or every test is excluded. Suite B's
> `conftest.py` stubs heavy ML libraries (`torch`, `openvino`, `pyannote`,
> `whisper`, etc.) into `sys.modules` so `tier1` tests can import app code
> without the full ML stack installed; an already-installed real package
> always takes precedence.

For a running deployment, check the active model/device and last-call
latency without digging through logs:

```bash
curl --noproxy '*' http://127.0.0.1:8010/v1/model-info
curl --noproxy '*' http://127.0.0.1:8010/v1/performance
```

If a container exits immediately after startup, grep logs for the exact
phrase `"ASR model is unavailable"` first — it distinguishes a model
acquisition failure (`ensure_model`) from a model loading failure
(`preload_models`) before you investigate further.

---

## Procedure: Debugging a Deployment Failure

Read [troubleshooting-deployment.md](./references/troubleshooting-deployment.md)
for the full catalog. Quick diagnosis checklist:

```bash
# 1. Is the container up and healthy?
docker compose ps
docker compose logs -f audio-analyzer

# 2. Is the configured device actually visible to OpenVINO inside the container?
docker compose exec audio-analyzer python3 -c \
  "import openvino as ov; print([str(d).upper() for d in ov.Core().available_devices])"

# 3. For NPU specifically, confirm the host node and the resolved Compose mapping
ls -l /dev/accel/
docker compose config   # check services.audio-analyzer.devices

# 4. Is this a permission problem on a reused volume?
docker compose exec audio-analyzer id        # expect uid=1000 gid=1000
```

Common root causes, roughly in likelihood order:
- Config/device mismatch (e.g. `provider: openai` with `device: GPU`) — fails
  startup validation immediately with a clear error.
- NPU/GPU runtime not visible because the service was started via host
  `.venv` instead of Docker Compose.
- `ACCEL_MOUNT_PATH` not set (or pointing at the wrong node) before
  `docker compose up`.
- Named volumes initialized by an earlier root-only run — permission denied
  under `/app/audio_analyzer/storage/...`.
- Diarization enabled without an accepted Pyannote license / valid `HF_TOKEN`
  — the service does not crash, it logs a warning and disables diarization
  for that session only.
