<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Release Notes

## Version 2026.3.0

This release adds XPU quantization in the LMCache transfer path and hybrid model support, based on vLLM v0.26.0 and LMCache v0.5.5.

**Features**:

- XPU (SYCL) quantization in the LMCache transfer path, with CPU as an option.
- Hybrid (Mamba / linear-attention) model support.
- Separate quantization switches for full-attention and linear-attention layers.
- Faster quantized KV transfers.
- Docker deployment upgraded to vLLM v0.26.0, LMCache v0.5.5 and PyTorch 2.12.0+xpu.

## Version 2026.2.0

This is the first release for kv-quant-offload. It is a near-lossless 4-bit KV-cache quantization codec for LMCache/vLLM, purpose-built for offloading KV caches from XPU memory to host memory / disk on edge devices — restoring prefix-cache hits that would otherwise be lost to memory pressure.

**Features**:

- Near-lossless 4-bit KV-cache quantization built on Randomized Hadamard Transform (RHT) preconditioning.
- Configurable scaling methods (`per_tensor` / `per_channel` / `per_token`), optional asymmetric quantization, and optional RHT preconditioning.
- CPU kernels for AVX2 and AVX-512 (FP16/BF16), with optional OpenMP multithreading, selectable at build time through `KVWEAVE_ISA` and `KVWEAVE_MULTITHREAD`.
- Optional standalone SYCL/DPC++ quantize/dequantize kernels for Intel XPUs, built with the Intel oneAPI DPC++ compiler (`KVWEAVE_XPU=1`).
- Docker-based vLLM + LMCache + kvweave deployment through `integration/lmcache/vllm/vllm-start.sh`, including the MP-hybrid and kvweave codec patches for LMCache v0.4.7.
- Accuracy and performance test suites for the quantization kernels and the LMCache serde path, plus a two-waves prefix-cache-hit benchmark script.
