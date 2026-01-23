# How to Build from Source

Build the Audio Analyzer microservice from source to customize, debug, or extend its
functionality. In this guide, you will:

- Set up your development environment.
- Compile the source code and resolve dependencies.
- Generate a runnable build for local testing or deployment.

This guide is ideal for developers who want to work directly with the source code.

## Prerequisites

Before you begin, ensure the following:

- **System Requirements**: Verify your system meets the [minimum requirements](./get-started/system-requirements.md).
- This guide assumes basic familiarity with Git commands, Python virtual environments, and
terminal usage. If you are new to these concepts, see:
  - [Git Documentation](https://git-scm.com/doc)
  - [Python Virtual Environments](https://docs.python.org/3/tutorial/venv.html)
- Follow all the steps provided in [get started](./get-started.md) documentation with respect to [environment variables](./get-started.md#environment-variables) configuration, setting up of [storage backends](./get-started.md#setup-the-storage-backends) and [model selection](./get-started.md#model-selection).

## Steps to Build

The following options are provided to build the microservice:

- [Build and run application with required dependencies using Docker Script](#build-and-run-in-container-using-docker-script).
- [Build and run on host using Setup Script](#build-and-run-on-host-using-setup-script).

### Build and run in container using Docker script

1. Clone the repository:
    ```bash
    # Clone the latest on mainline
    git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
    # Alternatively, Clone a specific release branch
    git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries -b <release-tag>
    ```

2. Default storage backend used in the Docker script based setup is `minio`. We need to set following required environment variables for Minio on shell:

    ```bash
    # MinIO credentials (required)
    export MINIO_ACCESS_KEY=<your-minio-username>
    export MINIO_SECRET_KEY=<your-minio-password>
    ```

    > __NOTE :__ To override the default storage backend, see [setup the storage backends](./get-started.md#setup-the-storage-backends).

3. The Docker setup will build the image if not already present on the machine. We can optionally set a registry URL and tag, if we wish to push this image to any repository. If not set, default image will be built as `audio-analyzer:latest`.

    ```bash
    # Optional: Set registry URL and project name for docker image naming
    export REGISTRY_URL=<your-registry-url>
    export PROJECT_NAME=<your-project-name>
    export TAG=<your-tag>
    ```

    If `REGISTRY_URL` is provided, the final image name will be: `${REGISTRY_URL}${PROJECT_NAME}/audio-analyzer:${TAG}`
    If `REGISTRY_URL` is not provided, the image name will be: `${PROJECT_NAME}/audio-analyzer:${TAG}`

4. Set the required environment variables:

    ```bash
    # (Required) Comma-separated list of models to download
    export ENABLED_WHISPER_MODELS=small.en,tiny.en,medium.en
    ```

5. **(OPTIONAL)** You can customize the setup with these additional environment variables:

    ```bash
    # Set a default model to use, if one is not provided explicitly. Should be one of the ENABLED_WHISPER_MODELS
    export DEFAULT_WHISPER_MODEL=tiny.en

    # Device to use: cpu, gpu, or auto
    export DEFAULT_DEVICE=cpu
    export USE_FP16=true

    # Storage backend: minio or local
    export STORAGE_BACKEND=minio
    export MAX_FILE_SIZE=314572800
    ```

6. Run the setup script to build and bring up production version of application. This also brings up Minio Server container (if default **minio** storage backend is used):

    ```bash
    cd edge-ai-libraries/microservices/audio-analyzer
    chmod +x ./setup_docker.sh
    ./setup_docker.sh
    ```

7. If above step is successful, it will print the complete URL of API endpoint along with URL of Swagger API docs. Please refer the API docs to learn how to send request to Audio-Analyzer when running with Minio.

#### Docker Setup Options

The `setup_docker.sh` script when run without any parameters builds and runs the production docker images. It additionally supports the following options:

```
Options:
  --dev                 Build and run development environment
  --build               Only build production Docker image
  --build-dev           Only build development Docker image
  --down                Stop and remove all containers, networks,
                        and volumes
  -h, --help            Show this help message
```

Examples:

- Production setup: `./setup_docker.sh`
- Development setup: `./setup_docker.sh --dev`
- Build production image only: `./setup_docker.sh --build`
- Build development image only: `./setup_docker.sh --build-dev`
- Stop and remove all containers: `./setup_docker.sh --down`

The development environment provides:

- Hot-reloading of code changes
- Mounting of local code directory into container
- Debug logging enabled

The production environment uses:

- Gunicorn with multiple worker processes
- Optimized container without development dependencies
- No source code mounting (code is copied at build time)

### Build and run on host using Setup Script

1. Clone the repository:
    ```bash
    # Clone the latest on mainline
    git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
    # Alternatively, Clone a specific release branch
    git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries -b <release-tag>
    ```

2. Run the setup script with desired options:
    ```bash
    cd edge-ai-libraries/microservices/audio-analyzer
    chmod +x ./setup_host.sh
    ./setup_host.sh
    ```

Available options:

- `--debug`, `-d`: Enable debug mode
- `--reload`, `-r`: Enable auto-reload on code changes

The setup script will:

- Install all required system dependencies
- Create directories for model storage. **For host setup using script, only storage backend available is local filesystem.**
- Install Poetry and project dependencies
- Start the Audio Analyzer service

## Validation

1. **Verify Build Success**:
   - Check the logs. Look for confirmation messages indicating the microservice started successfully.

## Supporting Resources

- [Get Started Guide](./get-started.md)
- [System Requirements](./get-started/system-requirements.md)
- [API Reference](./api-reference.md)
- [Troubleshooting](./troubleshooting.md)
