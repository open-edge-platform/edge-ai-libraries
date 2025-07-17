# Multimodal Embedding Serving Microservice

A CLIP-based Multimodal Embedding Serving microservice enables seamless integration of multimodal understanding into applications by exposing CLIP’s capabilities through OpenAI compliant API. The microservice accepts videos, images and text as input, returning high-dimensional embeddings that capture their semantic content in a shared space. This allows developers to build features such as cross-modal retrieval, visual search, and content recommendation with minimal effort. 

The microservice is optimized for performance and scalability, supporting batch processing and deployment on both cloud and edge environments. By abstracting the complexity of model management and inference, the microservice accelerates the adoption of advanced vision-language AI in diverse use cases.

## Documentation

- **Overview**
  - [Overview](docs/user-guide/Overview.md): A high-level introduction to the microservice.

- **Getting Started**
  - [Get Started](docs/user-guide/get-started.md): Step-by-step guide to getting started with the microservice.
  - [System Requirements](docs/user-guide/system-requirements.md): Hardware and software requirements for running the microservice.

- **Deployment**
  - [How to Build from Source](docs/user-guide/how-to-build-from-source.md): Instructions for building the microservice from source code.
  
- **API Reference**
  - [API Reference](docs/user-guide/api-reference.md): Comprehensive reference for the available REST API endpoints.

- **Release Notes**
  - [Release Notes](docs/user-guide/release-notes.md): Information on the latest updates, improvements, and bug fixes.

## BLIP2 Implementation

This microservice includes two BLIP2 implementations:

### Original LAVIS-based Implementation
- Model ID: `Blip2/blip2_feature_extractor`
- May encounter vocabulary size mismatch issues

### New Transformers-based Implementation (Recommended)
- Model ID: `Blip2/blip2_transformers` or `Blip2/blip2_transformers_vitL`
- Resolves vocabulary size mismatch issues
- Uses the standardized Transformers library
- Full OpenVINO support

**For users experiencing vocabulary size mismatch errors with BLIP2, please use the new Transformers-based implementation.**

See [BLIP2_TRANSFORMERS_SOLUTION.md](BLIP2_TRANSFORMERS_SOLUTION.md) for detailed information.

## Quick Test

Test the new BLIP2 implementation:
```bash
python compare_blip2_implementations.py
python examples/blip2_transformers_example.py
```


