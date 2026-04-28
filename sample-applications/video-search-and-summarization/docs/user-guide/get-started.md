# Get Started

The Video Search and Summarization (VSS) sample application helps developers create a summary of long form video, search for the right video, and combine both search and summarization pipelines. This guide will help you set up, run, and modify the sample application on local and Edge AI systems.

This guide shows how to:

- **Set up the sample application**: Use Setup script to quickly deploy the application in your environment.
- **Run different application modes**: Execute different application modes available in the application to perform video search and summarization.
- **Modify application parameters**: Customize settings like inference models and deployment configurations to adapt the application to your specific requirements.

## Prerequisites

- Verify that your system meets the [minimum requirements](./get-started/system-requirements.md).
- Install Docker tool: [Installation Guide](https://docs.docker.com/get-docker/).
- Install Docker Compose tool: [Installation Guide](https://docs.docker.com/compose/install/).
- Install Python programming language v3.11

## Project Structure

The repository is organized as follows:

```text
sample-applications/video-search-and-summarization/
├── config                     # Configuration files
│   ├── nginx.conf             # NGINX configuration
│   └── rmq.conf               # RabbitMQ configuration
├── docker                     # Docker Compose files
│   ├── compose.base.yaml      # Base services configuration
│   ├── compose.summary.yaml   # Compose override file for video summarization services
│   ├── compose.vllm.yaml      # vLLM inference service overlay
│   ├── compose.search.yaml    # Compose override file for video search services
│   ├── compose.telemetry.yaml # Optional telemetry collector (vss-collector)
│   └── compose.gpu_ovms.yaml  # GPU configuration for OpenVINO™ model server
├── docs                       # Documentation
│   └── user-guide             # User guides and tutorials
├── pipeline-manager           # Backend service which orchestrates the video Summarization and search
├── search-ms                  # Video search microservice
├── ui                         # Video search and summarization UI code
├── build.sh                   # Script for building application images
├── setup.sh                   # Setup script for environment and deployment
└── README.md                  # Project documentation
```

## Set Required Environment Variables

Before running the application, you need to set several environment variables:

1. **Configure the registry**:
   The application uses registry URL and tag to pull the required images.

   ```bash
   export REGISTRY_URL=intel
   export TAG=latest
   ```

2. **Set required credentials for some services**:
   Following variables **MUST** be set on your current shell before running the setup script:

   ```bash
   # MinIO credentials (object storage)
   export MINIO_ROOT_USER=<your-minio-username>
   export MINIO_ROOT_PASSWORD=<your-minio-password>

   # PostgreSQL credentials (database)
   export POSTGRES_USER=<your-postgres-username>
   export POSTGRES_PASSWORD=<your-postgres-password>

   # RabbitMQ credentials (message broker)
   export RABBITMQ_USER=<your-rabbitmq-username>
   export RABBITMQ_PASSWORD=<your-rabbitmq-password>
   ```

3. **Set environment variables for customizing model selection**:

   You **must** set these environment variables on your current shell. Setting these variables help you customize the models used for deployment.

   ```bash
   # For VLM-based chunk captioning and video summarization on CPU
   export VLM_MODEL_NAME="Qwen/Qwen2.5-VL-3B-Instruct"  # or any other supported VLM model on CPU

   # For VLM-based chunk captioning and video summarization on GPU
   export VLM_MODEL_NAME="OpenVINO/Phi-3.5-vision-instruct-int8-ov"  # or any other supported VLM model on GPU
   export VLM_TARGET_DEVICE="GPU"  # Options: CPU, GPU, NPU, HETERO:GPU,CPU

   # (Optional) For OVMS split-model summarization, set a dedicated LLM model for final summary.
   # If this is not set, OVMS uses VLM_MODEL_NAME for both chunk captioning and final summarization.
   export OVMS_LLM_MODEL_NAME="Intel/neural-chat-7b-v3-3"  # or any other supported LLM model
   export LLM_TARGET_DEVICE="CPU"  # Options: CPU, GPU, NPU, HETERO:GPU,CPU

   # When ENABLE_VLLM=true, vLLM is the only inference backend and setup.sh ignores OVMS_LLM_MODEL_NAME.

   # Model used by Audio Analyzer service. Only Whisper models variants are supported.
   # Common Supported models: tiny.en, small.en, medium.en, base.en, large-v1, large-v2, large-v3.
   # You can provide just one or comma-separated list of models.
   export ENABLED_WHISPER_MODELS="tiny.en,small.en,medium.en"

   # Object detection model used for Video Ingestion Service. Only Yolo models are supported.
   export OD_MODEL_NAME="yolov8l-worldv2"

   # --search : use any multimodal embedding model for video-only search flows
   export EMBEDDING_MODEL_NAME="CLIP/clip-vit-b-32"

   # --all    : configure both the multimodal embedding model and a dedicated text embedding model
   export EMBEDDING_MODEL_NAME="CLIP/clip-vit-b-32"
   export TEXT_EMBEDDING_MODEL_NAME="QwenText/qwen3-embedding-0.6b"

    # (Optional, summary mode only) Set the default for audio transcript summarization.
    # Default is true. Users can override this per-video in the upload modal.
    # export PM_AUDIO_USE_FULL_TRANSCRIPT_SUMMARY=false
   ```

   > **Audio Transcript Summarization (`PM_AUDIO_USE_FULL_TRANSCRIPT_SUMMARY`)**:
   > When enabled (the default), the pipeline runs a separate LLM-based map-reduce summarization pass over the complete audio transcript *before* generating the final video summary. The condensed transcript summary is then injected into the video summary prompt via the `%audio_summary%` placeholder, giving the LLM a coherent, high-quality representation of spoken content rather than raw subtitle fragments. This significantly improves accuracy for dialogue-heavy or narration-heavy videos. When disabled, audio transcripts are only used at the chunk captioning level — each chunk's VLM prompt includes its time-matched portion of the transcript — but no audio content is included in the final map-reduce video summary.
   >
   > This environment variable sets the **default** value. Users can override it per-video using the **"Use Audio in Summary"** checkbox in the Audio Settings section of the video upload modal.

   > **Note**: `TEXT_EMBEDDING_MODEL_NAME` is required when running `source setup.sh --all`. The setup script validates both variables and uses the text embedding value to override `EMBEDDING_MODEL_NAME` for unified search + summarization deployment. Review the supported model list in [supported-models](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/microservices/multimodal-embedding-serving/docs/user-guide/supported-models.md) before choosing model IDs.

4. **Configure Directory Watcher (Video Search Mode Only)**:

   For automated video ingestion in search mode, you can use the directory watcher service:

   ```bash
   # Path to the directory to watch on the host system. Default: "edge-ai-libraries/sample-applications/video-search-and-summarization/data"
   export VS_WATCHER_DIR="/path/to/your/video/directory"
   ```

   > **📁 Directory Watcher**: For complete setup instructions, configuration options, and usage details, see the [Directory Watcher Service Guide](./directory-watcher-guide.md). This service only works with the `--search` mode.

5. **Control the frame extraction interval (Video Search Mode)**:

   The DataPrep microservice samples frames from uploaded videos according to the `FRAME_INTERVAL` environment variable. Set this variable before running `source setup.sh --search` to control how often frames are selected for processing.

   ```bash
   export FRAME_INTERVAL=15
   ```

   In the example above, DataPrep processes every fifteenth frame: each selected frame (optionally after object detection) is converted into embeddings and stored in the vector database. Lower values improve recall at the cost of higher compute and storage usage, while higher values reduce processing load but may skip important frames. If you do not set this variable, the service falls back to its configured default.

6. **Enable ROI consolidation (Video Search Mode)**:

   ROI consolidation groups overlapping object detections into merged regions of interest (ROIs) before cropping for embeddings. Enable this feature and tune it with the following environment variables:

   ```bash
   # Enable ROI consolidation (default: false)
   export ROI_CONSOLIDATION_ENABLED=true

   # IoU threshold for grouping ROIs (higher = stricter merging)
   export ROI_CONSOLIDATION_IOU_THRESHOLD=0.2

   # Only merge ROIs with the same class label when true
   export ROI_CONSOLIDATION_CLASS_AWARE=false

   # Expand merged ROIs by a fraction of width/height
   export ROI_CONSOLIDATION_CONTEXT_SCALE=0.2
   ```

   The IoU calculation follows the standard formula:

   $$
   IoU(A, B) = \frac{|A \cap B|}{|A \cup B|}
   $$

   > **Note:** Enabling ROI consolidation can improve search relevance by creating more meaningful regions for embedding, but it may also increase processing time.

7. **(Optional) Telemetry collection for Search**:

   The Video Search mode can start a lightweight telemetry collector (`vss-collector`) that streams CPU/RAM/GPU metrics to the Pipeline Manager and renders them in the UI.

   ```bash
   # Disabled by default for --search and --all
   export ENABLE_VSS_COLLECTOR=false

   # Enable the collector if you want telemetry
   export ENABLE_VSS_COLLECTOR=true
   ```

8. **Tune Inference Concurrency (Video Summarization Mode)**:

   Control how many concurrent inference requests the pipeline manager sends to OVMS or vLLM. These values affect throughput and resource utilization:

   ```bash
   # Maximum concurrent VLM requests for chunk captioning (default: 6 for CPU, 1 for GPU)
   export PM_VLM_CONCURRENT=6

   # Maximum concurrent LLM requests for final summarization (default: 1)
   export PM_LLM_CONCURRENT=1
   ```

   > **Note**: For OVMS deployments, these values should not exceed the `max_num_seqs` parameter configured during model export (default: 256). For GPU deployments, lower concurrency (1-2) is recommended to avoid memory pressure. The setup script automatically adjusts these defaults based on the selected device (CPU vs GPU).

9. **Override OVMS Model Weight Compression Format (Video Summarization Mode)**:

    When using OVMS for inference, the setup script auto-selects the model weight compression format based on the target device (`int8` for CPU, `int4` for GPU/NPU). You can override this auto-detection by setting these variables before running the setup script:

    ```bash
    # Override VLM model weight compression format (default: int8 for CPU, int4 for GPU/NPU)
    export VLM_COMPRESSION_WEIGHT_FORMAT=int4

    # Override LLM model weight compression format (default: int8 for CPU, int4 for GPU/NPU)
    export LLM_COMPRESSION_WEIGHT_FORMAT=int4
    ```

    > **Note**: Lower precision formats like `int4` reduce memory usage and can improve throughput, but may affect output quality. The default auto-detection (`int8` for CPU, `int4` for GPU/NPU) is recommended for most use cases.

10. **Configure Embedding Processing Mode (Video Search Mode)**:

    Control how the embedding model is loaded and invoked during video search indexing:

    ```bash
    # Embedding processing mode: "sdk" (default) or "api"
    #   - "sdk": Loads the embedding model directly within the vdms-dataprep container (optimized, lower memory overhead)
    #   - "api": Routes embedding requests via HTTP to the multimodal-embedding-serving container
    export EMBEDDING_PROCESSING_MODE=sdk

    # Enable OpenVINO optimization for SDK-mode embedding (default: true)
    # Automatically set to true when using GPU mode
    export SDK_USE_OPENVINO=true
    ```

    > **Note**: SDK mode is recommended for most deployments as it avoids inter-container HTTP overhead. Set `EMBEDDING_PROCESSING_MODE=api` if you need the embedding model served as a standalone microservice.

**🔐 Work with Gated Models**

To run a **GATED MODEL** like Llama models, you will need to pass your [huggingface token](https://huggingface.co/docs/hub/security-tokens#user-access-tokens). You will need to request for an access to a specific model by going to the respective model page on Hugging Face website.

Go to <https://huggingface.co/settings/tokens> to get your token.

```bash
export GATED_MODEL=true
export HUGGINGFACE_TOKEN=<your_huggingface_token>
```

Once exported, run the setup script as mentioned [here](#run-the-application). Switch off the `GATED_MODEL` flag by running `export GATED_MODEL=false`, once you no longer use gated models. This avoids unnecessary authentication step during setup.

## Application Mode Overview

The Video Summarization application offers multiple modes and deployment options:

| Mode | Description | Flag (used with setup script) |
|-------|-------------|------|
| Video Summarization | Video frame captioning and summarization | `--summary` |
| Video Search | Video indexing and semantic search | `--search` |
| Video Search + Summarization | Both search and summarization capabilities | `--all` |

> **Automated Video Ingestion**: The Video Search mode includes an optional Directory Watcher service for automated video processing. See the [Directory Watcher Service Guide](./directory-watcher-guide.md) for details on setting up automatic video monitoring and ingestion.

### Deployment Options for Video Summarization

| Deployment Option | Chunk-Wise Summary<sup>(1)</sup> Configuration | Final Summary<sup>(2)</sup> Configuration | Environment Variables to Set | Recommended Models | Recommended Usage Model |
|--------|--------------------|---------------------|-----------------------|----------------|----------------|
| OVMS shared-model CPU | OVMS-hosted VLM on CPU | Same OVMS-hosted VLM on CPU | Default | VLM: `Qwen/Qwen2.5-VL-3B-Instruct` | Default CPU-only summarization flow. |
| OVMS shared-model GPU | OVMS-hosted VLM on GPU | Same OVMS-hosted VLM on GPU | `VLM_TARGET_DEVICE=GPU` | VLM: `OpenVINO/Phi-3.5-vision-instruct-int8-ov` | Single-model OVMS deployment with GPU acceleration. |
| OVMS split-model CPU/CPU | OVMS-hosted VLM on CPU | OVMS-hosted LLM on CPU | `OVMS_LLM_MODEL_NAME=<llm-model>` | VLM: `Qwen/Qwen2.5-VL-3B-Instruct`<br>LLM: `Intel/neural-chat-7b-v3-3` | One OVMS instance hosts separate VLM and LLM models on CPU. |
| OVMS split-model GPU/CPU | OVMS-hosted VLM on GPU | OVMS-hosted LLM on CPU | `VLM_TARGET_DEVICE=GPU` with `OVMS_LLM_MODEL_NAME=<llm-model>` | VLM: `OpenVINO/Phi-3.5-vision-instruct-int8-ov`<br>LLM: `Intel/neural-chat-7b-v3-3` | Use GPU for captioning while keeping final summary on CPU. |
| OVMS split-model CPU/GPU | OVMS-hosted VLM on CPU | OVMS-hosted LLM on GPU | `LLM_TARGET_DEVICE=GPU` with `OVMS_LLM_MODEL_NAME=<llm-model>` | VLM: `Qwen/Qwen2.5-VL-3B-Instruct`<br>LLM: `Intel/neural-chat-7b-v3-3` | Use GPU for the final-summary LLM while keeping captioning on CPU. |
| OVMS split-model CPU/NPU | OVMS-hosted VLM on CPU | OVMS-hosted LLM on NPU | `LLM_TARGET_DEVICE=NPU` with `OVMS_LLM_MODEL_NAME=<llm-model>` | VLM: `Qwen/Qwen2.5-VL-3B-Instruct`<br>LLM: `OpenVINO/Qwen3-8B-int4-cw-ov` | Use NPU for the final-summary LLM while keeping captioning on CPU. |
| vLLM-only CPU | vLLM-hosted VLM on CPU | Same vLLM-hosted VLM on CPU | `ENABLE_VLLM=true` | VLM: `Qwen/Qwen2.5-VL-3B-Instruct` | All-vLLM mode for CPU-only deployments. |

> **Note:**
>
> 1) Chunk-Wise Summary is a method of summarization where it breaks videos into chunks and then summarizes each chunk.
> 2) Final Summary is a method of summarization where it summarizes the whole video.
> 3) Mixed OVMS+vLLM deployments are not supported in the compose setup. Choose either OVMS-only or vLLM-only for summarization.
> 4) `VLM_TARGET_DEVICE` and `LLM_TARGET_DEVICE` support values: `CPU`, `GPU`, `NPU`, or `HETERO:GPU,CPU` for heterogeneous execution.
> 5) **NPU Support:** Not all models support NPU execution. Verify model compatibility at the [OpenVINO Supported Models](https://docs.openvino.ai/2026/documentation/compatibility-and-support/supported-models.html) page before selecting `NPU` as target device.

## Using Edge Microvisor Toolkit

If you are running the VSS application on an OS image built with **Edge Microvisor Toolkit** — an Azure Linux-based build pipeline for Intel® platforms — follow the below listed guidelines. The guidelines vary based on the flavor of Edge Microvisor Toolkit used and the user is encouraged to refer to detailed documentation for [EMT-D](https://github.com/open-edge-platform/edge-microvisor-toolkit/blob/3.0/docs/developer-guide/emt-architecture-overview.md#developer-node-mutable-iso-image) and [EMT-S](https://github.com/open-edge-platform/edge-microvisor-toolkit-standalone-node). A few specific dependencies are called out below.

Install the `mesa-libGL` package. Installing `mesa-libGL` provides the OpenGL library which is needed by the `Audio Analyzer service`. Depending on `EMT-D` or `EMT-S`, the steps vary.

For `EMT-D`, the following steps should work.

```bash
sudo dnf install mesa-libGL
# If you are using TDNF, you can use the following command to install:
sudo tdnf search mesa-libGL
sudo tdnf install mesa-libGL
```

For `EMT-S`,

```bash
sudo env no_proxy="localhost,127.0.0.1" dnf --installroot=/opt/user-apps/tools/ -y install mesa-libGL
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/opt/user-apps/tools/usr/lib/
```

Additional tools and packages that should be installed includes `git` and `wget`. The instructions for the same is available in the detailed `EMT-S` and `EMT-D` documentations. The instructions work for any other required packages too.

## Run the Application

Follow these steps to run the application:

1. Clone the repository and navigate to the project directory:

   ```bash
   # Clone the latest on mainline
   git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
   # Alternatively, clone a specific release branch
   git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries -b <release-tag>

   cd edge-ai-libraries/sample-applications/video-search-and-summarization
   ```

2. [Set the required environment variables](#set-required-environment-variables).

3. Run the setup script with the appropriate flag, depending on your use case.

   > **Note:** Before switching to a different mode, always stop the current application mode by running:

   ```bash
   source setup.sh --down
   ```

   > **💡 Clean-up Tip**: If you encounter issues or want to completely reset the application data, use `source setup.sh --clean-data` to stop all containers and remove all Docker volumes including user data. This provides a fresh start for troubleshooting.

   - **To run Video Summarization only:**

     ```bash
     source setup.sh --summary
     ```

   - **To run Video Search only:**

     ```bash
     source setup.sh --search
     ```

     > **Telemetry**: By default, `--search` does not start the telemetry collector. To enable it:

     ```bash
     ENABLE_VSS_COLLECTOR=true source setup.sh --search
     ```

     > **📁 Directory Watcher**: For automated video ingestion and processing in search mode, see the [Directory Watcher Service Guide](./directory-watcher-guide.md) to learn how to set up automatic monitoring and processing of video files from a specified directory.

   - **To run a unified Video Search and Summarization:**

     ```bash
     source setup.sh --all
     ```

     > **Telemetry**: By default, `--all` does not start the telemetry collector. To enable it:

     ```bash
     ENABLE_VSS_COLLECTOR=true source setup.sh --all
     ```

   - **To run Video Summarization with OVMS using one shared model for both captioning and final summary:**

     ```bash
     source setup.sh --summary
     ```

   - **To run Video Summarization with OVMS using a dedicated LLM for final summary:**

    ```bash
   OVMS_LLM_MODEL_NAME="Intel/neural-chat-7b-v3-3" source setup.sh --summary
    ```

- **To run Video Summarization with vLLM as the only inference backend:**

    ```bash
    ENABLE_VLLM=true source setup.sh --summary
    ```

    > **Note:**
    > - The vLLM configuration has been tested on Intel® Xeon® 6 processors.
    > - Review [docker/compose.vllm.yaml](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/sample-applications/video-search-and-summarization/docker/compose.vllm.yaml) to understand the VLLM engine and environment variables exposed. Modify it as per your use case. Refer to the [vLLM Engine Arguments documentation](https://docs.vllm.ai/en/stable/configuration/engine_args/) and [vLLM Environment Variables documentation](https://docs.vllm.ai/en/stable/configuration/env_vars/) for more details.

4. (Optional) Verify the resolved environment variables and setup configurations:

   ```bash
   # To just set environment variables without starting containers
   source setup.sh --setenv

   # To see resolved configurations for summarization services without starting containers
   source setup.sh --summary config

   # To see resolved configurations for search services without starting containers
   source setup.sh --search config

   # To see resolved configurations for both search and summarization services combined without starting containers
   source setup.sh --all config

   # To see resolved configurations for OVMS split-model summarization without starting containers
   OVMS_LLM_MODEL_NAME="Intel/neural-chat-7b-v3-3" 
   source setup.sh --summary config

    # To see resolved configurations for summarization services with vLLM enabled without starting containers
    ENABLE_VLLM=true source setup.sh --summary config
   ```

### Use GPU/NPU Acceleration

> **Note:** Offloading models to different devices (e.g., VLM on CPU and LLM on NPU) is only supported with the OVMS backend. The vLLM backend runs a single model on a single device.
>
> **⚠️ NPU Support is Experimental:** Running VLM/LLM models on NPU is experimental and may not work with all models or configurations. Not all model architectures are supported on NPU. If you encounter issues, verify model compatibility at the [OpenVINO Supported Models](https://docs.openvino.ai/2026/documentation/compatibility-and-support/supported-models.html) page and consider falling back to CPU or GPU.

To use GPU acceleration for VLM inference:

> **Note:** Before switching to a different mode, always stop the current application mode by running:
>
> ```bash
> source setup.sh --down
> ```

```bash
VLM_TARGET_DEVICE=GPU source setup.sh --summary
```

To use GPU acceleration for the OVMS final-summary LLM:

```bash
LLM_TARGET_DEVICE=GPU OVMS_LLM_MODEL_NAME=Intel/neural-chat-7b-v3-3 source setup.sh --summary
```

To use NPU acceleration for the final-summary LLM (split-model mode):

```bash
LLM_TARGET_DEVICE=NPU OVMS_LLM_MODEL_NAME=OpenVINO/Qwen3-8B-int4-cw-ov source setup.sh --summary
```

To use GPU acceleration for vclip-embedding-ms for search usecase:

```bash
ENABLE_EMBEDDING_GPU=true source setup.sh --search
```

To verify the configuration and resolved environment variables without running the application:

```bash
# For VLM inference on GPU
VLM_TARGET_DEVICE=GPU source setup.sh --summary config
```

```bash
# For LLM on NPU (split-model mode)
LLM_TARGET_DEVICE=NPU OVMS_LLM_MODEL_NAME=OpenVINO/Qwen3-8B-int4-cw-ov source setup.sh --summary config
```

```bash
# For vclip-embedding-ms on GPU
ENABLE_EMBEDDING_GPU=true source setup.sh --search config
```

> **Tip:** `VLM_TARGET_DEVICE` and `LLM_TARGET_DEVICE` support values: `CPU` (default), `GPU`, `NPU`, or `HETERO:GPU,CPU` for heterogeneous execution with fallback.

## Access the Application

After successfully starting the application, open a browser and go to `http://<host-ip>:12345` to access the application dashboard.

## Monitoring OVMS Metrics

When running in summary mode with OVMS, Prometheus-compatible metrics are available at `http://<host-ip>:12345/ovms/metrics`. These metrics provide insights into inference performance:

```bash
curl http://localhost:12345/ovms/metrics
```

Key metrics include `ovms_requests_success`, `ovms_inference_time_us`, and `ovms_current_requests`. See [Deploy with Helm - Monitoring and Metrics](./deploy-with-helm.md#monitoring-and-metrics) for the full metrics list.

## CLI Usage

Refer to [CLI Usage](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/sample-applications/video-search-and-summarization/cli/README.md) for details on using the application from a text user interface (terminal-based UI).

## Running in Kubernetes Cluster

Refer to [Deploy with Helm](./deploy-with-helm.md) for the details. Ensure the prerequisites mentioned on this page are addressed before proceeding to deploy with Helm chart.

## Advanced Setup Options

For alternative ways to set up the sample application, see [How to Build from Source](./build-from-source.md)

## Supporting Resources

- [How it works](./how-it-works.md)
- [Troubleshooting](./troubleshooting.md)
- [Docker Compose Documentation](https://docs.docker.com/compose/)

<!--hide_directive
:::{toctree}
:hidden:

get-started/system-requirements

:::
hide_directive-->
