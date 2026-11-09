<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Build from Source

Build the Visual Pipeline and Platform Evaluation Tool from source to customize, debug, or extend its
functionality. In this guide, the following tasks are covered:

- Setting up the development environment.
- Compiling the source code and resolving dependencies.
- Generating a runnable build for local testing or deployment.

This guide is intended for developers working directly with the source code.

## Prerequisites

Before starting, ensure the following:

- **System requirements**: The system meets the [minimum requirements](./system-requirements.md).
- **Internet access**: The host has outbound internet connectivity. Base images, apt and Python packages, npm
  dependencies, sample videos, and models are downloaded during the build and on first start. Offline or
  air-gapped installation is not supported. See
  [Network Requirements](./system-requirements.md#network-requirements).
- **Docker platform**: **Docker Engine** is installed. On Linux, install it from the Docker apt repository, see
  [Install Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/), then complete the
  [post-installation steps](https://docs.docker.com/engine/install/linux-postinstall/) to run Docker as a non-root user.

  > [!NOTE]
   > Do not use Docker Desktop on Linux. It runs the Docker daemon inside a virtual machine that is not forwarding GPU
   > device on Linux (yet).

- **Dependencies installed**:
  - **Git**: [Install Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git).
  - **Make**: Standard build tool, typically provided by the `build-essential` (or equivalent) package on Linux.

For GPU and/or NPU usage, appropriate drivers must be installed. The recommended method is to use the DLS installation
script, which detects available devices and installs the required drivers. Follow the `Prerequisites` section in
[Install Guide Ubuntu](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/dlstreamer/install/install_guide_ubuntu.html#prerequisites).

> [!NOTE]
> The same steps apply to Ubuntu 24.04 running under WSL 2 on Windows - run all commands
> inside the WSL distribution. On WSL, only the CPU and GPU (WSL) variants are supported. See
> [System Requirements](./system-requirements.md#windows-subsystem-for-linux-wsl).

This guide assumes basic familiarity with Git commands and terminal usage. For more information, see
[Git Documentation](https://git-scm.com/doc).

Before building, review the [Pre-Installation Steps](./pre-installation-steps.md) for optional
configuration such as the Hugging Face access token used to download models from the
Hugging Face Hub.

## Steps to Build

Choose the section for your host operating system. The Ubuntu procedure builds and runs the
application in Docker. The native Windows procedure currently covers source and resource
preparation only; full native application startup is not yet supported.

### Native Ubuntu 24.04

1. Open a terminal on your Ubuntu host.
1. Install Docker Engine and the Docker Compose plugin using the
   [Docker apt repository instructions](https://docs.docker.com/engine/install/ubuntu/).
   Complete the [post-installation steps](https://docs.docker.com/engine/install/linux-postinstall/)
   so you can run Docker as a non-root user. Do not use Docker Desktop on Linux.
1. Install Git and Make, and configure GPU or NPU drivers if required, as described in
   [Prerequisites](#prerequisites).
1. Verify the tools before continuing:

   ```bash
   git --version
   make --version
   docker info
   docker compose version
   ```

Continue in the same Ubuntu terminal to build and verify the application.

1. Clone the repository:

   ```bash
   cd ~
   git clone https://github.com/open-edge-platform/edge-ai-libraries.git -b main
   cd edge-ai-libraries/tools/visual-pipeline-and-platform-evaluation-tool
   ```

1. Build and start the application:

   ```bash
   make build run
   ```

   Both `make build` and `make run` automatically invoke `setup_env.sh`, which detects the
   available hardware (CPU/GPU/NPU) and writes the appropriate `.env` file. They also create
   the required directories under `shared/`.

   The images are tagged with the version of the checked-out sources (for example `2026.3.0-dev`), or with
   `DOCKER_TAG` if it is set in the environment. `make run` does not rebuild images: after changing the
   sources, run `make build` again. To run published images instead, see
   [Use Pre-Built Docker Images](./docker-compose.md).

1. Verify that the application is running:

   ```bash
   docker compose ps
   ```

1. Access the application:

   Open a browser and navigate to `http://localhost` (or `http://<HOST-IP>`) to access
   the Visual Pipeline and Platform Evaluation Tool UI.

1. Access the application API documentation:

   Open a browser and navigate to `http://localhost/api/v1/docs` (or `http://<HOST-IP>/api/v1/docs`)
   to access the Swagger UI.

### Native Windows (preparation only)

These steps run directly in Windows PowerShell, without WSL or Docker. The Docker, Make and
Linux driver prerequisites above apply to the Ubuntu procedure, not to this preparation.

1. Install [Git for Windows](https://git-scm.com/downloads/win), open PowerShell and verify Git:

   ```powershell
   git --version
   ```

1. Clone the repository and set the backend working directory:

   ```powershell
   Set-Location $HOME
   git clone https://github.com/open-edge-platform/edge-ai-libraries.git -b main
   Set-Location edge-ai-libraries\tools\visual-pipeline-and-platform-evaluation-tool\vippet
   ```

1. Choose local data directories and configure their paths explicitly in the PowerShell
   session before starting the backend. Defaults remain Linux paths on every platform;
   the backend does not select Windows directories automatically. This example uses
   `%LOCALAPPDATA%\Vippet`, with a fallback to `%USERPROFILE%\AppData\Local\Vippet`:

   ```powershell
   $base = if ($env:LOCALAPPDATA) {
       Join-Path $env:LOCALAPPDATA "Vippet"
   } else {
       Join-Path $HOME "AppData\Local\Vippet"
   }
      $env:MODELS_PATH = Join-Path $base "models\output"
      $env:SCRIPTS_PATH = Join-Path $base "scripts"
      $env:PUBLIC_MODEL_PROC_PATH = Join-Path $base "model-proc\public"
      $env:AUTO_VIDEO_DIR = Join-Path $base "videos\input\auto"
      $env:UPLOADED_VIDEO_DIR = Join-Path $base "videos\input\uploaded"
      $env:OUTPUT_VIDEO_DIR = Join-Path $base "videos\output"
      $env:UPLOADED_IMAGES_DIR = Join-Path $base "images\input\uploaded"
      $env:METADATA_DIR = Join-Path $base "metadata"
      $env:DEFAULT_RECORDINGS_FILE = Join-Path $base "videos\default_recordings.yaml"
   $directories = @(
         "models\output", "scripts", "model-proc\public",
       "videos\input\auto", "videos\input\uploaded", "videos\output",
       "images\input\uploaded", "metadata"
   )
   foreach ($directory in $directories) {
       New-Item -ItemType Directory -Force -Path (Join-Path $base $directory) | Out-Null
   }
   ```

   Place models, scripts and public model-proc files in the corresponding directories;
   creating the directories does not install these resources. If using default recordings,
   provide `videos\default_recordings.yaml` under the same base directory.

1. Set `LABELS_PATH` to the labels directory in your DLStreamer installation. For the
   installation under `Program Files`, use:

   ```powershell
   $env:LABELS_PATH = Join-Path $env:ProgramFiles "Intel\dlstreamer\samples\labels"
   ```

   Adjust this path if DLStreamer is installed elsewhere. If public model-proc files are
   provided by your installation, set `PUBLIC_MODEL_PROC_PATH` to their actual directory
   instead of copying them to the example data directory. Configure model-download to use
   the same model directory as the backend. These environment variables apply to the current
   PowerShell session and child processes only; set them again in each new session.

> [!IMPORTANT]
> This is not a complete native Windows build or startup procedure. A native runtime still needs
> compatible Python, GStreamer, DLStreamer/OpenVINO and Python bindings, plus Windows subprocess
> control and multimedia adaptation. Installing Python dependencies alone is not sufficient.
> Full pipeline execution and automatic TS conversion are not yet supported natively. Do not run
> `make build run`, `setup_env.sh` or the Docker commands in this guide as native Windows steps.

## Optional: run pipelines on DL Streamer Pipeline Server 2.0 (experimental)

By default, pipelines run inside the `vippet` container. To run them on a separate
[DL Streamer Pipeline Server 2.0](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/microservices/dlstreamer-pipeline-server/dlsps2/README.md)
container instead, add `DLSPS2=1`:

```bash
make build run DLSPS2=1
make stop DLSPS2=1
```

This builds the server image from `microservices/dlstreamer-pipeline-server/dlsps2` in the
same repository, gives it the same devices as `vippet`, and sets
`VIPPET_EXECUTION_BACKEND=dlsps2`. Current limitations:

- Only pipeline validation and single-stream performance tests run on the server. Density
  tests, multi-stream performance tests and tests with latency metrics still run inside
  `vippet`.
- A pipeline that finishes in less than about one second reports 0 FPS.

The server is not part of `compose.yml`, so `docker compose logs` does not show it. Use
`docker logs -f dlstreamer-pipeline-server` to follow its log, or `make shell-dlsps` to
open a shell in it.

## Stop the application

Stop and remove all running containers:

```bash
make stop
```

Downloaded models and videos under `shared/` are preserved. To also remove
those artifacts, run:

```bash
make clean
```
