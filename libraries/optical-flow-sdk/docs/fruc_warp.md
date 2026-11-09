<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# FRUC / warp demos (P4)

Goal: show optical-flow SDK value beyond raw dx/dy — **frame interpolation
(FRUC)** and **flow-based warping** on Core Ultra Series 2 iGPU.

## Seed (landed)

| Sample | Path | Notes |
|--------|------|-------|
| `warp_with_flow` | `samples/warp_with_flow.cpp` | CPU DIS + bilinear mid-frame warp on synthetic shift |

## Planned

1. OpenCL path: `calc_device` → device or host warp kernel (no full D2H when possible)
2. Real video clip demo (stabilize / interpolate) under `samples/`
3. Optional gst-launch snippet once `gvaopticalflow` lab smoke passes
4. Report wall ms @720p/1080p next to DIS Fast resident numbers

Nvidia host FRUC comparison stays gated on available NVOFA hardware (PLAN P4).
