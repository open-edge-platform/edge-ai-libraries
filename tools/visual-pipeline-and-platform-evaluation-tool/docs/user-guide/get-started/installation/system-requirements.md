# System Requirements

This page provides detailed hardware and software requirements to help set up and run the application
efficiently.

## Hardware Requirements

| **Component**       | **Minimum**                     | **Recommended**                      |
|---------------------|---------------------------------|--------------------------------------|
| **Processor**       | 11th Gen Intel® Core™ Processor | Intel® Core™ Ultra 7 Processor 155H  |
| **Memory**          | 8 GB                            | 8 GB                                 |
| **Disk Space**      | 256 GB SSD                      | 256 GB SSD                           |
| **GPU/Accelerator** | Intel® UHD Graphics             | Intel® Arc™ Graphics                 |

## Software Requirements

- OS: Ubuntu 24.04.1 LTS (native installation, or as a WSL 2 distribution on Windows).
- Docker Engine version 20.10 or higher. Docker Desktop is not supported on Linux, because its virtual machine cannot
  access the host `/dev/dri` render nodes required for GPU acceleration.
- For GPU and/or NPU usage, appropriate drivers must be installed. The recommended method is to use the DL Streamer installation
script, which detects available devices and installs the required drivers. Follow the **Prerequisites** section in
[DL Streamer Install Guide - Ubuntu](https://docs.openedgeplatform.intel.com/2026.2/edge-ai-libraries/dlstreamer/install/install_guide_ubuntu.html#prerequisites).

## Network Requirements

**An outbound internet connection is required.** ViPPET is not supported in air-gapped or fully offline
environments: container images, sample videos, models, and Python packages are all fetched on demand and
are not bundled with the tool.

| **When**                | **What is downloaded**                                              | **From**                                                       |
|-------------------------|---------------------------------------------------------------------|----------------------------------------------------------------|
| Installation            | Docker Engine, GPU/NPU drivers, `git`, `make`, `curl`               | Ubuntu and Docker apt repositories                              |
| Installation            | ViPPET repository sources                                            | `github.com`                                                    |
| First `make run`        | Pre-built container images                                           | `docker.io` (Docker Hub)                                        |
| First start             | `model-download` plugin virtual environments (Python packages)       | `pypi.org`, `files.pythonhosted.org`                            |
| First start             | Default sample recordings listed in `shared/videos/default_recordings.yaml` | `storage.openvinotoolkit.org`, `github.com`, `pexels.com` |
| Model installation      | Model weights and metadata for the selected hub                      | `huggingface.co`, `ultralytics.com`, `storage.openvinotoolkit.org`, Intel® Geti™ |
| Build from source       | Base images, apt packages, Python and npm dependencies               | `docker.io`, distribution and language package registries        |
| UI and API docs in use  | Web fonts and the Swagger UI bundle                                  | `fonts.googleapis.com`, `cdn.jsdelivr.net`                       |

Notes:

- Downloaded artifacts are cached under `shared/`, so subsequent starts need far less bandwidth. A connection
  is still needed whenever a new model or sample video is installed, or after `make clean`.
- The first start can take several minutes and download several GB, depending on the selected models.
- Behind a corporate proxy, export `http_proxy`, `https_proxy`, and `no_proxy` in the shell before running
  `make run`, and configure the [Docker daemon proxy](https://docs.docker.com/engine/daemon/proxy/) so that
  image pulls succeed. `compose.yml` already appends the internal service names to `no_proxy`.
- Access to the Hugging Face Hub additionally requires a token for gated or private repositories. See
  [Pre-Installation Steps](./pre-installation-steps.md).
- Inbound access is not required. The UI is served on port `80` and is reachable at `http://localhost` or
  `http://<HOST-IP>` on the local network.

## Windows Subsystem for Linux (WSL)

Ubuntu 24.04 running under WSL 2 on Windows is supported. The installation steps are identical
to a native Ubuntu installation - run all commands
([Use Pre-Built Docker Images](./docker-compose.md) or [Build from Source](./build-from-source.md))
inside the Ubuntu 24.04 WSL distribution.

`setup_env.sh` detects `/dev/dxg` and selects the `gpu-wsl` Compose profile automatically, so no
manual configuration is required.

### Supported pipeline variants under WSL

| **Variant**   | **Supported under WSL** |
|---------------|-------------------------|
| CPU           | Yes                     |
| GPU (WSL)     | Yes                     |
| GPU (native)  | No                      |
| NPU           | No                      |

Pipelines expose a dedicated **GPU (WSL)** variant that is shown only when the application runs
under WSL. Native GPU and NPU variants are hidden in that environment.
