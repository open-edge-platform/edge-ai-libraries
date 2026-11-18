// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include "optical_flow_sdk/version.hpp"

#if OPTICALFLOW_HAS_SYCL

#include <cstddef>
#include <cstdint>
#include <utility>

namespace optical_flow_sdk {

// Owning SYCL USM device buffer for packed u8 luma (width * height).
// `handle` is a device pointer stored as void* so public headers need no sycl.hpp.
class SyclU8Image {
public:
  SyclU8Image() = default;
  SyclU8Image(void *handle, int width, int height, bool owns);
  ~SyclU8Image();

  SyclU8Image(SyclU8Image &&other) noexcept;
  SyclU8Image &operator=(SyclU8Image &&other) noexcept;
  SyclU8Image(const SyclU8Image &) = delete;
  SyclU8Image &operator=(const SyclU8Image &) = delete;

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

// Owning SYCL USM device buffer for interleaved float2 flow.
class SyclFlowBuffer {
public:
  SyclFlowBuffer() = default;
  SyclFlowBuffer(void *handle, int width, int height, bool owns);
  ~SyclFlowBuffer();

  SyclFlowBuffer(SyclFlowBuffer &&other) noexcept;
  SyclFlowBuffer &operator=(SyclFlowBuffer &&other) noexcept;
  SyclFlowBuffer(const SyclFlowBuffer &) = delete;
  SyclFlowBuffer &operator=(const SyclFlowBuffer &) = delete;

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

#endif // OPTICALFLOW_HAS_SYCL
