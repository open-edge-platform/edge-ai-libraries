# Build From Source

This page covers building the Audio Analyzer microservice from source.
Use this path when you need a code change. To run the prebuilt image
from Docker Hub without rebuilding, see
[Run with Docker Compose](./run-container.md).

## Prerequisites

- Verify the [system requirements](./system-requirements.md).
- Clone the repository and `cd` into the `audio-analyzer/` directory.

## Build the Docker Image

The repository ships `docker/Dockerfile` (Ubuntu 24.04-based, multi-stage)
and a `docker-compose.yml`. The compose file declares both `image:` and
`build:` for the service:

- `docker compose pull && docker compose up -d` runs the prebuilt
  image from Docker Hub.
- `docker compose build && docker compose up -d` rebuilds the result from source
  and tags as the same `${REGISTRY}/audio-analyzer:${RELEASE_TAG}`,
  so subsequent `docker compose up` calls reuse the local build.

```bash
docker compose build
docker compose up -d
```

To build the image directly with `docker` (run from `audio-analyzer/`,
note the `-f` flag since the Dockerfile lives under `docker/`, not at
the repository root):

```bash
docker build -f docker/Dockerfile -t audio-analyzer:local .
```

By default this builds the `full` image variant with GPU/NPU runtime
packages included (`IMAGE_VARIANT=full`, `INSTALL_GPU_NPU_RUNTIME=true`),
matching what `docker compose build` produces. For a smaller CPU-only,
default-ASR-only image, pass `--build-arg IMAGE_VARIANT=slim
--build-arg INSTALL_GPU_NPU_RUNTIME=false` explicitly.

### Optional Chinese/English FunASR Provider

The `funasr` ASR provider (Paraformer models for Chinese/English
transcription) is **not installed by default** in either the `slim` or
`full` variant, to keep the standard image unchanged for existing
consumers. To add it, build with:

```bash
docker build -f docker/Dockerfile -t audio-analyzer:full-cjk \
    --build-arg INSTALL_CJK=true .
```

This installs the extra dependencies listed in `requirements-cjk.txt`
(`funasr`, `modelscope`, etc.) on top of whichever `IMAGE_VARIANT` is
selected. See [`funasr` provider notes](./configuration.md#asr-provider-notes)
for the corresponding `config.yaml` settings
(`models.asr.provider: funasr`, `models.asr.name: paraformer-zh | paraformer-en | paraformer-online`).

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
python main.py
```

## Verifying the Build

After building and starting the service, confirm:

```bash
curl --noproxy '*' http://127.0.0.1:8010/health
```

A `{"status": "ok"}` response confirms the build is functional.
