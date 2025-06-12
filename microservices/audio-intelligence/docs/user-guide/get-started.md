# Get Started

The **Audio Intelligence microservice** enables developers to create speech transcription from video files. This section provides step-by-step instructions to:

- Set up the microservice using a pre-built Docker image for quick deployment.
- Run predefined tasks to explore its functionality.
- Learn how to modify basic configurations to suit specific requirements.

## Prerequisites

Before you begin, ensure the following:

- **System Requirements**: Verify that your system meets the [minimum requirements](./system-requirements.md).
- **Docker Installed**: Install Docker. For installation instructions, see [Get Docker](https://docs.docker.com/get-docker/).

This guide assumes basic familiarity with Docker commands and terminal usage. If you are new to Docker, see [Docker Documentation](https://docs.docker.com/) for an introduction.

## Environment Variables

The following environment variables can be configured:

- `DEBUG`: Enable debug mode (default: False)
- `UPLOAD_DIR`: Directory for uploaded files (default: /tmp/audio-intelligence/uploads)
- `OUTPUT_DIR`: Directory for transcription output (default: /tmp/audio-intelligence/transcripts)
- `ENABLED_WHISPER_MODELS`: Comma-separated list of Whisper models to enable and download
- `DEFAULT_WHISPER_MODEL`: Default Whisper model to use (default: tiny.en or first available model)
- `GGML_MODEL_DIR`: Directory for downloading GGML models (for CPU inference)
- `OPENVINO_MODEL_DIR`: Directory for storing OpenVINO optimized models (for GPU inference)
- `LANGUAGE`: Language code for transcription (default: None, auto-detect)
- `MAX_FILE_SIZE`: Maximum allowed file size in bytes (default: 100MB)
- `DEFAULT_DEVICE`: Device to use for transcription - 'cpu', 'gpu', or 'auto' (default: cpu)
- `USE_FP16`: Use half-precision (FP16) for GPU inference (default: True)

**MinIO Configuration**
- `STORAGE_BACKEND`: Storage backend to use - 'minio' or 'filesystem' (default: minio)
- `MINIO_ENDPOINT`: MinIO server endpoint (default: minio:9000 in Docker, localhost:9000 on host)
- `MINIO_ACCESS_KEY`: MinIO access key used as login username (default for docker setup: minioadmin)
- `MINIO_SECRET_KEY`: MinIO secret key used as login password (default for docker setup: minioadmin)

## Setup the Storage backends

The service supports two storage backends for source video files and transcript output:

- **MinIO** (default): Store transcripts in a MinIO bucket
- **Filesystem**: Store transcripts on the local filesystem. The API service runs standalone and will not have any dependency.

You can configure the storage backend using the `STORAGE_BACKEND` environment variable:

For Minio Storage (Default):
```bash
export STORAGE_BACKEND=minio
```

For Local filesystem storage:
```bash
export STORAGE_BACKEND=local
```

### MinIO integration
The service now supports MinIO object storage integration for:

1. **Video Source**: Fetch videos from a MinIO bucket instead of direct uploads
2. **Transcript Storage**: Store transcription outputs (SRT/TXT) in a MinIO bucket

### MinIO Configuration

To use MinIO integration, you need to configure the following environment variables:

```bash
# MinIO server connection
export MINIO_ACCESS_KEY=<your-minio-username>
export MINIO_SECRET_KEY=<your-minio-password>
```

## Models

The service automatically downloads and manages the required models based on configuration. Two types of models are supported:

1. **GGML Models** Primarily used for inference on CPU using whispercpp backend.
2. **OpenVINO Models** Optimized for GPU inference on Intel GPUs.

Models are downloaded on application startup, converted to OpenVINO format if needed, and stored in persistent volumes for reuse. The conversion process includes:
- Downloading the original Hugging Face Whisper model
- Converting the PyTorch model to OpenVINO format.
- Storing the encoder and decoder components separately for efficient inference

### Available Whisper Models

The following Whisper model variants are supported by the service (for both GGML and OpenVINO formats):

| Model ID | Description | Size | Languages |
|----------|-------------|------|-----------|
| tiny     | Tiny model  | ~75M | Multilingual |
| tiny.en  | Tiny model  | ~75M | English-only |
| base     | Base model  | ~150M | Multilingual |
| base.en  | Base model  | ~150M | English-only |
| small    | Small model | ~450M | Multilingual | 
| small.en | Small model | ~450M | English-only |
| medium   | Medium model | ~1.5GB | Multilingual |
| medium.en | Medium model | ~1.5GB | English-only |
| large-v1 | Large model (v1) | ~2.9GB | Multilingual |
| large-v2 | Large model (v2) | ~2.9GB | Multilingual |
| large-v3 | Large model (v3) | ~2.9GB | Multilingual |

You can specify which models to enable through the `ENABLED_WHISPER_MODELS` environment variable.

## Quick Start with Docker

### Setup in a container using Docker Script

1. Clone the repository:
```bash
git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
```

2. Set the required environment variables:

```bash
# MinIO credentials (required)
export MINIO_ACCESS_KEY=<your-minio-username>
export MINIO_SECRET_KEY=<your-minio-password>

# Optional: Set registry URL and project name for docker image naming
export REGISTRY_URL=<your-registry-url>
export PROJECT_NAME=<your-project-name> 
export TAG=<Your-Tag> # Default: latest
```

If `REGISTRY_URL` is provided, the final image name will be: `${REGISTRY_URL}${PROJECT_NAME}/audio-intelligence:${TAG}`  
If `REGISTRY_URL` is not provided, the image name will be: `${PROJECT_NAME}/audio-intelligence:${TAG}`

3. Run the setup script to bring up production version of application _(Brings up Minio server as well along with Audio-Intelligence service)_:

```bash
cd edge-ai-libraries/microservices/audio-intelligence
chmod +x ./setup_docker.sh
./setup_docker.sh
```

#### Docker Setup Options

The `setup_docker.sh` script supports the following options:

```
Options:
  --dev                 Build and run development environment
  --build-only          Only build Docker images (don't run containers)
  --build-dev           Only build development Docker image
  --build-prod          Only build production Docker image
  -h, --help            Show this help message
```

Examples:
- Production setup: `./setup_docker.sh`
- Development setup: `./setup_docker.sh --dev`
- Build production image only: `./setup_docker.sh --build-prod`
- Build development image only: `./setup_docker.sh --build-dev`

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

> _**NOTE :**_ To use Minio storage on host, you need to manually spin a Minio container [(see Running a Local Minio Server)](#running-a-local-minio-server) and update the STORAGE BACKEND which is explained in step 2. 


1. Clone the repository:
```bash
git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
```

2. Run the setup script with desired options:
```bash
cd edge-ai-libraries/microservices/audio-intelligence
chmod +x ./setup_host.sh
./setup_host.sh
```

To run with Minio storage backend, run this: 
```bash
STORAGE_BACKEND=minio ./setup_host.sh
```

Minio server container must be running on `localhost:9000` for this to work. Please see [Running a Local Minio Server](#running-a-local-minio-server).

Available options:
- `--debug`, `-d`: Enable debug mode
- `--reload`, `-r`: Enable auto-reload on code changes

The setup script will:
- Install all required system dependencies
- Create directories for model storage. For host setup, only storage backend available is local filesystem.
- Install Poetry and project dependencies
- Start the Audio Intelligence service


## API Usage

Below are examples of how to use the API with curl for both filesystem and MinIO storage setups.

### Health Check

```bash
curl -X GET "http://localhost:8000/api/v1/health"
```

### Get Available Models

```bash
curl -X GET "http://localhost:8000/api/v1/models"
```

### Filesystem Storage Examples

#### Upload a Video File for Transcription (Filesystem)
```bash
curl -X POST "http://localhost:8000/api/v1/transcriptions" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@/path/to/your/video.mp4" \
  -F "include_timestamps=true" \
  -F "device=cpu" \
  -F "model_name=small.en" 
```

### MinIO Storage Examples

Before using MinIO storage, make sure:
1. Your MinIO server is running
2. You have configured proper credentials
3. You have created the necessary buckets

```bash
curl -X POST "http://localhost:8000/api/v1/transcriptions" \
  -H "Content-Type: application/json" \
  -d '{
    "minio_bucket": "videos",
    "video_name": "example.mp4",
    "video_id": "project1/raw",
    "include_timestamps": true,
    "device": "cpu",
    "model_name": "medium.en"
  }'
```

This API endpoint returns a job ID, transcription path and other details once the transcription is done.

## Transcription Performance and Optimization on CPU

The service uses pywhispercpp with the following optimizations for CPU transcription:

- **Multithreading**: Automatically uses the optimal number of threads based on your CPU cores
- **Parallel Processing**: Utilizes multiple CPU cores for audio processing
- **Greedy Decoding**: Faster inference by using greedy decoding instead of beam search
- **OpenVINO IR Models**: Can download and use OpenVINO IR models for even faster CPU inference

## Running Tests

The project uses `pytest` for testing. After installing and setting up the application on host, we can run tests as follows:

```bash
# Run all tests
poetry run pytest

# Run tests with verbose output
poetry run pytest -v

# Run tests by type (unit or api)
poetry run pytest -m unit
poetry run pytest -m api

# Run tests for a specific module (eg. utils/hardware_utils.py)
poetry run pytest tests/test_utils/test_hardware_utils.py
```

### Generate Test Coverage Reports

To generate a coverage report:

```bash
# Run tests with coverage
poetry run pytest --cov=audio_intelligence

# Generate detailed HTML coverage report
poetry run pytest --cov=audio_intelligence --cov-report=html

# Open the HTML report
xdg-open htmlcov/index.html  
```

Make sure `xdg-open` is installed on the host machine. The coverage report helps identify which parts of the codebase are well tested and which may need additional test coverage.

## API Documentation

When running the service, you can access the Swagger UI documentation at:

```
http://localhost:8000/docs
```

## Manual Host Setup using Poetry

1. Clone the repository and change directory to the audio-intelligence microservice:
```bash
git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
cd edge-ai-libraries/microservices/audio-intelligence
```

2. Install Poetry if not already installed.
```bash
pip install poetry==1.8.3
```

3. Configure poetry to create a local virtual environment.
```bash
poetry config virtualenvs.create true
poetry config virtualenvs.in-project true
```

4. Install dependencies:
```bash
poetry lock --no-update
poetry install
```

5. Set comma-separated list of whisper models that need to be enabled:
```bash
export ENABLED_WHISPER_MODELS=small.en,tiny.en,medium.en
```

6. Set directories on host where models will be downloaded:
```bash
export GGML_MODEL_DIR=/tmp/audio_intelligence_model/ggml
export OPENVINO_MODEL_DIR=/tmp/audio_intelligence_model/openvino
```

7. Run the service:
```bash
DEBUG=True poetry run uvicorn audio_intelligence.main:app --host 0.0.0.0 --port 8000 --reload
```

8. _(Optional):_ To run the service with Minio storage backend. Please make sure Minio Server is running on `localhost:9000`. Please see [Running a Local Minio Server](#running-a-local-minio-server). 
```bash
STORAGE_BACKEND=minio DEBUG=True poetry run uvicorn audio_intelligence.main:app --host 0.0.0.0 --port 8000 --reload
```

## Advanced Setup Options

### Running a Local MinIO Server

If you're not using Docker Compose, you can run a local MinIO server using:

```bash
docker run -d -p 9000:9000 -p 9001:9001 --name minio \
  -e MINIO_ROOT_USER=${MINIO_ACCESS_KEY} \
  -e MINIO_ROOT_PASSWORD=${MINIO_SECRET_KEY} \
  -v minio_data:/data \
  minio/minio server /data --console-address ':9001'
```

You can then access the MinIO Console at http://localhost:9001 with these credentials:
- **Username**: <MINIO_ACCESS_KEY>
- **Password**: <MINIO_SECRET_KEY>

### When to use Filesystem vs. MinIO backend

Use **Filesystem** backend when:
- Running in a simple, single-node deployment
- No need for distributed/scalable storage
- No integration with other services that might need to access transcripts
- Running in resource-constrained environments

Use **MinIO** backend (default) when:
- Running in a containerized/cloud environment
- Need for scalable, distributed object storage
- Integration with other services that need to access transcripts
- Building a clustered/distributed system
- Need for better data organization and retention policies

### Deploy from Helm chart
For alternative ways to set up the microservice, see:

<!-- - [How to Build from Source](./how-to-build-from-source.md) -->
- [How to Deploy with Helm](./how-to-deploy-with-helm.md)

## Next Steps


## Troubleshooting

1. **Docker Container Fails to Start**:
    - Run `docker logs {{container-name}}` to identify the issue.
    - Check if the required port is available.


2. **Cannot Access the Microservice**:
    - Confirm the container is running:
      ```bash
      docker ps
      ```

## Supporting Resources

* [Overview](Overview.md)
* [API Reference](api-reference.md)
* [System Requirements](system-requirements.md)
