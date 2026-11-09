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
| CPU / OpenCL Farneback + sparse PyrLK | Available; full poly expansion; soft vs OpenCV identity (`docs/farneback.md`) |
| EPE / Middlebury `.flo` metrics | Available (`metrics.hpp`, `eval_flow_epe`) |
| OpenCL DIS + `calc_device` | Device-resident ≥10× on Series 2 iGPU; prefer over host `calc` (`docs/backend-selection.md`) |
| SYCL DIS | Landed + `calc_device` / resident microbench; OpenCL remains ≥10× path |
| SEA-RAFT OpenVINO | P2 quality PASS + preset/resolution FPS notes (`docs/sea_raft.md`) |
| OpenCV Mat adapter | Optional (`-DOPTICALFLOW_BUILD_OPENCV_ADAPTER=ON`) |
| Python (`optical_flow_sdk`) | Available when `-DOPTICALFLOW_BUILD_PYTHON=ON` |
| Samples | CPU calc / stabilize / track; OpenCL `calc_device`; warp seed (`docs/fruc_warp.md`) |
| Lab GPU timing / Sintel·KITTI OpenCV parity | §8 gate **FAIL** for DIS-lite (PLAN §11.6) |

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

For OpenCL on an Intel GPU host (ICD + headers; override include dir if needed):

```bash
cmake -S . -B build-opencl \
  -DCMAKE_BUILD_TYPE=Release \
  -DOPTICALFLOW_ENABLE_CPU=ON \
  -DOPTICALFLOW_ENABLE_OPENCL=ON \
  -DOPTICALFLOW_BUILD_TESTS=ON \
  -DOPTICALFLOW_BUILD_BENCHMARKS=ON
cmake --build build-opencl --parallel
./build-opencl/test_optical_flow_opencl_shift
./build-opencl/microbench_opencl_resident   # ≥10× path (calc_device)
./build-opencl/sample_calc_flow_opencl_device
```

**Speed tip:** use `OpenCLOpticalFlow::calc_device` for pipelines. Host
`OpticalFlow::calc` on OpenCL is convenience-only (~6–8×); see
`docs/backend-selection.md`.

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

GPU-resident (preferred for speed):

```cpp
#include "optical_flow_sdk/opencl_optical_flow.hpp"

optical_flow_sdk::OpenCLOpticalFlow of(optical_flow_sdk::Preset::Fast);
auto d_prev = of.create_u8_image(w, h);
auto d_next = of.create_u8_image(w, h);
auto d_flow = of.create_flow_buffer(w, h);
of.upload_u8(d_prev, prev_view);
of.upload_u8(d_next, next_view);
of.calc_device(d_prev, d_next, d_flow);  // flow stays on GPU
```

## License

Apache-2.0. See `LICENSES/Apache-2.0.txt` and `REUSE.toml`.
