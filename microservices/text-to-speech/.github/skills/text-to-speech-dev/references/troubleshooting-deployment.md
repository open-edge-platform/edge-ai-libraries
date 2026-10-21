<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Troubleshooting Deployment Reference

Deployment and operations failures, in the order a developer is likely to
hit them.

---

## Service Will Not Start

Check in order:

1. Port `8011` is free: `ss -ltnp | grep 8011`.
2. The active config is valid YAML. The service loads `config.yaml`, then
   applies `TEXT_TO_SPEECH__...` overrides. Same file for standalone and
   container.
3. Docker is being run from the `text-to-speech/` directory that actually
   contains this service's `docker-compose.yml` — `docker compose down`/`up`
   from the wrong directory silently targets the wrong project.
4. No leftover container name conflict (see next section).

## Container Name Already In Use

**Symptom:**
```text
Conflict. The container name "/text-to-speech" is already in use
```

**Cause:** `docker-compose.yml` sets an explicit `container_name:
text-to-speech`, so Compose will not auto-resolve a naming collision the way
it would for an auto-generated name.

**Fix:**
```bash
docker rm -f text-to-speech
docker compose up -d
```

## First Startup Is Slow

Expected. On first run the service may download model artifacts, export
models to OpenVINO IR under `models/`, and populate the Hugging Face cache
under `.cache/huggingface/`. Later starts reuse those cached files.

## Model Download Times Out Behind A Proxy

If model downloads succeed on the host but time out inside the container,
the proxy environment variables were not forwarded. Export them before
starting Compose — it passes both uppercase and lowercase variants through
to the service:

```bash
export HTTP_PROXY="http://proxy.example.com:8080"
export HTTPS_PROXY="$HTTP_PROXY"
export NO_PROXY="localhost,127.0.0.1"
docker compose up -d --force-recreate
docker compose logs -f text-to-speech
```

Never commit proxy URLs containing credentials — set authenticated proxy
values in the shell or another approved secret-management mechanism, not in
a tracked `.env` file.

## `health` Endpoint Fails

```bash
docker compose ps
docker compose logs -f text-to-speech
curl --noproxy '*' http://127.0.0.1:8011/health
```

For standalone:
```bash
source .venv/bin/activate
python -c "import fastapi, openvino, soundfile; print('imports-ok')"
python main.py
curl --noproxy '*' http://127.0.0.1:8011/health
```

Behind a corporate proxy, always use `--noproxy '*'` for local health checks.

## GPU Startup Fails In Docker

**Typical fatal error:**
```text
[GPU] Context was not initialized for 0 device
```

Check in this order — do not change model code before exhausting these:

1. `/dev/dri` is exposed to the container (already default in
   `docker-compose.yml`).
2. The host actually has GPU device nodes: `ls -l /dev/dri`.
3. The container has the right group access for the render node. On many
   systems `/dev/dri/renderD*` is owned by group `render`, not `video`. This
   service runs as a non-root user, so it must be given the host render
   group ID explicitly:
   ```bash
   # In .env:
   RENDER_GID=$(stat -c '%g' /dev/dri/render* | head -1)
   ```
   `RENDER_GID` is **host-specific** — never assume `992` (the Compose
   fallback default) is correct on a new machine.
4. Restart cleanly:
   ```bash
   docker compose down
   docker rm -f text-to-speech 2>/dev/null || true
   docker compose up --build
   ```
5. If GPU still fails, isolate whether the problem is Docker permissions or
   the model/runtime path:
   - Try the same deployment with `device: CPU` first.
   - If the configured model is **SpeechT5**, this isolation is meaningful —
     SpeechT5 GPU is a genuinely separate validation from SpeechT5 CPU.
   - If the configured model is **Qwen3-TTS**, device isolation will not
     help — Qwen3-TTS currently fails at startup with a dependency error
     regardless of `device` (see
     [model-and-device-config.md](./model-and-device-config.md#known-limitations-models-that-cannot-currently-run)).
     A "GPU context" error cannot actually originate from a Qwen3-TTS
     deployment, because startup fails on the `qwen-tts` import before any
     GPU/OpenVINO code runs — if you see a genuine GPU context error on a
     Qwen3-TTS config, re-check `models.tts.name`; something else is
     configured than what was reported.

## NPU Does Not Behave As Expected

No TTS model in this service can currently complete a request on NPU, even
though `NPU` is an accepted `device` value. See
[model-and-device-config.md](./model-and-device-config.md#npu-accepted-but-universally-non-functional)
for the full per-model failure matrix (`utils/device_validation.py::resolve_tts_device`,
Kokoro/pytorch-runtime/SpeechT5/Qwen3-TTS each fail differently). Key point
for diagnosis: `preload_models()` does not run this validation at startup,
so an invalid `models.tts.device: NPU` can still let the service **start**
(the mismatch only logs as a warmup warning) — only a **per-request** `NPU`
selection is rejected immediately, before that request's model loads.

## Qwen3-TTS / Parler-TTS Fail At Startup (Dependency Conflict, Not a Bug)

If `models.tts.name` is set to a Qwen3-TTS or Parler-TTS value and the
container fails to start (or `main.py`'s startup event raises), check logs
for one of these two distinct causes before assuming a deployment mistake:

- `"qwen-tts is not installed. Install dependencies from requirements.txt
  before starting the service."` — Qwen3-TTS requires `qwen-tts`, which
  pins `transformers==4.57.3`; this service requires `transformers>=5.3.0`
  for security fixes, so the two cannot coexist and `qwen-tts` is
  deliberately not installed. This is not fixable by changing config — do
  not deploy Qwen3-TTS until this upstream conflict is resolved.
- `"parler-tts is not installed..."` — a separate, unrelated gap: the
  `parler-tts` package is simply not listed in `requirements.txt`.

Full detail:
[model-and-device-config.md](./model-and-device-config.md#known-limitations-models-that-cannot-currently-run).

## Permission Errors On Mounted Volumes

```text
PermissionError: [Errno 13] Permission denied: '/app/text-to-speech/storage/...'
```

The container runs as UID/GID `1000:1000`, and fresh named volumes are
initialized with that ownership — this rarely fails on a clean install. It
usually means the volumes were initialized by an earlier root-only run.
Reset them:

```bash
docker compose down
docker volume rm \
  text-to-speech_text_to_speech_models \
  text-to-speech_text_to_speech_storage \
  text-to-speech_text_to_speech_cache
docker compose up -d
```

This deletes cached models and session data — confirm with the user before
running it, since it forces a slow re-export/re-download on next start.

## Standalone Import Or Audio Dependency Errors

Make sure the local virtual environment is active and dependencies are
installed into it:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If audio loading fails on the host:
```bash
sudo apt-get update
sudo apt-get install -y libsndfile1
```

## Port 8011 Already in Use

```bash
ss -ltnp | grep 8011
docker compose down
```
