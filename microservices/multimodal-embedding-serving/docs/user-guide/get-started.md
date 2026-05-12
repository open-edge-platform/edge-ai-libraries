# Get Started

This guide provides step-by-step instructions to quickly deploy and test the **Multimodal Embedding Serving microservice**.

## Prerequisites

Before you begin, confirm the following:

- **System Requirements**: Your system meets the [minimum requirements](./get-started/system-requirements.md).
- **Docker Installed**: Install Docker if needed. See [Get Docker](https://docs.docker.com/get-docker/).

This guide assumes basic familiarity with Docker commands and terminal usage.


## Environment Variables Reference

### Model Configuration

- **EMBEDDING_MODEL_NAME** - The model to use (e.g., "CLIP/clip-vit-b-16"). Refer to the [Supported Models](./supported-models.md) list for additional choices.
- **EMBEDDING_DEVICE** - Device for inference (CPU/GPU, default: CPU)
- **EMBEDDING_USE_OV** - Enable OpenVINO optimization (true/false, default: false)
- **EMBEDDING_OV_MODELS_DIR** - Directory for OpenVINO models (default: ./ov-models)

### Model Handler Performance

- **INFER_BATCH_SIZE** - Batch size for inference (default: 64). Compiles model to accept fixed batch input. Padding or split is done to accommodate dynamic input sizes.
- **PREPROCESS_WORKERS** - Number of parallel preprocessing workers (default: min(16, cpu_count * 2)). Higher is better but yields diminishing returns if > number of CPU cores.

### Video Frame Extraction

These variables control the video frame extraction pipeline performance and memory usage.

#### Extraction Performance
- **VIDEO_FRAME_BATCH_SIZE** - Batch size for video frame extraction (default: 64)
- **VIDEO_FRAME_DECODER_WORKERS** - Number of workers for video frame decoding (default: 8)
- **VIDEO_FRAME_QUEUE_SIZE** - Queue size for frame extraction pipeline (default: 32)

#### Shared Memory Configuration
- **VIDEO_FRAME_SHM_POOL_BLOCK_SIZE** - Shared memory block size in bytes (default: 1920*1080*3 = 6,220,800 bytes for 1080p RGB)
- **VIDEO_FRAME_SHM_POOL_BLOCKS_MULTIPLIER** - Multiplier for total shared memory blocks (default: 2)
  - Total blocks = VIDEO_FRAME_BATCH_SIZE × VIDEO_FRAME_SHM_POOL_BLOCKS_MULTIPLIER

#### Logging
- **VIDEO_FRAME_LOG_LEVEL** - Logging level for video frame extraction (DEBUG/INFO/WARNING/ERROR/CRITICAL, default: INFO)


## Set Environment Values

### Basic Setup

Set the required environment variables before launching the service.

```bash
export EMBEDDING_MODEL_NAME=CLIP/clip-vit-b-32
```

Refer to the [Supported Models](./supported-models.md) list for additional choices.

> **_NOTE:_** You can change the model, OpenVINO conversion, device, or tokenization parameters by editing `setup.sh`.

### Configure the Registry

```bash
export REGISTRY_URL=intel
export TAG=latest
```

### Configuration Examples

**Basic CPU setup (default)**:
```bash
export EMBEDDING_MODEL_NAME=CLIP/clip-vit-b-32
```

**GPU acceleration with OpenVINO**:
```bash
export EMBEDDING_MODEL_NAME=CLIP/clip-vit-b-32
export EMBEDDING_DEVICE=GPU
export EMBEDDING_USE_OV=true
```

**High Performance Video Processing**:
```bash
export EMBEDDING_MODEL_NAME=CLIP/clip-vit-b-32
export VIDEO_FRAME_BATCH_SIZE=256
export VIDEO_FRAME_DECODER_WORKERS=8
export VIDEO_FRAME_SHM_POOL_BLOCK_SIZE=$((1920 * 1080 * 3))  # 6MB for 1080p
export VIDEO_FRAME_SHM_POOL_BLOCKS_MULTIPLIER=2
export INFER_BATCH_SIZE=64
export PREPROCESS_WORKERS=16
```

**Memory-Constrained Environment**:
```bash
export EMBEDDING_MODEL_NAME=CLIP/clip-vit-b-32
export VIDEO_FRAME_BATCH_SIZE=64
export VIDEO_FRAME_DECODER_WORKERS=4
export VIDEO_FRAME_SHM_POOL_BLOCK_SIZE=$((1280 * 720 * 3))  # 2.8MB for 720p
export VIDEO_FRAME_SHM_POOL_BLOCKS_MULTIPLIER=2
```

**With OpenVINO Optimization on GPU**:
```bash
export EMBEDDING_MODEL_NAME=CLIP/clip-vit-b-16
export EMBEDDING_USE_OV=true
export EMBEDDING_DEVICE=GPU
export INFER_BATCH_SIZE=64
export PREPROCESS_WORKERS=16
```

**Debug Mode with Detailed Logging**:
```bash
export VIDEO_FRAME_LOG_LEVEL=INFO
export EMBEDDING_DEVICE=CPU
```

### Performance Tuning Guide

#### For Video Processing Bottlenecks
1. Increase `VIDEO_FRAME_BATCH_SIZE` (trades memory for throughput)
2. Increase `VIDEO_FRAME_DECODER_WORKERS` (limited by CPU cores)
3. Increase `VIDEO_FRAME_QUEUE_SIZE` if frames are being dropped

#### For Memory Constraints
1. Decrease `VIDEO_FRAME_BATCH_SIZE`
2. Decrease `VIDEO_FRAME_SHM_POOL_BLOCKS_MULTIPLIER`
3. Reduce `VIDEO_FRAME_SHM_POOL_BLOCK_SIZE` if processing lower resolutions

#### For Inference Performance
1. Increase `INFER_BATCH_SIZE` and `PREPROCESS_WORKERS`
2. Enable OpenVINO: `EMBEDDING_USE_OV=true`
3. Use GPU if available: `EMBEDDING_DEVICE=GPU`

### Set the environment variables

Set the environment with default values by running the below command. Note that this needs to be run anytime the environment variables are changed. For example: if running on GPU, additional environment variables will need to be set.

```bash
source setup.sh
```

## Quick Start with Docker

You can [build the Docker image](./get-started/build-from-source.md#steps-to-build) or pull a prebuilt image from the configured registry and tag. For prebuilt image, the `setup` script will configure the necessary variables to pull the right version of the image.

## Running the Server with CPU

```bash
docker compose -f docker/compose.yaml up -d
```

Verify the deployment by running the below command. The user should see a `healthy` status printed on the console.

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
set `num_frames: 0` to process all the frames.

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

- [Overview](./index.md)
- [System Requirements](./get-started/system-requirements.md)
- [How to Build from Source](./get-started/build-from-source.md)
- [Supported Models](./supported-models.md)
- [API Reference](./api-reference.md)
- [SDK Usage](./sdk-usage.md)
- [Wheel Installation](./wheel-installation.md)

<!--hide_directive
:::{toctree}
:hidden:

./get-started/system-requirements.md
./get-started/build-from-source.md

:::
hide_directive-->
