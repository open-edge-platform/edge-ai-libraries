<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Device import / reduced-copy paths (P3)

Goal: avoid per-frame host luma packs where the pipeline allows it.

## APIs (`OpenCLOpticalFlow`)

| API | Role |
|-----|------|
| `upload_u8` | Host→device. Contiguous: `WriteBuffer`. **Strided** (NV12 Y): `WriteBufferRect` |
| `wrap_u8_image` | Non-owning wrap of an existing `cl_mem` |
| `supports_dmabuf_import` / `import_dmabuf_u8` | `cl_khr_external_memory` DMA-BUF → packed u8 |
| `opencl_set_va_display` | Bind `VADisplay*` **before** first OpenCL use |
| `supports_va_media_sharing` / `import_va_surface_luma` | `cl_intel_va_api_media_sharing`: VA plane0 → `OpenCLU8Image` |
| `copy_u8` / buffer swap | Device ping-pong (prev stays on GPU) |

Series 2 lab (`clinfo`): DMA-BUF external memory **and** `cl_intel_va_api_media_sharing`.

## Pipeline guidance

1. **System memory NV12/GRAY8:** map Y → strided `upload_u8` → `calc_device` → swap device prev/next (one H2D/frame).
2. **DMABuf:** `gst_dmabuf_memory_get_fd` → `import_dmabuf_u8` when packed; else strided upload.
3. **VAMemory:** element advertises VAMemory/DMABuf caps and binds VA display via
   `gst.va.display.handle` → `opencl_set_va_display`. Runtime path:
   `import_va_surface_luma(surface_id, dst)` then `calc_device`.
   **Lab note (2026-11-10):** `vainfo --display drm` fails (`iHD_drv_video.so`
   init) on `labrat`, so VA end-to-end smoke is blocked; API + caps are landed
   and system-memory path remains the validated gate.

## Caps

`gvaopticalflow` pad templates include `memory:VAMemory` and `memory:DMABuf`
(NV12) plus system-memory formats. Without a working VA display / surface
getter, the element falls back to system-memory mapping.
