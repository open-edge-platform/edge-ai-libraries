# Docker Deployment Guide

This guide provides comprehensive instructions for deploying the Multimodal Embedding Serving microservice using Docker. Whether you're setting up for development, testing, or production, this guide covers all deployment scenarios.

## Prerequisites

### System Requirements
- **Docker**: Version 20.10 or higher
- **Docker Compose**: Version 2.0 or higher (optional, for orchestration)
- **System Memory**: Minimum 4GB RAM (8GB+ recommended for larger models)
- **Storage**: 5-10GB free space for models and containers

### For GPU Support (Optional)
- **NVIDIA Docker**: nvidia-docker2 or Docker with NVIDIA Container Runtime
- **NVIDIA GPU**: Compatible GPU with CUDA support
- **NVIDIA Drivers**: Latest drivers installed

## Quick Start with Docker

### 1. Pull the Pre-built Image

```bash
# Pull the latest image
docker pull intel/multimodal-embedding-serving:latest

# Or pull a specific version
docker pull intel/multimodal-embedding-serving:v1.0.0
```

### 2. Run with Default Configuration

```bash
docker run -d \
  --name multimodal-embedding \
  -p 9777:9777 \
  -e EMBEDDING_MODEL_NAME="CLIP/clip-vit-b-16" \
  -e EMBEDDING_DEVICE="CPU" \
  intel/multimodal-embedding-serving:latest
```

### 3. Verify the Service

```bash
# Check if the service is running
curl http://localhost:9777/health

# Get current model information
curl http://localhost:9777/model/current

# Test text embedding
curl -X POST http://localhost:9777/embeddings \
  -H "Content-Type: application/json" \
  -d '{
    "input": {"type": "text", "text": ["Hello world"]},
    "model": "CLIP/clip-vit-b-16",
    "encoding_format": "float"
  }'
```

## Building from Source

### 1. Clone the Repository

```bash
git clone https://github.com/intel/edge-ai-libraries.git
cd edge-ai-libraries/microservices/multimodal_embedding_serving
```

### 2. Build the Docker Image

```bash
# Build with default settings
docker build -t multimodal-embedding-serving .

# Build with custom tag
docker build -t my-org/multimodal-embedding:v1.0 .

# Build with build arguments
docker build \
  --build-arg PYTHON_VERSION=3.11 \
  --build-arg BASE_IMAGE=python:3.11-slim \
  -t multimodal-embedding-serving .
```

### 3. Run the Custom Built Image

```bash
docker run -d \
  --name multimodal-embedding \
  -p 9777:9777 \
  multimodal-embedding-serving
```

## Configuration Options

### Environment Variables

#### Model Configuration
```bash
# Model selection (REQUIRED - choose from supported-models.md)
export EMBEDDING_MODEL_NAME="CLIP/clip-vit-b-16"      # Replace with your chosen model
export EMBEDDING_DEVICE="CPU"                          # CPU or GPU
export EMBEDDING_USE_OV="false"                        # Enable OpenVINO
export EMBEDDING_OV_MODELS_DIR="/app/ov-models"       # OpenVINO models directory

# Alternative model examples (see supported-models.md for complete list)
export EMBEDDING_MODEL_NAME="CN-CLIP/cn-clip-vit-b-16"    # Chinese support
export EMBEDDING_MODEL_NAME="MobileCLIP/mobileclip_b"     # Mobile optimized
export EMBEDDING_MODEL_NAME="Blip2/blip2_transformers"    # Advanced multimodal
```

#### Application Configuration
```bash
export APP_NAME="Multimodal-Embedding-Serving"
export APP_DISPLAY_NAME="Multimodal Embedding Serving"
export APP_DESC="Multimodal embedding service for text, image, and video"
```

#### Network Configuration
```bash
export http_proxy="http://proxy.company.com:8080"
export https_proxy="http://proxy.company.com:8080"
export no_proxy="localhost,127.0.0.1,.local"
```

#### Video Processing Configuration
```bash
export DEFAULT_START_OFFSET_SEC=0      # Default video start offset
export DEFAULT_CLIP_DURATION=-1        # -1 for full video
export DEFAULT_NUM_FRAMES=64           # Default frames to extract
```

### Volume Mounts

#### Model Cache Volume
```bash
# Mount volume for model caching
docker run -d \
  --name multimodal-embedding \
  -p 9777:9777 \
  -v $(pwd)/models:/app/models \
  -v $(pwd)/ov-models:/app/ov-models \
  -e EMBEDDING_MODEL_PATH="/app/models" \
  -e EMBEDDING_OV_MODELS_DIR="/app/ov-models" \
  intel/multimodal-embedding-serving:latest
```

