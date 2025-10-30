# Release Notes

## Current Release: 0.0.2

**Release Date**: 2025-11-07

### Features

- Added `CLIPHandler` leveraging the `open_clip` library for CLIP family models.
- Introduced `MobileCLIPHandler` with URL-based model download support.
- Created `SigLIPHandler` mirroring the CLIP handler structure for SigLIP models.
- Implemented a model registry and factory pattern for configuration-driven handler creation across the CLIP, CN-CLIP, MobileCLIP, SigLIP, and BLIP-2 model families.
- Added an application-level `EmbeddingModel` class with high-level APIs, including video processing.
- Enabled deployments consumable through both API mode and SDK mode clients.

### Improvements

- Centralized model configuration management in `config.py`.
- Added shared text and image embedding utilities with base64 and URL input support.

## Previous Release: 0.0.1

**Release Date**: 2025-06-01

### Features

- **Feature 1**:

### Improvements

- **Improvement 1**:
  - **Impact**:
- **Improvement 2**:
  - **Impact**:
