# Get Started

This page is the entry point for running the Audio Analyzer microservice.
Pick one of the two deployment paths and follow the linked guide.

## Before You Begin

- Confirm that your machine meets the
  [system requirements](system-requirements.md).
- Review the [configuration guide](configuration.md) if you plan to change
  models, devices, or chunking behavior.

## Path 1: Run in Docker (Recommended)

The container image exposes the API on host port `8010` and mounts shared
folders for models, chunks, storage, and the Hugging Face cache.
Fresh clones include placeholder directories for these mount roots. If you
delete them and then start Compose, Docker may recreate the missing host
paths as `root` before the container starts.

See [run-container.md](run-container.md) for the full step-by-step guide.

Quick start:

```bash
docker compose up -d --build
curl --noproxy '*' http://127.0.0.1:8010/health
```

If you hit permission errors on `models/`, `chunks/`, `storage/`, or
`.cache/huggingface/`, see
[troubleshooting.md](troubleshooting.md#permission-errors-on-mounted-folders).

## Path 2: Run on the Host

Run the service directly with Python. This path is useful for development or
when you do not want to use Docker.

See [run-standalone.md](run-standalone.md) for the full step-by-step guide.

Quick start:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

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

- [API Reference](api-reference.md) for endpoint details and examples
- [Configuration](configuration.md) to customize models and devices
- [Troubleshooting](troubleshooting.md) for common startup issues