#### Configuration Volume
```bash
# Mount custom configuration
docker run -d \
  --name multimodal-embedding \
  -p 9777:9777 \
  -v $(pwd)/config:/app/config \
  -e CONFIG_PATH="/app/config" \
  intel/multimodal-embedding-serving:latest
```

## Docker Compose Deployment

### 1. Basic Docker Compose

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  multimodal-embedding:
    image: intel/multimodal-embedding-serving:latest
    container_name: multimodal-embedding
    ports:
      - "9777:9777"
    environment:
      - EMBEDDING_MODEL_NAME=CLIP/clip-vit-b-16
      - EMBEDDING_DEVICE=CPU
      - EMBEDDING_USE_OV=false
    volumes:
      - ./models:/app/models
      - ./ov-models:/app/ov-models
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9777/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

Run with:
```bash
docker-compose up -d
```

### 2. Multi-Model Setup

```yaml
version: '3.8'

services:
  # Standard CLIP service
  clip-service:
    image: intel/multimodal-embedding-serving:latest
    container_name: clip-embedding
    ports:
      - "9777:9777"
    environment:
      - EMBEDDING_MODEL_NAME=CLIP/clip-vit-b-16
      - EMBEDDING_DEVICE=CPU
    volumes:
      - ./models:/app/models

  # Chinese CLIP service  
  cn-clip-service:
    image: intel/multimodal-embedding-serving:latest
    container_name: cn-clip-embedding
    ports:
      - "9778:9777"
    environment:
      - EMBEDDING_MODEL_NAME=CN-CLIP/cn-clip-vit-b-16
      - EMBEDDING_DEVICE=CPU
    volumes:
      - ./models:/app/models

  # Mobile CLIP service
  mobile-clip-service:
    image: intel/multimodal-embedding-serving:latest
    container_name: mobile-clip-embedding
    ports:
      - "9779:9777"
    environment:
      - EMBEDDING_MODEL_NAME=MobileCLIP/mobileclip_b
      - EMBEDDING_DEVICE=CPU
    volumes:
      - ./models:/app/models
```

### 3. Production Setup with Load Balancer

```yaml
version: '3.8'

services:
  # Load balancer
  nginx:
    image: nginx:alpine
    container_name: embedding-lb
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    depends_on:
      - embedding-1
      - embedding-2
    restart: unless-stopped

  # Service replicas
  embedding-1:
    image: intel/multimodal-embedding-serving:latest
    container_name: embedding-service-1
    environment:
      - EMBEDDING_MODEL_NAME=CLIP/clip-vit-b-16
      - EMBEDDING_USE_OV=true
      - EMBEDDING_DEVICE=CPU
    volumes:
      - ./models:/app/models
      - ./ov-models:/app/ov-models
    restart: unless-stopped

  embedding-2:
    image: intel/multimodal-embedding-serving:latest
    container_name: embedding-service-2
    environment:
      - EMBEDDING_MODEL_NAME=CLIP/clip-vit-b-16
      - EMBEDDING_USE_OV=true
      - EMBEDDING_DEVICE=CPU
    volumes:
      - ./models:/app/models
      - ./ov-models:/app/ov-models
    restart: unless-stopped
```

## GPU Support

### 1. NVIDIA GPU Setup

```bash
# Install NVIDIA Container Runtime
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list

sudo apt-get update && sudo apt-get install -y nvidia-docker2
sudo systemctl restart docker
```

### 2. Run with GPU Support

```bash
docker run -d \
  --name multimodal-embedding-gpu \
  --gpus all \
  -p 9777:9777 \
  -e EMBEDDING_MODEL_NAME="CLIP/clip-vit-h-14" \
  -e EMBEDDING_DEVICE="GPU" \
  -v $(pwd)/models:/app/models \
  intel/multimodal-embedding-serving:latest
```

### 3. GPU Docker Compose

```yaml
version: '3.8'

services:
  multimodal-embedding-gpu:
    image: intel/multimodal-embedding-serving:latest
    container_name: multimodal-embedding-gpu
    ports:
      - "9777:9777"
    environment:
      - EMBEDDING_MODEL_NAME=CLIP/clip-vit-h-14
      - EMBEDDING_DEVICE=GPU
    volumes:
      - ./models:/app/models
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    restart: unless-stopped
```

## Performance Optimization

### 1. OpenVINO Optimization

