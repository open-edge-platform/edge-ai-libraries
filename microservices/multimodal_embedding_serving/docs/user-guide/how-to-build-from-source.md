# How to Build from Source

This guide covers building the **Multimodal Embedding Serving microservice** from source for customization, development, or debugging purposes.

## Prerequisites

Before you begin, ensure:

- **System Requirements**: Meet the [minimum requirements](./system-requirements.md)
- **Git**: For cloning the repository
- **Docker**: For building containers

## Build Steps

### 1. Clone Repository

```bash
git clone https://github.com/intel/edge-ai-libraries.git
cd edge-ai-libraries/microservices/multimodal_embedding_serving
```

### 2. Configure Environment

```bash
# Use setup script for default configuration
source setup.sh

# Or customize before building
export EMBEDDING_MODEL_NAME="CN-CLIP/cn-clip-vit-b-16"
export EMBEDDING_DEVICE="GPU"
source setup.sh
```

### 3. Build Docker Image

```bash
# Build the image
docker compose -f docker/compose.yaml build
```

### 4. Run Built Service

```bash
# Start the service
docker compose -f docker/compose.yaml up -d

# Verify build
docker logs multimodal-embedding-serving
```

## Custom Build Configuration

### Registry and Naming

```bash
export REGISTRY_URL="your-registry.com/"
export PROJECT_NAME="your-project/"
export TAG="v1.0.0"

# Apply configuration and build
source setup.sh
docker compose -f docker/compose.yaml build
```

Final image name: `your-registry.com/your-project/multimodal-embedding-serving:v1.0.0`

### Model Configuration

```bash
# Configure specific model for build
export EMBEDDING_MODEL_NAME="Blip2/blip2_transformers"
export EMBEDDING_DEVICE="GPU"
export DEFAULT_NUM_FRAMES=32

# Apply and build
source setup.sh
docker compose -f docker/compose.yaml build
```

## Development Workflow

### Local Development

For Python development without Docker:

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run locally (development mode)
python src/main.py
```

### Rebuild After Changes

```bash
# Rebuild with latest changes
docker compose -f docker/compose.yaml build --no-cache

# Test changes
docker compose -f docker/compose.yaml up -d
```

## Build Validation

### Verify Build Success

```bash
# Check image was created
docker images | grep multimodal-embedding-serving

# Verify container starts successfully
docker logs multimodal-embedding-serving

# Test API functionality
curl http://localhost:9777/health
```

## Common Build Issues

**Docker build fails:**
```bash
# Clean build cache and retry
docker system prune -a
docker compose -f docker/compose.yaml build --no-cache
```

**Python dependency conflicts:**
```bash
# Update pip and rebuild
pip install --upgrade pip setuptools wheel
docker compose -f docker/compose.yaml build --no-cache
```

## Supporting Resources

- [Get Started Guide](get-started.md) - Basic deployment guide
- [Quick Reference](quick-reference.md) - Essential commands and configurations
- [Supported Models](supported-models.md) - Available models for development
- [SDK Usage](sdk-usage.md) - Python SDK integration examples
- [System Requirements](system-requirements.md) - Hardware requirements
- [API Reference](api-reference.md) - API documentation