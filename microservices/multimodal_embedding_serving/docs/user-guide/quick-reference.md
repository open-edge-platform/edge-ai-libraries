# Quick Reference

Essential commands and configurations for the Multimodal Embedding Serving microservice.

## 🚀 Quick Start

### Using setup.sh (Recommended)

```bash
git clone https://github.com/intel/edge-ai-libraries.git
cd edge-ai-libraries/microservices/multimodal_embedding_serving

# REQUIRED: Set your model choice
export EMBEDDING_MODEL_NAME="your-chosen-model"  # See supported-models.md
source setup.sh

docker compose -f docker/compose.yaml up -d
```

### Direct Docker

```bash
docker run -d -p 9777:9777 -e EMBEDDING_MODEL_NAME="your-chosen-model" intel/multimodal-embedding-serving:latest
```

## 🔧 Environment Variables

### Essential Configuration

```bash
export EMBEDDING_MODEL_NAME="your-chosen-model"    # REQUIRED - See supported-models.md
export EMBEDDING_DEVICE="CPU"                       # CPU or GPU
export EMBEDDING_USE_OV="true"                      # Enable OpenVINO
```

### Optional Configuration

```bash
export EMBEDDING_OV_MODELS_DIR="./ov-models"       # OpenVINO cache directory
export DEFAULT_NUM_FRAMES=32                        # Video frame extraction
export DEFAULT_CLIP_DURATION=60                     # Video segment length (seconds)
```

## 🌐 API Examples

### Health Check

```bash
curl http://localhost:9777/health
```

### Text Embedding

```bash
curl -X POST http://localhost:9777/embeddings \
  -H "Content-Type: application/json" \
  -d '{
    "input": {"type": "text", "text": ["Hello world"]},
    "model": "'$EMBEDDING_MODEL_NAME'"
  }'
```

### Image Embedding

```bash
curl -X POST http://localhost:9777/embeddings \
  -H "Content-Type: application/json" \
  -d '{
    "input": {"type": "image_url", "image_url": "https://example.com/image.jpg"},
    "model": "'$EMBEDDING_MODEL_NAME'"
  }'
```

### Video Embedding

```bash
curl -X POST http://localhost:9777/embeddings \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "type": "video_url", 
      "video_url": "https://example.com/video.mp4",
      "segment_config": {"fps": 2.0, "clip_duration": 30}
    },
    "model": "'$EMBEDDING_MODEL_NAME'"
  }'
```

## Docker Compose

```yaml
version: '3.8'
services:
  embedding-service:
    image: intel/multimodal-embedding-serving:latest
    ports:
      - "9777:9777"
    environment:
      - EMBEDDING_MODEL_NAME=your-chosen-model
      - EMBEDDING_USE_OV=true
    volumes:
      - ./ov-models:/app/ov-models
    restart: unless-stopped
```

## 🔍 Troubleshooting

### Check Service Status

```bash
curl http://localhost:9777/health                    # Health check
curl http://localhost:9777/model/current            # Current model info
docker logs multimodal-embedding-serving            # Container logs
```

### Common Issues

```bash
# Model loading failed - check available models
curl http://localhost:9777/model/list

# Container won't start - check logs
docker logs multimodal-embedding-serving

# Port already in use
netstat -tulpn | grep 9777
```

## 📚 Documentation Links

- [📖 Supported Models](supported-models.md) - Complete model list and specifications
- [🚀 Get Started Guide](get-started.md) - Step-by-step deployment instructions  
- [🐍 SDK Usage Guide](sdk-usage.md) - Python SDK integration examples
- [🔌 API Reference](api-reference.md) - Complete REST API documentation
- [🏗️ Build from Source](how-to-build-from-source.md) - Development and customization
- [⚙️ System Requirements](system-requirements.md) - Hardware and software requirements
