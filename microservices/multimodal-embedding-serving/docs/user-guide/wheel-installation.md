# Wheel-Based Installation Guide

This guide shows how to build and install the Multimodal Embedding Serving microservice as a Python wheel package for use in your projects.

## Overview

Installing via wheel provides:
- **Clean installation** - No source code clutter in your project
- **Version control** - Lock to specific versions
- **Production ready** - Proper packaging for deployment
- **Easy distribution** - Share with team members
- **Dependency management** - Handles all requirements automatically

## Quick Start

### 1. Build the Wheel

Navigate to the microservice directory and build:

```bash
cd multimodal-embedding-serving
poetry build
```

This creates:
- `dist/multimodal_embedding_serving-0.1.1-py3-none-any.whl` (wheel file)
- `dist/multimodal_embedding_serving-0.1.1.tar.gz` (source distribution)

### 2. Install in Your Project

Choose one of the following methods:

#### Method A: Direct pip Install

```bash
pip install dist/multimodal_embedding_serving-0.1.1-py3-none-any.whl
```

#### Method B: Poetry Project (Recommended)

1. Copy the wheel to your project:
```bash
mkdir -p /path/to/your-project/wheels
cp dist/multimodal_embedding_serving-0.1.1-py3-none-any.whl /path/to/your-project/wheels/
```

2. Add to your `pyproject.toml`:
```toml
[tool.poetry.dependencies]
python = "^3.8"
multimodal-embedding-serving = {path = "wheels/multimodal_embedding_serving-0.1.1-py3-none-any.whl"}
```

3. Install:
```bash
poetry install
```

#### Method C: pip requirements.txt

Add to your `requirements.txt`:
```text
multimodal_embedding_serving @ file:///path/to/wheels/multimodal_embedding_serving-0.1.1-py3-none-any.whl
```

Then install:
```bash
pip install -r requirements.txt
```

### 3. Use in Your Code

```python
from multimodal_embedding_serving import get_model_handler, EmbeddingModel

# Create and load a model
handler = get_model_handler("CLIP/clip-vit-b-16")
handler.load_model()

# Create application wrapper
embedding_model = EmbeddingModel(handler)

# Generate embeddings
text = "A beautiful sunset over the ocean"
embedding = embedding_model.embed_query(text)
print(f"Embedding dimension: {len(embedding)}")
```

## Common Use Cases

### Use Case 1: Microservice Integration

```python
# your_service/main.py
from fastapi import FastAPI
from multimodal_embedding_serving import get_model_handler, EmbeddingModel

app = FastAPI()
embedding_model = None

@app.on_event("startup")
async def startup():
    global embedding_model
    handler = get_model_handler("CLIP/clip-vit-b-16", use_openvino=True)
    handler.load_model()
    embedding_model = EmbeddingModel(handler)

@app.post("/embed")
async def embed(text: str):
    return {"embedding": embedding_model.embed_query(text)}
```

### Use Case 2: Data Processing Pipeline

```python
# pipeline/embedding_stage.py
from multimodal_embedding_serving import get_model_handler, EmbeddingModel
import pandas as pd

class EmbeddingProcessor:
    def __init__(self, model_name="CLIP/clip-vit-b-16"):
        handler = get_model_handler(model_name)
        handler.load_model()
        self.model = EmbeddingModel(handler)
    
    def process_batch(self, texts):
        return self.model.embed_documents(texts)

# Usage
processor = EmbeddingProcessor()
df['embeddings'] = processor.process_batch(df['text'].tolist())
```

### Use Case 3: Research Notebook

```python
# notebook.ipynb
from multimodal_embedding_serving import get_model_handler, EmbeddingModel
import numpy as np

# Load model with OpenVINO for faster inference
handler = get_model_handler(
    "QwenText/qwen3-embedding-0.6b",
    use_openvino=True,
    device="GPU"
)
handler.load_model()
model = EmbeddingModel(handler)

# Experiment with different texts
queries = ["quantum computing", "machine learning", "data science"]
embeddings = model.embed_documents(queries)

# Analyze similarity
from sklearn.metrics.pairwise import cosine_similarity
similarity_matrix = cosine_similarity(embeddings)
```

## Version Management

### Pinning to Specific Version

In `pyproject.toml`:
```toml
[tool.poetry.dependencies]
multimodal-embedding-serving = {path = "wheels/multimodal_embedding_serving-0.1.1-py3-none-any.whl"}
```

### Upgrading

1. Build new version:
```bash
cd multimodal-embedding-serving
# Update version in pyproject.toml if needed
poetry build
```

2. Copy new wheel to your project:
```bash
cp dist/multimodal_embedding_serving-0.1.2-py3-none-any.whl /path/to/your-project/wheels/
```

3. Update `pyproject.toml`:
```toml
multimodal-embedding-serving = {path = "wheels/multimodal_embedding_serving-0.1.2-py3-none-any.whl"}
```

4. Reinstall:
```bash
poetry install
```

## Troubleshooting

### Issue: Module not found after installation

**Solution:** Verify installation:
```bash
pip list | grep multimodal-embedding-serving
# or
poetry show multimodal-embedding-serving
```

### Issue: Import errors

**Solution:** Check Python path:
```python
import sys
print(sys.path)

import multimodal_embedding_serving
print(multimodal_embedding_serving.__file__)
```

### Issue: Version conflicts

**Solution:** Use virtual environment:
```bash
# Create clean environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install wheel
pip install multimodal_embedding_serving-0.1.1-py3-none-any.whl
```

## Best Practices

1. **Version Control**: Track the wheel in version control or artifact repository
2. **Virtual Environments**: Always use virtual environments for clean installations
3. **Dependency Locking**: Use poetry.lock or requirements.txt to lock all dependencies
4. **Testing**: Test wheel installation in CI/CD before deployment
5. **Documentation**: Document which wheel version your project uses

## Related Documentation

- [SDK Usage Guide](sdk-usage.md) - Complete SDK usage examples
- [API Reference](api-reference.md) - Detailed API documentation
- [Supported Models](supported-models.md) - Available embedding models
