<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Backend selection

`Backend::Auto` resolves in this order:

1. OpenCL — if `OPTICALFLOW_ENABLE_OPENCL=ON` (primary GPU latency path)
2. SYCL — if `OPTICALFLOW_ENABLE_SYCL=ON` and the toolchain provides `-fsycl`
3. CPU — if `OPTICALFLOW_ENABLE_CPU=ON` (default)

OpenCL DIS is the primary device path. SYCL DIS is secondary (landed; speed
tuning is lower priority than OpenCL). Lab gates in `PLAN.md` target Core
Ultra Series 2 iGPU.

## `calc` vs `calc_device` (important)

| API | Copies | Use when |
|-----|--------|----------|
| `OpticalFlow::calc` / `OpenCLOpticalFlow::calc` | H→D frames + D→H flow every call | Quick host apps, tests, one-shot |
| `OpenCLOpticalFlow::calc_device` | Keeps prev/next/flow on GPU | Pipelines, ≥10× claims, `gvaopticalflow` |

On Series 2 iGPU lab (OpenCL Fast DIS):

- **`calc_device` (resident):** ≥10× vs OpenCV CPU DIS-Fast @720p/1080p (met)
- **Host `calc`:** typically ≈6–8× — H↔D tax; **do not** use for speed gates

Prefer:

```cpp
#include "optical_flow_sdk/opencl_optical_flow.hpp"

optical_flow_sdk::OpenCLOpticalFlow of(optical_flow_sdk::Preset::Fast);
auto prev = of.create_u8_image(w, h);
auto next = of.create_u8_image(w, h);
auto flow = of.create_flow_buffer(w, h);
of.upload_u8(prev, prev_view);
of.upload_u8(next, next_view);
of.calc_device(prev, next, flow);   // flow stays on device
// of.download_flow(flow, host_flow);  // only if a host consumer needs it
```

See `samples/calc_flow_opencl_device.cpp` and `benchmarks/microbench_opencl_resident.cpp`.
