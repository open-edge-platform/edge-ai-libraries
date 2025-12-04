# VA Enablement Node Profile

## Overview

The `va_enablement_node_profile.sh` script provides node profiling capabilities for the VA (Video Analytics) enablement framework. This script is designed to Install the required drivers, tools and libraries for edge devices to develop and run VA workloads.

## Usage

- For ESQ and Metro use cases
Additional command line parameters are not required.
```bash
./va_enablement_node_profile.sh [OPTIONS]
```
- Input parameters for TFCC and VPP RI use cases
```bash
"./va_enablement_node_profile.sh tfcc"
"./va_enablement_node_profile.sh vpp"
```
- Execute it with --help/-h for checking the availability of any additional use case support
```bash
"./va_enablement_node_profile.sh -h"
```

## Features

- Installs GPU, NPU drivers, iGPU and dGPU support, Media and computing stack.
- Observability stack with GPU telemetry tools (xpu-smi, intel_gpu_top)
- Metrics Collection (grafana and proemetheus)
- AI tools and VA library installation on baremetal - Intel's openvino, opencv, dlstreamer and ffmpeg
- Hardware capability assessment
- Use case and RI support
  Video Processing Platform - vpp
  Transportation Fustion Compute Controller - tfcc
  Pre-requiste support for Edge System Qualification suite - ESQ and Metro

## Requirements

- Ubuntu-based edge device (Currently supports Ubuntu 24.04.3)
- Bash shell environment
- Appropriate system permissions for hardware monitoring
- A Minimum of 16GB RAM and 100GB Disk space

## Configuration

The script can be configured through environment variables or command-line parameters. Refer to the script's help output for detailed configuration options.

## Output

The profiling logs are typically saved in output.log file for further analysis and integration with the VA enablement framework.

## Support

For issues and questions related to this profiling tool, please refer to the main project documentation or contact the development team.