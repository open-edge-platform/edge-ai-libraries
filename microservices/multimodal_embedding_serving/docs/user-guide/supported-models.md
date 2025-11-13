# Supported Models

The Multimodal Embedding Serving microservice supports multiple vision-language models for generating embeddings from text, images, and videos.

## Available Models

### CLIP (Contrastive Language-Image Pretraining)

| Model ID | Architecture | Embedding Dimension |
|----------|-------------|-------------------|
| `CLIP/clip-vit-b-32` | ViT-B-32 | 512 |
| `CLIP/clip-vit-b-16` | ViT-B-16 | 512 |
| `CLIP/clip-vit-l-14` | ViT-L-14 | 768 |
| `CLIP/clip-vit-h-14` | ViT-H-14 | 1024 |

Standard OpenAI CLIP models for general-purpose vision-language understanding.

### CN-CLIP (Chinese CLIP)

| Model ID | Architecture | Embedding Dimension |
|----------|-------------|-------------------|
| `CN-CLIP/cn-clip-vit-b-16` | ViT-B-16 | 512 |
| `CN-CLIP/cn-clip-vit-l-14` | ViT-L-14 | 768 |
| `CN-CLIP/cn-clip-vit-h-14` | ViT-H-14 | 1024 |

Chinese-optimized CLIP models supporting both Chinese and English text.

### MobileCLIP

| Model ID | Architecture | Embedding Dimension |
|----------|-------------|-------------------|
| `MobileCLIP/mobileclip_s0` | MobileCLIP-S0 | 512 |
| `MobileCLIP/mobileclip_s1` | MobileCLIP-S1 | 512 |
| `MobileCLIP/mobileclip_s2` | MobileCLIP-S2 | 512 |
| `MobileCLIP/mobileclip_b` | MobileCLIP-B | 512 |
| `MobileCLIP/mobileclip_blt` | MobileCLIP-BLT | 512 |

Lightweight CLIP models designed for mobile and edge deployment.

### SigLIP

| Model ID | Architecture | Embedding Dimension |
|----------|-------------|-------------------|
| `SigLIP/siglip2-vit-b-16` | ViT-B-16 | 768 |
| `SigLIP/siglip2-vit-l-16` | ViT-L-16 | 1024 |
| `SigLIP/siglip2-so400m-patch16-384` | ViT-So400M | 1152 |

CLIP models with sigmoid loss function.

### BLIP-2 (Semantic Search / Retrieval)

| Model ID | Architecture | Embedding Dimension | HuggingFace Model | Handler |
|----------|-------------|-------------------|-------------------|---------|
| `Blip2/blip2_transformers` | BLIP-2 + Q-Former | 256 | `Salesforce/blip2-itm-vit-g` | Transformers |

The BLIP-2 handler uses `Blip2ForImageTextRetrieval` from HuggingFace Transformers with projection layers (768D→256D) to generate compact embeddings.

For detailed architecture and implementation details, see [BLIP-2 Transformers Guide](blip2-transformers-embeddings.md).

### Qwen Text Embeddings

| Model ID | Hugging Face Repo | Embedding Dimension | Precision | Notes |
|----------|-------------------|---------------------|-----------|-------|
| `QwenText/qwen3-embedding-0.6b` | `Qwen/Qwen3-Embedding-0.6B` | 1024 | INT8 | Text-only, instruction-aware,  Context Length: 32k |
| `QwenText/qwen3-embedding-4b` | `Qwen/Qwen3-Embedding-4B` | 2560 | INT8 | Text-only, instruction-aware, Context Length: 32k |
| `QwenText/qwen3-embedding-8b` | `Qwen/Qwen3-Embedding-8B` | 4096 | INT8 | Text-only, instruction-aware, Context Length: 32k |

The Qwen text embedding handler provides high-quality multilingual embeddings optimised with OpenVINO. These models:

- Are **text-only** and do not expose image or video encoders.
- Automatically wrap queries using the recommended instruction template (`"Instruct: {task_description}\nQuery:{query}"`).
- Convert to OpenVINO INT8 format on first use and store compiled artifacts under the configured `EMBEDDING_OV_MODELS_DIR`.
- Require `trust_remote_code=true` (handled by the factory).
- Support Intel GPU execution via OpenVINO.

Use the `/model/capabilities` endpoint to inspect which modalities the currently loaded model supports.

## Model Configuration

Set your chosen model using environment variables:

```bash
# Example: Using BLIP-2 (Transformers)
export EMBEDDING_MODEL_NAME="Blip2/blip2_transformers"

# Example: Using CLIP
export EMBEDDING_MODEL_NAME="CLIP/clip-vit-b-16"

# Example: Using MobileCLIP
export EMBEDDING_MODEL_NAME="MobileCLIP/mobileclip_s0"

# Example: Using Qwen text embeddings (INT8 OpenVINO)
export EMBEDDING_MODEL_NAME="QwenText/qwen3-embedding-0.6b"
export EMBEDDING_USE_OV=true
export EMBEDDING_DEVICE=GPU  # or CPU/AUTO
export EMBEDDING_OV_MODELS_DIR=/app/ov_models

source setup.sh
```

All models support OpenVINO optimization for Intel hardware acceleration:

```bash
export EMBEDDING_USE_OV=true
export EMBEDDING_DEVICE=CPU  # or GPU
```

## OpenVINO Conversion Support

The service supports automatic OpenVINO conversion for all models. The conversion process automatically detects whether a model has HuggingFace Hub support and uses the appropriate conversion method.

## Supported Input Formats

- **Text**: UTF-8 strings (available for all models)
- **Images**: JPEG, PNG, WebP, base64-encoded (and other formats supported by PIL). _Not available for Qwen text-only models._
- **Videos**: Any format supported by FFmpeg (MP4, AVI, MOV, etc.), base64-encoded. _Not available for Qwen text-only models._

All models are compatible with the OpenAI embeddings API format.

## API Usage

Query available models:

```bash
curl http://localhost:9777/model/list
```

Get current model information:

```bash
curl http://localhost:9777/model/current
```

Inspect modality support for the active model:

```bash
curl http://localhost:9777/model/capabilities
```

## Related Documentation

- [Get Started](get-started.md): Step-by-step deployment instructions
- [Quick Reference](quick-reference.md): Essential commands and configurations
- [SDK Usage](sdk-usage.md): Python SDK integration guide
- [Overview](Overview.md): Architecture and capabilities overview
- [BLIP-2 Transformers Guide](blip2-transformers-embeddings.md): Detailed BLIP-2 implementation guide
