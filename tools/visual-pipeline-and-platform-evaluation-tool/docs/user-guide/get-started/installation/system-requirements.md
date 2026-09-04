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
[DL Streamer Install Guide - Ubuntu](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/dlstreamer/install/install_guide_ubuntu.html#prerequisites).

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
