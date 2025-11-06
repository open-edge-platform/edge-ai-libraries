# Multimodal Embedding Serving Microservice

A multimodal embedding microservice that enables seamless integration of vision-language understanding into applications through OpenAI-compliant APIs. The microservice supports multiple state-of-the-art models including CLIP, CN-CLIP, MobileCLIP, SigLIP, BLIP-2, and Qwen text embeddings, accepting modality-appropriate inputs and returning high-dimensional embeddings that capture their semantic content in a shared space.

The microservice is optimized for performance and scalability, supporting batch processing and deployment on both cloud and edge environments. By abstracting the complexity of model management and inference, the microservice accelerates the adoption of advanced vision-language AI in diverse use cases.

## Documentation

- **Overview**
  - [Overview](docs/user-guide/Overview.md): A high-level introduction to the microservice architecture and capabilities.

- **Getting Started**
  - [Get Started](docs/user-guide/get-started.md): Step-by-step guide to getting started with the microservice.
  - [Quick Reference](docs/user-guide/quick-reference.md): Essential commands and configurations at a glance.
  - [System Requirements](docs/user-guide/system-requirements.md): Hardware and software requirements for running the microservice.

- **Usage**
  - [SDK Usage](docs/user-guide/sdk-usage.md): Complete guide for using the service as a Python SDK.
  - [Wheel Installation](docs/user-guide/wheel-installation.md): Comprehensive guide for building and installing as a Python wheel package.
  - [Supported Models](docs/user-guide/supported-models.md): Complete list of supported models and their configurations.
  - [`/model/capabilities` endpoint](docs/user-guide/api-reference.md): Discover modality support for the loaded model.
  
- **Deployment**
  - [How to Build from Source](docs/user-guide/how-to-build-from-source.md): Instructions for building the microservice from source code.
  
- **API Reference**
  - [API Reference](docs/user-guide/api-reference.md): Comprehensive reference for the available REST API endpoints.

- **Release Notes**
  - [Release Notes](docs/user-guide/release-notes.md): Information on the latest updates, improvements, and bug fixes.

See [Get Started](docs/user-guide/get-started.md) for detailed setup instructions.
