# Release Notes

## Current Release

**Version**: 1.3.1 \
**Release Date**: 20 Nov 2025  

**Features**:

- Fixed dependent package vulnerabilities.

**HW used for validation**:

- Intel® Xeon® 5 + Intel® Arc&trade; B580 GPU
- Vanilla Kubernetes Cluster

## Previous Releases

**Version**: 1.3.0 \
**Release Date**: 14 Nov 2025  

**Features**:

- Implemented CLIP, CN-CLIP, MobileCLIP, SigLIP2, and BLIP2 model handlers to support by OpenVINO support.
- Added model registry and factory pattern for creating model handlers based on configuration.
- Introduced text-only Qwen3-embedding model family support.
- Enabled dual runtime support: models can run using native PyTorch or OpenVINO runtime.
- Microservice supports both API and SDK modes of operation for flexible integration.
- Implemented utility functions for embedding text and images with support for base64 and URL inputs.
- Created application-level EmbeddingModel class for high-level functionality, including video processing.

## Releases 1.2.0, 1.2.1, 1.2.2 and 1.2.3

This microservice supports features based on the requirements of Video Search and Summarization sample application which is using this microservice. Refer to Video Search and Summarization [release notes](../../../../sample-applications/video-search-and-summarization/docs/user-guide/release-notes.md) for release details of this microservice.
