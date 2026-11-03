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
| `KVWEAVE_XPU` | `0` | Set `1` to also build `kvweave.kvweave_quant_xpu`, the SYCL/DPC++ quantize/dequantize kernels for Intel GPUs. Requires the Intel oneAPI DPC++ compiler (`icpx`) in `PATH` and a PyTorch build with XPU support; forces `CC=icx`/`CXX=icpx` regardless of `KVWEAVE_COMPILER`. The LMCache integration Dockerfile (`integration/lmcache/vllm/docker/Dockerfile`) sets this by default so `LMCACHE_MP_KVWEAVE_QUANT_DEVICE=xpu` has a module to import; building `kvweave` standalone (e.g. via `pip install .` directly) still defaults to CPU-only unless you set this yourself. |

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
| `GPU_MEM_UTIL` | `0.8` | vLLM `--gpu-memory-utilization`. |
| `MAX_MODEL_LEN` | `8192` | vLLM `--max-model-len`. |
| `DTYPE` | `float16` | vLLM `--dtype`. |
| `QUANTIZATION` | `fp8` | vLLM `--quantization` (model weight quantization, unrelated to KVWeave KV-cache quantization). |
| `DEBUG` | `False` | Enable vLLM `VLLM_SERVER_DEV_MODE`. |
| `VLLM_BLOCK_SIZE_OVERRIDE` | (unset) | Force LMCache `--chunk-size`, vLLM `--block-size` and `max_num_batched_tokens` (e.g. `256` for dense models). Unset: calculated automatically. |
| `MAX_NUM_BATCHED_TOKENS` | (unset) | vLLM `max_num_batched_tokens`. Unset: the block size. |
| `HOST_BIND_ADDRESS` | `127.0.0.1` | Host address the container ports are published on. |
| `HOST_PORT` | `8000` | Host port mapped to the container's vLLM API port (8000). |
| `LMCACHE_MP_HOST` | `tcp://localhost` | LMCache MP host URI inside the container. |
| `LMCACHE_MP_PORT` | `6555` | LMCache MP server port. |
| `LMCACHE_MP_HTTP_PORT` | `8090` | LMCache MP HTTP healthcheck port. |
| `LMCACHE_MP_MQ_TIMEOUT` | `600` | LMCache MP message timeout, in seconds. |
| `LMCACHE_MP_HEARTBEAT_INTERVAL` | `15` | LMCache MP heartbeat interval, in seconds. |
| `LMCACHE_MP_L1_SIZE_GB` | `5` | LMCache L1 (host memory) tier size, in GB. |
| `LMCACHE_MP_L2_ENABLE` | `true` | Enable the LMCache L2 filesystem adapter (backed by `${MODEL_PATH}/lmcache_disk`). |
| `LMCACHE_MP_EVICTION_POLICY` | `LRU` | L1 eviction policy. |
| `LMCACHE_MP_EVICTION_TRIGGER_WATERMARK` | `0.7` | L1 eviction trigger watermark. |
| `LMCACHE_MP_EVICTION_RATIO` | `0.3` | L1 eviction ratio. |
| `LMCACHE_MP_SUPPORTED_TRANSFER_MODE` | `auto` | LMCache server transfer mode. |
| `LMCACHE_MP_TRANSFER_MODE` | `engine_driven` | LMCache transfer mode. |
| `LMCACHE_MP_SHM_NAME` | `lmcache_l1_pool_server` | LMCache server shared-memory pool name. |
| `LMCACHE_MP_L1_KVWEAVE_QUANT` | `1` | Master switch for KVWeave L1 quantization. |
| `LMCACHE_MP_KVWEAVE_QUANT_DEVICE` | `xpu` | Quantization hardware: `xpu` (SYCL kernels) or `cpu` (OpenMP kernels). `xpu` requires an image built with `KVWEAVE_XPU=1` (the Dockerfile sets it). |
| `FORCE_BUILD` | `0` | See [FORCE_BUILD](#force_build) below. |
| `DOCKER_BUILD_OPTS` | (empty) | Extra args appended to the `docker build` invocation. |
| `DOCKER_RUN_OPTS` | (empty) | Extra args appended to the `docker run` invocation. |

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
