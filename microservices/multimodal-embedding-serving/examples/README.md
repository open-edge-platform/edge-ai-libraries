# Multimodal Embedding Serving Examples

This directory contains examples demonstrating how to use the Multimodal Embedding Serving microservice both as an SDK and as a server.

## Files

- `sdk_examples.py` - Examples of using the service as an SDK/library
- `server_examples.py` - Examples of using the service as a FastAPI server
- `README.md` - This file

## SDK Examples

The SDK examples show how to import and use the embedding models directly in your Python code:

### Running SDK Examples

```bash
cd /path/to/multimodal-embedding-serving
python examples/sdk_examples.py
```

### What SDK Examples Cover

1. **List Available Models** - See all supported models
2. **Basic Text Embedding** - Generate embeddings for single text
3. **Multiple Text Embeddings** - Process multiple texts at once
4. **Model Comparison** - Compare different models on same input
5. **OpenVINO Conversion** - Convert models to OpenVINO format

### SDK Usage Pattern

```python
from src.models import get_model_handler, list_available_models
from src.models.wrapper import EmbeddingModel

# Get a model handler
handler = get_model_handler("CLIP/clip-vit-b-16")
handler.load_model()

# Create wrapper for high-level operations
embedding_model = EmbeddingModel(handler)

# Generate embeddings
text_embedding = embedding_model.embed_query("A beautiful sunset")
multiple_embeddings = embedding_model.embed_documents(["text1", "text2"])
```

## Server Examples

The server examples show how to run the FastAPI server and interact with it via HTTP API:

### Running Server Examples

```bash
cd /path/to/multimodal-embedding-serving
python examples/server_examples.py
```

### Starting the Server

#### Method 1: Using uvicorn directly
```bash
export EMBEDDING_MODEL_NAME=CLIP/clip-vit-b-16
export EMBEDDING_USE_OV=false
uvicorn app:app --host 0.0.0.0 --port 8080
```

#### Method 2: Using the launcher
```bash
python launcher.py
```

### API Endpoints

Once the server is running, you can test these endpoints:

#### Health Check
```bash
curl -X GET http://localhost:8080/health
```

#### Text Embedding
```bash
curl -X POST http://localhost:8080/embed_query \
  -H "Content-Type: application/json" \
  -d '{"text": "A beautiful sunset"}'
```

#### Multiple Text Embeddings
```bash
curl -X POST http://localhost:8080/embed_documents \
  -H "Content-Type: application/json" \
  -d '{"texts": ["A dog", "A cat", "A bird"]}'
```

#### Image Embedding from URL
```bash
curl -X POST http://localhost:8080/embed_image_url \
  -H "Content-Type: application/json" \
  -d '{"image_url": "https://example.com/image.jpg"}'
```

## Supported Models

The service supports multiple model families:

### CLIP Models
- `CLIP/clip-vit-b-32`
- `CLIP/clip-vit-b-16`
- `CLIP/clip-vit-l-14`
- `CLIP/clip-vit-h-14`

### MobileCLIP Models
- `MobileCLIP/mobileclip_s0`
- `MobileCLIP/mobileclip_s1`
- `MobileCLIP/mobileclip_s2`
- `MobileCLIP/mobileclip_b`
- `MobileCLIP/mobileclip_blt`

### SigLIP Models
- `SigLIP/siglip2-vit-b-16`
- `SigLIP/siglip2-vit-l-16`
- `SigLIP/siglip2-so400m-patch16-384`

### BLIP2 Models
- `Blip2/blip2_transformers`

## Environment Variables

### Required Variables
- `EMBEDDING_MODEL_NAME` - The model to use (e.g., "CLIP/clip-vit-b-16")

### Optional Variables
- `EMBEDDING_USE_OV` - Enable OpenVINO conversion (true/false, default: false)
- `EMBEDDING_DEVICE` - Device for inference (CPU/GPU, default: CPU)
- `EMBEDDING_OV_MODELS_DIR` - Directory for OpenVINO models (default: ./ov-models)

## Model Switching Examples

### Switch to MobileCLIP
```bash
export EMBEDDING_MODEL_NAME=MobileCLIP/mobileclip_s0
```

### Enable OpenVINO
```bash
export EMBEDDING_MODEL_NAME=CLIP/clip-vit-b-16
export EMBEDDING_USE_OV=true
export EMBEDDING_OV_MODELS_DIR=./ov-models
```

### Use SigLIP
```bash
export EMBEDDING_MODEL_NAME=SigLIP/siglip2-vit-b-16
```

## Dependencies

### For SDK Usage
```bash
pip install torch transformers pillow numpy
```

### For OpenVINO Support
```bash
pip install openvino
```

### For Server Usage
```bash
pip install fastapi uvicorn
```

## Docker Usage

### Build and Run
```bash
# Build image
docker build -t multimodal-embedding-serving .

# Run with CLIP
docker run -p 8080:8080 \
  -e EMBEDDING_MODEL_NAME=CLIP/clip-vit-b-16 \
  multimodal-embedding-serving

# Run with OpenVINO
docker run -p 8080:8080 \
  -e EMBEDDING_MODEL_NAME=CLIP/clip-vit-b-16 \
  -e EMBEDDING_USE_OV=true \
  -v $(pwd)/ov-models:/app/ov-models \
  multimodal-embedding-serving
```

## Performance Tips

1. **Model Selection**: MobileCLIP models are smaller and faster than CLIP models
2. **OpenVINO**: Enable for better CPU performance on Intel hardware
3. **Device Selection**: Use GPU if available for larger models
4. **Batch Processing**: Use `embed_documents` for multiple texts

## Troubleshooting

### Import Errors
Make sure you're running from the correct directory and have all dependencies installed.

### Model Loading Errors
Check that the model name is correct and supported. Use `list_available_models()` to see all options.

### OpenVINO Conversion Errors
Ensure OpenVINO is properly installed and you have write permissions to the models directory.

### Server Not Starting
Check that the port 8080 is not already in use and that all environment variables are set correctly.
