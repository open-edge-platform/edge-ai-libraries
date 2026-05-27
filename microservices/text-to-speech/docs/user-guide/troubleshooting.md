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

   Set these in `.env`:

   ```bash
   LOCAL_UID=$(id -u)
   LOCAL_GID=$(id -g)
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

## Permission Errors On Mounted Folders

The container runs as UID/GID `1000:1000` by default through:

```text
user: "${LOCAL_UID:-1000}:${LOCAL_GID:-1000}"
```

If your host user uses different IDs, mounted folders such as `models/`,
`storage/`, and `.cache/huggingface/` may become unwritable.

Typical errors:

```text
PermissionError: [Errno 13] Permission denied: '/app/text-to-speech/storage/...'
mkdir: cannot create directory 'models/...': Permission denied
```

Fix:

```bash
LOCAL_UID=$(id -u)
LOCAL_GID=$(id -g)
docker compose up -d --build
```

Or persist them in `.env`:

```bash
LOCAL_UID=$(id -u)
LOCAL_GID=$(id -g)
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
