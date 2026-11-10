<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Backend selection

Prefer the **facade APIs** and pick a `Backend` (and for dense flow, an
`Algorithm`). Do **not** start from OpenCL/SYCL types unless you need
device-resident buffers or VA/DMA-BUF import.

## Primary API

| Need | Class | Choice |
|------|-------|--------|
| Dense DIS / Farneback / SEA-RAFT | `OpticalFlow` | `Backend` + `Algorithm` + `Preset` |
| Sparse PyrLK | `SparsePyrLK` | `Backend` (+ options) |

`Backend::Auto` resolves in this order:

1. OpenCL — if `OPTICALFLOW_ENABLE_OPENCL=ON` (primary GPU path)
2. SYCL — if `OPTICALFLOW_ENABLE_SYCL=ON` and the toolchain provides `-fsycl`
3. CPU — if `OPTICALFLOW_ENABLE_CPU=ON` (default)

```cpp
#include "optical_flow_sdk/optical_flow.hpp"

optical_flow_sdk::OpticalFlow of(optical_flow_sdk::Backend::Auto,
                                 optical_flow_sdk::Preset::Fast,
                                 optical_flow_sdk::Algorithm::Dis);
optical_flow_sdk::FlowField flow;
of.calc(prev, next, flow);  // resolved backend stays internal
```

Farneback / PyrLK samples: `samples/calc_flow_farneback.cpp`,
`samples/track_points.cpp`.

## Why OpenCL/SYCL types still exist

`OpenCLOpticalFlow` / `SyclOpticalFlow` (and their buffer types) are
**escape hatches** for zero-copy pipelines:

- Keep frames and flow on device across many frames (`calc_device`)
- VA / DMA-BUF import (`import_va_surface_luma`, …)
- On-device warp / FRUC (`warp_u8`)

They are not required for normal host apps. Host `OpticalFlow::calc` on a
GPU backend already uploads/downloads for you (with an H↔D tax).

## `calc` vs `calc_device` (advanced)

| API | Copies | Use when |
|-----|--------|----------|
| `OpticalFlow::calc` | H→D frames + D→H flow when GPU | Apps, tests, one-shot |
| `OpenCLOpticalFlow::calc_device` / `SyclOpticalFlow::calc_device` | Buffers stay on device | Media pipelines, speed gates, `gvaopticalflow` |

On Series 2 iGPU (OpenCL DIS Fast, device-resident):

- **Product speed gate:** ≥6× vs OpenCV CPU DIS-Fast @720p (met ~6.1×); ~5.7× @1080p
- **Host `OpticalFlow::calc`:** typically slower than resident — H↔D tax
- **SYCL `calc_device`:** catch-up path; OpenCL remains the primary GPU backend under `Auto`

See `samples/calc_flow_opencl_device.cpp` and
`benchmarks/microbench_opencl_resident.cpp` only when you need the escape hatch.

Neural Slow accuracy: `Algorithm::SeaRaft` + `docs/sea_raft.md` (OpenVINO;
not a `Backend` value).
