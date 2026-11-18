# System Requirements

This page lists the hardware, software and deployment requirements for the
Data Intelligence Engine. Only container-based deployment with Docker Compose
is supported.

## Supported Platforms

**Operating Systems**:

- Linux x86_64 with Docker support. See the
  [Docker installation guide for Ubuntu](https://docs.docker.com/engine/install/ubuntu/)
  for host setup.

**Hardware**:

- An Intel processor supported by OpenVINO for local CPU inference.
- Optional Intel GPU supported by OpenVINO, with host GPU drivers installed and
  permission to access `/dev/dri`. Use `--cpu` with the quick-start script for
  CPU-only deployment; a host without `/dev/dri` falls back to CPU.
- System RAM sized for the selected models, database services and ingestion
  workload. Intel integrated GPUs share system RAM, and loading multiple models
  increases memory requirements.
- About **50 GB of free disk space** for the container image, all default models
  and their downloaded originals. Allow additional space for uploaded content
  and database indexes; preparing fewer models with `--models` reduces storage needs.

## Software Requirements

**Docker Deployment**:

- Docker Engine with Docker Compose v2 and BuildKit support.
- Bash, `curl` and `jq` on the host; Git if cloning the repository.
- A writable workspace for models, uploads, ingested content and database state.
- An available engine port, `16022` by default, configurable through `ENGINE_PORT`.

**Network Access**:

- First-time setup requires access to container registries, package repositories
  and Hugging Face for image builds and model downloads.
- Configure `http_proxy`/`https_proxy` and the Docker daemon proxy when needed.
  Set `HF_ENDPOINT` to a mirror if Hugging Face is not reachable.
- Prepare models before starting the engine; inference does not download them.
  See [How to prepare models](how-to-guides/how-to-prepare-models.md).

## Validation

- Ensure the required software, workspace permissions and selected models are
  ready before following [Get Started](get-start.md).