# SDK Usage Guide

This guide shows you how to use the Multimodal Embedding Serving microservice as a Python SDK for embedding text, images, and videos in your applications. The SDK provides a convenient wrapper around the REST API for seamless integration.

> **Model Selection**: The examples in this guide use placeholder model names (`"your-chosen-model"`). Replace these with a specific model from [Supported Models](supported-models.md) based on your requirements.

## Installation

### Option 1: Install from Wheel (Recommended for Production)

Build and install the microservice as a wheel package for clean, production-ready integration.

> **📖 Comprehensive Guide**: See [Wheel-Based Installation Guide](wheel-installation.md) for detailed instructions on building, installing, distributing, and troubleshooting wheel installations.

**Quick Install:**

```bash
# 1. Build the wheel
cd multimodal-embedding-serving
poetry build

# 2. Install in your project
pip install dist/multimodal_embedding_serving-0.1.1-py3-none-any.whl

# OR add to pyproject.toml (recommended)
# [tool.poetry.dependencies]
# multimodal-embedding-serving = {path = "wheels/multimodal_embedding_serving-0.1.1-py3-none-any.whl"}
```

### Option 2: Install from Source (Development)

```bash
git clone https://github.com/intel/edge-ai-libraries -b release-2025.2.0
cd edge-ai-libraries/microservices/multimodal-embedding-serving
pip install -e .
```

### Option 3: Using Poetry for Development

```bash
cd multimodal-embedding-serving
poetry install
poetry shell
```

## Quick Start

### 1. Basic SDK Usage

```python
# Import from the installed package
from multimodal_embedding_serving import get_model_handler, EmbeddingModel

# Create and load a model (replace with your chosen model from supported-models.md)
model_handler = get_model_handler("your-chosen-model")
model_handler.load_model()

# Create the application wrapper
embedding_model = EmbeddingModel(model_handler)

# Test the model
print("Model loaded successfully!")
print(f"Embedding dimension: {embedding_model.get_embedding_length()}")
```

### 2. Text Embeddings

```python
# Single text embedding
text = "A beautiful sunset over the mountains"
embedding = embedding_model.embed_query(text)
print(f"Text embedding shape: {len(embedding)}")

# Multiple text embeddings
texts = [
    "A red car driving down the road",
    "A blue ocean with white waves",
    "A green forest in spring"
]
embeddings = embedding_model.embed_documents(texts)
print(f"Batch embeddings shape: {len(embeddings)}x{len(embeddings[0])}")
```

> **Text-only models**: Qwen text embeddings expose only the text encoder. Use the `/model/capabilities` endpoint or `embedding_model.get_supported_modalities()` to confirm modality support before invoking image/video helpers.

#### Qwen text embeddings with OpenVINO INT8

```python
from multimodal_embedding_serving import get_model_handler, EmbeddingModel

handler = get_model_handler(
    "QwenText/qwen3-embedding-0.6b",
    device="GPU",  # or CPU / AUTO
    use_openvino=True,
    ov_models_dir="./ov-models"
)
handler.load_model()

embedding_model = EmbeddingModel(handler)
print(embedding_model.get_supported_modalities())  # ['text']

query = "How does photosynthesis work?"
embedding = embedding_model.embed_query(query)
print(len(embedding))
```

### 3. Image Embeddings

> Image helpers require a model with image modality support (e.g., CLIP, MobileCLIP, SigLIP, BLIP-2). They are not available when a text-only model such as Qwen is active.

#### From URL

```python
import asyncio

async def process_image_url():
    image_url = "https://example.com/image.jpg"
    embedding = await embedding_model.get_image_embedding_from_url(image_url)
    print(f"Image embedding shape: {len(embedding)}")

# Run async function
asyncio.run(process_image_url())
```

#### From Base64

```python
import base64
from PIL import Image
import io

# Convert image to base64
image = Image.new('RGB', (224, 224), color='red')
buffer = io.BytesIO()
image.save(buffer, format='JPEG')
image_base64 = base64.b64encode(buffer.getvalue()).decode()

# Get embedding
embedding = embedding_model.get_image_embedding_from_base64(image_base64)
print(f"Image embedding shape: {len(embedding)}")
```

### 4. Video Embeddings

> Video helpers rely on image encoders under the hood; ensure the active model advertises video support via `embedding_model.supports_video()`.

#### From_URL

