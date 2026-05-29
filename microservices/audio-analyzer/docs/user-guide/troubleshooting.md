# Troubleshooting

## Service Will Not Start

- Confirm port `8010` is not already in use:

  ```bash
  ss -ltnp | grep 8010
  ```

- Confirm the active config file is valid YAML. The service loads
  `config.yaml`, then applies `AUDIO_ANALYZER__...` environment overrides.
  The same `config.yaml` is used by both standalone and container runs
  (bind-mounted into the container).

## First Startup Is Slow

This is expected. On first run the service may download or export model
assets to `models/` and the Hugging Face cache. Subsequent starts reuse the
cached artifacts.

## `health` Endpoint Fails

- For Docker: check `docker compose ps` and
  `docker compose logs -f audio-analyzer`.
- For standalone: confirm the process is running and bound to the expected
  host/port (defaults `127.0.0.1:8010`).
- If you are behind a corporate proxy, pass `--noproxy '*'` to `curl` when
  hitting `127.0.0.1`.

## GPU Path Is Not Used

- The OpenVINO `GPU` device requires the Intel/OpenVINO host GPU runtime
  installed on the host (separate from the Python dependencies).
- For the container, `/dev/dri` must be exposed to the container (default in
  `docker-compose.yml`).

## Permission Errors on Mounted Folders

The container runs as UID/GID `1000:1000` (baked into the image).
Model, chunk, storage, and Hugging Face cache data are kept in named
Docker volumes (`audio_analyzer_{models,chunks,storage,cache}`)
initialized with that ownership, so this rarely fails on a fresh
install. If you do see:

```
PermissionError: [Errno 13] Permission denied: '/app/audio_analyzer/storage/...'
```

you are most likely reusing volumes that were initialized by a previous
run as a different UID (for example by an older root-only run). Reset
them:

```bash
docker compose down
docker volume rm \
  audio-analyzer_audio_analyzer_models \
  audio-analyzer_audio_analyzer_chunks \
  audio-analyzer_audio_analyzer_storage \
  audio-analyzer_audio_analyzer_cache
docker compose up -d
```

## Microphone / `GET /devices` Returns Empty

- Confirm ALSA capture devices exist on the host:

  ```bash
  arecord -l
  ```

- For the container, uncomment the `/dev/snd` device mapping in
  `docker-compose.yml`.

## FFmpeg or `libsndfile` Errors (Standalone)

Install the required host packages:

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg alsa-utils libsndfile1
```

## Sessions / Transcripts Not Persisting

Session files live under `storage/<session_id>/`. Confirm that directory is
writable by the process and is on a persistent volume in container
deployments.

## Supporting Resources

- [Configuration Guide](./get-started/configuration.md)
- [API Reference](./api-reference.md)
- [System Requirements](./get-started/system-requirements.md)
