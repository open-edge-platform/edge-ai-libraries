# SIFT Extractor

An experimental, cross-use-case SIFT feature extraction and matching library for Intel platforms. The intended applications include image registration, localization, reconstruction, inspection, and retrieval.

## Status

This component is an early development snapshot, not a production release. The
SYCL reference backend is a mechanics baseline (see provenance below); it is
not yet a reentrant application API. Public quality and performance framing
compares **OpenCV**, an **unoptimized/reference SIFT** baseline, **OpenCL**,
and **SYCL**—see [comparison](docs/comparison.md) and [quality](docs/quality.md).

- SYCL extraction kernels and the original kernel smoke test are present.
- A tiled SYCL descriptor matcher is included with deterministic basis-vector matching coverage.
- A small synthetic-image extraction test checks feature bounds and finite, nonzero descriptors.
- The extrema kernel has been changed to avoid assuming a fixed Intel GPU subgroup width.
- An independent OpenCL runtime target enumerates platforms and reports device capabilities.
- Context-owned OpenCL Gaussian blur, DoG, 2x downsample, and an incremental octave/scale Gaussian pyramid are covered against CPU references as initial scale-space building blocks.
- A separate OpenCL 3D DoG extrema-candidate kernel has deterministic interior maximum/minimum and border-exclusion coverage.
- Subpixel Taylor refinement and Hessian edge rejection are covered with a synthetic quadratic reference.
- An experimental image-to-feature path connects the pyramid and detector, retains octave/image-coordinate/sigma metadata, assigns primary/secondary orientations, and computes rotated 128-D trilinear descriptors with clipping and renormalization.
- Synthetic tests cover known directions, multiple orientation peaks, blank inputs, descriptor norms and a 90-degree ramp rotation. These are mechanics checks, not SIFT equivalence certification.
- Dual-backend dispatch keeps OpenCL and SYCL with explicit selection
  (`Backend::Auto` prefers SYCL for Arc speed, not quality).
  See [backend selection](docs/backend-selection.md). Public packaging, pkg-config,
  a native sample, optional Python bindings, and optional thin OpenCV type adapters
  (`SIFT_BUILD_OPENCV_ADAPTER`) are available. Listed under root README **Computer
  Vision Primitives**. Scoped GitHub Actions CI
  (`.github/workflows/sift-extractor.yml`) configures the tree without GPU
  backends and **explicitly discloses that no Intel GPU runners are attached**;
  OpenCL/SYCL CTest, Arc timing, soak and quality scoring are private-lab gates.
  Matching/geometry, held-out corpus and REUSE publication remain open. The OpenCV
  adapters wrap the core Extractor with `cv::Mat`/`cv::KeyPoint` only—they are not
  OpenCV features2d SIFT or upstream features2d work.
- Source-derived timings are not performance claims for redistributed binaries.

The legacy reference backend uses a process-global SYCL queue and scratch buffers. Do not use concurrent extraction calls. Its API and numerical behavior are not yet a stable compatibility contract. Early OpenCL correctness stages use host-visible vectors between pyramid and feature processing (the unoptimized/reference anchor); device-resident extract work is in progress. Feature sampling uses the nearest Gaussian level and local sigma derived from a DoG geometric-center convention; reference parity is outstanding. Refinement is single-step, not iterative relocation.

## Hardware Target

Intel Arc is the primary performance-optimization target. UHD Graphics 770 is
used for quick correctness validation and a CPU-versus-GPU regression check, not
as a tuning target or a requirement that constrains Arc-specific improvements.

**Previous-generation Intel integrated GPUs, including UHD Graphics 770, are not
recommended when a predictable SIFT performance boost is a requirement.** GPU
offload can be slower than CPU SIFT for some sizes/settings because allocation,
transfer and launch overhead can dominate. Measure against the CPU / unoptimized
reference path on the same host, with recorded CPU thread count and comparable
output quality; do not infer acceleration from GPU availability or advertised
TOPS alone.

An Arc optimization must preserve correctness on UHD 770. Older-GPU CPU/GPU
slowdowns must be reported rather than hidden by unmatched settings or omitted
overheads. Arc tuning proceeds even if an older GPU needs this performance caveat.
No automatic CPU fallback or universal acceleration guarantee is currently provided.

## Experimental Context

An [OpenCV-free SYCL context](docs/sycl-context.md) owns reusable image, feature
and scratch buffers. A matching OpenCL public wrapper and a dispatch
`Extractor` select between backends. Parameter contracts are intentionally
unequal; see [backend selection](docs/backend-selection.md).

### Install / pkg-config / Python

```bash
cmake -S . -B build -DCMAKE_CXX_COMPILER=icpx -DCMAKE_BUILD_TYPE=Release \
  -DSIFT_ENABLE_SYCL=ON -DSIFT_ENABLE_OPENCL=ON -DSIFT_BUILD_PYTHON=ON \
  -DSIFT_OPENCL_INCLUDE_DIR=/opt/intel/oneapi/compiler/latest/include \
  -DCMAKE_INSTALL_PREFIX=$PWD/install
cmake --build build --parallel
cmake --install build
export PKG_CONFIG_PATH=$PWD/install/lib/pkgconfig:$PKG_CONFIG_PATH
pkg-config --libs --cflags sift_extractor
```

Python (when `SIFT_BUILD_PYTHON=ON`):

```python
import numpy as np
import sift_extractor
ext = sift_extractor.Extractor(64, 64, backend="auto")
features = ext.extract(np.zeros((64, 64), dtype=np.float32))
```

