<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# KVCache Quantization and Offload Library

KVCache Quantization and Offload Library is a near-lossless 4-bit KV-cache quantization codec for LMCache/vLLM,
purpose-built for offloading KV caches from XPU memory to host memory / disk
on edge devices — restoring prefix-cache hits that would otherwise be lost to
memory pressure.

## Features

- Near-lossless 4-bit KV-cache quantization built on Randomized Hadamard
  Transform (RHT) preconditioning, tuned for edge accelerator deployments.
- Configurable scaling methods (`per_tensor` / `per_channel` / `per_token`),
  optional asymmetric quantization, and optional RHT preconditioning.
- CPU kernels (AVX2 or AVX-512, with optional OpenMP multithreading) plus an
  optional standalone SYCL/DPC++ kernel for Intel XPUs.
- Drop-in codec for LMCache's serde interface — stays
  transparent to vLLM's serving path.


## Prerequisites

See [docs/configuration.md](docs/configuration.md#prerequisites) for the full
list of prerequisites (Python/PyTorch/compiler versions, optional oneAPI and
`lmcache` dependencies, Docker).


## Architecture

### Why vLLM and LMCache

vLLM is the de-facto high-throughput serving engine with paged KV-cache
management; LMCache adds a layer that reuses KV caches across an
XPU-host-disk hierarchy. Together they give production-grade serving with
tiered offloading.

### Integrating with LMCache

LMCache does not offer KV-cache quantization for L1 storage level (host memory). This library closes that gap through the
bundled `kvweave` codec, plugged into LMCache's codec interface. The codec brings a novel quantization algorithm
with near-zero accuracy loss, optimized for Intel platforms; it stays
transparent to the serving engine while shrinking payloads to ease disk-I/O
pressure.

![KV quant offload plugged into the vLLM + LMCache component architecture](docs/assets/architecture.png)

### Data flow

During prefill, vLLM produces KV caches on the XPU. LMCache moves each chunk
off the device and passes it through the `kvweave` codec, which quantizes it
once and writes the compact payload to the host and disk tiers. When a later
request reuses that context, LMCache retrieves the payload, the `kvweave` codec
dequantizes it, and the reconstructed KV cache is loaded back to the XPU —
turning what would have been a full prefill into a cache hit served from disk.

![KV quant offload encode/decode across the XPU / host / disk tiers](docs/assets/dataflow.png)

## Repository layout

```
setup.py                  Build script for the kvweave.kvweave_quant extension
kvweave/                  Python package the compiled extensions install into
kvweave/csrc/             Core C++ quantize/dequantize kernels (CPU + XPU/SYCL)
kvweave/bindings/         pybind11 wrappers exposing kvweave/csrc/ as Python extensions
docs/assets/              README images and other static documentation assets
integration/lmcache/      Docker-based vLLM + LMCache + KV quant offload deployment scripts
tests/                    Quantization accuracy/perf and serde unit tests, vllm-bench-two-waves.sh benchmark
```

## Install

Create a virtual environment, and build the CPU extension (`kvweave.kvweave_quant`):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install . --extra-index-url https://download.pytorch.org/whl/xpu
```

See [docs/configuration.md](docs/configuration.md#build-environment-variables)
for the environment variables recognized by `setup.py` (`KVWEAVE_ISA`,
`KVWEAVE_COMPILER`, `KVWEAVE_MULTITHREAD`, `KVWEAVE_XPU`).


## Running Unit Tests

See [docs/configuration.md](docs/configuration.md#running-unit-tests) for how
to set up a venv, install `kvweave`, and run `pytest ./tests`.


## Quick Start

`integration/lmcache/vllm/vllm-start.sh` launches a Docker container that
clones LMCache v0.4.7, applies `integration/lmcache/patches/lmcache-mp-hybrid.patch`
and `integration/lmcache/patches/lmcache-v0.4.7-mp-hybrid-to-kvweave.patch`
(which together add MP-hybrid support and the `kvweave` codec), builds
`kvweave_quant` inside the container, starts an LMCache MP server, and then
starts vLLM's OpenAI-compatible API server wired to it via `LMCacheMPConnector`.

```bash
MODEL=model_name SERVE=model_name MODEL_PATH=/path/to/models bash integration/lmcache/vllm/vllm-start.sh
```

See [docs/configuration.md](docs/configuration.md#deployment-environment-variables-integrationlmcachevllmvllm-startsh)
for the full list of environment variables `vllm-start.sh` accepts (model
path, ports, LMCache sizing, `FORCE_BUILD`, and Docker build/run passthroughs).

Then test the running server, setting `TOKENIZER_PATH` to a model path your
host can load with `AutoTokenizer` (e.g. the same `${MODEL_PATH}/${MODEL}`
passed to `vllm-start.sh` above):

```bash
MODEL=model_name SERVE=model_name TOKENIZER_PATH=/path/to/models bash tests/vllm-bench-two-waves.sh
```

If you meet error about memory after build iamge, use:

```
echo 3 | sudo tee /proc/sys/vm/drop_caches
```
to clean the cache and restart the vllm server.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
