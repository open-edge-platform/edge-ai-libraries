# SIFT Extractor

An experimental, cross-use-case SIFT feature extraction and matching library for Intel platforms. The intended applications include image registration, localization, reconstruction, inspection, and retrieval.

## Status

This component is an early development snapshot, not a production release. The current SYCL reference backend is derived from the MIT-licensed CudaSift SYCL port. It is included to establish a reproducible build and correctness baseline; it is not yet a reentrant application API.

- SYCL extraction kernels and the original kernel smoke test are present.
- A tiled SYCL descriptor matcher is included with deterministic basis-vector matching coverage.
- A small synthetic-image extraction test checks feature bounds and finite, nonzero descriptors.
- The extrema kernel has been changed to avoid assuming a fixed Intel GPU subgroup width.
- An independent OpenCL runtime target enumerates platforms and reports device capabilities; no OpenCL SIFT kernels are implemented yet.
- Context-owned separable OpenCL Gaussian blur and DoG primitives are covered against CPU references, providing initial scale-space building blocks.
- OpenCL SIFT kernels, matching/geometry API, stable context ownership, Python bindings, packaging, and primary-host SIFT benchmarking remain in progress.
- Existing source-derived timings and reported CudaSift results are not performance claims for this component.

The legacy reference backend uses a process-global SYCL queue and scratch buffers. Do not use concurrent extraction calls. Its API and numerical behavior are not yet a stable compatibility contract.

## Build and Test

A DPC++ compiler and SYCL runtime are required. The current smoke tests expect an Intel GPU by default.

```bash
source /opt/intel/oneapi/setvars.sh
cmake -S . -B build-sycl \
  -DCMAKE_CXX_COMPILER=icpx \
  -DCMAKE_BUILD_TYPE=Release \
  -DSIFT_ENABLE_SYCL=ON \
  -DSIFT_BUILD_TESTS=ON
cmake --build build-sycl --parallel
ctest --test-dir build-sycl --output-on-failure
```

To diagnose the current implementation on an OpenCL CPU device instead of the default GPU:

```bash
ONEAPI_DEVICE_SELECTOR=opencl:cpu ctest --test-dir build-sycl --output-on-failure
```

The CPU selector is a diagnostic only; it does not count as GPU validation. To identify which extraction stage fails on a device, set `SIFT_SYCL_SYNC_EACH_STAGE=1` when running the extraction test. This adds synchronization and must not be used for performance measurements.

## Source and License Provenance

The reference SYCL files under `src/sycl_reference/` and `tests/sycl_reference/test_sycl_kernels.cpp` were copied from CudaSift worktree commit `7bbfacf84108aebd2300f449d3bc28ece11738a7`. The source's MIT license is retained in `LICENSES/MIT.txt`. New component files follow the Edge AI Libraries Apache-2.0 contribution policy. Review provenance and file-level licensing before redistributing derivative kernels.

## Hardware Inventory

Run `scripts/host_inventory.sh` to collect read-only CPU, GPU, driver, runtime, and compiler information. The script does not install dependencies or alter system settings.

For a user-space OpenCL runtime check on a remote Ubuntu host, run
`scripts/stage_opencl_host.sh user@host`. It stages the component and the
required Khronos headers under the remote user's `~/.local/share`, verifies a
SHA-256 manifest, and refuses to overwrite an existing content-addressed stage.
It does not install system packages or configure SSH credentials. SSH
host-key checking remains enabled; enter authentication directly in the
terminal.
