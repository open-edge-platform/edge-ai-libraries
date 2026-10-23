<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Build From Source

This page covers building the Audio Analyzer microservice from source.
Use this path when you need a code change. To run the prebuilt image
from Docker Hub without rebuilding, see
[Run with Docker Compose](./run-container.md).

## Prerequisites

- Verify the [system requirements](./system-requirements.md).
- Clone the repository and `cd` into the `audio-analyzer/` directory.

## Build the Docker Image

The repository ships a `Dockerfile` and a `docker-compose.yml`. The
compose file declares both `image:` and `build:` for the service:

- `docker compose pull && docker compose up -d` runs the prebuilt
  image from Docker Hub.
- `docker compose build && docker compose up -d` rebuilds the result from source
  and tags as the same `${REGISTRY}/audio-analyzer:${RELEASE_TAG}`,
  so subsequent `docker compose up` calls reuse the local build.

```bash
docker compose build
docker compose up -d
```

To build the image directly with `docker`:

```bash
docker build -t audio-analyzer:local .
```

The Compose setup bind-mounts `config.yaml` and stores model, chunk,
storage, and Hugging Face cache data in named Docker volumes
(`audio_analyzer_{models,chunks,storage,cache}`), and passes `/dev/dri`
through for host Intel iGPU access by default. The container runs as
UID/GID `1000:1000` by default; see
[Troubleshooting](../troubleshooting.md#permission-errors-on-mounted-folders)
if your host user differs.

## Build a Python Environment (Standalone)

Install host packages, then create a virtual environment and install Python
dependencies from source:

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg alsa-utils libsndfile1

python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Before starting a standalone process, provision the configured Hugging Face models
into its host model directory. From the same `audio-analyzer/` directory:

```bash
mkdir -p models
docker compose build model-downloader
docker compose run --rm -v "$PWD/models:/opt/models" model-downloader
python main.py
```

The `-v` override replaces the provisioning job's named models volume with the
host directory used by the standalone process. It must be writable by the
downloader's UID/GID `1000:1000`; see the linked permission troubleshooting guide
if your host identity differs. No downloader API remains running. For custom
`models_base_path` values, bind the corresponding host directory instead.
Repeat provisioning after changing model selections or enabling diarization;
provide its Hugging Face credentials to the provisioning job.
Native OpenAI Whisper and optional sentiment retain their direct-download setup.

## Verifying the Build

After building and starting the service, confirm:

```bash
curl --noproxy '*' http://127.0.0.1:8010/health
```

A `{"status": "ok"}` response confirms the build is functional.
