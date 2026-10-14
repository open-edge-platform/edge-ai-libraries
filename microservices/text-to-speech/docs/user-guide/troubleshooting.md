# Troubleshooting

Use this page when the service does not start, does not answer on port `8011`,
or behaves differently than expected in Docker or on the host.

## Quick Checks

Run these first before going deeper:

```bash
ss -ltnp | grep 8011
docker compose ps
docker compose logs --tail 100 text-to-speech
```

For standalone runs:

```bash
source .venv/bin/activate
python -c "import fastapi, openvino, soundfile; print('imports-ok')"
python main.py
```

## Service Will Not Start

Check these in order:

1. Port `8011` is free.

   ```bash
   ss -ltnp | grep 8011
   ```

2. The active config is valid YAML.

   The service loads `config.yaml`, then applies `TEXT_TO_SPEECH__...`
   environment overrides. The same `config.yaml` is used by both
   standalone and container runs (bind-mounted into the container).

3. Docker is using the expected service directory.

   Run `docker compose down` and `docker compose up` from the
   `text-to-speech/` directory that contains this service's
   `docker-compose.yml`.

4. There is no leftover container name conflict.

   If you see an error like:

   ```text
   Conflict. The container name "/text-to-speech" is already in use
   ```

   remove the old container explicitly:

   ```bash
   docker rm -f text-to-speech
   ```

## First Startup Is Slow

This is expected.

On first run the service may:

- download model artifacts
- export models to OpenVINO IR under `models/`
- populate the Hugging Face cache under `.cache/huggingface/`

Later starts reuse those cached files and should be much faster.

## Model Download Times Out Behind A Proxy

If model downloads work on the host but time out in the container, export the
host proxy variables before starting Compose. The Compose configuration passes
both uppercase and lowercase variants to the service:

```bash
export HTTP_PROXY="http://proxy.example.com:8080"
export HTTPS_PROXY="$HTTP_PROXY"
export NO_PROXY="localhost,127.0.0.1"
docker compose up -d --force-recreate
docker compose logs -f text-to-speech
```

Do not commit proxy URLs containing credentials. Configure authenticated proxy
values in the shell or another approved secret-management mechanism.

## `health` Endpoint Fails

For Docker:

```bash
docker compose ps
docker compose logs -f text-to-speech
curl --noproxy '*' http://127.0.0.1:8011/health
```

For standalone:

```bash
source .venv/bin/activate
python main.py
curl --noproxy '*' http://127.0.0.1:8011/health
```

If you are behind a proxy, always use `--noproxy '*'` for local health checks.

## GPU Startup Fails In Docker

If the container keeps restarting or logs show OpenVINO GPU failures, check the
container GPU path before changing the model code.

Typical fatal error:

```text
[GPU] Context was not initialized for 0 device
```

Check these in order:

1. `/dev/dri` is exposed to the container.

   This service already mounts `/dev/dri:/dev/dri` in `docker-compose.yml`.

2. The host actually has the GPU device nodes.

   ```bash
   ls -l /dev/dri
   ```

3. The container has the right group access for the render node.

   On many systems `/dev/dri/renderD*` is owned by group `render`, not `video`.
   This service runs as a non-root user, so it must be given the host render
   group ID explicitly.

   Set this in `.env`:

   ```bash
   RENDER_GID=$(stat -c '%g' /dev/dri/render* | head -1)
   ```

   `RENDER_GID` is host-specific. Do not assume `992` on every machine.

4. Restart the container cleanly.

   ```bash
   docker compose down
   docker rm -f text-to-speech 2>/dev/null || true
   docker compose up --build
   ```

5. If GPU still fails, isolate whether the problem is Docker permissions or the
   model/runtime path.

   - Try the same service with `device: CPU`
   - Try a simpler GPU path first, such as SpeechT5 on GPU
   - Then retry Qwen on GPU

That separation matters because a working Whisper or SpeechT5 GPU path does not
guarantee that Qwen GPU initialization will also succeed.

## NPU Does Not Behave As Expected

No TTS model in this service can currently complete a request on NPU, even
though `NPU` is an accepted `device` value. Device validation
(`utils/device_validation.py::resolve_tts_device`) applies to per-request
`device` selections and to the startup GPU-warmup synthesis — but not to
`preload_models()`, which loads the configured model directly at startup
without going through this check. A warmup failure after preload is only
logged as a warning and does not stop the service from starting. The
exact error for an actual request depends on the model/runtime:

- **Kokoro**: rejected immediately for per-request selections —
  `"The configured Kokoro model supports only CPU inference."`. If
  `models.tts.device: NPU` is configured instead, Kokoro still loads at
  startup (the device is ignored) and only a warmup warning is logged.
- **`models.tts.runtime: pytorch`** (non-Kokoro models): rejected
  immediately — `"The PyTorch TTS runtime does not support NPU
  inference."`
- **`models.tts.runtime: openvino` + SpeechT5**: if no NPU device is
  visible to OpenVINO, rejected with `"Requested TTS device 'NPU' is not
  visible in this runtime."`. If an NPU device *is* visible, this check
  passes, but the request then fails during model compilation with a raw
  OpenVINO compiler error (a `Reshape` / dynamic-dimension error) — this
  is a model limitation that device validation does not catch.
- **Qwen3-TTS**: fails with a dependency error on startup regardless of
  device (`CPU`, `GPU`, or `NPU`) — see
  [Configuration > Qwen3-TTS dependency limitation](./get-started/configuration.md#qwen3-tts-dependency-limitation).
- **Parler-TTS**: fails separately, because the `parler-tts` package is
  not installed (missing from `requirements.txt`), regardless of device.
  This is not the Qwen3-TTS/Transformers conflict described above.

See [Configuration > NPU](./get-started/configuration.md#npu) for the
full per-model breakdown.

## Permission Errors On Mounted Folders

The container runs as UID/GID `1000:1000` (baked into the image).
Model, storage, and Hugging Face cache data are kept in named Docker
volumes (`text_to_speech_{models,storage,cache}`) initialized with that
ownership, so this rarely fails on a fresh install. If you do hit:

```text
PermissionError: [Errno 13] Permission denied: '/app/text-to-speech/storage/...'
```

you are most likely reusing volumes that were initialized by a previous
run as a different UID (for example by an older root-only run). Reset
them:

```bash
docker compose down
docker volume rm \
  text-to-speech_text_to_speech_models \
  text-to-speech_text_to_speech_storage \
  text-to-speech_text_to_speech_cache
docker compose up -d
```

## Standalone Import Or Audio Dependency Errors

If standalone startup fails with missing Python modules, make sure you are using
the local virtual environment and that requirements are installed into it.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If audio loading fails on the host, install `libsndfile1`:

```bash
sudo apt-get update
sudo apt-get install -y libsndfile1
```

## Supporting Resources

- [Configuration Guide](./get-started/configuration.md)
- [API Reference](./api-reference.md)
- [System Requirements](./get-started/system-requirements.md)
