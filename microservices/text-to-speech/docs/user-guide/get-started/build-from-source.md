# Build From Source

This page covers building the Text To Speech microservice from source for
both Docker and standalone host execution.

## Prerequisites

- Verify the [System Requirements](./system-requirements.md).
- Clone the repository and `cd` into the `text-to-speech/` directory.

## Build the Docker Image

The repository ships a `Dockerfile` and a `docker-compose.yml`. To build
the image as part of the Compose stack:

```bash
docker compose build
docker compose up -d
```

To build the image directly with `docker`:

```bash
docker build -t text-to-speech:local .
```

The Compose setup mounts `config.yaml`, `models/`, `storage/`, and the
Hugging Face cache into the container, and passes `/dev/dri` through for
host Intel iGPU access by default. The container runs as
UID/GID `1000:1000` by default; see
[Troubleshooting](../troubleshooting.md#permission-errors-on-mounted-folders)
if your host user differs.

## Build a Python Environment (Standalone)

Install host packages, then create a virtual environment and install
Python dependencies from source:

```bash
sudo apt-get update
sudo apt-get install -y libsndfile1

python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

## Verifying the Build

After building and starting the service, confirm:

```bash
curl --noproxy '*' http://127.0.0.1:8011/health
```

A `{"status": "ok"}` response confirms the build is functional.
