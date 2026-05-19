# Troubleshooting

## Service Will Not Start

- Confirm port `8011` is not already in use:

  ```bash
  ss -ltnp | grep 8011
  ```

- Confirm the active config file is valid YAML. The service loads
  `config.yaml` first, then files listed in
  `TEXT_TO_SPEECH_CONFIG_OVERRIDE_PATHS`, then `TEXT_TO_SPEECH__...`
  environment overrides.

## First Startup Is Slow

This is expected. On first run the service may download or convert model
assets to `models/` and the Hugging Face cache. Subsequent starts reuse
the cached artifacts.

## `health` Endpoint Fails

- For Docker: check `docker compose ps` and
  `docker compose logs -f text-to-speech`.
- For standalone: confirm the process is running and bound to the
  expected host/port (defaults `127.0.0.1:8011`).
- If you are behind a corporate proxy, pass `--noproxy '*'` to `curl`
  when hitting `127.0.0.1`.

## GPU / NPU Path Is Not Used

- The OpenVINO `GPU` device requires the Intel/OpenVINO host GPU runtime
  installed on the host (separate from the Python dependencies).
- For the container, `/dev/dri` must be exposed to the container (default
  in `docker-compose.yml`).
- For NPU, the host must have the Intel NPU driver stack installed and
  the model must be NPU-compatible.
- If you rely on Intel oneAPI, source the environment script before
  starting the service:

  ```bash
  source /opt/intel/oneapi/setvars.sh
  ```

  This script only exists after the relevant Intel host stack is
  installed.

## Permission Errors on Mounted Folders

The container runs as UID/GID `1000:1000` by default (set via
`user: "${LOCAL_UID:-1000}:${LOCAL_GID:-1000}"` in `docker-compose.yml`).
If your host user has a different UID/GID, the container will write into
the mounted folders (`models/`, `storage/`, `.cache/huggingface/`) as
`1000:1000`, which can lead to errors such as:

```
PermissionError: [Errno 13] Permission denied: '/app/text-to-speech/storage/...'
```

or, on the host side:

```
mkdir: cannot create directory 'models/...': Permission denied
```

To fix this, start the container with your host user's UID/GID so the
mounted folders stay writable from both Docker and standalone runs:

```bash
LOCAL_UID=$(id -u) LOCAL_GID=$(id -g) docker compose up -d --build
```

Or persist it by editing the local `.env` file in the `text-to-speech/`
directory:

```bash
LOCAL_UID=$(id -u)
LOCAL_GID=$(id -g)
```

After that, plain `docker compose up -d --build` will pick up your IDs.

## `libsndfile` / Audio Errors (Standalone)

Install the required host package:

```bash
sudo apt-get update
sudo apt-get install -y libsndfile1
```

## Unsupported Language Returns 400

The service currently supports English only. Requests with any other
`language` value are rejected with HTTP `400`. Change the request to use
`English` (or omit the field).

## Where to Look Next

- [Configuration reference](configuration.md)
- [API reference](api-reference.md)
- [System requirements](system-requirements.md)
