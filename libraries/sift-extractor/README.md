# SIFT Extractor

Intel GPU SIFT feature extraction and matching for registration, localization,
reconstruction, inspection, and retrieval. Dual OpenCL and SYCL backends with
an explicit dispatch API; optional packaging, Python bindings, and thin OpenCV
type adapters.

Public quality and performance comparisons use OpenCV, OpenCL, and SYCL—backends
are **not** algorithm-equivalent (feature counts, thresholds, and timings are
not interchangeable). See [comparison](docs/comparison.md) and
[quality](docs/quality.md) before choosing a backend or reading ladder numbers.

## Features

- **OpenCL** extract pipeline (scale space, extrema, orientation, 128-D descriptors)
  and `OpenCLMatcher` (tiled GPU descriptor matching)
- **SYCL** extract path plus `MatchSiftData` tiled matcher
- **`Extractor` dispatch** with `Backend::OpenCL`, `Backend::Sycl`, or
  `Backend::Auto` (see [backend selection](docs/backend-selection.md))
- Install / pkg-config, native samples, optional Python wheel/bindings, optional
  OpenCV `cv::Mat` / `cv::KeyPoint` adapters (not OpenCV features2d SIFT)
- Scoped GitHub Actions configure/build without GPU backends (no Intel GPU
  runners in CI; OpenCL/SYCL CTest and Arc timing are lab gates)

## Hardware

Primary optimization target: **Intel Arc**. UHD Graphics 770 is used for
correctness checks, not as a tuning target.

Previous-generation Intel integrated GPUs (including UHD 770) are **not**
recommended when a predictable SIFT speedup is required. Offload can be slower
than CPU SIFT when allocation, transfer, and launch overhead dominate. Measure
against a CPU/reference path on the same host with recorded thread count and
comparable quality.

## Build

Requires a DPC++ / SYCL toolchain for the SYCL backend. OpenCL-only builds need
OpenCL headers and an ICD loader.

```bash
source /opt/intel/oneapi/setvars.sh
cmake -S . -B build -DCMAKE_CXX_COMPILER=icpx -DCMAKE_BUILD_TYPE=Release \
  -DSIFT_ENABLE_SYCL=ON -DSIFT_ENABLE_OPENCL=ON -DSIFT_BUILD_TESTS=ON \
  -DSIFT_OPENCL_INCLUDE_DIR=/opt/intel/oneapi/compiler/latest/include
cmake --build build --parallel
ctest --test-dir build --output-on-failure
```

Useful CMake options:

| Option | Default | Purpose |
| --- | --- | --- |
| `SIFT_ENABLE_SYCL` | ON | SYCL reference + extract |
| `SIFT_ENABLE_OPENCL` | OFF | OpenCL runtime + extract + matcher |
| `SIFT_BUILD_TESTS` | ON when `BUILD_TESTING` | CTest targets |
| `SIFT_BUILD_SAMPLES` | ON | `extract_and_match`, timing/soak helpers |
| `SIFT_BUILD_PYTHON` | OFF | `sift_extractor` Python package (`_native` extension) |
| `SIFT_BUILD_OPENCV_ADAPTER` | OFF | Thin OpenCV type adapters |
| `SIFT_ENABLE_OPENCV_VALIDATION` | OFF | `validate_sift_pair` diagnostic |

Device selection (Intel GPU by default):

```bash
ONEAPI_DEVICE_SELECTOR=level_zero:gpu ctest --test-dir build --output-on-failure
```

`ONEAPI_DEVICE_SELECTOR=opencl:cpu` is diagnostic only and does not count as GPU
validation. `SIFT_SYCL_SYNC_EACH_STAGE=1` forces per-stage sync for debugging
and must not be used for performance measurements.

## Install and use

This library does **not** install the GPU stack. Provide driver + compute
runtimes on the host, then install the native library (CMake) and/or a thin
Python wheel (pip).

### System requirements (host — not via pip / CMake install)

| Need | Used for |
| --- | --- |
| Intel GPU driver with compute | Device access |
| OpenCL ICD (`libOpenCL.so.1`) | OpenCL backend |
| Intel oneAPI SYCL + Level Zero | SYCL backend (often `source /opt/intel/oneapi/setvars.sh`) |

### Native install (CMake / pkg-config)

```bash
source /opt/intel/oneapi/setvars.sh   # when using SYCL
cmake -S . -B build -DCMAKE_CXX_COMPILER=icpx -DCMAKE_BUILD_TYPE=Release \
  -DSIFT_ENABLE_SYCL=ON -DSIFT_ENABLE_OPENCL=ON -DSIFT_BUILD_PYTHON=ON \
  -DSIFT_OPENCL_INCLUDE_DIR=/opt/intel/oneapi/compiler/latest/include \
  -DCMAKE_INSTALL_PREFIX=$PWD/install
cmake --build build --parallel
cmake --install build
export PKG_CONFIG_PATH=$PWD/install/lib/pkgconfig:$PKG_CONFIG_PATH
pkg-config --libs --cflags sift_extractor
```

