
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

**Hardware Platforms**
- Intel® Xeon® : Fourth generation processors onwards
- Intel 14th Gen Core with A750 GPU


## Minimum Requirements
<!--
**Guidelines**:
- Use a table to clearly outline minimum and recommended configurations.
-->

| **Component**      | **Minimum Requirement**   | **Recommended**         |
|---------------------|---------------------------|--------------------------|
| **Processor**       | Intel® Xeon® 4th Gen    | Intel® Xeon® 5th Gen     |
| **Memory**          | 64 GB                     | 128 GB+                   |
| **Disk Space**      | 128 GB SSD               | 256 GB SSD              |
| **GPU/Accelerator** | NA           | NA    |


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
