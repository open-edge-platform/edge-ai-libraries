# Overview

The Multimodal Embedding Serving microservice provides a scalable and efficient solution for generating multimodal embeddings from text, images, and videos. Built on state-of-the-art vision-language models, it enables applications to perform cross-modal search, retrieval, and similarity tasks through a simple, production-ready service.

## Architecture

The microservice is designed as a RESTful API service that:

- Accepts text, image, and video inputs through OpenAI-compatible endpoints
- Loads and manages multiple vision-language models dynamically
- Provides hardware-accelerated inference using OpenVINO for Intel hardware
- Returns high-dimensional embeddings in a shared semantic space
- Supports both synchronous and batch processing workflows

## Model Support

The service supports multiple model families:

- **CLIP**: General-purpose vision-language understanding
- **CN-CLIP**: Chinese-optimized models for multilingual applications  
- **MobileCLIP**: Lightweight models for mobile and edge deployment
- **SigLIP**: Models with sigmoid loss function
- **BLIP-2**: Advanced multimodal models with Q-Former architecture

For complete model specifications, see [Supported Models](supported-models.md).

## Key Capabilities

- **OpenAI-Compatible API**: Standard embeddings API format for seamless integration
- **Multi-Modal Processing**: Handle text, images (URL/base64), and videos (URL/base64/file)
- **Hardware Optimization**: CPU and GPU support with OpenVINO acceleration
- **Video Processing**: Advanced frame extraction with configurable sampling strategies
- **Production Features**: Health checks, monitoring, logging, and scalability

## Deployment Architecture

The microservice can be deployed in multiple configurations:

- **Docker Containers**: Single-node deployment using Docker Compose
- **Kubernetes**: Multi-node scalable deployment
- **Python SDK**: Direct integration into Python applications

The same container image supports both CPU and GPU deployments through runtime configuration.

## Supporting Resources

- [Get Started Guide](get-started.md) - Step-by-step deployment instructions
- [Quick Reference](quick-reference.md) - Essential commands and API examples
- [SDK Usage Guide](sdk-usage.md) - Python SDK integration examples
- [Supported Models](supported-models.md) - Complete model list and specifications
- [API Reference](api-reference.md) - Complete REST API documentation
- [System Requirements](system-requirements.md) - Hardware and software prerequisites