```python
async def process_video_url():
    video_url = "https://example.com/video.mp4"

    # Basic video processing
    frame_embeddings = await embedding_model.get_video_embedding_from_url(video_url)
    print(f"Video frame embeddings: {len(frame_embeddings)} frames")

    # With custom segment configuration
    segment_config = {
        "startOffsetSec": 10,
        "clip_duration": 30,
        "num_frames": 16
    }
    frame_embeddings = await embedding_model.get_video_embedding_from_url(
        video_url, segment_config
    )
    print(f"Custom video embeddings: {len(frame_embeddings)} frames")

asyncio.run(process_video_url())
```

#### From Local File

```python
async def process_local_video():
    video_path = "/path/to/your/video.mp4"

    # Advanced frame sampling options
    segment_config = {
        "fps": 2.0,  # Extract 2 frames per second
        "startOffsetSec": 0,
        "clip_duration": -1  # Process entire video
    }

    frame_embeddings = await embedding_model.get_video_embedding_from_file(
        video_path, segment_config
    )
    print(f"Local video embeddings: {len(frame_embeddings)} frames")

asyncio.run(process_local_video())
```

#### Using Specific Frame Indices

```python
segment_config = {
    "frame_indexes": [0, 15, 30, 45, 60],  # Extract specific frames
    "startOffsetSec": 5,
    "clip_duration": 20
}

frame_embeddings = await embedding_model.get_video_embedding_from_file(
    "video.mp4", segment_config
)
```

## Advanced Configuration

### 1. Using Different Models

```python
from multimodal_embedding_serving import get_model_handler, EmbeddingModel

# Standard CLIP
clip_handler = get_model_handler("your-chosen-model")
clip_model = EmbeddingModel(clip_handler)

# Chinese CLIP for multilingual support
cn_clip_handler = get_model_handler("CN-CLIP/cn-clip-vit-b-16")
cn_clip_model = EmbeddingModel(cn_clip_handler)

# Mobile-optimized CLIP
mobile_handler = get_model_handler("MobileCLIP/mobileclip_b")
mobile_model = EmbeddingModel(mobile_handler)

# BLIP-2 for advanced multimodal understanding
blip2_handler = get_model_handler("Blip2/blip2_transformers")
blip2_model = EmbeddingModel(blip2_handler)
```

### 2. OpenVINO Optimization

```python
from multimodal_embedding_serving import get_model_handler, EmbeddingModel

# Enable OpenVINO for faster inference
model_handler = get_model_handler(
    model_id="your-chosen-model",
    device="CPU",
    use_openvino=True,
    ov_models_dir="./ov-models"
)
model_handler.load_model()
embedding_model = EmbeddingModel(model_handler)
```

### 3. GPU Acceleration (if available)

```python
from multimodal_embedding_serving import get_model_handler

# Use GPU for inference
model_handler = get_model_handler(
    model_id="your-chosen-model",
    device="GPU"
)
```

## Practical Examples

### 1. Image-Text Similarity

```python
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

# Get embeddings
text_embedding = embedding_model.embed_query("A red sports car")
image_embedding = await embedding_model.get_image_embedding_from_url(
    "https://example.com/red_car.jpg"
)

# Calculate similarity
similarity = cosine_similarity(
    [text_embedding],
    [image_embedding]
)[0][0]
print(f"Similarity: {similarity:.3f}")
```

### 2. Video Content Search

```python
async def search_video_content():
    # Process video to get frame embeddings
    video_embeddings = await embedding_model.get_video_embedding_from_file(
        "movie.mp4",
        {"fps": 0.5, "clip_duration": -1}  # 1 frame every 2 seconds
    )

    # Search query
    query = "person walking in a park"
    query_embedding = embedding_model.embed_query(query)

    # Find most similar frames
    similarities = []
    for i, frame_emb in enumerate(video_embeddings):
        sim = cosine_similarity([query_embedding], [frame_emb])[0][0]
        similarities.append((i, sim))

    # Get top 5 matches
    top_matches = sorted(similarities, key=lambda x: x[1], reverse=True)[:5]

    for frame_idx, similarity in top_matches:
        timestamp = frame_idx * 2  # Since we used 0.5 fps
        print(f"Frame {frame_idx} (t={timestamp}s): {similarity:.3f}")

asyncio.run(search_video_content())
```

### 3. Multilingual Text Processing

