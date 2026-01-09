# System Requirements

This page provides detailed hardware, software, and platform requirements to help set up and run the application
efficiently.

<!--
## User Stories Addressed
- **US-2: Evaluating System Requirements**
  - **As a developer**, I want to review the hardware and software requirements, so that I can determine if my
    environment supports the application.

### Acceptance Criteria
1. A detailed table of hardware requirements (e.g., processor type, memory).
2. A list of software dependencies and supported operating systems.
3. Clear guidance on compatibility issues.
-->

## Supported Platforms

<!--
**Guidelines**:
- Include supported operating systems, versions, and platform-specific notes.
-->

### Operating Systems

- Ubuntu 24.04.1 LTS

<!--
**Hardware Platforms**
- Intel® Core™ processors (Intel® Core™ i5 processor or higher)
- Intel® Xeon® processors (recommended for large deployments)
-->

## Minimum Requirements

| **Component**       | **Minimum**                     | **Recommended**                      |
|---------------------|---------------------------------|--------------------------------------|
| **Processor**       | 11th Gen Intel® Core™ Processor | Intel® Core™ Ultra 7 Processor 155H  |
| **Memory**          | 8 GB                            | 8 GB                                 |
| **Disk Space**      | 256 GB SSD                      | 256 GB SSD                           |
| **GPU/Accelerator** | Intel® UHD Graphics             | Intel® Arc™ Graphics                 |

## Software Requirements

- Docker Engine version 20.10 or higher.
- For GPU and/or NPU usage, appropriate drivers must be installed. The recommended method is to use the DLS installation
script, which detects available devices and installs the required drivers. Follow the **Prerequisites** section in:
[Install Guide Ubuntu – Prerequisites](https://github.com/open-edge-platform/dlstreamer/blob/master/docs/source/get_started/install/install_guide_ubuntu.md#prerequisites)

## Compatibility Notes

<!--
**Guidelines**:
- Include any limitations or known issues with supported platforms.
-->

**Known Limitations**:

- GPU compute engine utilization metrics require Intel® Graphics.

## Validation

- Ensure all dependencies are installed and configured before proceeding to [Get Started](./get-started.md).
