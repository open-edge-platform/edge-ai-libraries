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
| `fruc_opencl` | `samples/fruc_opencl.cpp` | `calc_device` → `warp_u8(t=0.5)` synthetic pair |
| `fruc_video_opencl` | `samples/fruc_video_opencl.cpp` | Multi-frame clip @720p/1080p; pipeline + resident ms |
| `OpenCLOpticalFlow::warp_u8` | `opencl_optical_flow.hpp` | `dst(x) = bilinear(src, x - t·flow)` |

```bash
# Synthetic pan clip (default 16 frames)
./sample_fruc_video_opencl 720
./sample_fruc_video_opencl 1080 24

# Optional packed gray file: N frames of W×H uint8
./sample_fruc_video_opencl --raw 1280 720 16 clip.gray
```

## Planned

1. Optional gst-launch snippet once `gvaopticalflow` lab smoke passes
2. Nvidia host FRUC comparison (gated on NVOFA hardware)

Report wall ms next to DIS Fast resident numbers from
`microbench_opencl_resident`.
