# Get Started

The Video Search and Summarization (VSS) sample application helps developers create a summary of long form video, search for the right video, and combine both search and summarization pipelines. This guide will help you set up, run, and modify the sample application on local and Edge AI systems.

This guide shows how to:

- **Set up the sample application**: Use the setup script to quickly deploy the application in your environment.
- **Run different application modes**: Deploy in summary-only, search-only, dual-UI, or unified mode.
- **Modify application parameters**: Customize settings like inference models and deployment configurations to adapt the application to your specific requirements.

## Deployment Modes

The application supports **four** deployment modes. Each mode deploys only the services and UI(s) relevant to the selected functionality:

| Mode | Features | UI Layout | Description |
|------|-------------|-----------|----------------------------|
| **Summary** | Video summarization only | Summary UI available at `/` (root URL) | Microservices dependencies required for Video Summarization are deployed. |
| **Search** | Video Search only | Search UI available at `/` (root URL). | **Search is done on video frame embeddings**. Microservices required for Video Search are deployed. |
| **Dual** | Both Video Summarization and Search available. | Two separate UIs available for Summarization and Search respectively at `/summary/` and `/search/` URI. |  **Search is done on video frame embeddings**. All microservices components are deployed. |
| **Unified** | Both Video Summarization and Search available | A single unified UI containing both summarization and search features available at `/` (root URL). | **Search is done on video summary's text embeddings**. All microservices components are deployed. |


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

   - **Common to all modes (except `--search`):**

   ```bash
   # For VLM-based chunk captioning and video summarization on CPU
   export VLM_MODEL_NAME="Qwen/Qwen2.5-VL-3B-Instruct"  # or any other supported VLM model on CPU

   # For VLM-based chunk captioning and video summarization on GPU
   export VLM_MODEL_NAME="microsoft/Phi-3.5-vision-instruct"  # or any other supported VLM model on GPU

   # (Optional) For OVMS-based video summarization (when using with ENABLE_OVMS_LLM_SUMMARY=true or ENABLE_OVMS_LLM_SUMMARY_GPU=true)
   export OVMS_LLM_MODEL_NAME="Intel/neural-chat-7b-v3-3"  # or any other supported LLM model

   # Model used by Audio Analyzer service. Only Whisper models variants are supported.
   # Common Supported models: tiny.en, small.en, medium.en, base.en, large-v1, large-v2, large-v3.
   # You can provide just one or comma-separated list of models.
   export ENABLED_WHISPER_MODELS="tiny.en,small.en,medium.en"

   # Object detection model used for Video Ingestion Service. Only Yolo models are supported.
   export OD_MODEL_NAME="yolov8l-worldv2"
   ```

   - **Mode-specific variables:**

   | Variable | Required For | Purpose |
   |----------|-------------|---------|
   | `VLM_MODEL_NAME` | `--summary`, `--dual`, `--unified` | VLM model for video captioning and summarization. |
   | `ENABLED_WHISPER_MODELS` | `--summary`, `--dual`, `--unified` | Whisper model(s) for audio analysis. |
   | `OD_MODEL_NAME` | `--summary`, `--dual`, `--unified` | YOLO model for object detection during video ingestion. |
   | `MULTIMODAL_EMBEDDING_MODEL` | `--search`, `--dual` | Multimodal model for generating video frame embeddings. |
   | `TEXT_EMBEDDING_MODEL` | `--unified` | Text embedding model for generating summary text embeddings. |
   | `OVMS_LLM_MODEL_NAME` | _(Optional)_ Any of `--summary`, `--dual` or `--unified` mode with `ENABLE_OVMS_LLM_SUMMARY=true` | LLM for OVMS-based final summary generation. |

   ```bash
   # Required for --search and --dual (when search is done on video frame embeddings)
   export MULTIMODAL_EMBEDDING_MODEL="CLIP/clip-vit-b-32"

   # Required for --unified (when search is done on text embeddings)
   export TEXT_EMBEDDING_MODEL="QwenText/qwen3-embedding-0.6b"
   ```

   > **Note**: Review the supported model list in [supported-models](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/microservices/multimodal-embedding-serving/docs/user-guide/supported-models.md) before choosing model names.

