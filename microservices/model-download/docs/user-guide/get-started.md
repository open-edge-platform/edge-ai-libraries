# Model Download Service

The Model Download Service is a microservice that enables downloading models from multiple hubs: Hugging Face, Ollama, and Ultralytics. It also supports conversion to OpenVINO Model Server (OVMS) format for Hugging Face models. The service exposes a RESTful API for managing model downloads and conversions.

## Features

- Download models from Hugging Face, Ollama, and Ultralytics model hubs
- Convert Hugging Face models to OVMS format
- Support for multiple model precisions (INT8, FP16, FP32)
- Support for various device targets (CPU, GPU)
- Parallel download capability
- Configurable model caching
- REST API with OpenAPI documentation

## Prerequisites

- Docker and Docker Compose
- Hugging Face API token (only required for gated Hugging Face models or conversion)
- Sufficient disk space for model storage

## Quick Start

1. Clone the repository and navigate to the `model-download` directory:
```bash
cd microservices/model-download
```
2. Configure the environment variables and launch the service
```bash
export REGISTRY=""
export TAG=""
export HF_TOKEN=<your huggingface token>
source scripts/run_service.sh --plugins all --model-path <host path>
```
__NOTE__: For public models, no token is needed. Set the Hugging Face token via the `HF_TOKEN` environment variable to download GATED models and for conversion to Openvino IR format

The `run_service.sh` script is a Docker Compose wrapper that builds and manages the model download service container with configurable plugins, model paths, and deployment options.

#### Options available with the script:

```text
Usage: source scripts/run_service.sh [options] [action]

Actions:
  up                     Start the services (default)
  down                   Stop the services

Options:
  --build                Build the Docker image before running
  --rebuild              Force rebuild the Docker image without cache
  --model-path <path>    Set custom model path (default: /home/intel/models/)
  --plugins <list>       Comma-separated list of plugins to enable (e.g., huggingface,ollama,ultralytics) or all to enable all available plugins
  --help                 Show this help message
```

3. Start the service using Docker Compose:
```bash
docker compose -f docker/compose.yaml up
```

The service will be available at `http://localhost:8200/api/v1/docs`, where you can view the Swagger documentation for all available APIs.

##  API Documentation

### Endpoints

#### Download Models

`POST /api/v1/models/download`

Downloads one or more models from Hugging Face, Ollama, or Ultralytics. Hugging Face models can optionally be converted to OVMS format.

**Request Body:**
To download the models available on Hugging Face hub. Also conversion to Openvino IR format is supported with __is_ovms__ flag with more details added in the config section of the payload
```json
{
  "models": [
    {
      "name": "microsoft/Phi-3.5-mini-instruct",
      "hub": "huggingface",
      "type": "llm",
      "is_ovms": true,
      "config": {
        "precision": "int8",
        "device": "CPU",
        "cache_size": 10
      }
    }
  ],
  "parallel_downloads": false
}
```

To download the models available on Ollama hub. 
```json
{
  "models": [
    {
      "name": "tinyllama",
      "hub": "ollama",
      "type": "llm",
    }
  ],
  "parallel_downloads": false
}
```
To download a yolo vision models
```json
{
    "models": [
        {
            "name": "yolov8s",
            "hub":"ultralytics",
            "type": "vision",
            "is_ovms": false,
            "config": {
                "precision": "fp16",
                "device": "CPU"
            }
        }
    ],
    "parallel_downloads": true
}
```

**Parameters:**
- `name` (required): The name/ID of the model (Hugging Face, Ollama, or Ultralytics)
- `hub` (required): The model hub to download from (Options: huggingface, ollama, ultralytics)
- `type`: Model type (e.g., llm, embeddings, rerank)
- `is_ovms`: Whether to convert the model to OVMS format (default: false, only for Hugging Face models)
- `config`: Configuration for OVMS conversion
  - `precision`: Model precision (int8, fp16, fp32)
  - `device`: Target device (CPU, GPU)
  - `cache_size`: Cache size for model optimization

**Response:**
```json
{
  "message": "Model download completed",
  "results": [
    {
      "status": "success",
      "model_name": "microsoft/Phi-3.5-mini-instruct",
      "model_path": "/app/models/microsoft_Phi-3.5-mini-instruct",
      "is_ovms": true
    }
  ]
}
```

### Configuration

The service can be configured through environment variables and Docker volumes:

#### Environment Variables:
- `HF_HUB_ENABLE_HF_TRANSFER`: Enable Hugging Face transfer (default: 1)
- `HF_TOKEN`: Hugging Face token (only required for gated models or conversion)

#### Volumes:
- `~/.cache/huggingface:/home/appuser/.cache/huggingface`: Cache Hugging Face models
- `~/models:/app/models`: Persist downloaded models

## Error Handling

The API returns appropriate HTTP status codes:

- `200`: Successful operation
- `400`: Bad request or model processing error
- `401`: Authentication token missing or invalid (only for gated Hugging Face models)
- `422`: Validation error in request

Error responses include a detail message explaining the error:
```json
{
  "detail": "Error message here"
}
```

## Best Practices

1. Use parallel downloads with caution, as they can consume significant resources.
2. Configure cache sizes based on available memory.
3. Select model precision according to your performance requirements.
4. Mount volumes for both Hugging Face cache and model storage to persist data.
5. Use appropriate model types and configurations for OVMS conversion.
