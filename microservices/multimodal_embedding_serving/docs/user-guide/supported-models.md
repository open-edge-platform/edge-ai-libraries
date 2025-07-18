# Supported Models

The Multimodal Embedding Serving microservice supports multiple vision-language models for generating embeddings from text, images, and videos. This document provides the complete specification of all supported models.

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

CLIP models with sigmoid loss function for improved training.

### BLIP-2

| Model ID | Architecture | Embedding Dimension |
|----------|-------------|-------------------|
| `Blip2/blip2_feature_extractor` | BLIP-2 + ViT | 768 |
| `Blip2/blip2_transformers` | BLIP-2 + ViT | 768 |
| `Blip2/blip2_transformers_vitL` | BLIP-2 + ViT-L | 1024 |

Advanced multimodal models with Q-Former architecture.

## Model Configuration

Set your chosen model using environment variables:

```bash
export EMBEDDING_MODEL_NAME="CLIP/clip-vit-b-16"  # Replace with your chosen model
source setup.sh
```

All models support OpenVINO optimization for Intel hardware acceleration:

```bash
export EMBEDDING_USE_OV=true
export EMBEDDING_DEVICE=CPU  # or GPU
```

## Input Formats and API Compatibility

### Supported Input Formats

- **Text**: UTF-8 strings
- **Images**: JPEG, PNG, WebP, base64-encoded (and other formats supported by PIL)
- **Videos**: Any format supported by FFmpeg (MP4, AVI, MOV, FLV, WMV, MKV, VOB, WebM, etc.), base64-encoded

### API Compatibility

All models are compatible with the OpenAI embeddings API format, ensuring seamless integration with existing applications.

### Video Format Handling

The service automatically detects video formats using FFmpeg's content analysis, eliminating the need for file extensions. This provides maximum compatibility with various video container formats and codecs.

## Querying Model Information

You can query available models and their configurations via the API:

```bash
curl http://localhost:9777/model/list
```

Or get current model information:

```bash
curl http://localhost:9777/model/current
```

## Related Documentation

- [Get Started](get-started.md): Step-by-step deployment instructions
- [Quick Reference](quick-reference.md): Essential commands and configurations
- [SDK Usage](sdk-usage.md): Python SDK integration guide
- [Overview](Overview.md): Architecture and capabilities overview
