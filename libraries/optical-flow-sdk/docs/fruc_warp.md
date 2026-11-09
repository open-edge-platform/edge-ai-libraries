<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# FRUC / warp demos (P4)

Goal: show optical-flow SDK value beyond raw dx/dy — **frame interpolation
(FRUC)** and **flow-based warping** on Core Ultra Series 2 iGPU.

## Landed

| Sample / API | Path | Notes |
|--------------|------|-------|
| `warp_with_flow` | `samples/warp_with_flow.cpp` | CPU DIS + host bilinear mid-frame warp |
| `fruc_opencl` | `samples/fruc_opencl.cpp` | `calc_device` → `warp_u8(t=0.5)` device-resident |
| `OpenCLOpticalFlow::warp_u8` | `opencl_optical_flow.hpp` | `dst(x) = bilinear(src, x - t·flow)` |

## Planned

1. Real video clip demo (stabilize / interpolate) under `samples/`
2. Optional gst-launch snippet once `gvaopticalflow` lab smoke passes
3. Report wall ms @720p/1080p next to DIS Fast resident numbers

Nvidia host FRUC comparison stays gated on available NVOFA hardware (PLAN P4).
