# `gvaopticalflow` (P3) — metadata contract

Element home: **DL Streamer** (`src/monolithic/gst/elements/gvaopticalflow/`),
not this SDK tree. Build with `-DENABLE_OPTICAL_FLOW=ON` against an installed
`optical_flow_sdk` package.

## Pipeline

```bash
decodebin3 ! videoconvert ! video/x-raw,format=NV12 ! \
  gvaopticalflow preset=fast device=GPU ! …
```

## Metadata (v0)

Dense flow is attached as `GstGVATensorMeta`:

| Field | Value |
|-------|-------|
| `model_name` | `optical-flow-sdk` |
| `layer_name` | `flow` |
| `format` | `optical_flow_dense` |
| `precision` | FP32 |
| `layout` | NHWC |
| `dims` | `[1, H, W, 2]` interleaved `dx`, `dy` (pixels/frame) |

Optional `attach-cost=true` adds a second meta with `layer_name=cost`
(U8 HxW).

## Device path

- `device=GPU` / `AUTO` + OpenCL SDK build → `OpenCLOpticalFlow::calc_device`
  after H2D luma upload; flow downloaded only to fill tensor meta (v0).
- `device=CPU` → `OpticalFlow` CPU facade.
- VAMemory / DMABuf → OpenCL import (no host luma copy) is the P3 resident
  upgrade; not in v0.

## Consumers

| Consumer | v0 | Notes |
|----------|----|-------|
| `gvapython` / custom apps | Yes | Read `GstGVATensorMeta` by `model_name` / `layer_name` |
| `gvatrack` | Not yet | Needs flow→track prior or ROI bridge |
| `gvamotiondetect` | Not yet | Frame-diff today; optional flow magnitude ROI later |
| `gvawatermark` | Not yet | Flow visualization follow-on |

## Status

Scaffold landed 2026-11-10 on dlstreamer branch `feat/gvaopticalflow`
(sibling checkout). Lab smoke and VAMemory upgrade remain.
