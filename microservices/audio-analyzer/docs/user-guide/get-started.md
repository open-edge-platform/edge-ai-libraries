# Get Started

The **Audio Analyzer microservice** enables developers to create speech transcription from video files. This section provides step-by-step instructions to:

- Set up the microservice using a pre-built Docker image for quick deployment.
- Run predefined tasks to explore its functionality.
- Learn how to modify basic configurations to suit specific requirements.

# Prerequisites

Before you begin, ensure the following:

- **System Requirements**: Verify that your system meets the [minimum requirements](./system-requirements.md).
- **Docker Installed**: Install Docker. Make sure the `docker` command can be run without `sudo`. For installation instructions, see [Get Docker](https://docs.docker.com/get-docker/).

This guide assumes basic familiarity with Docker commands and terminal usage. If you are new to Docker, see [Docker Documentation](https://docs.docker.com/) for an introduction.

# Configurations

## Environment Variables

The following environment variables can be configured:

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

The Docker setup for Audio Analyzer has **local filesystem** as default storage backend. You can configure the storage backend using the `STORAGE_BACKEND` environment variable:

For Minio Storage:
```bash
export STORAGE_BACKEND=minio
```

For Local filesystem storage (Default for Docker Setup):
```bash
export STORAGE_BACKEND=local
```

## MinIO integration
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

# Quick Start with Docker

The user has an option to either [build the docker images](./how-to-build-from-source.md#steps-to-build) or use prebuilt images as documented below.

1. Pull public image for Audio-Analyzer Microservice:

    ```bash
    docker pull intel/audio-analyzer:latest
    ```
2. Set the required environment variables:

    ```bash
    export ENABLED_WHISPER_MODELS=small.en,tiny.en,medium.en
    export DEFAULT_WHISPER_MODEL=tiny.en
    ```

3. Set and create the directory in filesystem where transcripts will be stored:

    ```bash
    export AUDIO_ANALYZER_DIR=~/audio_analyzer_data
    mkdir $AUDIO_ANALYZER_DIR
    ```

4. Stop any existing Audio-Analyzer container (if any):

    ```bash
    docker stop audioanalyzer
    ```

5. Run the Audio-Analyzer Microservice:

    ```bash
    # Run audio-analyzer with a randomly assigned port
    docker run --rm -d -P -v $AUDIO_ANALYZER_DIR:/data -e http_proxy -e https_proxy -e ENABLED_WHISPER_MODELS -e DEFAULT_WHISPER_MODEL --name audioanalyzer intel/audio-analyzer:latest
    ```

6. Access the Audio-Analyzer API in a web browser on the URL given by this command:

    ```bash
    host=$(ip route get 1 | awk '{print $7}')
    port=$(docker port audioanalyzer 8000 | head -1 | cut -d ':' -f 2)
    echo http://${host}:${port}/docs
    ```


## API Usage

Below are examples of how to use the API with curl for both filesystem and MinIO storage setups.

### Health Check

  ```bash
  curl "http://localhost:$port/api/v1/health"
  ```

### Get Available Models

  ```bash
  curl "http://localhost:$port/api/v1/models"
  ```

### Filesystem Storage Examples

#### Upload a Video File for Transcription

  ```bash
  curl -X POST "http://localhost:$port/api/v1/transcriptions" \
    -H "Content-Type: multipart/form-data" \
    -F "file=@/path/to/your/video.mp4" \
    -F "include_timestamps=true" \
    -F "device=cpu" \
    -F "model_name=small.en" 
  ```

#### Get Transcripts from Local Filesystem

Once the transcription process is completed, the transcript files will be available in the directory set by `AUDIO_ANALYZER_DIR` variable. We can check the transcripts as follows:

  ```bash
  ls $AUDIO_ANALYZER_DIR/transcript
  ```

# Docker setup with Minio Storage (Not Recommended)

> __**NOTE :**__ For a quick setup with Minio, using a Docker Compose template is recommended. Please check: [Setup in a container using Docker script](./how-to-build-from-source.md#setup-in-a-container-using-docker-script)

#### Before using MinIO storage, consider following pre-requisites:

1. MinIO server should be running and the required environment variable is set:

    ```bash
    export MINIO_ENDPOINT=<minio_host>:<minio_port>
    ```

2. Credentials used to setup Minio server are set as following environment variables:

    ```bash
    export MINIO_ACCESS_KEY=<your-minio-username>
    export MINIO_SECRET_KEY=<your-minio-password>
    ```

3. Required buckets are created in the Minio server. Check the [Minio Docs](https://docs.min.io/) on how to login to Minio UI and create the Minio Buckets. 


#### Running the Audio-Analyzer with Minio Storage:

1. Set the required environment variables:

    ```bash
    export STORAGE_BACKEND=minio
    export ENABLED_WHISPER_MODELS=small.en,tiny.en,medium.en
    export DEFAULT_WHISPER_MODEL=tiny.en
    ```

2. Stop any existing Audio-Analyzer container (if any):

    ```bash
    docker stop audioanalyzer
    ```

3. Run the Audio-Analyzer Docker container with Minio specific environment variables:

    ```bash
    docker run --rm -d -P -v audio_analyzer_vol:/data -e http_proxy -e https_proxy -e ENABLED_WHISPER_MODELS -e DEFAULT_WHISPER_MODEL -e STORAGE_BACKEND -e MINIO_ENDPOINT -e MINIO_ACCESS_KEY -e MINIO_SECRET_KEY --name audioanalyzer intel/audio-analyzer:latest
    ```

4. Access the Audio-Analyzer API in a web browser on the URL given by this command:

    ```bash
    host=$(ip route get 1 | awk '{print $7}')
    port=$(docker port audioanalyzer 8000 | head -1 | cut -d ':' -f 2)
    echo http://${host}:${port}/docs
    ```

### API Usage with Minio Storage

  ```bash
  curl -X POST "http://localhost:$port/api/v1/transcriptions" \
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

# Manual Host Setup using Poetry

1. Clone the repository and change directory to the audio-analyzer microservice:
```bash
# Clone the latest on mainline
git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
# Alternatively, Clone a specific release branch
git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries -b <release-tag>
# Access the code
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

## Running Tests

We can run unit tests and generate coverage by running following command in the application's directory (microservices/audio-analyzer) in the cloned repo:

```bash
poetry lock --no-update
poetry install --with dev
# set a required env var to set model name : required due to compliance issue
export ENABLED_WHISPER_MODELS=tiny.en

# Run tests
poetry run coverage run -m pytest ./tests

# Generate Coverage report
poetry run coverage report -m
```

## API Documentation

When running the service, you can access the Swagger UI documentation at:

```
http://localhost:8000/docs
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
