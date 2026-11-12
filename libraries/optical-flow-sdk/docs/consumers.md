<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Downstream consumers (P3)

## Contract

| Meta | When | Fields |
|------|------|--------|
| `GstGVATensorMeta` | always (after frame 0) | `model_name=optical-flow-sdk`, `layer_name=flow`, FP32 NHWC `[1,H,W,2]` |
| `GstVideoRegionOfInterestMeta` | `emit-motion-rois=true` or `track-motion-rois=true` | `roi_type=optical-flow-motion` + `detection` params (see below) |
| `object_id` param on ROI | `track-motion-rois=true` | `id` (int) — standalone IoU prior |

### Detection-shaped ROI (gvatrack-compatible)

Each motion block attaches a `detection` GstStructure matching `gvadetect` /
`gvatrack` expectations:

| Field | Type | Meaning |
|-------|------|---------|
| `confidence` | double | Scaled from mean \|flow\| vs `roi-mag-threshold` |
| `label_id` | int | `0` (`optical-flow-motion`) |
| `x_min`/`x_max`/`y_min`/`y_max` | double | Normalized to frame size |
| `model_name` | string | `optical-flow-sdk` |
| `layer_name` | string | `motion-roi` |

With `track-motion-rois=true`, an `object_id` structure (`id=int`) is also
attached via greedy IoU association (`track-iou-threshold`, default 0.3).

## Element → consumer map

| Consumer | How to use today |
|----------|------------------|
| `gvapython` / apps | Tensor meta (`examples/flow_consumer.py`); ROI+track (`examples/flow_track_consumer.py`) |
| `gvawatermark` | `emit-motion-rois=true` or `track-motion-rois=true` for ROI boxes |
| `gvamotiondetect` | Complementary (frame-diff). Prefer flow ROIs instead of chaining both |
| `gvatrack` | **Wired via detection-shaped ROIs** — feed `emit-motion-rois=true` into `gvatrack tracking-type=zero-term-imageless` (or use built-in `track-motion-rois` when DL Streamer `gvatrack` is absent) |

## Examples

Standalone (Series 2 lab plugin — no DL Streamer required):

```bash
gst-launch-1.0 videotestsrc pattern=ball ! video/x-raw,format=NV12,width=640,height=480 ! \
  gvaopticalflow preset=fast device=GPU track-motion-rois=true roi-mag-threshold=0.5 ! \
  fakesink
python3 examples/flow_track_consumer.py
```

Full consumer-chain smoke (gvatrack prior + watermark draw; no DL Streamer plugins):

```bash
export GST_PLUGIN_PATH=.../integrations/gvaopticalflow/build
python3 examples/flow_full_chain.py
# frames>0 with_roi>0 tracked_frames>0 unique_object_ids>0 watermarked>0 → PASS
```

**Lab PASS 2026-11-10** on Series 2 (`flow_full_chain.py`): track-motion-rois →
`object_id` association → NV12 box watermark. `gvamotiondetect` is intentionally
not chained (complementary frame-diff).

Full DL Streamer (when plugins are installed):

```bash
... ! gvaopticalflow preset=fast device=GPU emit-motion-rois=true roi-mag-threshold=0.5 ! \
  gvatrack tracking-type=zero-term-imageless ! \
  gvawatermark ! ...
```

`zero-term-imageless` is the natural match: motion ROIs are already imageless
detections; gvatrack assigns / refreshes `object_id` from IoU. Short-term /
Deep SORT need appearance features and are optional follow-ons.
