<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Build, Test, and Deployment Configuration

## Prerequisites

- Python >= 3.10.
- PyTorch (`torch`, `numpy` — base dependencies).
- A C++17 compiler. Builds against AVX2 by default; set `KVWEAVE_ISA=avx512`
  on hosts with AVX-512 FP16/BF16 support.
- Optional: the Intel oneAPI DPC++ compiler (`icpx`) — only needed for
  `KVWEAVE_COMPILER=icpx` or to build the XPU kernels (`KVWEAVE_XPU=1`). See
  [Building with `icpx`](#building-with-icpx-kvweave_compilericpx-or-kvweave_xpu1)
  for installation and `PATH`/`LD_LIBRARY_PATH` setup.
- Optional, for `KVWEAVE_XPU=1`: a PyTorch build with XPU support.
- Optional: the `lmcache` package (`pip install ".[lmcache]"`) — needed to use
  the LMCache serde plugin.
- Optional: Docker — needed to run the Docker-based vLLM + LMCache + KV quant offload
  deployment in [Quick Start](../README.md#quick-start).

## Build Environment Variables

Recognized by `setup.py` when building the `kvweave.kvweave_quant` extension
(and optionally `kvweave.kvweave_quant_xpu`):

| Variable | Default | Meaning |
|---|---|---|
| `KVWEAVE_ISA` | `avx2` | Instruction set to compile the CPU kernels against. `avx2` is the safe default for client CPUs. Set `avx512` only on hosts confirmed to support AVX-512 FP16/BF16 — using it on unsupported hardware makes Python terminate with "Illegal instruction". |
| `KVWEAVE_COMPILER` | `default` | Set `icpx` to build with the Intel oneAPI DPC++ compiler instead of the system default compiler. Requires `icpx` in `PATH`. |
| `KVWEAVE_MULTITHREAD` | `1` | Set `0` to disable OpenMP multithreading in the CPU kernels. |
| `KVWEAVE_XPU` | `0` | Set `1` to also build `kvweave.kvweave_quant_xpu`, the standalone SYCL/DPC++ quantize/dequantize kernels for Intel GPUs. Requires the Intel oneAPI DPC++ compiler (`icpx`) in `PATH` and a PyTorch build with XPU support; forces `CC=icx`/`CXX=icpx` regardless of `KVWEAVE_COMPILER`. This module is standalone — it is not wired into the LMCache serde/codec path. |

### Building with `icpx` (`KVWEAVE_COMPILER=icpx` or `KVWEAVE_XPU=1`)

If `icpx` is not already installed, add the Intel oneAPI apt repository and
install the DPC++/C++ compiler package (which provides `icpx`):

```bash
# Add the Intel repository GPG key
wget -qO- https://apt.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB \
  | gpg --dearmor | sudo tee /usr/share/keyrings/oneapi-archive-keyring.gpg > /dev/null

# Add the repository
echo "deb [signed-by=/usr/share/keyrings/oneapi-archive-keyring.gpg] https://apt.repos.intel.com/oneapi all main" \
  | sudo tee /etc/apt/sources.list.d/oneAPI.list

# Install the 2025.3 compiler package (icpx is provided by this package)
sudo -E apt update
sudo -E apt install -y intel-oneapi-base-toolkit-2025.3
```

Set up the compiler environment with `setvars.sh`:

```bash
source /opt/intel/oneapi/setvars.sh
```

Then prepare a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

If you want to build with `KVWEAVE_XPU=1`:

```bash
KVWEAVE_COMPILER=icpx KVWEAVE_XPU=1 pip install . --extra-index-url https://download.pytorch.org/whl/xpu
```


## Running Unit Tests

Create a virtual environment, install the package into it, and run the test
suite:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install . --extra-index-url https://download.pytorch.org/whl/xpu
pip install pytest
pytest ./tests
```

Performance benchmarks are marked `perf` and deselected by default; pass
`-m ""` to include them (e.g. `pytest ./tests -m ""`).

## Deployment Environment Variables (`integration/lmcache/vllm/vllm-start.sh`)

`vllm-start.sh` builds the Docker image (if needed) and starts the
`vllm-kvweave` container. All variables are optional:

| Variable | Default | Meaning |
|---|---|---|
| `IMAGE_NAME` | `kv-quant-offload-vllm-xpu:latest` | Docker image tag to build/run. |
| `MODEL_PATH` | `/models` | Host directory mounted read-only at `/models` in the container. |
| `MODEL` | `Qwen3.5-9B` | Model path/name under `MODEL_PATH`, passed to vLLM as `/models/${MODEL}`. |
| `SERVE` | same as `MODEL` | Served model name exposed by the OpenAI-compatible API. |
| `TP` | `1` | Tensor parallel size. |
| `GPU_MEM_UTIL` | `0.86` | vLLM `--gpu-memory-utilization`. |
| `MAX_MODEL_LEN` | `8192` | vLLM `--max-model-len`. |
| `DTYPE` | `float16` | vLLM `--dtype`. |
| `QUANTIZATION` | `fp8` | vLLM `--quantization` (model weight quantization). Unrelated to the KVWeave KV cache quantization variables below. |
| `DEBUG` | `False` | Enables `VLLM_SERVER_DEV_MODE`. |
| `HOST_BIND_ADDRESS` | `127.0.0.1` | Host address the container ports are published on. |
| `HOST_PORT` | `8000` | Host port mapped to the container's vLLM API port (8000). |
| `LMCACHE_MP_PORT` | `6555` | LMCache MP server port. |
| `LMCACHE_MP_HTTP_PORT` | `8090` | LMCache MP HTTP healthcheck port. |
| `LMCACHE_MP_L1_SIZE_GB` | `5` | LMCache L1 (host memory) tier size, in GB. |
| `LMCACHE_MP_L2_ENABLE` | `true` | Enable the LMCache L2 filesystem adapter (disk tier). |
| `LMCACHE_MP_EVICTION_TRIGGER_WATERMARK` | `0.7` | L1 occupancy fraction at which eviction starts. |
| `LMCACHE_MP_EVICTION_RATIO` | `0.3` | Fraction of L1 evicted once the watermark is reached. |
| `LMCACHE_MP_L1_KVWEAVE_QUANT` | `1` | See [KV cache quantization](#kv-cache-quantization) below. |
| `LMCACHE_MP_KVWEAVE_LINEAR_QUANT_ENABLED` | `1` | See [KV cache quantization](#kv-cache-quantization) below. |
| `LMCACHE_MP_KVWEAVE_CONV_QUANT_ENABLED` | `1` | See [KV cache quantization](#kv-cache-quantization) below. |
| `LMCACHE_MP_KVWEAVE_SSM_QUANT_ENABLED` | `1` | See [KV cache quantization](#kv-cache-quantization) below. |
| `FORCE_BUILD` | `0` | See [FORCE_BUILD](#force_build) below. |
| `DOCKER_BUILD_OPTS` | (empty) | Extra args appended to the `docker build` invocation. |
| `DOCKER_RUN_OPTS` | (empty) | Extra args appended to the `docker run` invocation. |

### KV cache quantization

These four variables control KVWeave 4-bit quantization of the offloaded KV
cache. They are distinct from `QUANTIZATION`, which is vLLM's *model weight*
quantization. All default to `1` (enabled), matching the `ENV` defaults baked
into `docker/Dockerfile`.

| Variable | Scope |
|---|---|
| `LMCACHE_MP_L1_KVWEAVE_QUANT` | Master switch for worker-side L1 quantization. |
| `LMCACHE_MP_KVWEAVE_LINEAR_QUANT_ENABLED` | Group-level gate: skips quantization for the entire linear-attention / Mamba group. Overrides the two sub-state switches below. |
| `LMCACHE_MP_KVWEAVE_CONV_QUANT_ENABLED` | Mamba `conv_state` sub-state. |
| `LMCACHE_MP_KVWEAVE_SSM_QUANT_ENABLED` | Mamba `ssm_state` sub-state. |

The last three only apply to hybrid (Mamba / linear-attention) models such as
Qwen3.5-9B. Pure attention models like Qwen3-8B are unaffected by them.

Each variable can be disabled independently. To store the KV cache
uncompressed, set the master switch to `0` — the other three then have no
effect:

```bash
LMCACHE_MP_L1_KVWEAVE_QUANT=0 \
  bash integration/lmcache/vllm/vllm-start.sh
```

Skip quantization for the whole linear-attention / Mamba group, leaving the
full-attention layers quantized:

```bash
LMCACHE_MP_KVWEAVE_LINEAR_QUANT_ENABLED=0 \
  bash integration/lmcache/vllm/vllm-start.sh
```

Store Mamba `conv_state` at full precision (`ssm_state` stays quantized):

```bash
LMCACHE_MP_KVWEAVE_CONV_QUANT_ENABLED=0 \
  bash integration/lmcache/vllm/vllm-start.sh
```

Store Mamba `ssm_state` at full precision (`conv_state` stays quantized):

```bash
LMCACHE_MP_KVWEAVE_SSM_QUANT_ENABLED=0 \
  bash integration/lmcache/vllm/vllm-start.sh
```

The two sub-state switches combine, so both Mamba states can be kept at full
precision while attention stays quantized:

```bash
LMCACHE_MP_KVWEAVE_CONV_QUANT_ENABLED=0 \
LMCACHE_MP_KVWEAVE_SSM_QUANT_ENABLED=0 \
  bash integration/lmcache/vllm/vllm-start.sh
```

> **Note:** All four variables only take effect on the data-transfer path used
> by XPU. On CUDA the transfer context defaults to a handle-passing mode that
> never applies KVWeave quantization, so setting them has no effect unless
> `LMCACHE_MP_TRANSFER_MODE=data` is also set.

> **Note:** `LMCACHE_MP_L1_KVWEAVE_QUANT` is read by both the L1 worker and the
> L2 storage manager, with opposite effects. Setting it to `0` disables L1
> quantization, but if an L2 adapter is configured with a `serde_config`, that
> serde wrapper is then *enabled* — the two tiers are mutually exclusive by
> design, so that data is not compressed twice. Setting it to `0` alone
> therefore does not guarantee that nothing is quantized.

### `FORCE_BUILD`

By default, `vllm-start.sh` only runs `docker build` when `IMAGE_NAME` does
not already exist (checked via `docker image inspect`); otherwise it reuses
the existing image and prints `Using existing image ...`. This makes repeat
runs fast, but means the image silently goes stale if you've changed
`setup.py`, the kvweave sources, or the Dockerfile without changing
`IMAGE_NAME`.

Set `FORCE_BUILD=1` to always rebuild (with `--no-cache`), regardless of
whether an image with that tag already exists:

```bash
FORCE_BUILD=1 MODEL_PATH=/path/to/models bash integration/lmcache/vllm/vllm-start.sh
```
