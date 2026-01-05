# Get Started

The **Visual Pipeline and Platform Evaluation Tool** helps hardware decision-makers and software developers
select the optimal Intel® platform by adjusting workload parameters and analyzing performance metrics.
Through an intuitive web-based interface, the Smart NVR pipeline can be executed and key metrics such as
throughput and CPU/GPU utilization can be evaluated to assess platform performance and determine appropriate
system sizing.

By following this guide, the following tasks can be completed:

- **Set up the sample application**: Use the Docker Compose tool to quickly deploy the application in a target environment.
- **Run a predefined pipeline**: Execute the Smart NVR pipeline and observe metrics.

## Prerequisites

Before starting, ensure the following:

- **System requirements**: The system meets the [minimum requirements](./system-requirements.md).
- **Docker platform**: Docker is installed. For details, see the [Docker installation guide](https://docs.docker.com/get-docker/).
- **Dependencies installed**:
  - **Git**: [Install Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git).
  - **Make**: Standard build tool, typically provided by the `build-essential` (or equivalent) package on Linux.
  - **curl**: Command-line tool for transferring data with URLs, typically provided by the `curl` package on Linux.

For GPU and/or NPU usage, appropriate drivers must be installed. The recommended method is to use the DLS installation
script, which detects available devices and installs the required drivers. Follow the **Prerequisites** section in:

- [Install Guide Ubuntu – Prerequisites](https://github.com/open-edge-platform/dlstreamer/blob/master/docs/source/get_started/install/install_guide_ubuntu.md#prerequisites)

This guide assumes basic familiarity with Git commands and terminal usage. For more information, see:

- [Git Documentation](https://git-scm.com/doc)

## Set up and First Use

1. **Set up the working directory**:

   ```bash
   mkdir -p visual-pipeline-and-platform-evaluation-tool/models
   mkdir -p visual-pipeline-and-platform-evaluation-tool/shared/models
   mkdir -p visual-pipeline-and-platform-evaluation-tool/shared/videos
   cd visual-pipeline-and-platform-evaluation-tool
   ```

2. **Download all required files**:

   ```bash
   curl -LO "https://github.com/open-edge-platform/edge-ai-libraries/raw/refs/heads/release-2025.2.0/tools/visual-pipeline-and-platform-evaluation-tool/setup_env.sh"
   curl -LO "https://github.com/open-edge-platform/edge-ai-libraries/raw/refs/heads/release-2025.2.0/tools/visual-pipeline-and-platform-evaluation-tool/compose.yml"
   curl -LO "https://github.com/open-edge-platform/edge-ai-libraries/raw/refs/heads/release-2025.2.0/tools/visual-pipeline-and-platform-evaluation-tool/compose.cpu.yml"
   curl -LO "https://github.com/open-edge-platform/edge-ai-libraries/raw/refs/heads/release-2025.2.0/tools/visual-pipeline-and-platform-evaluation-tool/compose.gpu.yml"
   curl -LO "https://github.com/open-edge-platform/edge-ai-libraries/raw/refs/heads/release-2025.2.0/tools/visual-pipeline-and-platform-evaluation-tool/compose.npu.yml"
   curl -LO "https://github.com/open-edge-platform/edge-ai-libraries/raw/refs/heads/release-2025.2.0/tools/visual-pipeline-and-platform-evaluation-tool/Makefile"
   curl -Lo models/Dockerfile "https://github.com/open-edge-platform/edge-ai-libraries/raw/refs/heads/release-2025.2.0/tools/visual-pipeline-and-platform-evaluation-tool/models/Dockerfile"
   curl -Lo models/model_manager.sh "https://github.com/open-edge-platform/edge-ai-libraries/raw/refs/heads/release-2025.2.0/tools/visual-pipeline-and-platform-evaluation-tool/models/model_manager.sh"
   curl -Lo shared/videos/default_recordings.yaml "https://github.com/open-edge-platform/edge-ai-libraries/raw/refs/heads/release-2025.2.0/tools/visual-pipeline-and-platform-evaluation-tool/shared/videos/default_recordings.yaml"
   curl -Lo shared/models/supported_models.yaml "https://github.com/open-edge-platform/edge-ai-libraries/raw/refs/heads/release-2025.2.0/tools/visual-pipeline-and-platform-evaluation-tool/shared/models/supported_models.yaml"
   chmod +x models/model_manager.sh
   chmod +x setup_env.sh
   ```

3. **Start the application**:

   ```bash
   make build-models run
   ```

4. **Verify that the application is running**:

   ```bash
   docker compose ps
   ```

5. **Access the application API documentation**:

   - Open a browser and navigate to `http://localhost:7860/docs` to access the Swagger UI.

## Validation

1. **Verify build success**:
   - Check the logs and look for confirmation messages indicating that the microservice has started successfully.

## Advanced Setup Options

For alternative ways to set up the sample application, refer to:

- [How to Build from Source](./how-to-build-source.md)

### Model Installation and Management

When the Visual Pipeline and Platform Evaluation Tool is launched for the first time,
a prompt is displayed to select and install the models to be used.
This step allows installation of only the models relevant to the intended pipelines.

To manage the installed models again, run the following command:

```bash
make install-models-force
```

## Known issues, limitations and troubleshooting

- Refer to [Known issues, limitations and troubleshooting](known-issues.md).

## Supporting Resources

- [Docker Compose Documentation](https://docs.docker.com/compose/)
