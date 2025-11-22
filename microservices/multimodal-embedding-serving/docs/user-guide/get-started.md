# Get Started

This guide provides step-by-step instructions to quickly deploy and test the **Multimodal Embedding Serving microservice**.

## Prerequisites

Before you begin, confirm the following:

- **System Requirements**: Your system meets the [minimum requirements](./system-requirements.md).
- **Docker Installed**: Install Docker if needed. See [Get Docker](https://docs.docker.com/get-docker/).

This guide assumes basic familiarity with Docker commands and terminal usage.

## Set Environment Values

Set the required environment variables before launching the service.

```bash
export EMBEDDING_MODEL_NAME=CLIP/clip-vit-b-32
```

Refer to the [Supported Models](./supported-models.md) list for additional choices.

> **_NOTE:_** You can change the model, OpenVINO conversion, device, or tokenization parameters by editing `setup.sh`.

### Optional Environment Variables

The microservice supports several optional variables to customize performance and logging. For the full list and examples, see the [Environment Variables section in the examples guide](../../examples/README.md#environment-variables).

**Quick Configuration Examples**:

```bash
# Basic CPU setup (default)
export EMBEDDING_MODEL_NAME=CLIP/clip-vit-b-32

# GPU acceleration with OpenVINO
export EMBEDDING_MODEL_NAME=CLIP/clip-vit-b-32
export EMBEDDING_DEVICE=GPU
export EMBEDDING_USE_OV=true

# Custom OpenVINO cache directory
export EMBEDDING_MODEL_NAME=MobileCLIP/mobileclip_s0
export EMBEDDING_OV_MODELS_DIR=/app/ov-models
```

**Key Environment Variables**:

- **EMBEDDING_DEVICE**: `CPU` (default) or `GPU`.
- **EMBEDDING_USE_OV**: Enable OpenVINO optimizations (`true`/`false`).
- **EMBEDDING_OV_MODELS_DIR**: Persistent directory for converted models.

Set the environment with default values by running:

```bash
source setup.sh
```

## Quick Start with Docker

You can [build the Docker image](./how-to-build-from-source.md#steps-to-build) or pull a prebuilt image as shown below.

### Configure the registry

```bash
export REGISTRY_URL=intel
export TAG=latest
```

## Running the Server with CPU

```bash
docker compose -f docker/compose.yaml up -d
```

Verify the deployment:

```bash
curl --location --request GET 'http://localhost:9777/health'
```

## Running the Server with GPU

### 1. Configure GPU Device

```bash
# Automatic GPU selection
export EMBEDDING_DEVICE=GPU

# Specific GPU index (if applicable)
export EMBEDDING_DEVICE=GPU.0
```

### 2. Run Setup Script

```bash
source setup.sh
```

> **Note**: When `EMBEDDING_DEVICE=GPU` is set, `setup.sh` applies GPU-friendly defaults, including setting `EMBEDDING_USE_OV=true`.

### 3. Start the Service

```bash
docker compose -f docker/compose.yaml up -d
```

### 4. Verify GPU Configuration

```bash
# Check service health
curl --location --request GET 'http://localhost:9777/health'

# Inspect active model capabilities
curl --location --request GET 'http://localhost:9777/model/capabilities'
```

## Stop the Multimodal Embedding microservice

```bash
docker compose -f docker/compose.yaml down
```

## Sample CURL Commands

The following samples mirror the accompanying Postman collection. All requests target `http://localhost:9777`.

### Text Embedding

```bash
curl --location 'http://localhost:9777/embeddings' \
--header 'Content-Type: application/json' \
--data '{
  "input": {
    "type": "text",
    "text": "Sample input text1"
  },
  "model": "CLIP/clip-vit-b-32",
  "encoding_format": "float"
}'
```

### Document Embedding (multiple texts)

```bash
curl --location 'http://localhost:9777/embeddings' \
--header 'Content-Type: application/json' \
--data '{
  "input": {
    "type": "text",
    "text": ["Sample input text1", "Sample input text2"]
  },
  "model": "CLIP/clip-vit-b-32",
  "encoding_format": "float"
}'
```

### Image URL Embedding

```bash
curl --location 'http://localhost:9777/embeddings' \
--header 'Content-Type: application/json' \
--data '{
  "input": {
    "type": "image_url",
    "image_url": "https://i.ytimg.com/vi/H_8J2YfMpY0/sddefault.jpg"
  },
  "model": "CLIP/clip-vit-b-32",
  "encoding_format": "float"
}'
```

### Image Base64 Embedding

```bash
curl --location 'http://localhost:9777/embeddings' \
--header 'Content-Type: application/json' \
--data '{
  "model": "CLIP/clip-vit-b-32",
  "encoding_format": "float",
  "input": {
    "type": "image_base64",
    "image_base64": "<image base64 value here>"
  }
}'
```

### Video Frames Embedding

```bash
curl --location 'http://localhost:9777/embeddings' \
--header 'Content-Type: application/json' \
--data '{
  "model": "CLIP/clip-vit-b-32",
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
        "image_base64": "<image base64 value here>"
      }
    ]
  }
}'
```

### Video URL Embedding (with segment config)

```bash
curl --location 'http://localhost:9777/embeddings' \
--header 'Content-Type: application/json' \
--data '{
  "model": "CLIP/clip-vit-b-32",
  "encoding_format": "float",
  "input": {
    "type": "video_url",
    "video_url": "https://sample-videos.com/video321/mp4/720/big_buck_bunny_720p_10mb.mp4",
    "segment_config": {
      "startOffsetSec": 0,
      "clip_duration": -1,
      "num_frames": 64,
      "frame_indexes": [1, 10, 20]
    }
  }
}'
```

### Video Base64 Embedding

```bash
curl --location 'http://localhost:9777/embeddings' \
--header 'Content-Type: application/json' \
--data '{
  "model": "CLIP/clip-vit-b-32",
  "encoding_format": "float",
  "input": {
    "type": "video_base64",
    "segment_config": {
      "startOffsetSec": 0,
      "clip_duration": -1,
      "num_frames": 64
    },
    "video_base64": "<video base64 value here>"
  }
}'
```

### Models, Current Model, and Capabilities

```bash
# List all available models
curl --location --request GET 'http://localhost:9777/models'

# Inspect the currently loaded model
curl --location --request GET 'http://localhost:9777/model/current'

# View modality support for the active model
curl --location --request GET 'http://localhost:9777/model/capabilities'
```

## Troubleshooting

1. **Docker container fails to start**
  - Run `docker logs multimodal-embedding-serving` to inspect failures.
  - Ensure required ports (default `9777`) are available.

2. **Cannot access the microservice**
  - Confirm the containers are running:

    ```bash
    docker ps
    ```

  - Verify `EMBEDDING_MODEL_NAME` points to a supported entry and rerun `source setup.sh` if you make changes.

3. **GPU runtime errors**
  - Check Intel GPU device nodes:

    ```bash
    ls -la /dev/dri
    ```

  - Confirm `EMBEDDING_USE_OV=true` for best performance with OpenVINO on GPU.

## Supporting Resources

- [Overview](Overview.md)
- [Supported Models](supported-models.md)
- [API Reference](api-reference.md)
- [SDK Usage](sdk-usage.md)
- [How to Build from Source](how-to-build-from-source.md)
- [System Requirements](system-requirements.md)
- [Wheel Installation](wheel-installation.md)
