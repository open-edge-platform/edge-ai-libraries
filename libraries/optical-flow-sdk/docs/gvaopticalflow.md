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

- `device=GPU` / `AUTO` + OpenCL SDK build → map NV12/GRAY8 Y → strided
  `upload_u8` → `calc_device` with **device ping-pong** (prev stays on GPU);
  flow D2H only for tensor meta (v0). See `docs/device_import.md`.
- `device=CPU` → `OpticalFlow` CPU facade.
- DMA-BUF import API: `import_dmabuf_u8` (lab-supported). VAMemory pad
  templates + VA↔CL sharing still open.

## Consumers

| Consumer | v0 | Notes |
|----------|----|-------|
| `gvapython` / custom apps | Yes | Read `GstGVATensorMeta` by `model_name` / `layer_name` |
| `gvatrack` | Not yet | Needs flow→track prior or ROI bridge |
| `gvamotiondetect` | Not yet | Frame-diff today; optional flow magnitude ROI later |
| `gvawatermark` | Not yet | Flow visualization follow-on |

## Status

Scaffold on dlstreamer `feat/gvaopticalflow` + standalone lab build under
`integrations/gvaopticalflow/`. **Lab smoke PASS**; device ping-pong +
DMA-BUF import API + `examples/flow_consumer.py` landed 2026-11-10.
**Open:** VAMemory pads / VA↔CL sharing, track/motion/watermark hooks,
dlstreamer upstream PR (deferred). See PLAN §11.7.
