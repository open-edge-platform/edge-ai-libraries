# Troubleshooting

## Service Will Not Start

- Confirm port `8010` is not already in use:

  ```bash
  ss -ltnp | grep 8010
  ```

- Confirm the active config file is valid YAML. The service loads
  `config.yaml` first, then files listed in
  `AUDIO_ANALYZER_CONFIG_OVERRIDE_PATHS`, then `AUDIO_ANALYZER__...`
  environment overrides.

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
- If you rely on Intel oneAPI, source the environment script before starting
  the service:

  ```bash
  source /opt/intel/oneapi/setvars.sh
  ```

  This script only exists after the relevant Intel host stack is installed.

## Permission Errors on Mounted Folders

The container is intended to run as your current host user so shared folders
stay writable from both Docker and standalone runs. Start it with:

```bash
LOCAL_UID=$(id -u) LOCAL_GID=$(id -g) docker compose up -d --build
```

Or create a local `.env` file with `LOCAL_UID` and `LOCAL_GID`.

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

## Where to Look Next

- [Configuration reference](configuration.md)
- [API reference](api-reference.md)
- [System requirements](system-requirements.md)