4. **Configure Directory Watcher (Video Search)**:

   For automated video ingestion into the search pipeline (available only  in `--search` and `--dual` modes), you can use the directory watcher service:

      ```bash
      # Path to the directory to watch on the host system. Default: "edge-ai-libraries/sample-applications/video-search-and-summarization/data"
      export VS_WATCHER_DIR="/path/to/your/video/directory"
      ```

   > **📁 Directory Watcher**: For complete setup instructions, configuration options, and usage details, see the [Directory Watcher Service Guide](./directory-watcher-guide.md). This service only works with `--search` and `--dual` modes.

5. **Control the frame extraction interval (Video Search)**:

   The DataPrep microservice samples frames from uploaded videos according to the `FRAME_INTERVAL` environment variable. Set this variable before running `source setup.sh` to control how often frames are selected for processing.

   ```bash
   export FRAME_INTERVAL=15
   ```

   In the example above, DataPrep processes every fifteenth frame: each selected frame (optionally after object detection) is converted into embeddings and stored in the vector database. Lower values improve recall at the cost of higher compute and storage usage, while higher values reduce processing load but may skip important frames. If you do not set this variable, the service falls back to its configured default.

6. **Enable ROI consolidation (Video Search)**:

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

7. **Set advanced VLM Configuration Options**:

   The following environment variables provide additional control over VLM inference behavior and logging:

   ```bash
   # (Optional) OpenVINO configuration for VLM inference optimization
   # Pass OpenVINO configuration parameters as a JSON string to fine-tune inference performance
   # Default latency-optimized configuration (equivalent to not setting OV_CONFIG)
   # export OV_CONFIG='{"PERFORMANCE_HINT": "LATENCY"}'

   # Throughput-optimized configuration
   export OV_CONFIG='{"PERFORMANCE_HINT": "THROUGHPUT"}'
   ```

   > **IMPORTANT:** The `OV_CONFIG` variable is used to pass OpenVINO configuration parameters to the VLM service. It allows you to optimize inference performance based on your hardware and workload.
   > For a complete list of OpenVINO configuration options, refer to the [OpenVINO Documentation](https://docs.openvino.ai/2025/openvino-workflow/running-inference/inference-devices-and-modes.html).
   > **Note**: If OV_CONFIG is not set, the default configuration `{"PERFORMANCE_HINT": "LATENCY"}` will be used.

8. **(Optional) Telemetry collection (--search and --dual modes only)**:

   The deployment can start a lightweight telemetry collector (`vss-collector`) that streams CPU/RAM/GPU metrics to the Pipeline Manager and renders them in the UI. Telemetry is only applicable in `--search` and `--dual` modes.

   ```bash
   # Disabled by default
   export ENABLE_VSS_COLLECTOR=false

   # Enable the collector if you want telemetry
   export ENABLE_VSS_COLLECTOR=true
   ```

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

| Mode | UI Instances | Default URL(s) |
|------|-------------|----------------|
| `--summary` | Single Summary UI | `http://<host-ip>:12345/` |
| `--search` | Single Search UI | `http://<host-ip>:12345/` |
| `--dual` | Separate Summary and Search UIs | `http://<host-ip>:12345/summary/` and `http://<host-ip>:12345/search/` |
| `--unified` | Single unified UI (summary + search) | `http://<host-ip>:12345/` |

> **NOTE:** In `--dual` mode, visiting `http://<host-ip>:12345/` redirects to the Video Summarization UI.

In modes where Video Search is available (--search, --dual and --unified mode), the DB index, modality of input being used for creating embeddings and the embedding models would differ with modes.

| Mode | Vector-DB Index | Search Modality | Environment Variable Used |
|------|-----------------|-----------------|--------------------|
| `--search` | `video_frame_embeddings` | Multimodal embeddings of video frames | `MULTIMODAL_EMBEDDING_MODEL` |
| `--dual` | `video_frame_embeddings` | Multimodal embeddings of video frames | `MULTIMODAL_EMBEDDING_MODEL` |
| `--unified` | `video_summary_embeddings` | Text embeddings of generated summaries | `TEXT_EMBEDDING_MODEL` |

> **Automated Video Ingestion**: The Video Search pipeline includes an optional Directory Watcher service for automated video processing. See the [Directory Watcher Service Guide](./directory-watcher-guide.md) for details.

### Deployment Options for Video Summarization

| Deployment Option | Chunk-Wise Summary<sup>(1)</sup> Configuration | Final Summary<sup>(2)</sup> Configuration | Environment Variables to Set | Recommended Models | Recommended Usage Model |
|--------|--------------------|---------------------|-----------------------|----------------|----------------|
| VLM-CPU | vlm-openvino-serving on CPU | vlm-openvino-serving on CPU | Default | VLM: `Qwen/Qwen2.5-VL-3B-Instruct` | For usage with CPUs only; when inference speed is not a priority. |
| VLM-GPU | vlm-openvino-serving | vlm-openvino-serving GPU | `ENABLE_VLM_GPU=true` | VLM: `microsoft/Phi-3.5-vision-instruct` | For usage with CPUs and GPUs; when inference speed is a priority. |
| VLM-CPU-OVMS-CPU | vlm-openvino-serving on CPU | OVMS Microservice on CPU | `ENABLE_OVMS_LLM_SUMMARY=true` | VLM: `Qwen/Qwen2.5-VL-3B-Instruct`<br>LLM: `Intel/neural-chat-7b-v3-3` | For usage with CPUs and microservices; when inference speed is not a priority. |
| VLM-CPU-OVMS-GPU | vlm-openvino-serving on CPU | OVMS Microservice on GPU | `ENABLE_OVMS_LLM_SUMMARY_GPU=true` | VLM: `Qwen/Qwen2.5-VL-3B-Instruct`<br>LLM: `Intel/neural-chat-7b-v3-3` | For usage with CPUs, GPUs, and microservices; when inference speed is a priority. |
| VLM-GPU-OVMS-CPU | vlm-openvino-serving on GPU | OVMS Microservice on CPU | `ENABLE_VLM_GPU=true` `ENABLE_OVMS_LLM_SUMMARY=true` | VLM: `Qwen/Qwen2.5-VL-3B-Instruct`<br>LLM: `Intel/neural-chat-7b-v3-3` | For usage with CPUs, GPUs, and microservices; when inference speed is a priority. |
| vLLM-CPU | vLLM serving on CPU | vLLM Service on CPU | `ENABLE_VLLM=true` | VLM: `Qwen/Qwen2.5-VL-3B-Instruct` | Deploy on Intel® Xeon® Processors without GPU requirements. |
> **Note:**
>
> 1) Chunk-Wise Summary is a method of summarization where it breaks videos into chunks and then summarizes each chunk.
> 2) Final Summary is a method of summarization where it summarizes the whole video.
> 3) If both VLM and LLM is configured for GPU, VLM will be prioritized for GPU and LLM reset to CPU.

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

