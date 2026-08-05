# Release Notes

## Version 2026.2.0

**Release Date:** August 4, 2026

**Improved:**

- Added NPU device configuration support alongside the existing CPU/GPU execution paths.
- Bumped Intel® compute-runtime GPU driver to `26.18.38308` and NPU driver to `1.35.0`, with a matching driver case in `install_ubuntu_gpu_drivers.sh`.
- Advanced the `optimum-intel` pin and `av` (17→18); refreshed dependency version constraints and lock files.
- Added dev and user agent skills for AI coding assistants.
- Documentation formatting fixes and a clarified Dockerfile comment.

> **Note:** The Video Search and Summarization sample application replaced this microservice with OpenVINO™ Model Server (OVMS) as its unified VLM/LLM inference backend in release 1.3.3-rc1. Changes in this release are maintenance-only.

## Releases 1.2.0, 1.2.1, 1.2.2, 1.2.3, 1.3.0 and 1.3.1

This microservice supports features based on the requirements of Video Search and Summarization sample application which is using this microservice. Refer to Video Search and Summarization [release notes](../../../../sample-applications/video-search-and-summarization/docs/user-guide/release-notes.md) for release details of this microservice.
