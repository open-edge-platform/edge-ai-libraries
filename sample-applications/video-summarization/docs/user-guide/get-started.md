# 🚀 Get Started

<!--
**Sample Description**: Provide a brief overview of the application and its purpose.
-->
The Video summarization sample application is designed to help developers create summary of long form video. This guide will help you set up, run, and modify the sample application on local and Edge AI systems.

<!--
**What You Can Do**: Highlight the developer workflows supported by the guide.
-->
By following this guide, you will learn how to:
- **Set up the sample application**: Use Setup script to quickly deploy the application in your environment.
- **Run different application stacks**: Execute different application stacks available in the application to perform video search and summarization.
- **Modify application parameters**: Customize settings like inference models and deployment configurations to adapt the application to your specific requirements.

## ✅ Prerequisites
- Verify that your system meets the [minimum requirements](./system-requirements.md).
- Install Docker: [Installation Guide](https://docs.docker.com/get-docker/).
- Install Docker Compose: [Installation Guide](https://docs.docker.com/compose/install/).
- Python v3.10 or higher

## 📂 Project Structure

The repository is organized as follows:

```plaintext
sample-applications/video-summarization/
├── config                     # Configuration files
│   ├── nginx.conf             # Nginx configuration
│   └── rmq.conf               # RabbitMQ configuration
├── docker                     # Docker compose files
│   ├── compose.base.yaml      # Base services configuration
│   ├── compose.summary.yaml   # Compose override file for video summarization services
│   ├── compose.search.yaml    # Compose override file for Video search services 
│   ├── compose.gpu_vlm.yaml   # GPU configuration for VLM
│   └── compose.gpu_ovms.yaml  # GPU configuration for OVMS
├── docs                       # Documentation
│   └── user-guide             # User guides and tutorials
├── pipeline-manager           # Backend service which orchestrates the Video Summarization and Search
├── search-ms                  # Video Search Microservice
├── ui                         # Video Summary and Search UI code
├── build.sh                   # Script for building application images
├── setup.sh                   # Setup script for environment and deployment
└── README.md                  # Project documentation
```

## ⚙️ Setting Required Environment Variables

Before running the application, you need to set several environment variables:

1. **Registry Configuration**:
   The application uses registry URL, project name, and tag to pull or build required images.

    ```bash
    export REGISTRY_URL=<your-container-registry-url>    # e.g. "docker.io/username/"
    export PROJECT_NAME=<your-project-name>              # e.g. "egai" or "video-summary"
    export TAG=<your-tag>                                # e.g. "rc4" or "latest"
    ```

   > **_IMPORTANT:_** These variables control how image names are constructed. If `REGISTRY_URL` is **docker.io/username/** and `PROJECT_NAME` is **video-summary**, an image would be pulled or built as **docker.io/username/video-summary/<application-name>:tag**. The `<application-name>` is hardcoded in _image_ field of each service in all docker compose files. If `REGISTRY_URL` or `PROJECT_NAME` are not set, blank string will be used to construct the image name. If `TAG` is not set, **latest** will be used by default.

2. **Required credentials for some services**:
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

3.  **Setting environment variables for customizing model selection**:
    
    These environment variables **MUST** be set on your current shell. Setting these variables help you customize which models are used for deployment.

    ```bash
    # For VLM-based chunk captioning and video summarization on CPU
    export VLM_MODEL_NAME="Qwen/Qwen2.5-VL-7B-Instruct"  # or any other supported VLM model on CPU

    # For VLM-based chunk captioning and video summarization on GPU
    export VLM_MODEL_NAME="microsoft/Phi-3.5-vision-instruct"  # or any other supported VLM model on GPU


    # (Optional) For OVMS-based video summarization (when using with USE_OVMS=true or USE_OVMS_GPU=true)
    export OVMS_LLM_MODEL_NAME="Intel/neural-chat-7b-v3-3"  # or any other supported LLM model

    # Model used by Audio Intelligence service. Only Whisper models variants are supported.
    # Common Supported models: tiny.en, small.en, medium.en, base.en, large-v1, large-v2, large-v3.
    # You can provide just one or comma-separated list of models.
    export ENABLED_WHISPER_MODELS="tiny.en,small.en,medium.en"

    # Object detection model used for Video Ingestion Service. Only Yolo models are supported.
    export OD_MODEL_NAME="yolov8l-worldv2"

    # Multimodal embedding model. Only openai/clip-vit-base models are supported
    export VCLIP_MODEL=openai/clip-vit-base-patch32
    ```

**🔐 Working with Gated Models**

Some models on HuggingFace require authentication. To use these models, set these environment variable:

   ```bash
   export GATED_MODEL=true
   export HUGGINGFACE_TOKEN=<your_huggingface_token>
   ```

Once exported, run the setup script as mentioned [here](#running-the-application). Please switch off the `GATED_MODEL` flag by running `export GATED_MODEL=false`, once you are no more using gated models. This avoids unnecessary authentication step during setup.

## 📊 Application Stacks Overview

The Video Summarization application offers multiple stacks and deployment options:

| Stack | Description | Flag (used with setup script) |
|-------|-------------|------|
| Video Summarization | Video frame captioning and summarization | `--summary` |
| Video Search | Video indexing and semantic search | `--search` |
| Video Search + Summarization **_(Under Construction)_** | Both summarization and search capabilities | `--all` |

### 🧩 Deployment Options for Video Summarization

| Option | Chunk-Wise Summary | Final Summarization | Environment Variables | Recommended Models |
|--------|--------------------|---------------------|-----------------------|----------------|
| VLM-CPU |vlm-openvino-serving on CPU | vlm-openvino-serving on CPU | Default | VLM: `Qwen/Qwen2.5-VL-7B-Instruct` |
| VLM-GPU | vlm-openvino-serving |vlm-openvino-serving GPU | `USE_VLM_GPU=true` | VLM: `microsoft/Phi-3.5-vision-instruct` |
| VLM-OVMS-CPU | vlm-openvino-serving on CPU | OVMS Microservice on CPU | `USE_OVMS=true` | VLM: `Qwen/Qwen2.5-VL-7B-Instruct`<br>LLM: `Intel/neural-chat-7b-v3-3` |
| VLM-CPU-OVMS-GPU | vlm-openvino-serving on CPU | OVMS Microservice on GPU | `USE_OVMS_GPU=true` | VLM: `Qwen/Qwen2.5-VL-7B-Instruct`<br>LLM: `Intel/neural-chat-7b-v3-3` |

## ▶️ Running the Application

Follow these steps to run the application:

1. Clone the repository and navigate to the project directory:

    ```bash
    git clone https://github.com/open-edge-platform/edge-ai-libraries.git
    cd edge-ai-libraries/sample-applications/video-summarization
    ```

2. Set the required environment variables as [described above](#setting-required-environment-variables).

3. Run the setup script with the appropriate flag:

    ```bash
    # To run Video Summarization
    source setup.sh --summary

    # To run Video Search
    source setup.sh --search

    # To run both Video Summarization and Video Search
    source setup.sh --all

    # To run final video summarization on OVMS Microservice
    USE_OVMS=true source setup.sh --summary
    ```

5. Stop the application by bringing down all the containers:

    ```bash
    source setup.sh --down
    ```

6. (Optional) Verify the resolved environment variables and setup configurations.

    ```bash
    # To just set environment variables without starting containers
    source setup.sh --setenv

    # To see resolved configurations for summarization services without starting containers
    source setup.sh --summary config

    # To see resolved configurations for search services without starting containers
    source setup.sh --search config

    # To see resolved configurations for both search and summarization services combined without starting containers
    source setup.sh --all config

    # To see resolved configurations for summarization services with OVMS setup on CPU without starting containers
    USE_OVMS=true source setup.sh --summary config
    ```

### ⚡ Using GPU Acceleration

To use GPU acceleration for VLM inference:

```bash
USE_VLM_GPU=true source setup.sh --summary
```

To use GPU acceleration for OVMS-based summarization:

```bash
USE_OVMS_GPU=true source setup.sh --summary
```

To verify configuration and resolved environment variables without running the application:

```bash
# For VLM inference on GPU
USE_VLM_GPU=true source setup.sh --summary config
```

```bash
# For OVMS inference on GPU
USE_OVMS_GPU=true source setup.sh --summary config
```

> **_NOTE:_** Please avoid setting `USE_VLM_GPU` or `USE_OVMS_GPU` explicitly on shell using `export`, as you need to switch these flags off as well, to return back to CPU configuration.

## 🌐 Accessing the Application

After successfully starting the application, you can access the UI at URL provided by following command:

```bash
echo "http://${HOST_IP}:${APP_HOST_PORT}"
```

## 🏗️ Building Images

If you need to customize the application or build your own images, you can use the `build.sh` script included in the repository.

### ⚙️ Customizing Build Configuration

Before running the build script, you can modify these variables in the script to control where images are pushed:

```bash
# Open build.sh and update these values
export REGISTRY_URL=<your-container-registry>  # e.g. "docker.io/username/"
export PROJECT_NAME=<your-project-name>        # e.g. "video-summary"
export TAG=<your-version-tag>                  # e.g. "latest" or "rc4"
```

### 🔨 Building Images

The build script provides several options:

```bash
sudo chmod +x ./build.sh
# Build all microservice dependencies (vlm-openvino-serving, multimodal-embedding-serving, vdms-dataprep etc.)
./build.sh

# Build only the sample applications (pipeline-manager, search-ms and UI)
./build.sh --sample-app

# Push all built images to the configured registry
./build.sh --push
```

After building, you can verify the created images with:

```bash
docker images | grep <your-project-name>
```

### 🖼️ Using Custom Images

Once you've built and pushed custom images, update your environment variables to use them:

```bash
export REGISTRY_URL=<your-container-registry>
export PROJECT_NAME=<your-project-name>
export TAG=<your-version-tag>
```

Once images are built and pushed, follow the instructions to [run the application](#running-the-application) afterwards.

## ☸️ Running in Kubernetes
Refer to [Deploy with Helm](./deploy-with-helm.md) for the details. Ensure the prerequisites mentioned on this page are addressed before proceeding to deploy with Helm.

## 🔍 Advanced Setup Options

For alternative ways to set up the sample application, see:
- [How to Build from Source](./build-from-source.md)

## 🔗 Related Links
- [How to Test Performance](./how-to-performance.md)

## 📚 Supporting Resources
- [Docker Compose Documentation](https://docs.docker.com/compose/)
