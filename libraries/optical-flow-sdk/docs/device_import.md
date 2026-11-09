<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Device import / reduced-copy paths (P3)

Goal: avoid per-frame host luma packs where the pipeline allows it.

## APIs (`OpenCLOpticalFlow`)

| API | Role |
|-----|------|
| `upload_u8` | Host→device. Contiguous: `WriteBuffer`. **Strided** (NV12 Y): `WriteBufferRect` — no host pack buffer |
| `wrap_u8_image` | Non-owning wrap of an existing `cl_mem` |
| `supports_dmabuf_import` | True when platform advertises `cl_khr_external_memory` |
| `import_dmabuf_u8(fd, size, w, h)` | Import DMA-BUF as packed u8 luma (`clCreateBufferWithProperties`) |
| `copy_u8` / buffer swap | Keep the previous frame on-device (ping-pong) |

Series 2 lab (`clinfo`): `cl_khr_external_memory` + **External memory handle types: DMA buffer**, plus `cl_intel_va_api_media_sharing`.

## Pipeline guidance

1. **System memory NV12/GRAY8 (current `gvaopticalflow`):** map Y plane → `upload_u8` with stride → `calc_device` → swap device prev/next. Only one H2D of the new frame; flow D2H only for `GstGVATensorMeta` v0.
2. **DMABuf:** `gst_dmabuf_memory_get_fd` → `import_dmabuf_u8` when Y is packed (`stride == width`). If `stride != width`, prefer strided `upload_u8` until a pitch-aware kernel exists.
3. **VAMemory:** export DMA-BUF from the VA surface (or use `cl_intel_va_api_media_sharing`) then import/wrap. Full VA→CL sharing is the remaining resident upgrade.

## Caps note

`gvaopticalflow` v0 still advertises system-memory raw video. DMABuf/VAMemory
pad templates land with the VA sharing path.
