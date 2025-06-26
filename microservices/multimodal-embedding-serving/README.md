# MultiModal Embedding Serving

## Overview

The MultiModal Embedding Serving is designed to generate embeddings for text, image URLs, base64 encoded images, video URLs, and base64 encoded videos. It leverages the CLIP (Contrastive Language-Image Pretraining) model to create these embeddings.

## Contents

- [Project Structure](#project-structure)
- [Environment Variables](#environment-variables)
  - [List of Environment Variables](#list-of-environment-variables)
- [Running the Microservice](#running-the-microservice)
  - [CPU](#cpu)
  - [GPU - Arc](#gpu---arc)
- [Sample CURL Commands](#sample-curl-commands)

## Project Structure

```plaintext
multimodal-embedding-serving/
├── app/
│   ├── app.py             # FastAPI server setup
├── docker/
│   ├── Dockerfile             # Dockerfile for building the Docker image
│   ├── Dockerfile.arc-gpu     # Dockerfile for building the GPU Docker image
├── src/
│   ├── __init__.py        # Package initialization
|   ├── common.py          # Common utilities
│   ├── models.py          # Model definitions
│   ├── utils.py           # Utility functions
├── pyproject.toml         # Project configuration and dependencies
├── README.md              # Project documentation
├── setup.sh               # Script to set environment variables
├── compose.yaml           # Docker Compose configuration
├── compose.arc-gpu.yaml   # Docker Compose configuration for Intel Arc GPU
```

## 📄 Prerequisites

- Install Docker: [Installation Guide](https://docs.docker.com/get-docker/).
- Install Docker Compose: [Installation Guide](https://docs.docker.com/compose/install/).


**_(Optional)_** Docker Compose builds the _MultiModal Embedding Serving_ with a default image and tag name. If you want to use a different image and tag, export these variables:

    ```bash
    export REGISTRY_URL="your_container_registry_url"
    export PROJECT_NAME="your_project_name"
    export TAG="your_tag"
    ```

> **_NOTE:_** `PROJECT_NAME` will be suffixed to `REGISTRY_URL` to create a namespaced url. Final image name will be created/pulled by further suffixing the application name and tag with the namespaced url.

> **_EXAMPLE:_** If variables are set using above command, the final image names for _Video Summary Reference Application_ would be `<your-container-registry-url>/<your-project-name>/multimodal-embedding-serving:<your-tag>`. If variables are not set, in that case, the `TAG` will have default value as _latest_. Hence, final image will be : `multimodal-embedding-serving:latest`.

## Environment Variables

1. The service supports multimodal embedding models, but if you want to work only with text embeddings, set the following environment variable:

```bash
export USE_ONLY_TEXT_EMBEDDINGS=True
```

2. Set the required `VCLIP_MODEL` and `QWEN_MODEL` environment variable:

```bash
export VCLIP_MODEL="openai/clip-vit-base-patch32"
export QWEN_MODEL="Qwen/Qwen3-Embedding-0.6B"
```

3. Set the other required environment with default values by running the following script:

```bash
source setup.sh
```

### List of Environment Variables

- `APP_NAME`: Name of the application.
- `APP_DISPLAY_NAME`: Display name of the application.
- `APP_DESC`: Description of the application.
- `TEXT_EMBEDDING_MODEL_NAME`: Name of the pre-trained text embedding model.
- `IMAGE_EMBEDDING_MODEL_NAME`: Name of the pre-trained multimodal embedding model.
- `USE_ONLY_TEXT_EMBEDDINGS`: Set this to true to enable text embeddings only, instead of multimodal embeddings
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

## Running the Microservice

### CPU

1. **Build the Docker image**:

   ```bash
   docker compose -f compose.yaml build
   ```

2. **Run the service**:

   ```bash
   docker compose -f compose.yaml up
   ```

### GPU - Arc

1. **Build the Docker image**:

   ```bash
   docker compose -f compose.arc-gpu.yaml build
   ```

2. **Run the service**:

   ```bash
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
