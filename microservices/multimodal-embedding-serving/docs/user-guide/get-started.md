# Get Started

This guide provides step-by-step instructions to quickly deploy and test the **Multimodal Embedding Serving microservice**.

## Prerequisites

Before you begin, ensure the following:

- **System Requirements**: Verify that your system meets the [minimum requirements](./system-requirements.md)
- **Docker Installed**: Install Docker. For installation instructions, see [Get Docker](https://docs.docker.com/get-docker/)

This guide assumes basic familiarity with Docker commands and terminal usage.

## Quick Start

### 1. Clone and Choose Your Model

```bash
# Clone the repository
git clone https://github.com/intel/edge-ai-libraries.git
cd edge-ai-libraries/microservices/multimodal-embedding-serving

# REQUIRED: Choose and set your model
export EMBEDDING_MODEL_NAME="your-chosen-model"  # Replace with your preferred model

# Set environment variables using the setup script
source setup.sh
```

**Important**: You must set `EMBEDDING_MODEL_NAME` before running `setup.sh`. See [Supported Models](supported-models.md) for available options.

### 2. Configure Hardware (Optional)

```bash
# For GPU deployment (if Intel GPU available)
export EMBEDDING_DEVICE="GPU"
source setup.sh

# Default is CPU deployment
```

### 3. Run with Docker Compose

```bash
docker compose -f docker/compose.yaml up -d
```

### 4. Verify the Service

```bash
# Health check
curl http://localhost:9777/health

# Test text embedding
curl -X POST http://localhost:9777/embeddings \
  -H "Content-Type: application/json" \
  -d '{
    "input": {"type": "text", "text": "Hello world"},
    "model": "'$EMBEDDING_MODEL_NAME'"
  }'
```

## Quick API Test

Once the service is running, test different input types:

```bash
# Text embedding
curl -X POST http://localhost:9777/embeddings \
  -H "Content-Type: application/json" \
  -d '{
    "input": {"type": "text", "text": "A beautiful sunset"},
    "model": "'$EMBEDDING_MODEL_NAME'"
  }'

# Image URL embedding
curl -X POST http://localhost:9777/embeddings \
  -H "Content-Type: application/json" \
  -d '{
    "input": {"type": "image_url", "image_url": "https://example.com/image.jpg"},
    "model": "'$EMBEDDING_MODEL_NAME'"
  }'
```

For complete API documentation, see [API Reference](api-reference.md).

## Building from Source

To build from source instead of using pre-built images:

```bash
docker compose -f docker/compose.yaml build
docker compose -f docker/compose.yaml up -d
```

See [How to Build from Source](how-to-build-from-source.md) for detailed development instructions.

## Troubleshooting

**Service fails to start:**

```bash
docker logs multimodal-embedding-serving
```

**Model not found:**

```bash
# Check if model is supported
echo $EMBEDDING_MODEL_NAME

# Set a supported model (see supported-models.md)
export EMBEDDING_MODEL_NAME="your-chosen-model"
source setup.sh
```

**GPU issues:**

```bash
# Check Intel GPU availability
ls -la /dev/dri
```

## Next Steps

- [Quick Reference](quick-reference.md) - Essential commands and configurations
- [API Reference](api-reference.md) - Complete API documentation
- [SDK Usage](sdk-usage.md) - Direct Python integration
- [Wheel Installation](wheel-installation.md) - Build and install as Python package
- [Supported Models](supported-models.md) - Available models and configurations
