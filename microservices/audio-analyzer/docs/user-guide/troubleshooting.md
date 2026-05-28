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

The container runs as UID/GID `1000:1000` by default (set via
`user: "${LOCAL_UID:-1000}:${LOCAL_GID:-1000}"` in `docker-compose.yml`).
If your host user has a different UID/GID, the container will write into
the mounted folders (`models/`, `chunks/`, `storage/`,
`.cache/huggingface/`) as `1000:1000`, which can lead to errors such as:

```
PermissionError: [Errno 13] Permission denied: '/app/audio_analyzer/storage/...'
```

or, on the host side:

```
mkdir: cannot create directory 'models/...': Permission denied
```

This can also happen when a bind-mount source path does not exist on the host.
Docker Compose may create the missing directory as `root` before the
container starts. Fresh clones of this repository include placeholder files
for the expected mount roots, but if you deleted `models/`, `chunks/`,
`storage/`, or `.cache/huggingface/`, recreate them as your user first.

To fix this, start the container with your host user's UID/GID so the
mounted folders stay writable from both Docker and standalone runs:

```bash
LOCAL_UID=$(id -u) LOCAL_GID=$(id -g) docker compose up -d --build
```

Or persist it by creating a local `.env` file in the `audio_analyzer/`
directory:

```bash
LOCAL_UID=$(id -u)
LOCAL_GID=$(id -g)
```

After that, plain `docker compose up -d --build` will pick up your IDs.

If the directories already exist as `root`, repair them once on the host:

```bash
mkdir -p models chunks storage .cache/huggingface
sudo chown -R "$(id -u):$(id -g)" models chunks storage .cache
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