3. Run the setup script with the desired deployment mode:

   > **Note:** To bring down a running deployment before starting again, run:

   ```bash
   source setup.sh --stop    # or, `source setup.sh --down`
   ```

   > **💡 Clean-up Tip**: If you encounter issues or want to completely reset the application data, use `source setup.sh --clean-data` to stop all containers and remove all Docker volumes including user data. This provides a fresh start for troubleshooting.

   - **Summary-only mode: Setup only video summarization:**

     ```bash
     source setup.sh --summary
     ```

   - **Search-only mode: Setup only video search:**

     ```bash
     source setup.sh --search
     ```

   - **Dual mode: Setup both summarization and search application with separate UIs:**

     ```bash
     source setup.sh --dual
     ```

     When the script finishes, it prints the URLs for the both summary and search UI.

   - **Unified mode: single UI containing summarization and search features:**

     ```bash
     source setup.sh --unified    # or, `source setup.sh --all`
     ```

   > **Telemetry** (applicable to `--search` and `--dual` modes only): The telemetry collector is disabled by default. Enable it with:
   >
   > ```bash
   > ENABLE_VSS_COLLECTOR=true source setup.sh --search
   > # or
   > ENABLE_VSS_COLLECTOR=true source setup.sh --dual
   > ```

   > **📁 Directory Watcher**: For automated video ingestion into the Search pipeline, see the [Directory Watcher Service Guide](./directory-watcher-guide.md).

   - **Use OpenVINO model server microservice for the final summary:**

      ```bash
      ENABLE_OVMS_LLM_SUMMARY=true source setup.sh --summary      # for summary only mode
      ENABLE_OVMS_LLM_SUMMARY=true source setup.sh --dual         # for dual mode
      ```

   - **Use vLLM as the only inference backend:**

      ```bash
      ENABLE_VLLM=true source setup.sh --summary      # for summary only mode
      ENABLE_VLLM=true source setup.sh --dual         # for dual mode
      ```

    > **Note:**
    > - The vLLM configuration has been tested on Intel® Xeon® 6 processors.
    > - Review [docker/compose.vllm.yaml](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/sample-applications/video-search-and-summarization/docker/compose.vllm.yaml) to understand the VLLM engine and environment variables exposed. Modify it as per your use case. Refer to the [vLLM Engine Arguments documentation](https://docs.vllm.ai/en/stable/configuration/engine_args/) and [vLLM Environment Variables documentation](https://docs.vllm.ai/en/stable/configuration/env_vars/) for more details.

4. (Optional) Verify the resolved environment variables and setup configurations:

      ```bash
      # To just set environment variables without starting containers
      source setup.sh --setenv

      # To see the fully resolved compose configuration (defaults to --dual mode)
      source setup.sh config

      # To see resolved config for a specific mode
      source setup.sh config --summary
      source setup.sh config --search
      source setup.sh config --unified    # or, source setup.sh config --all

      # To see the resolved configuration with OpenVINO model server on CPU
      ENABLE_OVMS_LLM_SUMMARY=true source setup.sh config --dual

      # To see the resolved configuration with vLLM enabled
      ENABLE_VLLM=true source setup.sh config --summary
      ```

### Use GPU Acceleration

> **Note:** To bring down a running deployment before re-running with different flags, run:
>
> ```bash
> source setup.sh --stop    # or, `source setup.sh --down`
> ```

To use GPU acceleration for VLM inference:

```bash
# for summary only mode
ENABLE_VLM_GPU=true source setup.sh --summary
# for dual mode
ENABLE_VLM_GPU=true source setup.sh --dual
```

To use GPU acceleration for OpenVINO model server-based summarization:

```bash
# for summary only mode
ENABLE_OVMS_LLM_SUMMARY_GPU=true source setup.sh --summary
# for dual mode
ENABLE_OVMS_LLM_SUMMARY_GPU=true source setup.sh --dual
```

To use GPU acceleration for the multimodal embedding service used by search:

```bash
# for search only mode
ENABLE_EMBEDDING_GPU=true source setup.sh --search
# for dual mode
ENABLE_EMBEDDING_GPU=true source setup.sh --dual
```

To verify the configuration and resolved environment variables without running the application:

```bash
# For VLM inference on GPU
ENABLE_VLM_GPU=true source setup.sh config --summary        # for summary only mode
ENABLE_VLM_GPU=true source setup.sh config --dual           # for dual mode
```

```bash
# For OVMS inference on GPU
ENABLE_OVMS_LLM_SUMMARY_GPU=true source setup.sh config --summary    # for summary only mode
ENABLE_OVMS_LLM_SUMMARY_GPU=true source setup.sh config --dual       # for dual mode
```

```bash
# For embedding service on GPU
ENABLE_EMBEDDING_GPU=true source setup.sh config --search      # for search mode
ENABLE_EMBEDDING_GPU=true source setup.sh config --dual        # for dual mode
```

> **Note:** Avoid setting the `ENABLE_VLM_GPU`, `ENABLE_OVMS_LLM_SUMMARY_GPU`, or `ENABLE_EMBEDDING_GPU` flags explicitly on the shell using `export`, because you need to switch these flags off as well, to return to the CPU configuration.

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

### `--dual` mode

| UI | URL |
|----|-----|
| Video Summarization | `http://<host-ip>:12345/summary/` 
| Video Search       | `http://<host-ip>:12345/search/` |

Visiting the root URL `http://<host-ip>:12345/` redirects to the Video Summarization UI.

### `--unified` mode

| UI | URL |
|----|-----|
| Unified Summary/Search | `http://<host-ip>:12345/` |

### Customizing Application Port

- The port where we access the application is customizable by setting the `APP_HOST_PORT` environment variable (default `12345`).

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
