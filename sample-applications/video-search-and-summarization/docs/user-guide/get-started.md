# Get Started

The Video Search and Summarization (VSS) sample application helps developers create a summary of long form video, search for the right video, and combine both search and summarization pipelines. This guide will help you set up, run, and modify the sample application on local and Edge AI systems.

This guide shows how to:

- **Set up the sample application**: Use the setup script to quickly deploy the application in your environment.
- **Run different application modes**: Deploy in summary-only, search-only, dual-UI, or unified mode.
- **Modify application parameters**: Customize settings like inference models and deployment configurations to adapt the application to your specific requirements.

## Deployment Modes

The application supports **four** deployment modes. Each mode deploys only the services and UI(s) relevant to the selected functionality:

| Mode | Features | UI Layout | Description | Command Option |
|------|----|-------|-----------------------|---------|
| **Summary** | Video summarization only | Summary UI available at `/` (root URI) | Summarize a given video with several tunable parameters. | `--summary` |
| **Search** | Video Search only | Search UI available at `/` (root URI). | Search for entities in a given video. **Embedding used for search:** Video frame embeddings | `--search` |
| **Dual UI** | Video Summarization and Video Search | Two separate UIs available at `/summary/` and `/search/` URI. | **Embedding used for search:** Video frame embeddings | `--summary --search` |
| **Unified UI** | Video Summarization and **Modified** Video Search | A single unified UI available at `/` (root URI). | **Embedding used for search:** Summarized content text embeddings  | `--summary-and-search` |

> **NOTE :** The video search in **Unified UI** mode is modified for creating the embeddings of video summary texts and searching over them, rather than creating and using video frame embeddings. Hence, this mode includes video summarization feature, as well, in the same UI.

## Prerequisites

