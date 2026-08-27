<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Release Notes

## Current Release

**Version**: 2026.2

This is the first release for kv-quant-offload. It is a near-lossless 4-bit KV-cache quantization codec for LMCache/vLLM, purpose-built for offloading KV caches from XPU memory to host memory / disk on edge devices — restoring prefix-cache hits that would otherwise be lost to memory pressure.

**Features**

- Near-lossless 4-bit KV-cache quantization built on Randomized Hadamard Transform (RHT) preconditioning.
- Configurable scaling methods (`per_tensor` / `per_channel` / `per_token`), optional asymmetric quantization, and optional RHT preconditioning.
- CPU kernels for AVX2 and AVX-512 (FP16/BF16), with optional OpenMP multithreading, selectable at build time through `KVWEAVE_ISA` and `KVWEAVE_MULTITHREAD`.
- Optional standalone SYCL/DPC++ quantize/dequantize kernels for Intel XPUs, built with the Intel oneAPI DPC++ compiler (`KVWEAVE_XPU=1`).
- Docker-based vLLM + LMCache + kvweave deployment through `integration/lmcache/vllm/vllm-start.sh`, including the MP-hybrid and kvweave codec patches for LMCache v0.4.7.
- Accuracy and performance test suites for the quantization kernels and the LMCache serde path, plus a two-waves prefix-cache-hit benchmark script.
