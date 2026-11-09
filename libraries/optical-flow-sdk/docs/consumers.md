<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Downstream consumers (P3)

## Contract

| Meta | When | Fields |
|------|------|--------|
| `GstGVATensorMeta` | always (after frame 0) | `model_name=optical-flow-sdk`, `layer_name=flow`, FP32 NHWC `[1,H,W,2]` |
| `GstVideoRegionOfInterestMeta` | `emit-motion-rois=true` | `roi_type=optical-flow-motion`, block grid from `roi-block` / `roi-mag-threshold` |

## Element → consumer map

| Consumer | How to use today |
|----------|------------------|
| `gvapython` / apps | Read tensor meta (`examples/flow_consumer.py`) |
| `gvawatermark` | Enable `emit-motion-rois=true` so ROI boxes overlay; dense flow viz still future |
| `gvamotiondetect` | Complementary (frame-diff). Prefer flow ROIs via `emit-motion-rois` instead of chaining both for the same motion gate |
| `gvatrack` | Not wired yet. Future: feed flow-derived ROIs or a motion prior; today track still expects detector ROIs |

## Example

```bash
gst-launch-1.0 videotestsrc ! video/x-raw,format=NV12,width=640,height=480 ! \
  gvaopticalflow preset=fast device=GPU emit-motion-rois=true roi-mag-threshold=0.5 ! \
  # gvawatermark ! ...   # when running inside full DL Streamer
  fakesink
```