- Verify that your system meets the [minimum requirements](./get-started/system-requirements.md).
- Install Docker tool: [Installation Guide](https://docs.docker.com/get-docker/).
- Install Docker Compose tool: [Installation Guide](https://docs.docker.com/compose/install/).
- Install Python programming language v3.11

## Project Structure

The repository is organized as follows:

```text
sample-applications/video-search-and-summarization/
├── config/                        # Runtime configs
│   ├── nginx/                     # Nginx templates used by setup.sh + compose
│   │   ├── nginx.conf
│   │   ├── dual_ui.conf
│   │   └── singleton_ui.conf
│   └── rmq.conf                   # RabbitMQ configuration
├── docker/                        # Docker Compose base and overlays
│   ├── compose.base.yaml
│   ├── compose.ui.yaml
│   ├── compose.summary.yaml
│   ├── compose.search.yaml
│   ├── compose.vllm.yaml
│   ├── compose.gpu_ovms.yaml
│   └── compose.telemetry.yaml
├── docs/
│   └── user-guide/                # User guides and tutorials
├── pipeline-manager/              # Orchestrates summarization and search pipelines
├── search-ms/                     # Video search microservice
├── video-ingestion/               # Video ingestion and processing service
├── ui/
│   └── react/                     # Frontend application
├── cli/                           # Terminal UI and CLI workflows
├── scripts/                       # Utility and helper scripts
├── data/                          # Default watcher/input data directory
├── ov_models/                     # Local model cache/artifacts
├── build.sh                       # Script for building application images
├── setup.sh                       # Main setup and deployment script
└── README.md
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
   Following variables **must** be set on your current shell before running the setup script:

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

3. **Set environment variables for model selection**:

   You **must** set these environment variables on your current shell. Setting these variables is **mandatory** as they **do not** have any default values.

   - **Mode-specific environment variables to set Models:**

      | Variable | Mode | Purpose |
      |----------|-------------|---------|
      | `VLM_MODEL_NAME` | Summary, Dual UI, Unified UI | VLM model for video captioning and summarization. |
      | `ENABLED_WHISPER_MODELS` | Summary, Dual UI, Unified UI | Whisper model(s) for audio analysis. |
      | `OD_MODEL_NAME` | Summary, Dual UI, Unified UI | YOLO model for object detection during video ingestion. |
      | `MULTIMODAL_EMBEDDING_MODEL` | Search, Dual UI | Multimodal model for generating video frame embeddings. |
      | `TEXT_EMBEDDING_MODEL` | Unified UI | Text embedding model for generating summary text embeddings. |
      | `OVMS_LLM_MODEL_NAME` | _(Optional)_ Any of Summary, Dual UI or Unified UI mode with `ENABLE_OVMS_LLM_SUMMARY=true` | LLM for OVMS-based final summary generation. |
      | `PM_AUDIO_USE_FULL_TRANSCRIPT_SUMMARY` | _(Optional)_ Summary, Dual UI | Enables condensed transcript summary injection in the prompt to generate video summary. |

     **Common to all modes except `--search`:**

      ```bash
      # For VLM-based chunk captioning and video summarization on CPU
      export VLM_MODEL_NAME="Qwen/Qwen2.5-VL-3B-Instruct"  # or any other supported VLM model on CPU

      # For VLM-based chunk captioning and video summarization on GPU
      export VLM_MODEL_NAME="OpenVINO/Phi-3.5-vision-instruct-int8-ov"  # or any other supported VLM model on GPU
      export VLM_TARGET_DEVICE="GPU"  # Options: CPU, GPU, NPU, HETERO:GPU,CPU

      # (OPTIONAL) For OVMS split-model summarization, set a dedicated LLM model for final summary.
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
      ```

     **Required in `--search` and `--summary --search` mode:**

      ```bash
      # Required for searching on video frame embeddings
      export MULTIMODAL_EMBEDDING_MODEL="CLIP/clip-vit-b-32"
      ```

     **Required in `--summary-and-search` mode:**

      ```bash
      # Required for searching on video summary text embeddings
      export TEXT_EMBEDDING_MODEL="QwenText/qwen3-embedding-0.6b"
      ```

      > **Note**: Review the supported model list in [supported-models](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/microservices/multimodal-embedding-serving/docs/user-guide/supported-models.md) before choosing model names.

4. **Configure summarization to use audio transcript (Summary and Dual UI mode):**

   Used in `--summary` and `--summary --search` mode:

      ```bash
      # (OPTIONAL) Default value is true. Users can override this per-video in the upload modal.
      export PM_AUDIO_USE_FULL_TRANSCRIPT_SUMMARY=false
      ```

      > **Audio Transcript Summarization (`PM_AUDIO_USE_FULL_TRANSCRIPT_SUMMARY`)**:
      > When enabled (the default), the pipeline runs a separate LLM-based map-reduce summarization pass over the complete audio transcript *before* generating the final video summary. The condensed transcript summary is then injected into the video summary prompt via the `%audio_summary%` placeholder, giving the LLM a coherent, high-quality representation of spoken content rather than raw subtitle fragments. This significantly improves accuracy for dialogue-heavy or narration-heavy videos. When disabled, audio transcripts are only used at the chunk captioning level — each chunk's VLM prompt includes its time-matched portion of the transcript — but no audio content is included in the final map-reduce video summary.
      >
      > This environment variable sets the **default** value. Users can override it per-video using the **"Use Audio in Summary"** checkbox in the Audio Settings section of the video upload modal.


5. **Configure Directory Watcher (Search and Dual UI mode)**:

   For automated video ingestion into the search pipeline (available only  in `--search` and `--summary --search` modes), you can use the directory watcher service:

      ```bash
      # Path to the directory to watch on the host system. Default: "edge-ai-libraries/sample-applications/video-search-and-summarization/data"
      export VS_WATCHER_DIR="/path/to/your/video/directory"
      ```

   > **📁 Directory Watcher**: For complete setup instructions, configuration options, and usage details, see the [Directory Watcher Service Guide](./directory-watcher-guide.md). This service only works with `--search` and `--summary --search` modes.

6. **Control the frame extraction interval (Search and Dual UI mode)**:

   The DataPrep microservice samples frames from uploaded videos according to the `FRAME_INTERVAL` environment variable. Set this variable before running `source setup.sh` to control how often frames are selected for processing.

   ```bash
   export FRAME_INTERVAL=15
   ```

   In the example above, DataPrep processes every fifteenth frame: each selected frame (optionally after object detection) is converted into embeddings and stored in the vector database. Lower values improve recall at the cost of higher compute and storage usage, while higher values reduce processing load but may skip important frames. If you do not set this variable, the service falls back to its configured default.

7. **Enable ROI consolidation (Search and Dual UI mode)**:

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

8. **(Optional) Telemetry collection (Search and Dual UI mode)**:

   The deployment can start a lightweight telemetry collector (`vss-collector`) that streams CPU/RAM/GPU metrics to the Pipeline Manager and renders them in the UI. Telemetry is only applicable in `--search` and `--summary --search` modes.

   ```bash
   # Disabled by default
   export ENABLE_VSS_COLLECTOR=false

   # Enable the collector if you want telemetry
   export ENABLE_VSS_COLLECTOR=true
   ```

9. **Tune Inference Concurrency (Summary and Dual UI mode)**:

   Control how many concurrent inference requests the pipeline manager sends to OVMS or vLLM. These values affect throughput and resource utilization:

   ```bash
   # Maximum concurrent VLM requests for chunk captioning (default: 6 for CPU, 1 for GPU)
   export PM_VLM_CONCURRENT=6

   # Maximum concurrent LLM requests for final summarization (default: 1)
   export PM_LLM_CONCURRENT=1
   ```

   > **Note**: For OVMS deployments, these values should not exceed the `max_num_seqs` parameter configured during model export (default: 256). For GPU deployments, lower concurrency (1-2) is recommended to avoid memory pressure. The setup script automatically adjusts these defaults based on the selected device (CPU vs GPU).

10. **Override OVMS Model Weight Compression Format (Summary and Dual UI mode)**:

    When using OVMS for inference, the setup script auto-selects the model weight compression format based on the target device (`int8` for CPU, `int4` for GPU/NPU). You can override this auto-detection by setting these variables before running the setup script:

    ```bash
    # Override VLM model weight compression format (default: int8 for CPU, int4 for GPU/NPU)
    export VLM_COMPRESSION_WEIGHT_FORMAT=int4

    # Override LLM model weight compression format (default: int8 for CPU, int4 for GPU/NPU)
    export LLM_COMPRESSION_WEIGHT_FORMAT=int4
    ```

    > **Note**: Lower precision formats like `int4` reduce memory usage and can improve throughput, but may affect output quality. The default auto-detection (`int8` for CPU, `int4` for GPU/NPU) is recommended for most use cases.

11. **Configure Embedding Processing Mode (Search and Dual UI mode)**:

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

## Application Overview

The Video Search and Summarization application supports multiple deployment modes, each served behind a single nginx reverse proxy on one port. The mode determines which services and UI(s) are brought up.

> **NOTE:** The application runs on port 12345 by default. You can change this by setting `APP_HOST_PORT` environment variable to another port number.

| Mode | Command Option | UI Instances | Default URL(s) |
|------|--------|-------------|----------------|
| Summary | `--summary` | Single Summary UI | `http://<host-ip>:12345/` |
| Search | `--search` | Single Search UI | `http://<host-ip>:12345/` |
| Dual UI | `--summary --search` | Separate Summary and Search UIs | `http://<host-ip>:12345/summary/` and `http://<host-ip>:12345/search/` |
| Unified UI | `--summary-and-search` | Single unified UI (summary + search) | `http://<host-ip>:12345/` |

> **NOTE:** In `--summary --search` mode, visiting `http://<host-ip>:12345/` redirects to the Video Summarization UI.

In modes, where Video Search is available (Search, Dual UI and Unified UI mode), the Vector DB index, the modality of input being used for creating embeddings and the embedding models would differ with modes.

| Mode | Vector-DB Index | Search Modality | Environment Variable Used |
|------|-----------------|-----------------|--------------------|
| Search | `video_frame_embeddings` | Multimodal embeddings of video frames | `MULTIMODAL_EMBEDDING_MODEL` |
| Dual UI | `video_frame_embeddings` | Multimodal embeddings of video frames | `MULTIMODAL_EMBEDDING_MODEL` |
| Unified UI | `video_summary_embeddings` | Text embeddings of generated summaries | `TEXT_EMBEDDING_MODEL` |

> **Automated Video Ingestion**: The Video Search pipeline includes an optional Directory Watcher service for automated video processing. See the [Directory Watcher Service Guide](./directory-watcher-guide.md) for details.

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

If you are running the VSS application on an OS image built with **Edge Microvisor Toolkit (EMT)** — an Azure Linux-based build pipeline for Intel® platforms — the deployment approach depends on the EMT flavor. Refer to the detailed documentation for [EMT-D](https://github.com/open-edge-platform/edge-microvisor-toolkit/blob/3.0/docs/developer-guide/emt-architecture-overview.md#developer-node-mutable-iso-image) and [EMT-S](https://github.com/open-edge-platform/edge-microvisor-toolkit-standalone-node) for full details.

### EMT-D (Mutable)

EMT-D is a **mutable** image that supports standard package management. You can run the VSS `setup.sh` script directly on the node after installing the required dependencies.

Install the `mesa-libGL` package (required by the Audio Analyzer service):

```bash
sudo dnf install mesa-libGL
# Or using TDNF:
sudo tdnf install mesa-libGL
```

Install additional tools such as `git` and `wget` using the same package manager. Once dependencies are in place, proceed with [running the application](#run-the-application) normally.

### EMT-S (Immutable)

EMT-S is an **immutable** OS image — standard package managers such as `apt` are not available, and the VSS `setup.sh` script **cannot be run directly on the EMT-S node** (doing so will fail with `sudo: apt: command not found`). Use one of the following approaches:

- **Option 1 (USB provisioning):** While preparing the USB drive, copy the required Docker images under `/opt/user-apps` on the image, then flash and deploy the Edge node.
- **Option 2 (Remote copy):** On a Ubuntu development system, pull/build all required Docker images and prepare the project directory. Copy the entire directory to the EMT-S node without modifications and deploy from there. This approach has been verified to successfully bring up all VSS containers.

When packages must be installed on EMT-S (for example, `mesa-libGL`), use the installroot method:

```bash
sudo env no_proxy="localhost,127.0.0.1" dnf --installroot=/opt/user-apps/tools/ -y install mesa-libGL
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/opt/user-apps/tools/usr/lib/
```

The same method applies to any other required packages (for example, `git`, `wget`). Refer to the [EMT-S documentation](https://github.com/open-edge-platform/edge-microvisor-toolkit-standalone-node) for further details.

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

3. Run the setup script with the desired deployment mode:

   - First, bring down any running deployment before starting:

      ```bash
      source setup.sh --stop    # or, `source setup.sh --down`
      ```

      > **IMPORTANT :** You should always run the above command before changing modes _(for example: changing from --summary mode to --search mode)_.

      > **💡 Clean-up Tip**: If you encounter issues or want to completely reset the application data, use `source setup.sh --clean-data` to stop all containers and remove all Docker volumes including user data. This provides a fresh start for troubleshooting.

   - **Summary mode: Setup only video summarization:**

     ```bash
     source setup.sh --summary
     ```

   - **Search mode: Setup only video search:**

     ```bash
     source setup.sh --search
     ```

   - **Dual UI mode: Setup both video summarization and video search application with separate UIs:**

     ```bash
     source setup.sh --summary --search      # or, `source setup.sh --search --summary`
     ```

     When the script finishes, it prints the URLs for the both summary and search UI.

   - **Unified UI mode: Single UI containing video summarization and modified video search:**

     ```bash
     source setup.sh --summary-and-search    # or, `source setup.sh --search-and-summary`
     ```

      > **Telemetry** (applicable to `--search` and `--summary --search` modes only): The telemetry collector is disabled by default. Enable it with:
      >
      > ```bash
      > ENABLE_VSS_COLLECTOR=true source setup.sh --search
      > # or
      > ENABLE_VSS_COLLECTOR=true source setup.sh --summary --search
      > ```

      > **📁 Directory Watcher**: For automated video ingestion into the Search pipeline, see the [Directory Watcher Service Guide](./directory-watcher-guide.md).

   - **To run Video Summarization with OVMS using a dedicated LLM for final summary:**

      ```bash
      # Note: If OVMS_LLM_MODEL_NAME variable is not set, captioning and final summary both are done by a VLM.

      # For Summary mode
      OVMS_LLM_MODEL_NAME="Intel/neural-chat-7b-v3-3" source setup.sh --summary

      # For Dual UI mode
      OVMS_LLM_MODEL_NAME="Intel/neural-chat-7b-v3-3" source setup.sh --summary --search

      # For Unified UI mode
      OVMS_LLM_MODEL_NAME="Intel/neural-chat-7b-v3-3" source setup.sh --summary-and-search
      ```

   - **Use vLLM as the only inference backend:**

      ```bash
      ENABLE_VLLM=true source setup.sh --summary                 # for Summary mode
      ENABLE_VLLM=true source setup.sh --summary --search        # for Dual UI mode
      ENABLE_VLLM=true source setup.sh --summary-and-search      # for Unified UI mode
      ```

    > **Note:**
    > - The vLLM configuration has been tested on Intel® Xeon® 6 processors.
    > - Review [docker/compose.vllm.yaml](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/sample-applications/video-search-and-summarization/docker/compose.vllm.yaml) to understand the VLLM engine and environment variables exposed. Modify it as per your use case. Refer to the [vLLM Engine Arguments documentation](https://docs.vllm.ai/en/stable/configuration/engine_args/) and [vLLM Environment Variables documentation](https://docs.vllm.ai/en/stable/configuration/env_vars/) for more details.

4. (Optional) Verify the resolved environment variables and setup configurations:

      ```bash
      # To just set environment variables without starting containers
      source setup.sh --setenv

      # To see the fully resolved compose configuration (defaults to Dual UI mode)
      source setup.sh config

      # To see resolved config for a specific mode
      source setup.sh --summary config                # for Summary mode
      source setup.sh --search config                 # for Search Mode
      source setup.sh --summary --search config       # for Dual UI Mode
      source setup.sh --search-and-summary config     # for Unified UI Mode

      # To see resolved configurations for OVMS split-model summarization without starting containers.
      # (for other modes, combine --summary with --search option or replace all options with --summary-and-search)
      OVMS_LLM_MODEL_NAME="Intel/neural-chat-7b-v3-3" source setup.sh --summary config

      # To see resolved configurations for summarization services with vLLM enabled without starting containers.
      # (for other modes, combine --summary with --search option or replace all options with --summary-and-search)
      ENABLE_VLLM=true source setup.sh --summary config
      ```

### Use GPU/NPU Acceleration

> **Note:** Offloading models to different devices (e.g., VLM on CPU and LLM on NPU) is only supported with the OVMS backend. The vLLM backend runs a single model on a single device.
>
> **⚠️ NPU Support is Experimental:** Running VLM/LLM models on NPU is experimental and may not work with all models or configurations. Not all model architectures are supported on NPU. If you encounter issues, verify model compatibility at the [OpenVINO Supported Models](https://docs.openvino.ai/2026/documentation/compatibility-and-support/supported-models.html) page and consider falling back to CPU or GPU.

> **Note:** To bring down a running deployment before re-running with different options, run:
>
> ```bash
> source setup.sh --stop    # or, `source setup.sh --down`
> ```

#### Use GPU acceleration for VLM inference:

   ```bash
   # for Summary mode
   VLM_TARGET_DEVICE=GPU source setup.sh --summary
   
   # for Dual UI mode
   VLM_TARGET_DEVICE=GPU source setup.sh --summary --search
   
   # for Unified UI mode
   VLM_TARGET_DEVICE=GPU source setup.sh --summary-and-search
   ```

#### Use GPU acceleration for the OVMS final-summary LLM:

   ```bash
   # for Summary mode
   LLM_TARGET_DEVICE=GPU OVMS_LLM_MODEL_NAME=Intel/neural-chat-7b-v3-3 source setup.sh --summary

   # for Dual UI mode
   LLM_TARGET_DEVICE=GPU OVMS_LLM_MODEL_NAME=Intel/neural-chat-7b-v3-3 source setup.sh --summary --search

   # for Unified UI mode
   LLM_TARGET_DEVICE=GPU OVMS_LLM_MODEL_NAME=Intel/neural-chat-7b-v3-3 source setup.sh --summary-and-search
   ```

#### Use NPU acceleration for the final-summary LLM (split-model mode):

   ```bash
   # for Summary mode
   LLM_TARGET_DEVICE=NPU OVMS_LLM_MODEL_NAME=OpenVINO/Qwen3-8B-int4-cw-ov source setup.sh --summary

   # for Dual UI mode
   LLM_TARGET_DEVICE=NPU OVMS_LLM_MODEL_NAME=OpenVINO/Qwen3-8B-int4-cw-ov source setup.sh --summary --search

   # for Unified UI mode
   LLM_TARGET_DEVICE=NPU OVMS_LLM_MODEL_NAME=OpenVINO/Qwen3-8B-int4-cw-ov source setup.sh --summary-and-search
   ```

#### Use GPU acceleration for the multimodal embedding service used by search:

   ```bash
   # for Search mode
   ENABLE_EMBEDDING_GPU=true source setup.sh --search

   # for Dual UI mode
   ENABLE_EMBEDDING_GPU=true source setup.sh --summary --search
   ```

#### Verify the configuration and resolved environment variables:

   These commands help to validate the deployment configuration without actually deploying the application.

   ```bash
   # For VLM inference on GPU
   VLM_TARGET_DEVICE=GPU source setup.sh config --summary                             # for Summary mode
   VLM_TARGET_DEVICE=GPU source setup.sh config --summary --search                    # for Dual UI mode
   VLM_TARGET_DEVICE=GPU source setup.sh config --summary-and-search                  # for Unified UI mode
   ```

   ```bash
   # For LLM on NPU (split-model mode)
   LLM_TARGET_DEVICE=NPU OVMS_LLM_MODEL_NAME=OpenVINO/Qwen3-8B-int4-cw-ov source setup.sh config --summary                 # for Summary mode
   LLM_TARGET_DEVICE=NPU OVMS_LLM_MODEL_NAME=OpenVINO/Qwen3-8B-int4-cw-ov source setup.sh config --summary --search        # for Dual UI mode
   LLM_TARGET_DEVICE=NPU OVMS_LLM_MODEL_NAME=OpenVINO/Qwen3-8B-int4-cw-ov source setup.sh config --summary-and-search     # for Unified UI mode
   ```

   ```bash
   # For embedding service on GPU
   ENABLE_EMBEDDING_GPU=true source setup.sh config --search                  # for Search mode
   ENABLE_EMBEDDING_GPU=true source setup.sh config --search --summary        # for Dual UI mode
   ```

> **Tip:** `VLM_TARGET_DEVICE` and `LLM_TARGET_DEVICE` support values: `CPU` (default), `GPU`, `NPU`, or `HETERO:GPU,CPU` for heterogeneous execution with fallback.

## Access the Application

After successfully starting the application, access the application UI on following URLs based on chosen mode:

### `--summary` mode

| UI | URL |
|----|-----|
| Video Summarization | `http://<host-ip>:12345/` |

### `--search` mode

| UI | URL |
|----|-----|
| Video Search | `http://<host-ip>:12345/` |

### `--summary --search` mode

| UI | URL |
|----|-----|
| Video Summarization | `http://<host-ip>:12345/summary/` 
| Video Search       | `http://<host-ip>:12345/search/` |

Visiting the root URL `http://<host-ip>:12345/` redirects to the Video Summarization UI.

### `--summary-and-search` mode

| UI | URL |
|----|-----|
| Unified Summary/Search | `http://<host-ip>:12345/` |

### Customizing Application Port

- The port where we access the application is customizable by setting the `APP_HOST_PORT` environment variable (default `12345`).

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

## Connect AI Agents via MCP

Once VSS is running, you can connect AI agents to it using the included MCP server. The MCP server exposes VSS capabilities as typed tools and read-only resources for any MCP-compatible client.

See the [MCP Server guide](./mcp-server.md) for setup instructions.

<!--hide_directive
:::{toctree}
:hidden:

get-started/system-requirements

:::
hide_directive-->
