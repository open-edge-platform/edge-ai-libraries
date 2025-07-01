# 🚀 Get Started

<!--
**Sample Description**: Provide a brief overview of the application and its purpose.
-->
The Video Search and Summary (VSS) sample application helps developers create summary of long form video, search for the right video, and combine both search and summary pipelines. This guide will help you set up, run, and modify the sample application on local and Edge AI systems.

<!--
**What You Can Do**: Highlight the developer workflows supported by the guide.
-->
This guide shows how to:
- **Set up the sample application**: Use Setup script to quickly deploy the application in your environment.
- **Run different application stacks**: Execute different application stacks available in the application to perform video search and summary.
- **Modify application parameters**: Customize settings like inference models and deployment configurations to adapt the application to your specific requirements.

## ✅ Prerequisites
- Verify that your system meets the [minimum requirements](./system-requirements.md).
- Install Docker tool: [Installation Guide](https://docs.docker.com/get-docker/).
- Install Docker Compose tool: [Installation Guide](https://docs.docker.com/compose/install/).
- Install Python\* programming language v3.11

## 📂 Project Structure

The repository is organized as follows:

```plaintext
sample-applications/video-search-and-summarization/
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
<a name="required-env"></a>

Before running the application, you need to set several environment variables:

1. **Registry Configuration**:
   The application uses registry URL, project name, and tag to pull or build required images.

    ```bash
    export REGISTRY_URL=<your-container-registry-url>    # e.g. "docker.io/username/"
    export PROJECT_NAME=<your-project-name>              # e.g. "video-search-and-summary""
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
    # For VLM-based chunk captioning and video summary on CPU
    export VLM_MODEL_NAME="Qwen/Qwen2.5-VL-7B-Instruct"  # or any other supported VLM model on CPU

    # For VLM-based chunk captioning and video summary on GPU
    export VLM_MODEL_NAME="microsoft/Phi-3.5-vision-instruct"  # or any other supported VLM model on GPU


    # (Optional) For OVMS-based video summary (when using with ENABLE_OVMS_LLM_SUMMARY=true or ENABLE_OVMS_LLM_SUMMARY_GPU=true)
    export OVMS_LLM_MODEL_NAME="Intel/neural-chat-7b-v3-3"  # or any other supported LLM model

    # Model used by Audio Analyzer service. Only Whisper models variants are supported.
    # Common Supported models: tiny.en, small.en, medium.en, base.en, large-v1, large-v2, large-v3.
    # You can provide just one or comma-separated list of models.
    export ENABLED_WHISPER_MODELS="tiny.en,small.en,medium.en"

    # Object detection model used for Video Ingestion Service. Only Yolo models are supported.
    export OD_MODEL_NAME="yolov8l-worldv2"

    # Multimodal embedding model. Only openai/clip-vit-base models are supported
    export VCLIP_MODEL=openai/clip-vit-base-patch32
    ```

**🔐 Working with Gated Models**

   To run a **GATED MODEL** like Llama models, the user will need to pass their [huggingface token](https://huggingface.co/docs/hub/security-tokens#user-access-tokens). The user will need to request access to specific model by going to the respective model page on HuggingFace.
   
   Go to https://huggingface.co/settings/tokens to get your token.

   ```bash
   export GATED_MODEL=true
   export HUGGINGFACE_TOKEN=<your_huggingface_token>
   ```

Once exported, run the setup script as mentioned [here](#running-app). Please switch off the `GATED_MODEL` flag by running `export GATED_MODEL=false`, once you are no more using gated models. This avoids unnecessary authentication step during setup.

## 📊 Application Stacks Overview

The Video Summary application offers multiple stacks and deployment options:

| Stack | Description | Flag (used with setup script) |
|-------|-------------|------|
| Video Summary | Video frame captioning and Summary | `--summary` |
| Video Search | Video indexing and semantic search | `--search` |
| Video Search + Summary **_(Under Construction)_** | Both summary and search capabilities | `--all` |

### 🧩 Deployment Options for Video Summary

| Option | Chunk-Wise Summary | Final Summary | Environment Variables | Recommended Models |
|--------|--------------------|---------------------|-----------------------|----------------|
| VLM-CPU |vlm-openvino-serving on CPU | vlm-openvino-serving on CPU | Default | VLM: `Qwen/Qwen2.5-VL-7B-Instruct` |
| VLM-GPU | vlm-openvino-serving |vlm-openvino-serving GPU | `ENABLE_VLM_GPU=true` | VLM: `microsoft/Phi-3.5-vision-instruct` |
| VLM-OVMS-CPU | vlm-openvino-serving on CPU | OVMS Microservice on CPU | `ENABLE_OVMS_LLM_SUMMARY=true` | VLM: `Qwen/Qwen2.5-VL-7B-Instruct`<br>LLM: `Intel/neural-chat-7b-v3-3` |
| VLM-CPU-OVMS-GPU | vlm-openvino-serving on CPU | OVMS Microservice on GPU | `ENABLE_OVMS_LLM_SUMMARY_GPU=true` | VLM: `Qwen/Qwen2.5-VL-7B-Instruct`<br>LLM: `Intel/neural-chat-7b-v3-3` |

## ▶️ Running the Application
<a name="running-app"></a>

Follow these steps to run the application:

1. Clone the repository and navigate to the project directory:

    ```bash
    git clone https://github.com/open-edge-platform/edge-ai-libraries.git
    cd edge-ai-libraries/sample-applications/video-search-and-summarization
    ```

2. Set the required environment variables as described  [above](#required-env).

3. Run the setup script with the appropriate flag, depending on your use case. 

   > NOTE: Before switching to a different mode always stop the current application stack by running:

   ```bash
   source setup.sh --down
   ```

- **To run Video Summary only:**
    ```bash
    source setup.sh --summary
    ```

- **To run Video Search only:**
    ```bash
    source setup.sh --search
    ```

- **To run Video Summary with OVMS Microservice for final summary :**
    ```bash
    ENABLE_OVMS_LLM_SUMMARY=true source setup.sh --summary
    ```


4. (Optional) Verify the resolved environment variables and setup configurations.

    ```bash
    # To just set environment variables without starting containers
    source setup.sh --setenv

    # To see resolved configurations for summary services without starting containers
    source setup.sh --summary config

    # To see resolved configurations for search services without starting containers
    source setup.sh --search config

    # To see resolved configurations for both search and summary services combined without starting containers
    source setup.sh --all config

    # To see resolved configurations for summary services with OVMS setup on CPU without starting containers
    ENABLE_OVMS_LLM_SUMMARY=true source setup.sh --summary config
    ```

## Running Tests for Video Search Microservice

The project uses pytest for testing. After installing and setting up the application on host, we can run tests as follows:

```bash
# Run all tests
python -m pytest src/tests/

# Run tests with verbose output
python -m pytest src/tests/ -v

# Run tests by module - Utils
python -m pytest src/tests/test_utils/test_common.py
python -m pytest src/tests/test_utils/test_directory_watcher.py
python -m pytest src/tests/test_utils/test_minio_client.py
python -m pytest src/tests/test_utils/test_utils.py

# Run tests by module - VDMS Retriever
python -m pytest src/tests/test_vdms_retriever/test_embedding_wrapper.py
python -m pytest src/tests/test_vdms_retriever/test_retriever.py

# Run all tests in utils directory
python -m pytest src/tests/test_utils/

# Run all tests in vdms_retriever directory
python -m pytest src/tests/test_vdms_retriever/

# Run specific test class
python -m pytest src/tests/test_utils/test_common.py::TestCommon

# Run specific test method
python -m pytest src/tests/test_utils/test_common.py::TestCommon::test_settings_default_values
```

### Generate Test Coverage Reports

To generate a coverage report:

```bash
# Run tests with coverage
python -m pytest src/tests/ --cov=src

# Generate detailed HTML coverage report
python -m pytest src/tests/ --cov=src --cov-report=html --cov-report=term-missing

# Open the HTML report (Linux)
xdg-open htmlcov/index.html

# Open the HTML report (macOS)
open htmlcov/index.html

# Open the HTML report (Windows)
start htmlcov/index.html
```

## Using GPU Acceleration

To use GPU acceleration for VLM inference:

   > NOTE: Before switching to a different mode always stop the current application stack by running:

   ```bash
   source setup.sh --down
   ```

```bash
ENABLE_VLM_GPU=true source setup.sh --summary
```

To use GPU acceleration for OVMS-based summary:

```bash
ENABLE_OVMS_LLM_SUMMARY_GPU=true source setup.sh --summary
```

To use GPU acceleration for vclip-embedding-ms for search usecase:

```bash
ENABLE_EMBEDDING_GPU=true source setup.sh --search
```

To verify configuration and resolved environment variables without running the application:

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

> **_NOTE:_** Please avoid setting `ENABLE_VLM_GPU`, `ENABLE_OVMS_LLM_SUMMARY_GPU`, or `ENABLE_EMBEDDING_GPU` explicitly on shell using `export`, as you need to switch these flags off as well, to return back to CPU configuration.

## 🌐 Accessing the Application

After successfully starting the application, open a browser and go to `http://<host-ip>:12345` to access the application dashboard.

## ☸️ Running in Kubernetes
Refer to [Deploy with Helm](./deploy-with-helm.md) for the details. Ensure the prerequisites mentioned on this page are addressed before proceeding to deploy with Helm.

## 🔍 Advanced Setup Options

For alternative ways to set up the sample application, see:
- [How to Build from Source](./build-from-source.md)

## 🔗 Related Links
- [How to Test Performance](./how-to-performance.md)

## 📚 Supporting Resources
- [Docker Compose Documentation](https://docs.docker.com/compose/)
