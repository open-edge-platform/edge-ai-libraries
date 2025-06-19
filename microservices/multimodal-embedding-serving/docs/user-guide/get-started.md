# Get Started

The **Multimodal Embedding Serving microservice** is designed to generate embeddings for text, image URLs, base64 encoded images, video URLs, and base64 encoded videos. It leverages the CLIP (Contrastive Language-Image Pretraining) model to create these embeddings. This section provides step-by-step instructions to:

- Set up the microservice using a pre-built Docker image for quick deployment.
- Run predefined tasks to explore its functionality.
- Learn how to modify basic configurations to suit specific requirements.

## Prerequisites

Before you begin, ensure the following:

- **System Requirements**: Verify that your system meets the [minimum requirements](./system-requirements.md).
- **Docker Installed**: Install Docker. For installation instructions, see [Get Docker](https://docs.docker.com/get-docker/).

This guide assumes basic familiarity with Docker commands and terminal usage. If you are new to Docker, see [Docker Documentation](https://docs.docker.com/) for an introduction.

## Set Environment Values

First, set the required VCLIP_MODEL environment variable:

```bash
export VCLIP_MODEL="openai/clip-vit-base-patch32"
```

Set the environment with default values by running the following script:

```bash
source setup.sh
```

### List of Environment Variables

- `APP_NAME`: Name of the application.
- `APP_DISPLAY_NAME`: Display name of the application.
- `APP_DESC`: Description of the application.
- `VCLIP_MODEL`: Name of the pre-trained multimodal embedding model.
- `http_proxy`: HTTP proxy value.
- `https_proxy`: HTTPS proxy value.
- `no_proxy_env`: No proxy value(comma separated list).
- `DEFAULT_START_OFFSET_SEC`: Default start offset in seconds for video segmentation.
- `DEFAULT_CLIP_DURATION`: Default clip duration for video segmentation. (If DEFAULT_CLIP_DURATION == -1 then takes the video till end)
- `DEFAULT_NUM_FRAMES`: Default number of frames to extract from a video. (Uses uniform sampling)
- `EMBEDDING_USE_OV`: Set to `true` to use the OpenVINO backend for running the multimodal embedding model.
- `EMBEDDING_DEVICE`: Device to run the embedding model on (CPU, GPU, etc.). This is an OpenVINO related parameter.
- `REGISTRY_URL`: URL for the Docker registry.
- `PROJECT_NAME`: Project name for Docker images.
- `TAG`: Tag for Docker images (defaults to 'latest').

## Quick Start with Docker

The user has an option to either [build the docker images](./how-to-build-from-source.md#steps-to-build) or use prebuilt images as documented below.

_Document how to get prebuilt docker image_

## Running the Server

To run the server using Docker Compose, use the following command:

 ```bash
 # Run on CPU
 docker compose -f compose.yaml up
 # Run on GPU
 docker compose -f compose.arc-gpu.yaml up
 ```

## Sample CURL Commands

### Text Embedding

```bash
curl --location 'http://localhost:8000/embeddings' \
--header 'Content-Type: application/json' \
--data '{
    "input": {
        "type": "text",
        "text": "Sample input text"
    },
    "model": "openai/clip-vit-base-patch32",
    "encoding_format": "float"
}'
```

### Image URL Embedding

```bash
curl --location 'http://localhost:8000/embeddings' \
--header 'Content-Type: application/json' \
--data '{
    "input": {
        "type": "image_url",
        "image_url": "https://i.ytimg.com/vi/H_8J2YfMpY0/sddefault.jpg"
    },
    "model": "openai/clip-vit-base-patch32",
    "encoding_format": "float"
}'
```

### Base64 Image Embedding

```bash
curl --location 'http://localhost:8000/embeddings' \
--header 'Content-Type: application/json' \
--data '{
    "model": "openai/clip-vit-base-patch32",
    "encoding_format": "float",
    "input": {
        "type": "image_base64",
        "image_base64": "<base64_image>"
    }
}'
```

### Video URL Embedding

```bash
curl --location 'http://localhost:8000/embeddings' \
--header 'Content-Type: application/json' \
--data '{
    "model": "openai/clip-vit-base-patch32",
    "encoding_format": "float",
    "input": {
        "type": "video_url",
        "video_url": "https://sample-videos.com/video321/mp4/720/big_buck_bunny_720p_10mb.mp4",
        "segment_config": {
            "startOffsetSec": 0,
            "clip_duration": -1,
            "num_frames": 64
        }
    }
}'
```

### Base64 Video Embedding

```bash
curl --location 'http://localhost:8000/embeddings' \
--header 'Content-Type: application/json' \
--data '{
    "model": "openai/clip-vit-base-patch32",
    "encoding_format": "float",
    "input": {
        "type": "video_base64",
        "segment_config": {
            "startOffsetSec": 0,
            "clip_duration": -1,
            "num_frames": 64
        },
        "video_base64": "<base64_video>"
    }
}'
```

### Video Frames Embedding

```bash
curl --location 'http://localhost:8000/embeddings' \
--header 'Content-Type: application/json' \
--data '{
    "model": "openai/clip-vit-base-patch32",
    "encoding_format": "float",
    "input": {
        "type": "video_frames",
        "video_frames": [
            {
                "type": "image_url",
                "image_url": "https://i.ytimg.com/vi/H_8J2YfMpY0/sddefault.jpg"
            },
            {
                "type": "image_base64",
                "image_base64": "<base64_image>"
            }
        ]
    }
}'
```

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
