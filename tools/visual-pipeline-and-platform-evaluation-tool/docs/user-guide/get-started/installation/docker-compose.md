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
[Install Guide Ubuntu - Prerequisites](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/dlstreamer/get_started/install/install_guide_ubuntu.html#prerequisites)

This guide assumes basic familiarity with terminal usage.

Before starting the setup, review the [Pre-Installation Steps](./pre-installation-steps.md)
for optional configuration such as the Hugging Face access token used to download models
from the Hugging Face Hub.

## Setup

Follow the steps below to quickly set up the environment and start
the Visual Pipeline and Platform Evaluation Tool.
For alternative ways to set up the sample application, refer to
[How to Build from Source](./build-from-source.md).

1. Set up the working directory:

   ```bash
   mkdir -p visual-pipeline-and-platform-evaluation-tool/onvif_discovery
   mkdir -p visual-pipeline-and-platform-evaluation-tool/shared/models
   mkdir -p visual-pipeline-and-platform-evaluation-tool/shared/videos
   mkdir -p visual-pipeline-and-platform-evaluation-tool/shared/onvif
   cd visual-pipeline-and-platform-evaluation-tool
   ```

2. Download all required files:

   ```bash
   BRANCH=main
   BASE_URL="https://github.com/open-edge-platform/edge-ai-libraries/raw/refs/heads/${BRANCH}/tools/visual-pipeline-and-platform-evaluation-tool"

   # Top-level files used by docker compose and the Makefile
   curl -LO "${BASE_URL}/setup_env.sh"
   curl -LO "${BASE_URL}/compose.yml"
   curl -LO "${BASE_URL}/compose.cpu.yml"
   curl -LO "${BASE_URL}/compose.gpu.yml"
   curl -LO "${BASE_URL}/compose.npu.yml"
   curl -LO "${BASE_URL}/Makefile"
   curl -LO "${BASE_URL}/vippet-telegraf.conf"

   # Sources for the onvif-discovery image (not published, must be built locally)
   curl -Lo onvif_discovery/Dockerfile               "${BASE_URL}/onvif_discovery/Dockerfile"
   curl -Lo onvif_discovery/onvif_discovery_agent.py "${BASE_URL}/onvif_discovery/onvif_discovery_agent.py"

   # Default lists of recordings and supported AI models (bind-mounted into the app)
   curl -Lo shared/videos/default_recordings.yaml "${BASE_URL}/shared/videos/default_recordings.yaml"
   curl -Lo shared/models/supported_models.yaml   "${BASE_URL}/shared/models/supported_models.yaml"

   chmod +x setup_env.sh
   ```

3. Build the local image and start the application:

   ```bash
   make build-onvif-discovery run
   ```

   These targets automatically:

   - run `setup_env.sh` to detect available hardware (CPU/GPU/NPU) and write `.env`,
   - create the required directories under `shared/`,
   - build the `vippet-onvif-discovery` image locally (it is not published),
   - pull the pre-built images (`vippet-app`, `vippet-ui`, `model-download`,
     `metrics-manager`, `mediamtx`) and start all services.

4. Verify that the application is running:

   ```bash
   docker compose ps
   ```

5. Access the application:

   Open a browser and navigate to `http://localhost` (or `http://<HOST-IP>`) to access
   the Visual Pipeline and Platform Evaluation Tool UI.

6. Access the application API documentation:

   Open a browser and navigate to `http://localhost/api/v1/docs` (or `http://<HOST-IP>/api/v1/docs`)
   to access the Swagger UI.

> **Note:** On the first start the `model-download` service may take several minutes to become
> healthy because it provisions its plugin virtual environments. The other services wait for it
> automatically.