Native sample: `extract_sift [auto|opencl|sycl]`.
Matched timing: `time_sift_extract` and `share/sift_extractor/time_sift_extract.py`
(`[backend] [W] [H] [warmups] [samples] [seed] [image.pgm]`).
Release-gate harness: `soak_sift_extract [--release] [--calls N] [--minutes M]
[--concurrency N]` (mixed backends single-threaded; OpenCL independent-context
concurrency when built). Default is exploratory; `--release` targets ≥10000
mixed calls (no wall-clock floor unless `--minutes` is set).

Optional OpenCV adapters (`-DSIFT_BUILD_OPENCV_ADAPTER=ON`, OpenCV `core` only):

```cpp
#include <sift_extractor/opencv_adapter.hpp>
sift_extractor::experimental::Extractor extractor(w, h, backend);
std::vector<cv::KeyPoint> keypoints;
cv::Mat descriptors;
sift_extractor::experimental::opencv::detect_and_compute(
    extractor, gray_u8_or_f32, keypoints, descriptors);
```

Sample: `extract_sift_opencv [auto|opencl|sycl]`. `KeyPoint::size` is
`2 * SiftFeature::scale` (diameter presentation). Core remains OpenCV-free.

## Build and Test

A DPC++ compiler and SYCL runtime are required for SYCL, not the OpenCL-only build. The current GPU tests expect Intel hardware by default.

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

Current-source extraction on the local CPU returned zero features and failed the
nonempty-output check; the exact same binary returned 1009 features on UHD 770.
CPU support is not validated.

## Real-Image Diagnostic

An optional validation adapter uses OpenCV for image loading, reference features,
matching and known-transform geometry. It does not add OpenCV to the core library.

```bash
cmake -S . -B build-opencl -DSIFT_ENABLE_SYCL=OFF -DSIFT_ENABLE_OPENCL=ON \
  -DSIFT_ENABLE_OPENCV_VALIDATION=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build-opencl --target validate_sift_pair
build-opencl/validate_sift_pair /path/to/image.pgm
```

The JSON report compares a 30-degree rotation/0.85 scale against ground truth at
3 pixels. Prototype and OpenCV-default parameters are explicitly not equivalent;
the tool is a diagnostic among OpenCV / OpenCL / SYCL (when enabled), not a
quality acceptance test or benchmark. Initial `left.pgm` diagnostics showed a
large coverage gap versus OpenCV-default SIFT. Do not claim parity.

When both backends are enabled, this tool also evaluates SYCL on an Intel GPU and
rejects CPU fallback. Write JSON to a file because the reference prints console
logs. An optional iteration count adds diagnostic end-to-end extraction timing:

```bash
ONEAPI_DEVICE_SELECTOR=level_zero:gpu \
  build/validate_sift_pair /path/to/image.pgm report.json 10
```

See [comparison protocol](docs/comparison.md) for timing scope and
hardware-normalization requirements.

## Source and License Provenance

The reference SYCL files under `src/sycl_reference/` and
`tests/sycl_reference/test_sycl_kernels.cpp` were derived from CudaSift
worktree commit `7bbfacf84108aebd2300f449d3bc28ece11738a7`. The component is
licensed under Apache-2.0 (`LICENSES/Apache-2.0.txt`). Acknowledgment of the
original SIFT method is in `third_party_programs.txt`.

## Hardware Inventory

Run `scripts/host_inventory.sh` to collect read-only CPU, GPU, driver, runtime, and compiler information. The script does not install dependencies or alter system settings.

For a user-space OpenCL runtime check on a remote Ubuntu host, run
`scripts/stage_opencl_host.sh user@host`. It stages the component and the
required Khronos headers under the remote user's `~/.local/share`, verifies a
SHA-256 manifest, and refuses to overwrite an existing content-addressed stage.
It does not install system packages or configure SSH credentials. SSH
host-key checking remains enabled; enter authentication directly in the
terminal.

Append `--test` to build and execute the whole OpenCL test slice in the same
connection. For portable, locally compiled SYCL tests without a remote compiler:

```bash
source /opt/intel/oneapi/setvars.sh
SIFT_STAGE_SYCL_BUILD=/tmp/sift-extractor-both \
  bash scripts/stage_opencl_host.sh user@host --test
```

This optionally stages three SYCL test binaries, runtime dependencies, and
compiler/UMF/TCM/Level Zero licenses and third-party notices (~79 MiB locally).
The bundle includes both `libze_loader.so.1` and its matching
`libze_tracing_layer.so.1`: these are loaded dynamically, so `ldd` alone does not
discover them. Mixing loader/tracing-layer releases can fail device enumeration
before any SIFT kernel runs. The staging guard checks the loader exports
`zeDeviceGetRootDevice`, but that alone does not establish runtime compatibility.

By default the pair comes from the local system loader directory, with Ubuntu's
`/usr/share/doc/libze1/copyright` notice. To use a private build, build both
`ze_loader` and `ze_tracing_layer` targets from the same Level Zero source release:

```bash
SIFT_STAGE_SYCL_BUILD=/tmp/sift-extractor-both \
SIFT_STAGE_LEVEL_ZERO_LOADER=/path/to/level-zero/build/lib/libze_loader.so.1 \
SIFT_STAGE_LEVEL_ZERO_NOTICE=/path/to/level-zero/LICENSES \
  bash scripts/stage_opencl_host.sh user@host --test
```

The tracing layer is resolved next to the loader; override
`SIFT_STAGE_LEVEL_ZERO_TRACING` only with a matching library. Notices may be a
file or directory. The bundle relies on the target GPU driver and compatible
system C++/C libraries, not a copied compiler or driver. It is an internal
smoke-test deployment, not a general release package. Other target GPUs still
require their own runtime validation.
