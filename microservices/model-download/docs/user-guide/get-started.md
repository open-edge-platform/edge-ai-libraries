# Model Download Service

The Model Download Service is a microservice that facilitates downloading and converting models from Hugging Face to OpenVINO Model Server (OVMS) format. This service provides a RESTful API for managing model downloads and conversions.

## Features

- Download models from Hugging Face Hub
- Convert models to OVMS format
- Support for various model precisions (INT8, FP16, FP32)
- Support for different device targets (CPU, GPU)
- Parallel download capability
- Configurable model caching
- REST API with OpenAPI documentation

## Prerequisites

- Docker and Docker Compose
- Hugging Face API token
- Sufficient disk space for model storage

## Quick Start

1. Clone the repository and navigate to the model-download directory:
```bash
cd microservices/model-download
```

2. Start the service using Docker Compose:
```bash
docker compose -f docker/compose.yaml up --build
```

The service will be available at `http://localhost:32004/api/v1`

## API Documentation

### Authentication

All API endpoints require authentication using a Hugging Face API token. Pass the token in the `Authorization` header:

```http
Authorization: your_hugging_face_token
```

### Endpoints

#### Download Models

`POST /api/v1/models/download`

Downloads one or more models from Hugging Face and optionally converts them to OVMS format.

**Request Body:**
If the model is present in HuggingFace hub
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

If the model is present in Ollama hub (OVMS support not available yet for Ollama models)
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

**Parameters:**
- `name` (required): The name/ID of the Hugging Face model
- `hub` (required): The model hub to download from (Options - huggingface or ollama)
- `type`: Model type (e.g., llm, embeddings, rerank)
- `is_ovms`: Whether to convert the model to OVMS format (default: false)
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

#### Volumes:
- `~/.cache/huggingface:/root/.cache/huggingface`: Cache Hugging Face models
- `~/models:/app/models`: Persist downloaded models

## Docker Compose Configuration

The service can be run using Docker Compose with the following configuration:

```yaml
services:
  model_download_service:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    environment:
      - HF_HUB_ENABLE_HF_TRANSFER=1
    ports:
      - "32004:8000"
    volumes:
      - ~/.cache/huggingface:/root/.cache/huggingface
      - ~/models:/app/models
```

## Error Handling

The API returns appropriate HTTP status codes:

- `200`: Successful operation
- `400`: Bad request or model processing error
- `401`: Authentication token missing or invalid
- `422`: Validation error in request

Error responses include a detail message explaining the error:
```json
{
  "detail": "Error message here"
}
```

## Best Practices

1. Use parallel downloads with caution as they can consume significant resources
2. Configure appropriate cache sizes based on your available memory
3. Choose the appropriate model precision based on your performance requirements
4. Mount volumes for both the Hugging Face cache and model storage to persist data
5. Use appropriate model types and configurations for OVMS conversion