```python
from multimodal_embedding_serving import get_model_handler, EmbeddingModel

# Using CN-CLIP for Chinese text
cn_clip_handler = get_model_handler("CN-CLIP/cn-clip-vit-b-16")
cn_clip_handler.load_model()
cn_model = EmbeddingModel(cn_clip_handler)

# Process Chinese and English text
texts = [
    "一只可爱的小猫",  # Chinese: "A cute little cat"
    "A beautiful landscape",
    "红色的汽车",  # Chinese: "Red car"
    "Blue ocean waves"
]

embeddings = cn_model.embed_documents(texts)
print(f"Multilingual embeddings: {len(embeddings)} texts processed")
```

### 4. Batch Processing for Efficiency

```python
async def batch_process_images():
    image_urls = [
        "https://example.com/image1.jpg",
        "https://example.com/image2.jpg",
        "https://example.com/image3.jpg"
    ]

    # Process images concurrently
    import asyncio
    tasks = [
        embedding_model.get_image_embedding_from_url(url)
        for url in image_urls
    ]

    embeddings = await asyncio.gather(*tasks)
    print(f"Processed {len(embeddings)} images")

    return embeddings

asyncio.run(batch_process_images())
```

## Error Handling

```python
from multimodal_embedding_serving import get_model_handler, EmbeddingModel

try:
    # Load model with error handling
    model_handler = get_model_handler("your-chosen-model")
    model_handler.load_model()
    embedding_model = EmbeddingModel(model_handler)

    # Check if model is healthy
    if embedding_model.check_health():
        print("Model is ready!")
    else:
        print("Model health check failed")

except Exception as e:
    print(f"Failed to load model: {e}")

try:
    # Process with error handling
    embedding = embedding_model.embed_query("test text")
    print("Text processed successfully")
except Exception as e:
    print(f"Processing failed: {e}")
```

## Configuration Options

### Model Selection

See [Supported Models](supported-models.md) for all available models and their specifications.

```python
from multimodal_embedding_serving import get_model_handler

# Example: Using different models
clip_handler = get_model_handler("your-chosen-model")
cn_clip_handler = get_model_handler("CN-CLIP/cn-clip-vit-b-16")
mobile_handler = get_model_handler("MobileCLIP/mobileclip_b")
```

### OpenVINO Optimization

```python
from multimodal_embedding_serving import get_model_handler

# Enable OpenVINO for Intel hardware acceleration
model_handler = get_model_handler(
    "your-chosen-model",
    use_openvino=True
)
```

### Batch Processing

```python
# Process multiple texts for better throughput
embeddings = embedding_model.embed_documents(text_batch)
```

## Integration Examples

### 1. Flask Web Application

```python
from flask import Flask, request, jsonify
from multimodal_embedding_serving import get_model_handler, EmbeddingModel
import asyncio

app = Flask(__name__)

# Initialize model globally
model_handler = get_model_handler("your-chosen-model")
model_handler.load_model()
embedding_model = EmbeddingModel(model_handler)

@app.route('/embed', methods=['POST'])
def embed_text():
    data = request.json
    text = data.get('text', '')

    try:
        embedding = embedding_model.embed_query(text)
        return jsonify({'embedding': embedding})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
```

### 2. FastAPI Integration

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from multimodal_embedding_serving import get_model_handler, EmbeddingModel

app = FastAPI()

class TextRequest(BaseModel):
    text: str

@app.on_event("startup")
async def startup_event():
    global embedding_model
    model_handler = get_model_handler("your-chosen-model")
    model_handler.load_model()
    embedding_model = EmbeddingModel(model_handler)

@app.post("/embed")
async def embed_text(request: TextRequest):
    try:
        embedding = embedding_model.embed_query(request.text)
        return {"embedding": embedding}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

## Troubleshooting

### Common Issues

1. **Model Loading Errors**

   ```python
   # Check available models
   from multimodal_embedding_serving import list_available_models
   print(list_available_models())
   ```

2. **Memory Issues**

   ```python
   # Use smaller models for limited memory
   from multimodal_embedding_serving import get_model_handler
   model_handler = get_model_handler("MobileCLIP/mobileclip_s0")
   ```

3. **OpenVINO Issues**

   ```python
   # Disable OpenVINO if having issues
   from multimodal_embedding_serving import get_model_handler
   model_handler = get_model_handler(
       "your-chosen-model",
       use_openvino=False
   )
   ```

### Getting Help

- Check the [API Reference](api-reference.md) for detailed endpoint documentation
- See [Supported Models](supported-models.md) for model selection guidance
- Review system requirements in [System Requirements](system-requirements.md)
