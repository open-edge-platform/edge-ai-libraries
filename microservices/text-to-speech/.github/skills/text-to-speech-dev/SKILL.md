---
name: text-to-speech-dev
description: >
  Build, configure, deploy, and operate the Text To Speech microservice.
  Use this skill when a developer or operator wants to: run the service with
  Docker Compose or on the host; build the image from source; select a TTS
  model (Kokoro, SpeechT5, Qwen3-TTS) and runtime/device/precision; wire
  Docker volumes and `/dev/dri` GPU passthrough; tune `config.yaml` and
  `TEXT_TO_SPEECH__...` overrides; or debug a startup, permission,
  GPU-visibility, or stuck-container failure. Trigger on phrases like
  "deploy text-to-speech", "run text-to-speech in docker", "build
  text-to-speech image", "switch TTS model", "enable GPU for TTS",
  "configure Qwen voice design", "GPU context not initialized",
  "permission denied storage", "text-to-speech won't start", or "container
  name already in use".
argument-hint: >
  Describe what you want to deploy or debug (e.g. "deploy text-to-speech with
  Qwen3-TTS on GPU" or "switch the default model to SpeechT5")
---

# Text To Speech Developer Skill

Help developers and operators build, configure, deploy, and troubleshoot the
Text To Speech microservice.

> Codebase root: `microservices/text-to-speech/`

## When to Use

- Deploying the service with Docker Compose (prebuilt image or local build)
- Running the service directly on the host with a Python virtualenv
- Choosing a TTS model (Kokoro, SpeechT5, or Qwen3-TTS) and its
  runtime/device/precision
- Wiring GPU device passthrough (`/dev/dri`, `RENDER_GID`)
- Debugging a service that will not start, fails health checks, reports GPU
  context errors, or raises permission errors on mounted volumes
- Resolving a leftover container name conflict

## Quick Facts

| Fact | Value |
|------|-------|
| Default port | `8011` (standalone and Docker both bind here) |
| Config file | `config.yaml`, same file for standalone and container runs |
| Config overrides | `TEXT_TO_SPEECH__<SECTION>__<KEY>=<value>` environment variables |
| Container user | UID/GID `1000:1000` (baked into the image — do not change) |
| Named volumes | `text_to_speech_models`, `text_to_speech_storage`, `text_to_speech_cache` |
| Shipped default model | `kokoro` (ONNX runtime, CPU-only, `runtime`/`device` config ignored) — the docs' worked examples center on SpeechT5/Qwen, so confirm `models.tts.name` before assuming which model is active |
| Device support | `CPU` and `GPU` only — **no NPU path** for this service |
| Health check | `GET /health` → `{"status": "ok"}` |

## Reference Lookup

| Reference | When to read |
|-----------|-------------|
| [deployment-architecture.md](./references/deployment-architecture.md) | Compose service topology, volumes, `/dev/dri` passthrough, config load order, image build vs. pull |
| [model-and-device-config.md](./references/model-and-device-config.md) | Kokoro/SpeechT5/Qwen model matrix, runtime/device/precision support, known GPU precision caveat |
| [troubleshooting-deployment.md](./references/troubleshooting-deployment.md) | Permission errors, GPU context failures, container name conflicts, slow first startup |

## Example Prompts

| File | Covers |
|------|--------|
| [examples-prompts/docker-compose-deploy.md](./examples-prompts/docker-compose-deploy.md) | Standing up the service with Docker Compose and verifying health |
| [examples-prompts/switch-tts-model.md](./examples-prompts/switch-tts-model.md) | Switching between Kokoro, SpeechT5, and Qwen3-TTS |
| [examples-prompts/enable-gpu-acceleration.md](./examples-prompts/enable-gpu-acceleration.md) | Configuring OpenVINO GPU device passthrough end-to-end |

---

## Architecture Summary

```
text-to-speech/
├── api/
│   ├── openai_endpoints.py     ← POST /v1/audio/speech
│   ├── streaming_endpoints.py  ← POST /v1/audio/speech/stream (SSE, phrase-level)
│   └── custom_endpoints.py     ← /health, /v1/audio/voices, /v1/model-info, /v1/performance
├── pipeline.py                 ← orchestrates model load/warmup, speaker resolution, synthesis
├── components/
│   ├── tts/
│   │   ├── base.py / factory.py       ← backend selection
│   │   ├── kokoro/                     ← onnxruntime-based Kokoro backend
│   │   ├── openvino/                   ← OpenVINO SpeechT5/Qwen backends
│   │   ├── pytorch/                    ← PyTorch SpeechT5/Qwen backends
│   │   └── speecht5_voices.py          ← bundled SpeechT5 voice table
│   └── tts_component.py
├── utils/
│   ├── config_loader.py        ← config.yaml + TEXT_TO_SPEECH__ env merge
│   ├── ensure_kokoro.py / ensure_parler.py / ensure_qwen.py / ensure_speecht5.py
│   └── session_manager.py / storage_manager.py / session_state_manager.py
├── config.yaml                 ← single source of truth for runtime behavior
├── docker-compose.yml          ← service, volumes, /dev/dri mount, healthcheck
└── Dockerfile
```

---

## Procedure: Deploying with Docker Compose

Read [deployment-architecture.md](./references/deployment-architecture.md) first.

1. From `microservices/text-to-speech/`, review `config.yaml` and set
   `models.tts.name`/`runtime`/`device`/`dtype` as needed — this file is
   bind-mounted, so edits apply on `docker compose restart`.
2. Copy `.env.example` to `.env` and set `REGISTRY`, `RELEASE_TAG`, and (for
   GPU) `RENDER_GID`.
3. Start the service:
   ```bash
   docker compose pull   # or: docker compose build
   docker compose up -d
   ```
4. Verify:
   ```bash
   curl --noproxy '*' http://127.0.0.1:8011/health
   ```

> [!IMPORTANT]
> The container always runs as UID/GID `1000:1000`. Named volumes are
> initialized with that ownership on first run — do not override `user:` in
> Compose, and do not reuse volumes created by an older root-only run (see
> the troubleshooting reference for the reset procedure).

---

## Procedure: Choosing a Model, Runtime, and Device

Read [model-and-device-config.md](./references/model-and-device-config.md) first.

| Model | `name` value | Runtime | Device | Notes |
|-------|--------------|---------|--------|-------|
| Kokoro | `kokoro` | always onnxruntime — `runtime`/`device` config ignored | CPU only | Shipped default; lightest-weight |
| SpeechT5 | `microsoft/speecht5_tts` | `openvino` or `pytorch` | `CPU` or `GPU` | English only, 7 bundled voices, rejects `instructions` |
| Qwen3-TTS | `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice` | `openvino` or `pytorch` | `CPU` or `GPU` | `custom_voice` or `voice_design` variant, supports `instructions` |

> [!IMPORTANT]
> `dtype: int4` on integrated GPU is known to produce audible noise in the
> synthesized output. `fp16` on GPU is validated and performs well after
> warmup. Do not recommend `int4` for a GPU deployment without calling this
> out.

---

## Procedure: Building From Source or Running Standalone

1. Docker build: `docker compose build && docker compose up -d` (tags the
   same `${REGISTRY}/text-to-speech:${RELEASE_TAG}` so later `up` calls reuse
   the local build), or `docker build -t text-to-speech:local .` directly.
2. Standalone: install `libsndfile1`, create a venv, `pip install -r
   requirements.txt`, then `python main.py` (default bind `127.0.0.1:8011`;
   override with `TEXT_TO_SPEECH_SERVER_HOST` / `TEXT_TO_SPEECH_SERVER_PORT`).
3. Sanity-check imports before starting standalone if startup fails
   mysteriously:
   ```bash
   python -c "import fastapi, openvino, soundfile; print('imports-ok')"
   ```

---

## Procedure: Debugging a Deployment Failure

Read [troubleshooting-deployment.md](./references/troubleshooting-deployment.md)
for the full catalog. Quick diagnosis checklist:

```bash
# 1. Is the container up and healthy?
docker compose ps
docker compose logs --tail 100 text-to-speech

# 2. Is port 8011 free, or is an old container holding the name?
ss -ltnp | grep 8011
docker rm -f text-to-speech   # if "container name already in use"

# 3. GPU-specific: does the host expose the render node, and is RENDER_GID correct?
ls -l /dev/dri
stat -c '%g' /dev/dri/render* | head -1   # compare against .env RENDER_GID

# 4. Is this a permission problem on a reused volume?
docker compose exec text-to-speech id        # expect uid=1000 gid=1000
```

Common root causes, roughly in likelihood order:
- Leftover container with the same name from a previous run — remove it
  explicitly rather than assuming Compose will resolve the conflict.
- `RENDER_GID` not matching the host's actual render group GID — this is
  host-specific and must never be hardcoded to a prior machine's value.
- Named volumes initialized by an earlier root-only run — permission denied
  under `/app/text-to-speech/storage/...`.
- GPU failure isolated to a specific model — a working SpeechT5 GPU path
  does not guarantee Qwen GPU initialization also succeeds; test with
  `device: CPU` first, then SpeechT5 GPU, then Qwen GPU.
