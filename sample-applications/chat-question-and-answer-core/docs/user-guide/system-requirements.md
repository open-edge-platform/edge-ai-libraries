<!--
# How to Use This Template
1. **Purpose**:
    - Provide developers with detailed hardware, software, and platform requirements to set up and run the application.
2. **Content Customization**:
   - Replace placeholders (e.g., `/path/to/directory`, `http://<host-ip>:<port>`) with specific details about your application.
   - Ensure the description and tasks align with the application's purpose and developer workflows.
   - Refer to the user stories in comments to understand what information developers expect to find.

3. **Style Guidelines**:
   - Follow the **Microsoft Developer Writing Style Guide** for clarity, consistency, and accessibility.
   - Use the second person (“you”) to engage directly with the reader.
   - Provide examples and validation steps for every action.
   - Ensure accessibility by avoiding complex sentences and providing alt text for all images.

4. **GitHub Copilot Can Help**:
   - **For Style Adherence**:
     - This template specifys the style guide to be followed, ask Copilot to check.
     - Copilot can generate suggestions in line with the specified writing style.
   - **To Validate Content Completeness**:
     - The template includes in comments the user stories and acceptance criteria to be fulfilled by its content in each section. Copilot can check if you included all required information.

5. **Validation**:
   - Include expected results for key actions, along with screenshots or logs where applicable.
   - Ensure troubleshooting guidance covers realistic developer scenarios.


6. **Testing Your Guide**:
   - Test all steps and commands to ensure accuracy.
   - Have another developer review the guide for clarity and completeness.
-->

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
- Intel® Core™ Ultra 7 165H
- Intel® Core™ Ultra 7 256V
- Intel® Core&trade; Ultra 7 265K Arc&trade; A770 GPU


## System Configuration
<!--
**Guidelines**:
- Use a table to clearly outline minimum and recommended configurations.
-->

| **Component**      | **Requirement**   | **Recommended**         |
|---------------------|---------------------------|--------------------------|
| **Processor**       | Intel® Core™ Ultra 7 165H     | Intel® Core™ Ultra 7 265K     |
| **Memory**          | 64 GB                     | 192 GB                   |
| **Disk Space**      | 128 GB SSD               | 256 GB SSD              |
| **GPU/Accelerator** | iGPU           | dGPU Arc770    |


## Software Requirements
<!--
**Guidelines**:
- List software dependencies, libraries, and tools.
-->
**Required Software**:
- Docker 24.0 or higher
- Python 3.11

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
- Validation is pending on dGPU configuration.


## Validation
- Ensure all dependencies are installed and configured before proceeding to [Get Started](./get-started.md).
