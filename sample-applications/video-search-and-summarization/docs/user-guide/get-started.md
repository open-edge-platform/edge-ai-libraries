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
   export VLM_MODEL_NAME="microsoft/Phi-3.5-vision-instruct"  # or any other supported VLM model on GPU

   # (Optional) For OVMS-based video summarization (when using with ENABLE_OVMS_LLM_SUMMARY=true or ENABLE_OVMS_LLM_SUMMARY_GPU=true)
   export OVMS_LLM_MODEL_NAME="Intel/neural-chat-7b-v3-3"  # or any other supported LLM model

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
   ```

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

    > **_IMPORTANT:_** The `OV_CONFIG` variable is used to pass OpenVINO configuration parameters to the VLM service. It allows you to optimize inference performance based on your hardware and workload.
    > For a complete list of OpenVINO configuration options, refer to the [OpenVINO Documentation](https://docs.openvino.ai/2025/openvino-workflow/running-inference/inference-devices-and-modes.html).
    > **Note**: If OV_CONFIG is not set, the default configuration `{"PERFORMANCE_HINT": "LATENCY"}` will be used.

7. **(Optional) Telemetry collection for Search**:

    The Video Search mode can start a lightweight telemetry collector (`vss-collector`) that streams CPU/RAM/GPU metrics to the Pipeline Manager and renders them in the UI.

    ```bash
    # Disabled by default for --search and --all
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

Once exported, run the setup script as mentioned [here](#running-the-application). Switch off the `GATED_MODEL` flag by running `export GATED_MODEL=false`, once you no longer use gated models. This avoids unnecessary authentication step during setup.

## Application Mode Overview

The Video Summarization application offers multiple modes and deployment options:

| Mode | Description | Flag (used with setup script) |
|-------|-------------|------|
| Video Summarization | Video frame captioning and summarization | `--summary` |
| Video Search | Video indexing and semantic search | `--search` |
| Video Search + Summarization | Both search and summarization capabilities | `--all` |

> **Automated Video Ingestion**: The Video Search mode includes an optional Directory Watcher service for automated video processing. See the [Directory Watcher Service Guide](./directory-watcher-guide.md) for details on setting up automatic video monitoring and ingestion.

### Deployment Options for Video Summarization

| Deployment Option | Chunk-Wise Summary<sup>(1)</sup> Configuration | Final Summary<sup>2</sup> Configuration | Environment Variables to Set | Recommended Models | Recommended Usage Model |
|--------|--------------------|---------------------|-----------------------|----------------|----------------|
| VLM-CPU |vlm-openvino-serving on CPU | vlm-openvino-serving on CPU | Default | VLM: `Qwen/Qwen2.5-VL-3B-Instruct` | For usage with CPUs only; when inference speed is not a priority. |
| VLM-GPU | vlm-openvino-serving |vlm-openvino-serving GPU | `ENABLE_VLM_GPU=true` | VLM: `microsoft/Phi-3.5-vision-instruct` | For usage with CPUs and GPUs; when inference speed is a priority. |
| VLM-CPU-OVMS-CPU | vlm-openvino-serving on CPU | OVMS Microservice on CPU | `ENABLE_OVMS_LLM_SUMMARY=true` | VLM: `Qwen/Qwen2.5-VL-3B-Instruct`<br>LLM: `Intel/neural-chat-7b-v3-3` | For usage with CPUs and microservices; when inference speed is not a priority. |
| VLM-CPU-OVMS-GPU | vlm-openvino-serving on CPU | OVMS Microservice on GPU | `ENABLE_OVMS_LLM_SUMMARY_GPU=true` | VLM: `Qwen/Qwen2.5-VL-3B-Instruct`<br>LLM: `Intel/neural-chat-7b-v3-3` | For usage with CPUs, GPUs, and microservices; when inference speed is a priority. |
| VLM-GPU-OVMS-CPU | vlm-openvino-serving on GPU | OVMS Microservice on CPU | `ENABLE_VLM_GPU=true` `ENABLE_OVMS_LLM_SUMMARY=true` | VLM: `Qwen/Qwen2.5-VL-3B-Instruct`<br>LLM: `Intel/neural-chat-7b-v3-3` | For usage with CPUs, GPUs, and microservices; when inference speed is a priority. |

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
   # Alternatively, Clone a specific release branch
   git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries -b <release-tag>

   cd edge-ai-libraries/sample-applications/video-search-and-summarization
   ```

2. [Set the required environment variables](#set-required-environment-variables).

3. Run the setup script with the appropriate flag, depending on your use case.

   > Note: Before switching to a different mode, always stop the current application mode by running:

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

   - **To run a unified Video Search and Summarization :**

       ```bash
       source setup.sh --all
       ```

    > **Telemetry**: By default, `--all` does not start the telemetry collector. To enable it:

    ```bash
    ENABLE_VSS_COLLECTOR=true source setup.sh --all
    ```

- **To run Video Summarization with OpenVINO model server microservice for a final summary :**

       ```bash
       ENABLE_OVMS_LLM_SUMMARY=true source setup.sh --summary
       ```

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

   # To see resolved configurations for summarization services with OpenVINO model server setup on CPU without starting containers
   ENABLE_OVMS_LLM_SUMMARY=true source setup.sh --summary config
   ```

### Use GPU Acceleration

To use GPU acceleration for VLM inference:

> **Note:** Before switching to a different mode, always stop the current application mode by running:
>
> ```bash
> source setup.sh --down
> ```

```bash
ENABLE_VLM_GPU=true source setup.sh --summary
```

To use GPU acceleration for OpenVINO model server-based summarization:

```bash
ENABLE_OVMS_LLM_SUMMARY_GPU=true source setup.sh --summary
```

To use GPU acceleration for vclip-embedding-ms for search usecase:

```bash
ENABLE_EMBEDDING_GPU=true source setup.sh --search
```

To verify the configuration and resolved environment variables without running the application:

```bash
# For VLM inference on GPU
ENABLE_VLM_GPU=true source setup.sh --summary config
```

```bash
# For OVMS inference on GPU
ENABLE_OVMS_LLM_SUMMARY_GPU=true source setup.sh --summary config
```

```bash
# For vclip-embedding-ms on GPU
ENABLE_EMBEDDING_GPU=true source setup.sh --search config
```

> **Note:** Avoid setting the `ENABLE_VLM_GPU`, `ENABLE_OVMS_LLM_SUMMARY_GPU`, or `ENABLE_EMBEDDING_GPU` flags explicitly on the shell using `export`, because you need to switch these flags off as well, to return to the CPU configuration.

## Access the Application

After successfully starting the application, open a browser and go to `http://<host-ip>:12345` to access the application dashboard.

## CLI Usage

Refer to [CLI Usage](../../cli/README.md) for details on using the application from a text user interface (terminal-based UI).

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
