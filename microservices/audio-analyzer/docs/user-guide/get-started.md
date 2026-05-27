# Get Started

This page is the entry point for running the Audio Analyzer microservice.
Pick one of the two deployment paths and follow the linked guide.

## Before You Begin

- Confirm that your machine meets the
  [System Requirements](./get-started/system-requirements.md).
- Review the [Configuration Guide](./get-started/configuration.md) if you plan to change
  models, devices, or chunking behavior.

## Choose Deployment Path

<!--hide_directive::::{tab-set}
:::{tab-item}hide_directive--> **Run in Docker (Recommended)**
<!--hide_directive:sync: Docker hide_directive-->

The container image exposes the API on host port `8010` and mounts shared
folders for models, chunks, storage, and the Hugging Face cache.
Fresh clones include placeholder directories for these mount roots. If you
delete them and then start Compose, Docker may recreate the missing host
paths as `root` before the container starts.

See [Run with Docker Compose](./get-started/run-container.md) for the full step-by-step guide.

Quick start:

```bash
docker compose up -d --build
curl --noproxy '*' http://127.0.0.1:8010/health
```

If you hit permission errors on `models/`, `chunks/`, `storage/`, or
`.cache/huggingface/`, see
[Troubleshooting](./troubleshooting.md#permission-errors-on-mounted-folders).

<!--hide_directive:::
:::{tab-item}hide_directive--> **Run on the Host**
<!--hide_directive:sync: Host hide_directive-->

Run the service directly with Python. This path is useful for development or
when you do not want to use Docker.

See [Run on the Host](./get-started/run-standalone.md) for the full step-by-step guide.

Quick start:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```
<!--hide_directive:::
::::hide_directive-->

## Verify

Once the service is running:

```bash
curl --noproxy '*' http://127.0.0.1:8010/health
```

Expected response:

```json
{"status": "ok"}
```

## Next Steps

- [API Reference](./api-reference.md) for endpoint details and examples
- [Configuration Guide](./get-started/configuration.md) to customize models and devices
- [Troubleshooting](./troubleshooting.md) for common startup issues

<!--hide_directive
:::{toctree}
:hidden:

./get-started/system-requirements.md
./get-started/configuration.md
./get-started/build-from-source.md
./get-started/run-container.md
./get-started/run-standalone.md

:::
hide_directive-->