```bash
# Enable OpenVINO for Intel CPU optimization
docker run -d \
  --name multimodal-embedding-ov \
  -p 9777:9777 \
  -e EMBEDDING_MODEL_NAME="CLIP/clip-vit-b-16" \
  -e EMBEDDING_USE_OV="true" \
  -e EMBEDDING_DEVICE="CPU" \
  -v $(pwd)/ov-models:/app/ov-models \
  intel/multimodal-embedding-serving:latest
```

### 2. Memory Optimization

```bash
# Limit container memory
docker run -d \
  --name multimodal-embedding \
  --memory="4g" \
  --memory-swap="6g" \
  -p 9777:9777 \
  -e EMBEDDING_MODEL_NAME="MobileCLIP/mobileclip_b" \
  intel/multimodal-embedding-serving:latest
```

### 3. CPU Optimization

```bash
# Allocate specific CPU cores
docker run -d \
  --name multimodal-embedding \
  --cpus="4.0" \
  --cpuset-cpus="0-3" \
  -p 9777:9777 \
  intel/multimodal-embedding-serving:latest
```

## Production Deployment

### 1. Security Configuration

```yaml
version: '3.8'

services:
  multimodal-embedding:
    image: intel/multimodal-embedding-serving:latest
    container_name: multimodal-embedding
    ports:
      - "127.0.0.1:9777:9777"  # Bind to localhost only
    environment:
      - EMBEDDING_MODEL_NAME=CLIP/clip-vit-b-16
    volumes:
      - ./models:/app/models:ro  # Read-only volume
    restart: unless-stopped
    user: "1000:1000"  # Non-root user
    read_only: true
    tmpfs:
      - /tmp
    security_opt:
      - no-new-privileges:true
```

### 2. Health Monitoring

```yaml
version: '3.8'

services:
  multimodal-embedding:
    image: intel/multimodal-embedding-serving:latest
    container_name: multimodal-embedding
    ports:
      - "9777:9777"
    environment:
      - EMBEDDING_MODEL_NAME=CLIP/clip-vit-b-16
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9777/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    restart: unless-stopped
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### 3. Resource Limits

```yaml
version: '3.8'

services:
  multimodal-embedding:
    image: intel/multimodal-embedding-serving:latest
    container_name: multimodal-embedding
    ports:
      - "9777:9777"
    deploy:
      resources:
        limits:
          cpus: '4.0'
          memory: 8G
        reservations:
          cpus: '2.0'
          memory: 4G
    environment:
      - EMBEDDING_MODEL_NAME=CLIP/clip-vit-b-16
    restart: unless-stopped
```

## Scaling and Load Balancing

### 1. Horizontal Scaling

```bash
# Scale with Docker Compose
docker-compose up -d --scale multimodal-embedding=3

# Or using Docker Swarm
docker service create \
  --name multimodal-embedding \
  --replicas 3 \
  --publish 9777:9777 \
  intel/multimodal-embedding-serving:latest
```

### 2. NGINX Load Balancer Configuration

Create `nginx.conf`:

```nginx
events {
    worker_connections 1024;
}

http {
    upstream embedding_backend {
        server embedding-1:9777;
        server embedding-2:9777;
        server embedding-3:9777;
    }

    server {
        listen 80;
        
        location / {
            proxy_pass http://embedding_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_connect_timeout 30s;
            proxy_send_timeout 30s;
            proxy_read_timeout 30s;
        }
        
        location /health {
            proxy_pass http://embedding_backend/health;
        }
    }
}
```

## Troubleshooting

### 1. Common Issues

#### Container Won't Start
```bash
# Check container logs
docker logs multimodal-embedding

# Check resource usage
docker stats multimodal-embedding

# Inspect container configuration
docker inspect multimodal-embedding
```

#### Model Loading Issues
```bash
# Check available disk space
df -h

# Verify model cache volume
docker exec multimodal-embedding ls -la /app/models

# Check environment variables
docker exec multimodal-embedding env | grep EMBEDDING
```

#### Memory Issues
```bash
# Monitor memory usage
docker stats --no-stream multimodal-embedding

# Use smaller model
docker run -d \
  --name multimodal-embedding \
  -e EMBEDDING_MODEL_NAME="MobileCLIP/mobileclip_s0" \
  intel/multimodal-embedding-serving:latest
```

### 2. Performance Issues

#### Slow Response Times
```bash
# Enable OpenVINO optimization
docker run -d \
  --name multimodal-embedding-ov \
  -e EMBEDDING_USE_OV="true" \
  intel/multimodal-embedding-serving:latest

# Allocate more CPU
docker update --cpus="4.0" multimodal-embedding
```

#### High Memory Usage
```bash
# Restart container to clear memory
docker restart multimodal-embedding

