# Build from Source

Build the Multi-level Video Understanding Microservice from source to customize, debug, or extend its functionality. In this guide, you will:

- Set up your development environment.
- Compile the source code and resolve dependencies.
- Generate a runnable build for local testing or deployment.

This guide is ideal for developers who want to work directly with the source code.

## Prerequisites

Before you begin, ensure the following:

- **System Requirements**: Verify your system meets the [system requirements](./system-requirements.md).
- Follow all the steps provided in [Get Started](../get-started.md) with respect to [Setup GenAI Model Servings for VLM and LLM](../get-started.md#setup-genai-model-servings-for-vlm-and-llm), setting up dependent VLM and LLM model serving services.
- This guide assumes basic familiarity with Git commands, Python virtual environments, and terminal usage. If you are new to these concepts, see:
  - [Git Documentation](https://git-scm.com/doc)
  - [Python Virtual Environments](https://docs.python.org/3/tutorial/venv.html)

## Steps to Build

Following options are provided to build the microservice.

### Setup in a container using Docker Script

1. Clone the repository:

   ```bash
   git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
   ```

2. Set the required environment variables:

   ```bash
   # Optional: Set registry URL and project name for docker image naming
   export REGISTRY_URL=<your-registry-url>
   export TAG=<your-yag> # Default: latest
   ```

   If `REGISTRY_URL` is provided, the final image name will be: `${REGISTRY_URL}/multilevel-video-understanding:${TAG}`
   If `REGISTRY_URL` is not provided, the image name will be: `multilevel-video-understanding:${TAG}`

3. Run the setup script to build docker image:

   ```bash
   cd edge-ai-libraries/microservices/multilevel-video-understanding
   chmod +x ./setup_docker.sh
   ./setup_docker.sh --build
   ```

4. Run the setup script to bring up production version of application:

   ```bash
   ./setup_docker.sh --prod
   # Or just eliminate `--prod`: ./setup_docker.sh
   ```

#### Docker Setup Options

The `setup_docker.sh` script supports the following options:

```console
Usage: ./setup_docker.sh [options]

Options:
  --prod                Create and start production containers only
  --build               Build production Docker image only
  --build-prod          Build and then run production Docker images
  --down                Stop and remove all containers, networks, and volumes
  -h, --help            Show this help message

Examples:
  ./setup_docker.sh                    Create and start production containers only
  ./setup_docker.sh --prod             Create and start production containers only
  ./setup_docker.sh --build            Build production Docker image only
  ./setup_docker.sh --build-prod       Build and then run production Docker images
  ./setup_docker.sh --down             Stop and remove all containers
```

### Setup and run on host

Host setup by default uses local filesystem storage backend.

Please refer to [Manual Host Setup using Poetry](../get-started.md#manual-host-setup-using-poetry)

<!-- ## Troubleshooting -->

## Supporting Resources

- [Overview](../index.md)
- [System Requirements](../get-started/system-requirements.md)
- [API Reference](../api-reference.md)