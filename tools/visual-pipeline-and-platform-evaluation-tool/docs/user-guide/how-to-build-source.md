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
- **Docker platform**: Docker is installed. For details, see the [Docker installation guide](https://docs.docker.com/get-docker/).
- **Dependencies installed**:
  - **Git**: [Install Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git).
  - **Make**: Standard build tool, typically provided by the `build-essential` (or equivalent) package on Linux.

For GPU and/or NPU usage, appropriate drivers must be installed. The recommended method is to use the DLS installation
script, which detects available devices and installs the required drivers. Follow the **Prerequisites** section in:

- [Install Guide Ubuntu – Prerequisites](https://github.com/open-edge-platform/dlstreamer/blob/master/docs/source/get_started/install/install_guide_ubuntu.md#prerequisites)

This guide assumes basic familiarity with Git commands and terminal usage. For more information, see:

- [Git Documentation](https://git-scm.com/doc)

## Steps to Build

1. **Clone the repository**:

   ```bash
   git clone https://github.com/open-edge-platform/edge-ai-libraries.git
   cd ./edge-ai-libraries/tools/visual-pipeline-and-platform-evaluation-tool
   ```

2. **Build and start the application**:

   ```bash
   make build run
   ```

## Validation

1. **Verify build success**:
   - Logs should be checked for confirmation messages indicating that the microservice has started successfully.
2. **Access the application API documentation**:
   - Open a browser and navigate to `http://localhost:7860/docs` to access the Swagger UI.

## Known issues, limitations and troubleshooting

- Refer to [Known issues, limitations and troubleshooting](known-issues.md).