# Use memory-efficient model
docker run -d \
  --memory="2g" \
  -e EMBEDDING_MODEL_NAME="MobileCLIP/mobileclip_s0" \
  intel/multimodal-embedding-serving:latest
```

### 3. Debugging

#### Enable Debug Logging
```bash
docker run -d \
  --name multimodal-embedding \
  -e LOG_LEVEL="DEBUG" \
  intel/multimodal-embedding-serving:latest
```

#### Interactive Debugging
```bash
# Run container interactively
docker run -it \
  --rm \
  -p 9777:9777 \
  intel/multimodal-embedding-serving:latest \
  /bin/bash

# Or exec into running container
docker exec -it multimodal-embedding /bin/bash
```

## Monitoring and Maintenance

### 1. Health Checks

```bash
# Built-in health endpoint
curl http://localhost:9777/health

# Custom health check script
#!/bin/bash
response=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:9777/health)
if [ $response = "200" ]; then
    echo "Service is healthy"
    exit 0
else
    echo "Service is unhealthy"
    exit 1
fi
```

### 2. Log Management

```bash
# View recent logs
docker logs --tail 100 multimodal-embedding

# Follow logs
docker logs -f multimodal-embedding

# Export logs
docker logs multimodal-embedding > embedding-service.log
```

### 3. Backup and Recovery

```bash
# Backup model cache
tar -czf models-backup.tar.gz ./models ./ov-models

# Backup configuration
docker inspect multimodal-embedding > container-config.json

# Recovery
tar -xzf models-backup.tar.gz
docker-compose up -d
```

## Example Deployment Scripts

### 1. Quick Deployment Script

```bash
#!/bin/bash
# deploy.sh

set -e

if [ -z "$1" ]; then
    echo "ERROR: Model name is required"
    echo "Usage: ./deploy.sh <MODEL_NAME> [PORT]"
    echo "Example: ./deploy.sh CLIP/clip-vit-b-16 9777"
    echo "See docs/user-guide/supported-models.md for available models"
    exit 1
fi

MODEL_NAME=$1
PORT=${2:-9777}

echo "Deploying Multimodal Embedding Service..."
echo "Model: $MODEL_NAME"
echo "Port: $PORT"

# Pull latest image
docker pull intel/multimodal-embedding-serving:latest

# Stop existing container
docker stop multimodal-embedding 2>/dev/null || true
docker rm multimodal-embedding 2>/dev/null || true

# Start new container
docker run -d \
  --name multimodal-embedding \
  -p $PORT:9777 \
  -e EMBEDDING_MODEL_NAME="$MODEL_NAME" \
  -e EMBEDDING_DEVICE="CPU" \
  -v $(pwd)/models:/app/models \
  -v $(pwd)/ov-models:/app/ov-models \
  --restart unless-stopped \
  intel/multimodal-embedding-serving:latest

# Wait for service to be ready
echo "Waiting for service to start..."
sleep 30

# Test service
if curl -f http://localhost:$PORT/health; then
    echo "✅ Service deployed successfully!"
    echo "📊 Service URL: http://localhost:$PORT"
    echo "📖 API Docs: http://localhost:$PORT/docs"
else
    echo "❌ Service deployment failed!"
    docker logs multimodal-embedding
    exit 1
fi
```

### 2. Production Deployment Script

```bash
#!/bin/bash
# deploy-production.sh

set -e

if [ -z "$2" ]; then
    echo "ERROR: Model name is required"
    echo "Usage: ./deploy-production.sh <ENVIRONMENT> <MODEL_NAME>"
    echo "Example: ./deploy-production.sh production CLIP/clip-vit-b-16"
    echo "See docs/user-guide/supported-models.md for available models"
    exit 1
fi

ENVIRONMENT=${1:-production}
MODEL_NAME=$2

echo "Deploying to $ENVIRONMENT environment..."

# Create necessary directories
mkdir -p ./models ./ov-models ./logs

# Set production configuration
cat > .env << EOF
EMBEDDING_MODEL_NAME=$MODEL_NAME
EMBEDDING_DEVICE=CPU
EMBEDDING_USE_OV=true
EMBEDDING_OV_MODELS_DIR=/app/ov-models
LOG_LEVEL=INFO
EOF

# Deploy with Docker Compose
docker-compose -f docker-compose.prod.yml up -d

# Verify deployment
sleep 60
curl -f http://localhost:9777/health || exit 1

echo "✅ Production deployment successful!"
```

This comprehensive Docker deployment guide covers all aspects of deploying the Multimodal Embedding Serving microservice using Docker, from quick starts to production-ready configurations.
