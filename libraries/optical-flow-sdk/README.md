<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Intel Optical Flow SDK

Dense optical flow for Intel CPU / iGPU / Arc. Product goal: close Nvidia
Optical Flow SDK (NVOFA) moat with SYCL/OpenCL implementations, first-class
C++ and Python APIs, and NVOFA-shaped presets / cost / forward-backward.

See [PLAN.md](PLAN.md) for decisions, gates, and roadmap. IPU DVS is deferred.

## Status (this tree)

| Piece | State |
|-------|--------|
| C++ API (`OpticalFlow`, presets, cost, `calcBoth`) | Available |
| CPU DIS-style backend | Available (OpenCV-free) |
| CPU Farneback dense + sparse PyrLK | Available (OpenCV-free) |
| EPE / Middlebury `.flo` metrics | Available (`metrics.hpp`, `eval_flow_epe`) |
| OpenCL / SYCL backends | Wired; currently fall back to CPU until device kernels land |
| OpenCV Mat adapter | Optional (`-DOPTICALFLOW_BUILD_OPENCV_ADAPTER=ON`) |
| Python (`optical_flow_sdk`) | Available when `-DOPTICALFLOW_BUILD_PYTHON=ON` |
| CPU microbench / OpenCV DIS·Farneback·PyrLK compare | Available under `benchmarks/` |
| OpenCV CPU synthetic parity test | Soft GT-EPE gates when adapter ON |
| Lab GPU timing / Sintel·KITTI OpenCV parity | Not runnable without datasets + oneAPI + Intel GPU |

## Build (CPU)

```bash
cmake -S . -B build \
  -DCMAKE_BUILD_TYPE=Release \
  -DOPTICALFLOW_ENABLE_CPU=ON \
  -DOPTICALFLOW_ENABLE_SYCL=OFF \
  -DOPTICALFLOW_ENABLE_OPENCL=OFF \
  -DOPTICALFLOW_BUILD_TESTS=ON \
  -DOPTICALFLOW_BUILD_SAMPLES=ON \
  -DOPTICALFLOW_BUILD_BENCHMARKS=ON \
  -DOPTICALFLOW_BUILD_OPENCV_ADAPTER=ON \
  -DOPTICALFLOW_BUILD_PYTHON=ON
cmake --build build --parallel
ctest --test-dir build --output-on-failure
./build/microbench_cpu
./build/compare_opencv_dis   # requires OpenCV adapter
```

For SYCL on a oneAPI host:

```bash
cmake -S . -B build-sycl \
  -DCMAKE_CXX_COMPILER=icpx \
  -DOPTICALFLOW_ENABLE_SYCL=ON \
  -DOPTICALFLOW_ENABLE_CPU=ON
```

## Minimal C++ usage

```cpp
#include "optical_flow_sdk/optical_flow.hpp"

optical_flow_sdk::OpticalFlow of(optical_flow_sdk::Backend::Cpu,
                                 optical_flow_sdk::Preset::Fast);
optical_flow_sdk::FlowField flow;
of.calc(prev, next, flow);  // dense dx/dy floats
```

## License

Apache-2.0. See `LICENSES/Apache-2.0.txt` and `REUSE.toml`.
