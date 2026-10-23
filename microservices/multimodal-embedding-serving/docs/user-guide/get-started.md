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
- **EMBEDDING_USE_OV** - Enable OpenVINO optimization (true/false, default: false; `setup.sh` sets it to `true` unless it is already set). GME models (`GME/*`) run only on OpenVINO and require `EMBEDDING_USE_OV=true` on every device; with `false`, the service fails to start.
- **EMBEDDING_OV_MODELS_DIR** - OpenVINO model root. With `setup.sh` and Docker Compose, this is a **container path**, defaulting to `/app/ov_models`, not a host directory. See [Use a prepared GME OpenVINO model](#use-a-prepared-gme-openvino-model).

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

### Use a prepared GME OpenVINO model

By default, the service downloads the original GME checkpoint from Hugging Face
and converts it to OpenVINO on its first start. To skip that, for example when
the serving host has no Hugging Face access, prepare the OpenVINO model first
and then start the service with it.

#### Prepare the OpenVINO model

Skip this part if you already have a GME OpenVINO model: a directory that
contains `gme_openvino_config.json` and the `gme_language_*` and `gme_visual_*`
XML/BIN files.

1. From the microservice root, select the GME model and build the image. The
   same image converts the model and serves it:

   ```bash
   export EMBEDDING_MODEL_NAME=GME/gme-qwen2-vl-2b-instruct   # INT4: GME/gme-qwen2-vl-2b-instruct-int4
   unset REGISTRY_URL PROJECT_NAME
   export TAG=gme-local
   source setup.sh
   docker compose -f docker/compose.yaml build
   ```

   Run this and all the following commands in the same Bash terminal.

2. Download the original checkpoint (about 9 GB) from Hugging Face:

   ```bash
   pip install -U huggingface_hub
   hf download Alibaba-NLP/gme-Qwen2-VL-2B-Instruct \
     --include "*.json" --include "*.safetensors" --include "merges.txt" \
     --local-dir ./gme-Qwen2-VL-2B-Instruct
   ```

   To download through a Hugging Face mirror, set `HF_ENDPOINT` first, for
   example `export HF_ENDPOINT=https://hf-mirror.com`.

3. Convert the checkpoint with the export script in the image:

   ```bash
   mkdir -p ./gme-ov
   docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
     -v "$PWD/gme-Qwen2-VL-2B-Instruct:/checkpoint:ro" \
     -v "$PWD/gme-ov:/output" \
     "multimodal-embedding-serving:$TAG" \
     python scripts/export_gme_ov.py \
       --model "$EMBEDDING_MODEL_NAME" --checkpoint /checkpoint --output-dir /output
   ```

   [`scripts/export_gme_ov.py`](../../scripts/export_gme_ov.py) runs the same
   conversion as the service's first start, checks the result against the
   original model, and writes the OpenVINO model to `./gme-ov/<model directory>`
   (see the table below). INT8 takes several minutes; INT4 adds a calibration
   pass and takes longer.

#### Start the service with the prepared model

The Compose file keeps models in the Docker named volume `ov-models`, mounted
at `/app/ov_models` in the container. Copy the OpenVINO model into that volume
once; the service then loads it without downloading or converting anything.
The model directory in the volume must have the name registered for the model:

| `EMBEDDING_MODEL_NAME` | Model directory |
| --- | --- |
| `GME/gme-qwen2-vl-2b-instruct` | `gme-qwen2-vl-2b-instruct-openvino` |
| `GME/gme-qwen2-vl-2b-instruct-int4` | `gme-qwen2-vl-2b-instruct-openvino-int4` |

1. If you skipped the preparation above, select the model and build the image
   as in its step 1. Then point to the OpenVINO model on the host and name its
   directory in the volume:

   ```bash
   export GME_OV_MODEL_DIR="$PWD/gme-ov/gme-qwen2-vl-2b-instruct-openvino"
   export GME_MODEL_DIR_NAME=gme-qwen2-vl-2b-instruct-openvino
   ```

   `GME_OV_MODEL_DIR` must point directly to the directory containing
   `gme_openvino_config.json`; its own name does not matter.
   `GME_MODEL_DIR_NAME` is the name from the table above for your
   `EMBEDDING_MODEL_NAME`.

2. Stop a running service, then copy the model into the volume:

   ```bash
   docker compose -f docker/compose.yaml stop multimodal-embedding-serving
   set -o pipefail
   tar -C "$GME_OV_MODEL_DIR" -cf - . |
     docker compose -f docker/compose.yaml run --rm --no-deps -T \
       -e GME_MODEL_DIR_NAME="$GME_MODEL_DIR_NAME" \
       --user root --entrypoint sh multimodal-embedding-serving -c '
         set -eu
         model_dir="/app/ov_models/$GME_MODEL_DIR_NAME"
         if [ -e "$model_dir" ]; then
           echo "Refusing to overwrite existing model: $model_dir" >&2
           exit 1
         fi
         mkdir -p "$model_dir"
         tar -xf - -C "$model_dir"
         chown -R appuser:appuser "$model_dir"
       '
   ```

   The copy refuses to overwrite a model that is already in the volume.
   Continue only after it succeeds.

3. Start the service and check that it loaded the model:

   ```bash
   docker compose -f docker/compose.yaml up -d --force-recreate
   docker logs -f --tail=100 multimodal-embedding-serving
   ```

   The log shows `Reusing existing GME OpenVINO package at /app/ov_models/...`.
   Once loading finishes, exit the log viewer with `Ctrl+C` and check:

   ```bash
   curl -fsS http://localhost:9777/health
   curl -fsS http://localhost:9777/model/current
   ```

The model stays in the `ov-models` volume when the container is recreated or
removed, so later starts reuse it. Do not delete the volume to get a fresh
container.

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

> [!IMPORTANT]
> To run a GME model on the integrated GPU of an Intel Core Ultra Series 3
> (Panther Lake) processor, set `OV_PERFORMANCE_MODE=LATENCY`. `setup.sh` sets
> `THROUGHPUT` for GPU, so export `LATENCY` again after `source setup.sh`:
>
> ```bash
> export OV_PERFORMANCE_MODE=LATENCY
> ```
>
> In `THROUGHPUT` mode on this GPU, GME image and image+text requests can hang,
> while the host kernel log reports a reset of the `xe` driver's BCS engine.
> Other GPUs are not affected.

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
