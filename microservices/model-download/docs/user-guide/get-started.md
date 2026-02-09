# Model Download Service

The Model Download Service is a microservice that enables downloading models from multiple hubs: Hugging Face, Ollama, GETI and Ultralytics. It also supports conversion to OpenVINO Model Server (OVMS) format for Hugging Face models. The service exposes a RESTful API for managing model downloads and conversions.

## Features

- Download models from Hugging Face, Ollama, Geti™ and Ultralytics model hubs
- Convert Hugging Face models to OVMS format
- Support for multiple model precisions (INT8, FP16, FP32)
- Support for various device targets (CPU, GPU and NPU)
- OpenVINO plugin supports NPU model conversion exclusively in INT4 precision.
- Parallel download capability
- Configurable model caching
- REST API with OpenAPI documentation

## Prerequisites

- Docker and Docker Compose
- Hugging Face API token (only required for gated Hugging Face models or conversion)
- Sufficient disk space for model storage

## Quick Start

1. **Clone the Repository**:
    - Clone the model-download repository:
      ```bash
      # Clone the latest on mainline
        git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
      # Alternatively, Clone a specific release branch
        git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries -b <release-tag>
      ```
2. **Navigate to the directory**:
    - Go to the model-download microservice directory
      ```bash
      cd edge-ai-libraries/microservices/model-download
      ```
