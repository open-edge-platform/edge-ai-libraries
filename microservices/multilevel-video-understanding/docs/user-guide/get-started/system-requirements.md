# System Requirements

This page provides detailed hardware, software, and platform requirements to help you set up and run the microservice efficiently.

## Supported Platforms

The `multilevel-video-understanding` microservice itself is platform-agnostic — it only needs an OpenAI-compatible model serving. In practice the platform sensitivity comes entirely from the model serving (**vLLM-IPEX**: [llm-scaler](https://github.com/intel/llm-scaler)). To run on a different platform, simply deploy llm-scaler on that platform and point the microservice at its endpoint; nothing else changes.

Two platforms have been validated:

- **Intel® Core™ Ultra (Panther Lake, PTL 358H)** with integrated GPU sharing system RAM — the on-device profile this Get Started guide is written around (no discrete accelerator or remote inference cluster required).
- **Intel® Xeon™ (e.g. GOLD 6530) + Intel® Arc™ Pro B60 Graphics** — a discrete-GPU serving host.

**Operating Systems**

- Ubuntu 24.04 LTS or later

**Hardware — Platform #1: Intel® Core™ Ultra (PTL 358H), on-device iGPU**

- Intel® Core™ Ultra processor with integrated GPU (validated on Panther Lake, PTL 358H), sharing system RAM
- At least **64 GB RAM** — default deployment target for `Qwen3.5-35B-A3B` (FP8, 60k context)
- At least **32 GB swap** — so the model load and KV cache can spill under peak memory pressure
- At least 128 GB disk space (model weights + Hugging Face cache)

> **Note:** To fit smaller-memory hosts, lower `MAX_MODEL_LEN` or use `awq` / `sym_int4` quantization in `docker/set_env.sh`.

**Hardware — Platform #2: Intel® Xeon™ + Intel® Arc™ Pro B60, discrete-GPU serving host**

- Intel® Xeon™ processor (validated on Intel® Xeon™ GOLD 6530)
- Intel® Arc™ Pro B60 Graphics — multiple GPUs may be required to serve `Qwen3.5-35B-A3B`
- At least **64 GB RAM**
- At least 128 GB disk space (model weights + Hugging Face cache)

> **Note:** On this platform, deploy vLLM-IPEX ([llm-scaler](https://github.com/intel/llm-scaler)) on the B60 host and point the microservice at its endpoint via `VLM_BASE_URL` / `LLM_BASE_URL`.

<!-- ## Minimum Requirements
- As per sample application documentation. -->

## Software Requirements

**Required Software**:

- Docker 24.0
- Python 3.10

## Validation

- Ensure all required software are installed and configured before proceeding to [Get Started](../get-started.md).

## Supporting Resources

- [Overview](../index.md)
- [API Reference](../api-reference.md)
