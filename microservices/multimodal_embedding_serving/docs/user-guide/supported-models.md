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
| `SigLIP/siglip-vit-b-16` | ViT-B-16 | 768 |
| `SigLIP/siglip-vit-l-16` | ViT-L-16 | 1024 |
| `SigLIP/siglip-so400m-patch14-384` | ViT-So400M | 1152 |

CLIP models with sigmoid loss function.

### BLIP-2 (Semantic Search / Retrieval)

| Model ID | Architecture | Embedding Dimension | HuggingFace Model | Handler |
|----------|-------------|-------------------|-------------------|---------|
| `Blip2/blip2_transformers` | BLIP-2 + Q-Former | 256 | `Salesforce/blip2-itm-vit-g` | Transformers |
| `Blip2/blip2_feature_extractor` | BLIP-2 + Q-Former | 256 | via LAVIS | LAVIS (legacy) |

**Transformers Handler** (recommended): Uses `Blip2ForImageTextRetrieval` from HuggingFace Transformers with projection layers (768D→256D).

**LAVIS Handler** (legacy): Uses LAVIS library for backward compatibility. Both handlers produce the same 256D embeddings.

For detailed architecture and implementation details, see [BLIP-2 Transformers Guide](blip2-transformers-embeddings.md).

## Model Configuration

Set your chosen model using environment variables:

```bash
# Example: Using BLIP-2 (Transformers)
export EMBEDDING_MODEL_NAME="Blip2/blip2_transformers"

# Example: Using BLIP-2 (LAVIS - legacy)
export EMBEDDING_MODEL_NAME="Blip2/blip2_feature_extractor"

# Example: Using CLIP
export EMBEDDING_MODEL_NAME="CLIP/clip-vit-b-16"

# Example: Using MobileCLIP
export EMBEDDING_MODEL_NAME="MobileCLIP/mobileclip_s0"

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

- **Text**: UTF-8 strings
- **Images**: JPEG, PNG, WebP, base64-encoded (and other formats supported by PIL)
- **Videos**: Any format supported by FFmpeg (MP4, AVI, MOV, etc.), base64-encoded

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

## Related Documentation

- [Get Started](get-started.md): Step-by-step deployment instructions
- [Quick Reference](quick-reference.md): Essential commands and configurations
- [SDK Usage](sdk-usage.md): Python SDK integration guide
- [Overview](Overview.md): Architecture and capabilities overview
- [BLIP-2 Transformers Guide](blip2-transformers-embeddings.md): Detailed BLIP-2 implementation guide
