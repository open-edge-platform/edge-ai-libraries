// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include "optical_flow_sdk/version.hpp"

#if OPTICALFLOW_HAS_OPENCL

#include <cstddef>
#include <cstdint>
#include <utility>

namespace optical_flow_sdk {

// Owning OpenCL buffer for a packed u8 image (width * height bytes).
// `handle` is a cl_mem stored as void* so public headers need no CL/cl.h.
class OpenCLU8Image {
public:
  OpenCLU8Image() = default;
  OpenCLU8Image(void *handle, int width, int height, bool owns);
  ~OpenCLU8Image();

  OpenCLU8Image(OpenCLU8Image &&other) noexcept;
  OpenCLU8Image &operator=(OpenCLU8Image &&other) noexcept;
  OpenCLU8Image(const OpenCLU8Image &) = delete;
  OpenCLU8Image &operator=(const OpenCLU8Image &) = delete;

  void *handle() const { return handle_; }
  int width() const { return width_; }
  int height() const { return height_; }
  bool empty() const { return handle_ == nullptr; }
  std::size_t bytes() const {
    return static_cast<std::size_t>(width_) * static_cast<std::size_t>(height_);
  }

  void *release() {
    owns_ = false;
    void *out = handle_;
    handle_ = nullptr;
    width_ = height_ = 0;
    return out;
  }

private:
  void *handle_ = nullptr;
  int width_ = 0;
  int height_ = 0;
  bool owns_ = false;
};

// Owning OpenCL buffer for interleaved float2 flow (width * height * 2 floats).
class OpenCLFlowBuffer {
public:
  OpenCLFlowBuffer() = default;
  OpenCLFlowBuffer(void *handle, int width, int height, bool owns);
  ~OpenCLFlowBuffer();

  OpenCLFlowBuffer(OpenCLFlowBuffer &&other) noexcept;
  OpenCLFlowBuffer &operator=(OpenCLFlowBuffer &&other) noexcept;
  OpenCLFlowBuffer(const OpenCLFlowBuffer &) = delete;
  OpenCLFlowBuffer &operator=(const OpenCLFlowBuffer &) = delete;

  void *handle() const { return handle_; }
  int width() const { return width_; }
  int height() const { return height_; }
  bool empty() const { return handle_ == nullptr; }
  std::size_t floats() const {
    return static_cast<std::size_t>(width_) * static_cast<std::size_t>(height_) * 2u;
  }
  std::size_t bytes() const { return floats() * sizeof(float); }

  void *release() {
    owns_ = false;
    void *out = handle_;
    handle_ = nullptr;
    width_ = height_ = 0;
    return out;
  }

private:
  void *handle_ = nullptr;
  int width_ = 0;
  int height_ = 0;
  bool owns_ = false;
};

} // namespace optical_flow_sdk

#endif // OPTICALFLOW_HAS_OPENCL
