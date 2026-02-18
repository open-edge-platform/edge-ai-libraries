# Get Started

The **Audio Analyzer microservice** enables developers to create speech transcription from
video files. This section provides step-by-step instructions on how to:

- Set up the microservice using a pre-built Docker image for quick deployment.
- Run predefined tasks to explore its functionality.
- Learn how to modify basic configurations to suit specific requirements.

## Prerequisites

Before you begin, ensure the following:

- **System Requirements**: Verify that your system meets the [minimum requirements](./get-started/system-requirements.md).
- **Docker Installed**: Install Docker. Make sure the `docker` command can be run without
`sudo`. For installation instructions, see [Get Docker](https://docs.docker.com/get-docker/).

This guide assumes basic familiarity with Docker commands and terminal usage. If you are new
to Docker, see [Docker Documentation](https://docs.docker.com/) for an introduction.

## Configurations

### Environment Variables

The following environment variables can be configured:

- `UPLOAD_DIR`: Directory for uploaded files (default: /tmp/audio-analyzer/uploads)
- `OUTPUT_DIR`: Directory for transcription output (default: /tmp/audio-analyzer/transcripts)
- `ENABLED_WHISPER_MODELS`: Comma-separated list of Whisper models to enable and download
- `DEFAULT_WHISPER_MODEL`: Default Whisper model to use if a model name is not provided
explicitly (default: tiny.en or first model from ENABLED_WHISPER_MODELS list, if tiny.en is
not available)
- `GGML_MODEL_DIR`: Directory for downloading GGML models (for CPU inference)
- `OPENVINO_MODEL_DIR`: Directory for storing OpenVINO optimized models (for GPU inference)
- `LANGUAGE`: Language code for transcription (default: None, auto-detect)
- `MAX_FILE_SIZE`: Maximum allowed file size in bytes (default: 100MB)
- `DEFAULT_DEVICE`: Device to use for transcription - 'cpu', 'gpu', or 'auto' (default: cpu)
- `USE_FP16`: Use half-precision (FP16) for GPU inference (default: True)
- `STORAGE_BACKEND`: Storage backend to use - 'minio' or 'filesystem'.

**MinIO Configuration**

- `MINIO_ENDPOINT`: MinIO server endpoint (default: `minio:9000` in Docker setup script)
- `MINIO_ACCESS_KEY`: MinIO access key used as login username
- `MINIO_SECRET_KEY`: MinIO secret key used as login password

### Setup the Storage backends

The service supports two storage backends for source video files and transcript output:

- **MinIO** : Store transcripts in a MinIO bucket. (Default value when Docker setup script is
used)
- **Filesystem**: Store transcripts on the local filesystem. The API service will not have any
external storage dependency. (Default value when application runs in [standalone mode](#standalone-setup-in-docker-container).)

The Docker setup script `setup_docker.sh` has **minio** as default storage backend. You can
override the default value by setting `STORAGE_BACKEND` environment variable:

For Minio Storage:
```bash
export STORAGE_BACKEND=minio
```

For Local filesystem storage:
```bash
export STORAGE_BACKEND=local
```

On the other hand, the host setup script `setup_host.sh` uses **local** filesystem as the
only storage backend available.

### MinIO integration

The service supports MinIO object storage integration for:

1. **Video Source**: Fetch videos from a MinIO bucket instead of direct uploads
2. **Transcript Storage**: Store transcription outputs (SRT/TXT) in a MinIO bucket

#### MinIO Configuration

To use MinIO integration, you need to configure the following environment variables:

```bash
# MinIO server connection
export MINIO_ACCESS_KEY=<your-minio-username>
export MINIO_SECRET_KEY=<your-minio-password>
```

### Model Selection

Refer to [supported models](./index.md#available-whisper-models) for the list of models that
can be used for transcription. You can specify which models to enable through the
`ENABLED_WHISPER_MODELS` environment variable.

## Quick Start

User has following different options to setup/build and use the application.

### Recommended Setup

- [Use pre-built image for standalone setup](#standalone-setup-in-docker-container).
Standalone setup has no external dependency. Storage backend used: `local`.
- [Build and run on host using setup script](./get-started/build-from-source.md#build-and-run-on-host-using-setup-script).
Storage backend used: `local`

### Advanced Setup

> __**NOTE :**__ Audio-Analyzer microservice can also be run with Minio as its storage backend.
However, this is not a recommended setup and is only meant for advanced users. This setup
requires familiarity with using Minio and using non-documented API requests.

- [Build and run in container using Docker script](./get-started/build-from-source.md#build-and-run-in-container-using-docker-script).
Docker script helps build images for application and deploy the application with any optional
dependency. Default storage backend used here is `minio` but can be updated to use `local`
storage backend. If `minio` storage backend is used, then the script also brings up Minio server
container along with application container.
- [Build and run on host manually](#build-and-run-on-host-manually). Default storage backend
used is `local` but can be configured to use `minio` storage backend.

## Standalone Setup in Docker Container

1. Set the registry and tag for the public image to be pulled.

    ```bash
    export PUB_REGISTRY=intel/
    export PUB_TAG=latest
    ```
2. Pull public image for Audio Analyzer Microservice:

    ```bash
    docker pull ${PUB_REGISTRY}audio-analyzer:${PUB_TAG:-latest}
    ```
3. Set the required environment variables:

    ```bash
    export ENABLED_WHISPER_MODELS=small.en,tiny.en,medium.en
    ```

4. Set and create the directory in filesystem where transcripts will be stored:

    ```bash
    export AUDIO_ANALYZER_DIR=~/audio_analyzer_data
    mkdir $AUDIO_ANALYZER_DIR
    ```

5. Stop any existing Audio-Analyzer container (if any):

    ```bash
    docker stop audioanalyzer
    ```

6. Run the Audio-Analyzer Microservice:

    ```bash
    # Run Audio Analyzer application container exposed on a randomly assigned port
    docker run --rm -d -P -v $AUDIO_ANALYZER_DIR:/data -e http_proxy -e https_proxy -e ENABLED_WHISPER_MODELS -e DEFAULT_WHISPER_MODEL --name audioanalyzer ${PUB_REGISTRY}audio-analyzer:${PUB_TAG:-latest}
    ```

7. Access the Audio-Analyzer API in a web browser on the URL given by this command:

    ```bash
    host=$(ip route get 1 | awk '{print $7}')
    port=$(docker port audioanalyzer 8000 | head -1 | cut -d ':' -f 2)
    echo http://${host}:${port}/docs
    ```

### API Usage

Below are examples of how to use the API on command line with `curl`.

#### Health Check

  ```bash
  curl "http://localhost:$port/api/v1/health"
  ```

#### Get Available Models

  ```bash
  curl "http://localhost:$port/api/v1/models"
  ```

#### Filesystem Storage Examples

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

Once the transcription process is completed, the transcript files will be available in the
directory set by `AUDIO_ANALYZER_DIR` variable. We can check the transcripts as follows:

  ```bash
  ls $AUDIO_ANALYZER_DIR/transcript
  ```

### Transcription Performance and Optimization on CPU

The service uses **pywhispercpp** with the following optimizations for CPU transcription:

- **Multithreading**: Automatically uses the optimal number of threads based on your CPU cores
- **Parallel Processing**: Utilizes multiple CPU cores for audio processing
- **Greedy Decoding**: Faster inference by using greedy decoding instead of beam search
- **OpenVINO IR Models**: Can download and use OpenVINO IR models for even faster CPU inference

## Build and run on host manually

> **__NOTE :__** This is an advanced setup and is recommended for development/contribution only.
As an alternative method to setup on host, please see : [setting up on host using setup script](./get-started/build-from-source.md#setup-and-run-on-host-using-setup-script).
When setting up on host, the default storage backend would be local filesystem. Please make
sure `STORAGE_BACKEND` is not overridden to **minio**, unless you want to explicitly use the
Minio backend.

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

8. _(Optional):_ To run the service with Minio storage backend, make sure Minio Server is running. Please see [Running a Local Minio Server](#manually-running-a-local-minio-server). User might need to update the `MINIO_ENDPOINT` environment variable depending on where the Minio Server is running (if not set, default value considered is `localhost:9000`).

    ```bash
    export MINIO_ENDPOINT="<minio_host>:<minio_port>"
    ```
    Run the Audio Analyzer application on host:
    ```bash
    STORAGE_BACKEND=minio DEBUG=True poetry run uvicorn audio_analyzer.main:app --host 0.0.0.0 --port 8000 --reload
    ```

### Running tests for host setup

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

### API Documentation

When running the service, you can access the Swagger UI documentation at:

```bash
http://localhost:8000/docs
```

## More Advanced Setup Options

### Manually Running a Local MinIO Server

If you're not using the bundled Docker Setup script `setup_docker.sh` and still want to use
the application with Minio storage, you can manually run a local MinIO server using:

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

Use **Filesystem** backend when (Default for standalone setup on host):

- Running in a simple, single-node deployment
- No need for distributed/scalable storage
- No integration with other services that might need to access transcripts
- Running in resource-constrained environments

Use **MinIO** backend when (Default for setup using Docker script):

- Running in a containerized/cloud environment
- Need for scalable, distributed object storage
- Integration with other services that need to access transcripts
- Building a clustered/distributed system
- Need for better data organization and retention policies

## Supporting Resources

- [Overview](./index.md)
- [API Reference](./api-reference.md)
- [Troubleshooting](./troubleshooting.md)

<!--hide_directive
:::{toctree}
:hidden:

./get-started/system-requirements
./get-started/build-from-source

:::
hide_directive-->
