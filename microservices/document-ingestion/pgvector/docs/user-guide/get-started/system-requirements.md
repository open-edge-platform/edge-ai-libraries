
# System Requirements

This page provides detailed hardware, software, and platform requirements to help you set up and run the application efficiently.

<!--
## User Stories Addressed
- **US-2: Evaluating System Requirements**
  - **As a developer**, I want to review the hardware and software requirements, so that I can determine if my environment supports the application.

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
**Operating Systems**
- Ubuntu 22.04.2 LTS
- If GPU is available, refer to the official [documentation](https://dgpu-docs.intel.com/devices/hardware-table.html) for details on the required kernel version. For the listed hardware platforms, the kernel requirement translates to Ubuntu OS version 24.04 or Ubuntu OS version 24.10, depending on the GPU used.
- Validation on latest version of EMT-S and EMT-D is also done periodically though there could be gaps in validation regression. Raise an issue if any defects are observed.

**Hardware Platforms**
- The microservice is used in the context of a reference application like chat-question-and-answer. Requirement of respective application overrides the requirement of this microservice.


## Software Requirements
<!--
**Guidelines**:
- List software dependencies, libraries, and tools.
-->
**Required Software**:
- Docker 24.0 or higher
- Python 3.9+
<!--
**Dependencies**:
- Intel® Distribution of OpenVINO™ Toolkit 2024.5
- Intel® oneMKL
-->

## Compatibility Notes
<!--
**Guidelines**:
- Include any limitations or known issues with supported platforms.
-->
**Known Limitations**:
- Validation is pending on any hardware configuration other than Intel® Xeon® processors.

## Validation
- Ensure all dependencies are installed and configured before proceeding to [Get Started](../get-started.md).
