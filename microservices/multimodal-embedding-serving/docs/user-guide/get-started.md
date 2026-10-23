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
- **EMBEDDING_DEVICE** - Device for inference (CPU/GPU/NPU, default: CPU)
- **EMBEDDING_USE_OV** - Enable OpenVINO optimization (true/false, default: false)
- **EMBEDDING_OV_MODELS_DIR** - OpenVINO model root. With `setup.sh` and Docker Compose, this is a **container path**, defaulting to `/app/ov_models`, not a host directory. See [Reuse local OpenVINO models](#reuse-local-openvino-models).

### Model Handler Performance

- **INFER_BATCH_SIZE** - Batch size for inference (default: 64; `setup.sh` overrides this to 16 on CPU/NPU and 32 on GPU). Compiles model to accept fixed batch input. Padding or split is done to accommodate dynamic input sizes.
- **PREPROCESS_WORKERS** - Number of parallel preprocessing workers (default: min(16, cpu_count * 2)). Higher is better but yields diminishing returns if > number of CPU cores.

### QwenText Models on NPU

QwenText models require static-shape compilation on NPU and expose two
additional variables (`EMBEDDING_STATIC_SEQ_LEN` and
`EMBEDDING_CHUNK_LONG_TEXT`) that control the token budget and how longer text
is handled. These apply only to the QwenText family on NPU and need no
configuration by default.

See [QwenText Models on NPU](./qwentext-on-npu.md).

### Video Frame Extraction

These variables control the video frame extraction pipeline performance and memory usage.

#### Extraction Performance

- **VIDEO_FRAME_BATCH_SIZE** - Batch size for video frame extraction (default: 64; `setup.sh` overrides this to 64 on CPU/NPU and 256 on GPU)
- **VIDEO_FRAME_DECODER_WORKERS** - Number of workers for video frame decoding (default: 8)
- **VIDEO_FRAME_QUEUE_SIZE** - Queue size for frame extraction pipeline (default: 32)

The defaults above are the application's built-in values, which apply when the
service runs without `setup.sh` (for example the SDK/wheel or a bare container).
When you source `setup.sh`, it selects the batch sizes from `EMBEDDING_DEVICE`.
Exporting either variable before sourcing `setup.sh` always takes precedence.

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

> ***NOTE:*** You can change the model, OpenVINO conversion, device, or tokenization parameters by editing `setup.sh`.

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
export PREPROCESS_WORKERS=16
```

`EMBEDDING_DEVICE=GPU` already selects the tuned GPU batch sizes
(`INFER_BATCH_SIZE=32`, `VIDEO_FRAME_BATCH_SIZE=256`), so set those two only to
override the defaults.

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
3. Use GPU or NPU if available: `EMBEDDING_DEVICE=GPU` or `EMBEDDING_DEVICE=NPU`

### Set the environment variables

Set the environment with default values by running the below command. Note that this needs to be run anytime the environment variables are changed. For example: if running on GPU, additional environment variables will need to be set.

```bash
source setup.sh
```

## Quick Start with Docker

You can [build the Docker image](./get-started/build-from-source.md#steps-to-build) or pull a prebuilt image from the configured registry and tag. For prebuilt image, the `setup` script will configure the necessary variables to pull the right version of the image.

### Reuse local OpenVINO models

The default Compose file mounts the Docker **named volume** `ov-models` at
`/app/ov_models`. This is not a directory named `ov-models` in your checkout.
Putting files in `./ov-models`, or setting `EMBEDDING_OV_MODELS_DIR` to a host
path, does not make those files available inside the container.

You can copy an existing model package into the named volume once and use the
unchanged Compose file. The example below uses a complete, exported GME
OpenVINO package, not an original PyTorch checkpoint.

1. From the microservice root, configure the service and build an image containing
   the current GME handler. Run all commands in the same Bash terminal:

   ```bash
   export GME_OV_MODEL_DIR="/absolute/path/to/exported-gme-package"
   export EMBEDDING_MODEL_NAME="GME/gme-qwen2-vl-2b-instruct"
   export EMBEDDING_DEVICE=CPU
   export EMBEDDING_USE_OV=true
   export EMBEDDING_OV_MODELS_DIR=/app/ov_models
   unset REGISTRY_URL PROJECT_NAME
   export TAG=gme-local
   source setup.sh
   docker compose -f docker/compose.yaml build
   ```

   `GME_OV_MODEL_DIR` is a host-side variable used only by the copy command below.
   It must point directly to the directory containing `gme_openvino_config.json`.
   Copy the entire package, including its XML/BIN pairs, model configuration,
   processor and tokenizer files.

2. Stop any existing service instance before modifying its model volume:

   ```bash
   docker compose -f docker/compose.yaml stop multimodal-embedding-serving
   ```

3. Copy the package through a temporary container using the service's existing
   volume mount. This does not start the model server or add a host bind mount:

   ```bash
   set -o pipefail
   tar -C "$GME_OV_MODEL_DIR" -cf - . |
     docker compose -f docker/compose.yaml run --rm --no-deps -T \
       --user root --entrypoint sh multimodal-embedding-serving -c '
         set -eu
         model_dir=/app/ov_models/gme-qwen2-vl-2b-instruct-openvino
         if [ -e "$model_dir" ]; then
           echo "Refusing to overwrite existing package: $model_dir" >&2
           exit 1
         fi
         mkdir -p "$model_dir"
         tar -xf - -C "$model_dir"
         chown -R appuser:appuser "$model_dir"
         chmod -R u+rwX "$model_dir"
       '
   ```

   The copy refuses to overwrite an existing package. Continue only after it
   succeeds. The resulting layout inside the container is:

   ```text
   /app/ov_models/
   └── gme-qwen2-vl-2b-instruct-openvino/
       ├── gme_openvino_config.json
       ├── gme_language_int8.xml
       ├── gme_language_int8.bin
       ├── gme_visual_int8.xml
       ├── gme_visual_int8.bin
       └── ... processor, tokenizer and model configuration files
   ```

   The package directory name must match the layout above; the host directory
   can have a different name. To inspect the named volume's location, run
   `docker volume inspect ov-models --format '{{.Mountpoint}}'`. Docker manages
   this location; use the container-based copy instead of editing Docker's
   storage directory directly.

4. Create a fresh service container and check startup:

   ```bash
   docker compose -f docker/compose.yaml up -d --force-recreate
   docker logs -f --tail=100 multimodal-embedding-serving
   ```

   A complete package is reused without downloading or converting the original
   weights. An existing but incomplete package causes startup to fail rather
   than being overwritten. Once loading finishes, exit the log viewer with
   `Ctrl+C` and check:

   ```bash
   curl -fsS http://localhost:9777/health
   curl -fsS http://localhost:9777/model/current
   ```

Recreating or removing the container does not remove the external `ov-models`
volume. Do not delete that volume to obtain a fresh container.

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

> [!NOTE]
> When `EMBEDDING_DEVICE=GPU` is set, `setup.sh` applies GPU-friendly defaults, including setting `EMBEDDING_USE_OV=true`.

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

### 5. (Optional) Optimize GME on GPU

For lower GME latency on an Intel GPU, use the INT4 GME model
(`GME/gme-qwen2-vl-2b-instruct-int4`) together with an image whose OpenVINO
GPU plugin is rebuilt with GME-specific optimization patches. See
[Optimize GME on Intel GPU](./gme-embedding-optimization.md).

## Running the Server with NPU

### 1. Configure NPU Device

```bash
export EMBEDDING_DEVICE=NPU
```

> [!NOTE]
> NPU support is model-dependent. Verify that the selected model is supported on NPU by checking the [OpenVINO Supported Models](https://docs.openvino.ai/2026/documentation/compatibility-and-support/supported-models.html).

### 2. Run the Setup Script

```bash
source setup.sh
```

> [!NOTE]
> When `EMBEDDING_DEVICE=NPU` is set, `setup.sh` automatically enables `EMBEDDING_USE_OV=true`.

### 3. Start the Service with docker compose

```bash
docker compose -f docker/compose.yaml up -d
```

### 4. Verify NPU Configuration

```bash
# Verify /dev/accel/accel0 is available on the host
ls -l /dev/accel/accel0

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

`encoding_format` is optional for `/embeddings`; if omitted, the service defaults it to `float`.

### Text Embedding

```bash
curl --location 'http://localhost:9777/embeddings' \
--header 'Content-Type: application/json' \
--data '{
  "input": {
    "type": "text",
    "text": "Sample input text1"
  },
  "model": "CLIP/clip-vit-b-32"
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
    "image_url": "https://storage.openvinotoolkit.org/repositories/openvino_notebooks/data/data/image/coco_bike.jpg"
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
        "image_url": "https://storage.openvinotoolkit.org/repositories/openvino_notebooks/data/data/image/coco_bike.jpg"
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
    "video_url": "https://raw.githubusercontent.com/intel-iot-devkit/sample-videos/refs/heads/master/car-detection.mp4",
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

### Fused Image + Text Embedding

Each item's image and text are embedded jointly into one vector. Only models whose `/model/capabilities` reports `supports_fused: true` (GME) accept this input.

```bash
curl --location 'http://localhost:9777/embeddings' \
--header 'Content-Type: application/json' \
--data '{
  "model": "GME/gme-qwen2-vl-2b-instruct",
  "encoding_format": "float",
  "input": {
    "type": "fused",
    "items": [
      {
        "text": "Figure 3: throughput under different loads",
        "image": {"type": "image_base64", "image_base64": "<image base64 value here>"}
      }
    ]
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

1. **Cannot access the microservice**

- Confirm the containers are running:

    ```bash
    docker ps
    ```

- Verify `EMBEDDING_MODEL_NAME` points to a supported entry and rerun `source setup.sh` if you make changes.

1. **GPU runtime errors**

- Check Intel GPU device nodes:

    ```bash
    ls -la /dev/dri
    ```

- Confirm `EMBEDDING_USE_OV=true` for best performance with OpenVINO on GPU.

1. **NPU acceleration inactive**

- Confirm `/dev/accel/accel0` is available on the host:

    ```bash
    ls -l /dev/accel/accel0
    ```

- Ensure `EMBEDDING_DEVICE=NPU` is set and `EMBEDDING_USE_OV=true`.
- Verify the selected model supports NPU inference via the [OpenVINO Supported Models](https://docs.openvino.ai/2026/documentation/compatibility-and-support/supported-models.html) page.

## Known Issues and NPU Notes

- **First NPU run is slow (one-time model compilation)**: The first time a model
  is loaded on NPU, OpenVINO compiles the model to an NPU-specific blob, which can
  take noticeably longer than CPU/GPU startup. This is expected and happens only
  once per model/configuration.
- **Model caching speeds up subsequent runs**: The service caches the compiled
  OpenVINO blob on disk, so later starts reuse it and come up quickly. The cache
  location is controlled by `OV_CACHE_DIR` (or `EMBEDDING_OV_CACHE_DIR`); when
  unset it defaults to an `ov_cache/` directory next to the OpenVINO IR. Persist
  this directory (for example, via a mounted volume) to retain the cache across
  container restarts.

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
