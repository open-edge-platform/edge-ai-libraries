
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

**Guidelines**:
- Include supported operating systems, versions, and platform-specific notes.
-->
**Operating Systems**
- Ubuntu 24.04.1 LTS
<!--
**Hardware Platforms**
- Intel® Core™ processors (i5 or higher)
- Intel® Xeon® processors (recommended for large deployments)
-->


## Minimum Requirements
| **Component**       | **Minimum**              | **Recomended**           |     
|---------------------|--------------------------|--------------------------|
| **Processor**       | Intel® 11th Gen Core™ CPU| Intel Ultra 7-155H       |
| **Memory**          | 8 GB                     | 8 GB                     |
| **Disk Space**      | 256 GB SSD               | 256 GB SSD               | 
| **GPU/Accelerator** | Intel® UHD Graphic       | Intel Arc Graphics       |


## Software Requirements
**Required Software**:
- Docker 20.10 or higher

- Ensure the device has the required drivers. If not, follow the steps in [Intel® Edge Device Enablement Framework (EEF)](https://docs.edgeplatform.intel.com/edge-device-enablement-framework/user-guide/Get-Started-Guide.html).

## Compatibility Notes
<!--
**Guidelines**:
- Include any limitations or known issues with supported platforms.
-->
**Known Limitations**:
- GPU compute engine utilization metric require Intel® graphics. 
- When there are multiple GPUs in the system, the collector collects GPU metrics for the discrete GPU. 


## Validation
- Ensure all dependencies are installed and configured before proceeding to [Get Started](./get-started.md).
