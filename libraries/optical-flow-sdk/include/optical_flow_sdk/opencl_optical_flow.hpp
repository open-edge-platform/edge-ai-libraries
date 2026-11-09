// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include "optical_flow_sdk/backend.hpp"
#include "optical_flow_sdk/opencl_device.hpp"
#include "optical_flow_sdk/types.hpp"
#include "optical_flow_sdk/version.hpp"

#include <cstddef>
#include <cstdint>
#include <memory>

#if OPTICALFLOW_HAS_OPENCL

namespace optical_flow_sdk {

// Bind a VADisplay* before the first OpenCLOpticalFlow / shared context use so
// the OpenCL context is created with CL_CONTEXT_VA_API_DISPLAY_INTEL.
// No-op if display is null. Throws if context already exists with a different display.
void opencl_set_va_display(void *va_display);
void *opencl_va_display();

// OpenCL DIS backend: device-resident pyramid + patch inverse search + densify.
class OpenCLOpticalFlow {
public:
  explicit OpenCLOpticalFlow(Preset preset = Preset::Fast);
  ~OpenCLOpticalFlow();

  OpenCLOpticalFlow(OpenCLOpticalFlow &&) noexcept;
  OpenCLOpticalFlow &operator=(OpenCLOpticalFlow &&) noexcept;
  OpenCLOpticalFlow(const OpenCLOpticalFlow &) = delete;
  OpenCLOpticalFlow &operator=(const OpenCLOpticalFlow &) = delete;

  // Host path: H→D frames, kernels, D→H flow (wall includes copies).
  void calc(const ImageView &prev, const ImageView &next, FlowField &flow) const;
  void calc(const ImageView &prev, const ImageView &next, FlowField &flow, CostMap &cost) const;

  // Device-resident path: prev/next/flow stay on the GPU (no host flow readback).
  OpenCLU8Image create_u8_image(int width, int height) const;
  OpenCLFlowBuffer create_flow_buffer(int width, int height) const;
  // Non-owning wrap of an existing cl_mem (packed u8 luma). Caller keeps lifetime.
  OpenCLU8Image wrap_u8_image(void *cl_mem_handle, int width, int height) const;
  // Import a DMA-BUF fd as packed u8 luma via cl_khr_external_memory (when available).
  // `size_bytes` is the import size (typically stride * height for a Y plane).
  // Requires device support (clinfo: "External memory handle types: DMA buffer").
  OpenCLU8Image import_dmabuf_u8(int fd, std::size_t size_bytes, int width, int height) const;
  bool supports_dmabuf_import() const;
  bool supports_va_media_sharing() const;
  // Copy VA surface plane 0 (luma) into dst via cl_intel_va_api_media_sharing.
  // Requires opencl_set_va_display() before context creation. `va_surface_id` is VASurfaceID.
  void import_va_surface_luma(std::uint32_t va_surface_id, OpenCLU8Image &dst) const;
  void upload_u8(OpenCLU8Image &dst, const ImageView &src) const;
  void download_u8(const OpenCLU8Image &src, std::uint8_t *dst, std::size_t dst_bytes) const;
  void download_flow(const OpenCLFlowBuffer &src, FlowField &dst) const;
  void copy_u8(const OpenCLU8Image &src, OpenCLU8Image &dst) const;
  void calc_device(const OpenCLU8Image &prev, const OpenCLU8Image &next,
                  OpenCLFlowBuffer &flow) const;
  // Device-resident FRUC/warp: dst(x) = bilinear(src, x - t * flow). t=0.5 ≈ mid-frame.
  void warp_u8(const OpenCLU8Image &src, const OpenCLFlowBuffer &flow, OpenCLU8Image &dst,
               float t = 0.5f) const;
  void finish() const;

  Preset preset() const;

private:
  void calc_impl(const ImageView &prev, const ImageView &next, FlowField &flow, CostMap &cost,
                 bool want_cost) const;

  struct Impl;
  std::unique_ptr<Impl> impl_;
};

} // namespace optical_flow_sdk

#endif // OPTICALFLOW_HAS_OPENCL
