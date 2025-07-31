
# Build from Source

Build the ViPPET (Visual Pipeline and Platform Evaluation Tool) from source to customize, debug, or extend its functionality. In this guide, you will:
- Set up your development environment.
- Compile the source code and resolve dependencies.
- Generate a runnable build for local testing or deployment.

This guide is ideal for developers who want to work directly with the source code.

## Prerequisites

Before you begin, ensure the following:
- **System Requirements**: Verify your system meets the [minimum requirements](./system-requirements.md).
- **Dependencies Installed**:
    - **Git**: [Install Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git)
- **Permissions**: Confirm you have permissions to install software and modify environment configurations.

This guide assumes basic familiarity with Git commands, Python virtual environments, and terminal usage. If you are new to these concepts, see:
- [Git Documentation](https://git-scm.com/doc)


## Steps to Build

1. **Clone the Repository**:
   - Run:
     ```bash
     git clone https://github.com/open-edge-platform/edge-ai-libraries.git
     cd ./edge-ai-libraries/tools/visual-pipeline-and-platform-evaluation-tool
     ```
     
2. **Set Up Environment Variables**:
   - Execute the setup script with the desired device profile:
      ```bash
       # For default CPU setup
       source setup_env.sh

       # For GPU setup
       source setup_env.sh -d gpu
     
       # For NPU setup
       source setup_env.sh -d npu
      ```

3. **Build and Start the Tool**:
   - Run:
     ```bash
     docker pull ghcr.io/open-edge-platform/edge-ai-libraries/intel/edge-ai-dlstreamer:20250729_EAL1.2_DLS_RC2-ubuntu24
     docker pull docker.io/library/rust:1.87
     docker pull docker.io/library/telegraf:1.32
     docker compose build
     docker compose up -d
     ```


## Validation

1. **Verify Build Success**:
   - Check the logs. Look for confirmation messages indicating the microservice started successfully.
2. **Access the Microservice**:
   - Open a browser and go to:
     ```
     http://localhost:7860/?__theme=light
     ```
   - Expected result: The microservice’s UI loads successfully.


## Troubleshooting

1. **Environment Configuration Issues**:
   - Verify environment variables:
     ```bash
     echo $VARIABLE_NAME
     ```
