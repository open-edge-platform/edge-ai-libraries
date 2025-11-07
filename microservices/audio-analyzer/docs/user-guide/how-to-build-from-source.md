# How to Build from Source

Build the Audio Analyzer microservice from source to customize, debug, or extend its functionality. In this guide, you will:
- Set up your development environment.
- Compile the source code and resolve dependencies.
- Generate a runnable build for local testing or deployment.

This guide is ideal for developers who want to work directly with the source code.


## Prerequisites

Before you begin, ensure the following:
- **System Requirements**: Verify your system meets the [minimum requirements](./system-requirements.md).
- This guide assumes basic familiarity with Git commands, Python virtual environments, and terminal usage. If you are new to these concepts, see:
  - [Git Documentation](https://git-scm.com/doc)
  - [Python Virtual Environments](https://docs.python.org/3/tutorial/venv.html)
- Follow all the steps provided in [get started](./get-started.md) documentation with respect to [environment variables](./get-started.md#environment-variables) configuration, setting up of [storage backends](./get-started.md#setup-the-storage-backends) and [model selection](./get-started.md#models-selection).

## Steps to Build
Following options are provided to build the microservice.

### Setup in a container using Docker Script

1. Clone the repository:
```bash
# Clone the latest on mainline
git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
# Alternatively, Clone a specific release branch
git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries -b <release-tag>
```

2. Set the required environment variables:

```bash
# MinIO credentials (required)
export MINIO_ACCESS_KEY=<your-minio-username>
export MINIO_SECRET_KEY=<your-minio-password>

# Optional: Set registry URL and project name for docker image naming
export REGISTRY_URL=<your-registry-url>
export PROJECT_NAME=<your-project-name> 
export TAG=<your-yag> # Default: latest
```

If `REGISTRY_URL` is provided, the final image name will be: `${REGISTRY_URL}${PROJECT_NAME}/audio-analyzer:${TAG}`  
If `REGISTRY_URL` is not provided, the image name will be: `${PROJECT_NAME}/audio-analyzer:${TAG}`

3. Run the setup script to bring up production version of application _(Brings up Minio server as well along with audio-analyzer service)_:

```bash
cd edge-ai-libraries/microservices/audio-analyzer
chmod +x ./setup_docker.sh
./setup_docker.sh
```

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
- Stop and remove all contianers: `./setup_docker.sh --down`

#### Additional Configuration

You can customize the setup with these environment variables:

```bash
# Model configuration
export ENABLED_WHISPER_MODELS=small.en,tiny.en,medium.en  # Comma-separated list of models to download
export DEFAULT_WHISPER_MODEL=tiny.en  # Default model for transcription. Shoule be one of the ENABLED_WHISPER_MODELS.

# Performance configuration
export DEFAULT_DEVICE=auto  # Device to use: cpu, gpu, or auto
export USE_FP16=true  # Use half-precision for better performance on GPUs

# Storage configuration
export STORAGE_BACKEND=minio  # Storage backend: minio or local
export MAX_FILE_SIZE=314572800  # Maximum file size in bytes (300MB)
```

The development environment provides:
- Hot-reloading of code changes
- Mounting of local code directory into container
- Debug logging enabled

The production environment uses:
- Gunicorn with multiple worker processes
- Optimized container without development dependencies
- No source code mounting (code is copied at build time)

### Setup and run on host

Host setup by default uses local filesystem storage backend. 

> _**NOTE :**_ To use Minio storage on host, you need to manually spin a Minio container [(see Running a Local Minio Server)](./get-started.md#running-a-local-minio-server) and update the STORAGE BACKEND which is explained in step 2. 


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

To run with Minio storage backend, run this: 
```bash
STORAGE_BACKEND=minio ./setup_host.sh
```

Minio server container must be running on `localhost:9000` for this to work. Please see [Running a Local Minio Server](./get-started.md#running-a-local-minio-server).

Available options:
- `--debug`, `-d`: Enable debug mode
- `--reload`, `-r`: Enable auto-reload on code changes

The setup script will:
- Install all required system dependencies
- Create directories for model storage. For host setup, only storage backend available is local filesystem.
- Install Poetry and project dependencies
- Start the Audio Analyzer service

## Validation

1. **Verify Build Success**:
   - Check the logs. Look for confirmation messages indicating the microservice started successfully.

## Troubleshooting


## Supporting Resources
* [Overview](Overview.md)
* [System Requirements](system-requirements.md)
* [API Reference](api-reference.md)