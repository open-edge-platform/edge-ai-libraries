# Use Pre-Built Docker Images

This guide explains how to deploy ViPPET using pre-built Docker images, without building the
application components from source. It is the fastest way to get a working local environment
for evaluation, demos, and API exploration.

## Prerequisites

Before starting, ensure the following:

- **System requirements**: The system meets the [minimum requirements](./system-requirements.md).
- **Docker platform**: Docker is installed. For details, see the [Docker installation guide](https://docs.docker.com/get-docker/).
- **Dependencies installed**:
  - **Make**: Standard build tool, typically provided by the `build-essential` (or equivalent) package on Linux.
  - **curl**: Command-line tool for transferring data with URLs, typically provided by the `curl` package on Linux.

For GPU and/or NPU usage, appropriate drivers must be installed. The recommended method is to use the DLS installation
script, which detects available devices and installs the required drivers. Follow the `Prerequisites` section in
[Install Guide Ubuntu - Prerequisites](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/dlstreamer/install/install_guide_ubuntu.html#prerequisites).

> **Note:** The same steps apply to Ubuntu 24.04 running under WSL 2 on Windows - run all commands
> inside the WSL distribution. On WSL, only the CPU and GPU (WSL) variants are supported. See
> [System Requirements](./system-requirements.md#windows-subsystem-for-linux-wsl).

This guide assumes basic familiarity with terminal usage.

Before starting the setup, review the [Pre-Installation Steps](./pre-installation-steps.md)
for optional configuration such as the Hugging Face access token used to download models
from the Hugging Face Hub.

## Setup

Follow the steps below to quickly set up the environment and start
the Visual Pipeline and Platform Evaluation Tool.
For alternative ways to set up the sample application, refer to
[How to Build from Source](./build-from-source.md).

1. Clone the repository:

   ```bash
   git clone -b main --sparse --filter=blob:none https://github.com/open-edge-platform/edge-ai-libraries.git
   cd edge-ai-libraries
   git sparse-checkout set tools/visual-pipeline-and-platform-evaluation-tool
   cd tools/visual-pipeline-and-platform-evaluation-tool
   ```

1. Build the `vippet-onvif-discovery` image and start the application:

   ```bash
   make build-onvif-discovery run
   ```

   These targets automatically:

   - run `setup_env.sh` to detect available hardware (CPU/GPU/NPU) and write `.env`,
   - create the required directories under `shared/`,
   - build the `vippet-onvif-discovery` image locally (it is not published),
   - pull the pre-built images (`vippet-app`, `vippet-ui`, `model-download`,
     `metrics-manager`, `mediamtx`) and start all services.

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

> **Note:** On the first start the `model-download` service may take several minutes to become
> healthy because it provisions its plugin virtual environments. The other services wait for it
> automatically.

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