3. **Configure the environment variables**
    - Set the following environment variables:
      ```bash
      export REGISTRY="intel/"
      export TAG=rc3.1_2026.0
      export HUGGINGFACEHUB_API_TOKEN=<your-huggingface-token>
      ```
    - To use the Geti™ plugin, set these variables:
      ```bash
      export GETI_WORKSPACE_ID=<YOUR_GETI_WORKSPACE_ID>
      export GETI_HOST=<GETI_HOST_ADDRESS>
      export GETI_TOKEN=<GETI_ACCESS_TOKEN>
      export GETI_SERVER_API_VERSION=v1
      export GETI_SERVER_SSL_VERIFY=False  # Default is FALSE
      ```
      **Note:** For Geti™ setup instructions, see the documentation [here](https://github.com/open-edge-platform/geti).
4. **Launch the service**
    - Use the run script to start the service and enable the plugins
      ```bash
      source scripts/run_service.sh up --plugins all --model-path <host path>
      ```
      __NOTE__: For public models, no token is needed. Set the Hugging Face token via the `HUGGINGFACEHUB_API_TOKEN` environment variable to download GATED models and for conversion to Openvino IR format
      
      __NOTE__: Ensure the host path does not require privileged access for directory creation. It is recommended to use `$PWD/host_path` or a similar location within your working directory.

      The `run_service.sh` script is a Docker Compose wrapper that builds and manages the model download service container with configurable plugins, model paths, and deployment options.

      #### Options available with the script:

        __Usage__: 
        ```bash
          source scripts/run_service.sh [options] [action]
        ```

        __Actions__:
        ```text
            up                     Start the services (default)
            down                   Stop the services
        ```
        __Options__:
        | Option                   | Description                                                                                      |
        |--------------------------|--------------------------------------------------------------------------------------------------|
        | `--build`                | Build the Docker image before running                                                            |
        | `--rebuild`              | This flag instructs to ignore any existing cached images and rebuild them from scratch using the Dockerfile definitions|
        | `--model-path <path>`    | Set custom model path (default: `$HOME/models/`)                                           |
        | `--plugins <list>`       | Comma-separated list of plugins to enable (e.g., `huggingface,ollama,openvino,ultralytics,geti`) or `all` to enable all available plugins |
        | `--help`                 | Show this help message                                                                           |
      
      **Examples**:
        - Start the service with default settings: `source scripts/run_service.sh up`
        - Stop the service: `source scripts/run_service.sh down`
        - Enable specific plugins: `source scripts/run_service.sh up --plugins huggingface`
        - Enable multiple plugins: `source scripts/run_service.sh up --plugins huggingface,ollama,ultralytics,geti`
        - Use a custom model storage location: `source scripts/run_service.sh up --model-path /data/my-models`
        - Production deployment with all plugins: `source scripts/run_service.sh up --plugins all --model-path tmp/models`
        - Display usage information: `source scripts/run_service.sh --help`

5. **Access the service**
    - The service will be available at `http://<host-ip>:8200/api/v1/docs`, where you can view the Swagger documentation for all available APIs.

## Verification

- Ensure that the application is running by checking the Docker container status:
  ```bash
  docker ps
  ```
- Access the application dashboard and verify that it is functioning as expected.


## Sample usage with CURL command
**Download a Hugging Face model:**
```bash
curl -X POST "http://<host-ip>:8200/api/v1/models/download?download_path=hf_model" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "microsoft/Phi-3.5-mini-instruct",
        "hub": "huggingface",
        "type": "llm"
      }
    ],
    "parallel_downloads": false
  }'
```

**Download a model from Ollama:**
```bash
curl -X POST "http://<host-ip>:8200/api/v1/models/download?download_path=ollama_model" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "tinyllama",
        "hub": "ollama",
        "type": "llm"
      }
    ],
    "parallel_downloads": false
  }'
```

**Download a YOLO vision model from Ultralytics:**
```bash
curl -X POST "http://<host-ip>:8200/api/v1/models/download?download_path=yolo_model" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "yolov8s",
        "hub": "ultralytics",
        "type": "vision"
      }
    ],
    "parallel_downloads": true
  }'
```
> **Note:** YOLO vision models from Ultralytics will be downloaded and converted to OpenVINO IR format with FP32 and FP16 precision by default.

**Download a Hugging Face model and convert to OpenVINO IR format:**
```bash
curl -X POST "http://<host-ip>:8200/api/v1/models/download?download_path=ovms_model" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "BAAI/bge-reranker-base",
        "hub": "openvino",
        "type": "rerank",
        "is_ovms": true,
        "config": {
          "precision": "fp32",
          "device": "CPU",
          "cache_size": 10
        }
      }
    ],
    "parallel_downloads": false
  }'
```

**Download models from GETI optimized with openvino:**
```bash
curl -X POST 'http://<host-ip>:8200/api/v1/models/download?download_path=geti_folder' \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
        {
            "name": "yolox-tiny",
            "hub": "geti",
            "revision": "1",
            "config":{
                "precision": "fp32"
            }
        }
    ],
    "parallel_downloads": true
  }'
```
  **Note:** The default precision is FP16.

**Query Parameter:**
- `download_path` (string): Specify a local file system path where the downloaded model should be saved. If not provided, the model will be saved to a default location.

**Response:**
  **Sample Response (when a download request is started):**
  ```json
  {
    "message": "Started processing 1 model(s)",
    "job_ids": [
      "5f0d4eba-c79c-4d02-97a6-43c3d0168ca0"
    ],
    "status": "processing"
  }
  ```

  Each model download request returns a `job_id`. To check the status of a download, use the following CURL command:

  ```bash
  curl -X GET "http://<host-ip>:8200/api/v1/jobs/<job_id>"
  ```

  **Sample Response (when the job is completed):**
  ```json
  {
    "id": "5f0d4eba-c79c-4d02-97a6-43c3d0168ca0",
    "operation_type": "download",
    "model_name": "yolov8s",
    "hub": "ultralytics",
    "output_dir": "/opt/models/ultra_folder",
    "status": "completed",
    "start_time": "2025-10-27T08:24:23.510870",
    "plugin_name": "ultralytics",
    "model_type":"vision",
    "plugin": "ultralytics",
    "completion_time": "2025-10-27T08:30:14.443898",
    "result": {
      "model_name": "yolov8s",
      "source": "ultralytics",
      "download_path": "model/download/path",
      "return_code": 0
    }
  }
  ```
  - For more details checkout the API [Spec](./api-docs/openapi.yaml)
### Configuration

The service can be configured through environment variables and Docker volumes:

#### Environment Variables:
- `HF_HUB_ENABLE_HF_TRANSFER`: Enable Hugging Face transfer (default: 1)
- `HUGGINGFACEHUB_API_TOKEN`: Hugging Face token (only required for gated models or conversion)

#### Volumes:
- `~/models:/app/models`: Persist downloaded models

## Troubleshooting

- If you encounter any issues during the build or run process, check the Docker logs for errors:
  ```bash
  docker logs <container-id>
  ```

## Best Practices

1. Use parallel downloads with caution, as they can consume significant resources.
2. Configure cache sizes based on available memory.
3. Select model precision according to your performance requirements.
4. Use appropriate model types and configurations for OVMS conversion.

## Running in Kubernetes

Refer to [Deploy with Helm](./deploy-with-helm.md) for the details. Ensure the prerequisites mentioned on this page are addressed before proceeding to deploy with Helm.


## Advanced Setup Options

For alternative ways to set up the sample application, see:

- [How to Build from Source](./build-from-source.md)
