# Get Started

The **Audio Analyzer microservice** enables developers to create speech transcription from video files. This section provides step-by-step instructions to:

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
- `UPLOAD_DIR`: Directory for uploaded files (default: /tmp/audio-analyzer/uploads)
- `OUTPUT_DIR`: Directory for transcription output (default: /tmp/audio-analyzer/transcripts)
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

## Models Selection
Refer to [supported models](./Overview.md#models-supported) for the list of models that can be used for transcription. You can specify which models to enable through the `ENABLED_WHISPER_MODELS` environment variable.

## Quick Start with Docker

The user has an option to either [build the docker images](./how-to-build-from-source.md#steps-to-build) or use prebuilt images as documented below.

_To be documented_

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
poetry run pytest --cov=audio_analyzer

# Generate detailed HTML coverage report
poetry run pytest --cov=audio_analyzer --cov-report=html

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

1. Clone the repository and change directory to the audio-analyzer microservice:
```bash
git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries -b release-1.2.0
cd edge-ai-libraries/microservices/audio-analyzer
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
export GGML_MODEL_DIR=/tmp/audio_analyzer_model/ggml
export OPENVINO_MODEL_DIR=/tmp/audio_analyzer_model/openvino
```

7. Run the service:
```bash
DEBUG=True poetry run uvicorn audio_analyzer.main:app --host 0.0.0.0 --port 8000 --reload
```

8. _(Optional):_ To run the service with Minio storage backend. Please make sure Minio Server is running on `localhost:9000`. Please see [Running a Local Minio Server](#running-a-local-minio-server). 
```bash
STORAGE_BACKEND=minio DEBUG=True poetry run uvicorn audio_analyzer.main:app --host 0.0.0.0 --port 8000 --reload
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