Native samples after build/install:

```bash
./build/extract_and_match [auto|opencl|sycl]  # extract two views + Lowe-ratio match
./build/time_sift_extract [backend] [W] [H] [warmups] [samples] [seed] [image.pgm]
./build/soak_sift_extract [--release] [--calls N] [--minutes M] [--concurrency N]
```

`extract_and_match` prints feature counts for both images and ratio-accepted matches
(OpenCL `OpenCLMatcher` when built; otherwise a host dot-product fallback).

`--release` targets ≥10 000 mixed calls (no wall-clock floor unless `--minutes`
is set).

Optional OpenCV adapters (`-DSIFT_BUILD_OPENCV_ADAPTER=ON`):

```cpp
#include <sift_extractor/opencv_adapter.hpp>
#if SIFT_EXTRACTOR_HAS_OPENCL
#include <sift_extractor/opencl_matcher.hpp>
#endif

sift_extractor::Extractor extractor(w, h, backend);
std::vector<cv::KeyPoint> keypoints;
cv::Mat descriptors;
sift_extractor::opencv::detect_and_compute(
    extractor, gray_u8_or_f32, keypoints, descriptors);
// Match via sift_extractor::OpenCLMatcher (or host) on SiftFeature lists from
// Extractor::extract — same Lowe-ratio convention as the Python wheel.
```

`KeyPoint::size` is `2 * SiftFeature::scale` (diameter). The core library does
not depend on OpenCV.

### Python install (thin wheel)

The wheel ships the pybind extension (`.so`) only — not drivers, OpenCL, or
oneAPI. Details: [`python/README.python.md`](python/README.python.md).

```bash
source /opt/intel/oneapi/setvars.sh   # SYCL / Intel runtime on loader path
bash python/build_wheel.sh            # writes python/dist/sift_extractor-*-linux_*.whl

python3 -m venv --system-site-packages /tmp/sift-venv
source /tmp/sift-venv/bin/activate
pip install python/dist/sift_extractor-*.whl   # also needs numpy
python python/samples/extract_and_match.py scene.pgm          # affine pair + match
python python/samples/extract_and_match.py left.png right.png # two views + match
```

After `cmake --install` with `-DSIFT_BUILD_PYTHON=ON`, the same package also
lands under `$PREFIX/lib/python3/dist-packages/sift_extractor/` (set
`PYTHONPATH` if not using the wheel).

### Python usage

```python
import numpy as np
import sift_extractor

print(sift_extractor.__version__)
print(sift_extractor.system_requirements())  # stack is host-provided
print(list(sift_extractor.available_backends()))  # e.g. ['opencl', 'sycl']
print("opencl_matcher:", sift_extractor.has_opencl_matcher)

# Contiguous float32 grayscale HxW; shape must match Extractor width/height.
ext = sift_extractor.Extractor(image1.shape[1], image1.shape[0], backend="auto")
feats1 = ext.extract(image1)
ext2 = sift_extractor.Extractor(image2.shape[1], image2.shape[0], backend="auto")
feats2 = ext2.extract(image2)
# Match descriptors (OpenCL GPU matcher when built; Lowe ratio on ambiguity).
matches = sift_extractor.match(feats1, feats2, ratio=0.8)
print(ext.backend, len(feats1), len(feats2), "matches", len(matches))
```

If `import sift_extractor` fails on a missing shared library, the GPU/runtime
stack or loader path is incomplete — fix the host environment, not pip.

## Diagnostics

Optional OpenCV-backed pair validation (image I/O and reference features only;
not a quality gate):

```bash
cmake -S . -B build -DSIFT_ENABLE_SYCL=ON -DSIFT_ENABLE_OPENCL=ON \
  -DSIFT_ENABLE_OPENCV_VALIDATION=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build --target validate_sift_pair
ONEAPI_DEVICE_SELECTOR=level_zero:gpu \
  ./build/validate_sift_pair /path/to/image.pgm report.json 10
```

Resolution-ladder / match microbenches (when OpenCV validation is enabled):
`resolution_ladder_bench`, `match_opt_sweep`.

Host inventory (read-only): `scripts/host_inventory.sh`.

Remote user-space staging helper: `scripts/stage_opencl_host.sh user@host`
(optional `--test`). Stages under `~/.local/share`; does not install system
packages or change SSH credentials.

## Documentation

| Doc | Contents |
| --- | --- |
| [backend-selection.md](docs/backend-selection.md) | Auto / OpenCL / SYCL contracts |
| [comparison.md](docs/comparison.md) | OpenCV / reference / OpenCL / SYCL protocol |
| [quality.md](docs/quality.md) | Quality scoring expectations |
| [sycl-context.md](docs/sycl-context.md) | SYCL context ownership |

## License and provenance

Apache-2.0 (`LICENSES/Apache-2.0.txt`). SYCL reference sources under
`src/sycl_reference/` were derived from CudaSift worktree commit
`7bbfacf84108aebd2300f449d3bc28ece11738a7`. SIFT method acknowledgment:
`third_party_programs.txt`.
