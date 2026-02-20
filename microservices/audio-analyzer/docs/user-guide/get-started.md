# Get Started

The **Audio Analyzer microservice** enables developers to create speech transcription from video files. This section provides step-by-step instructions on how to:

- Set up the microservice using a pre-built Docker image for quick deployment.
- Run predefined tasks to explore its functionality.
- Learn how to modify basic configurations to suit specific requirements.

## Prerequisites

Before you begin, ensure the following:

- **System Requirements**: Verify that your system meets the [minimum requirements](./get-started/system-requirements.md).
- **Docker Installed**: Install Docker. Make sure the `docker` command can be run without
`sudo`. For installation instructions, see [Get Docker](https://docs.docker.com/get-docker/).

This guide assumes basic familiarity with Docker commands and terminal usage. If you are new to Docker, see [Docker Documentation](https://docs.docker.com/) for an introduction.

## Configurations

Note: The Audio Analyzer microservice currently supports only CPU as the device. Though documentation refers to other devices from a future feature extension perspective, these other devices should not be used.

### Environment Variables

The following environment variables can be configured:

- `UPLOAD_DIR`: Directory for uploaded files (default: /tmp/audio-analyzer/uploads)
- `OUTPUT_DIR`: Directory for transcription output (default: /tmp/audio-analyzer/transcripts)
- `ENABLED_WHISPER_MODELS`: Comma-separated list of Whisper models to enable and download
- `DEFAULT_WHISPER_MODEL`: Default Whisper model to use if a model name is not provided
explicitly (default: tiny.en or first model from ENABLED_WHISPER_MODELS list, if tiny.en is
not available)
- `GGML_MODEL_DIR`: Directory for downloading GGML models (for CPU inference)
- `MAX_FILE_SIZE`: Maximum allowed file size in bytes (default: 100MB)
- `DEFAULT_DEVICE`: Device to use for transcription - 'cpu', 'gpu', or 'auto' (default: cpu). 
- `STORAGE_BACKEND`: Storage backend to use - 'minio' or 'local'.

**MinIO Configuration (Advanced Setup)**

These variables are only required when `minio` storage backend is used.

- `MINIO_ENDPOINT`: MinIO server endpoint (default: `minio:9000` in Docker setup script)
- `MINIO_ACCESS_KEY`: MinIO access key used as login username
- `MINIO_SECRET_KEY`: MinIO secret key used as login password

### Storage Backends

The service supports **two storage backends** for getting input video and saving transcription output:

1. **Local** : _(Recommended)_ Source videos are uploaded from local filesystem. Final transcripts are also stored on the local filesystem Application will not have any external storage dependency.
2. **MinIO** : _(Used in Advanced Setup)_ Storage requirements are handled by an externally running Minio Instance. Source videos are picked from a Minio bucket. Transcripts are stored in the same MinIO bucket.

### Model Selection

Refer to [supported models](./index.md#available-whisper-models) for the list of models that can be used for transcription. You can specify which models to enable through the
`ENABLED_WHISPER_MODELS` environment variable.

## Quick Start

There are following **four different options** to setup and run the application. 

### Recommended Setup

1.  [Use pre-built image for standalone setup](#standalone-setup-in-docker-container) : Application runs containerised using a pre-built image. This setup has no external storage dependency. Storage backend used is `local` and **can not** be overridden.

### Advanced Setup

2.  [Build and run on host using setup script](./get-started/build-from-source.md#build-and-run-on-host-using-setup-script) : Application is built from source and runs directly on host. No external storage dependency. Storage backend used is `local` and **can not** be overriden.

3.  [Build and run in container using Docker script](./get-started/build-from-source.md#build-and-run-in-container-using-docker-script) : _(Not Recommended)_ Docker script helps build docker image for the application from the source code and deploy it with **optional Minio dependency**. 
    -   Storage backend used here is `minio` but [can be overridden](#overriding-storage-backends) to use `local`. 
    -   In case `minio` storage backend is used, this setup also brings up Minio server container along with application container and configures the integration between both services.
    -   If storage backend is overridden to use `local`, no Minio server containers will be brought up.

4.  [Build and run on host manually](./get-started/build-from-source.md#build-and-run-on-host-manually) : _(Not Recommended)_ Manually setup pre-requisites and build the application on host.
    -   Storage backend used here is `local` but [can be overridden](#overriding-storage-backends) to use `minio`.
    -   If `minio` storage backend is used, Minio server and its integration with the application needs to be setup and configured manually.

    > __**NOTE :**__ Audio-Analyzer microservice can be run with Minio as its storage backend. However, this is not a recommended setup and is only meant for advanced users. This setup requires familiarity with using Minio and using un-documented API requests.

#### Overriding Storage Backends

Run this command in current shell with desired new value to change storage backend. This needs to be run before running the setup, otherwise you will need to run the setup again, in order to consider the new value.

```bash
export STORAGE_BACKEND=<new_value>    # local or minio
```

> **_NOTE :_** This works only with setup methods which allow overriding storage backend.

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

Replace the `/path/to/your/video.mp4` in curl command below, with actual path of a video file on your machine.

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
