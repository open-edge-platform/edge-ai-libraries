// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <cstddef>
#include <cstdint>
#include <stdexcept>
#include <vector>

namespace optical_flow_sdk {

// Non-owning 8-bit single-channel image view (row-major).
struct ImageView {
  const std::uint8_t *data = nullptr;
  int width = 0;
  int height = 0;
  std::size_t stride = 0; // bytes per row; 0 means width

  std::size_t row_stride() const {
    return stride == 0 ? static_cast<std::size_t>(width) : stride;
  }

  void validate() const {
    if (data == nullptr || width <= 0 || height <= 0)
      throw std::invalid_argument("ImageView requires non-null data and positive size");
  }

  const std::uint8_t *row(int y) const { return data + static_cast<std::size_t>(y) * row_stride(); }
};

// Dense flow field, interleaved dx/dy floats (size = width * height * 2).
struct FlowField {
  int width = 0;
  int height = 0;
  std::vector<float> data; // [y * width + x] * 2 + {0:dx, 1:dy}

  void allocate(int w, int h) {
    if (w <= 0 || h <= 0)
      throw std::invalid_argument("FlowField size must be positive");
    width = w;
    height = h;
    data.assign(static_cast<std::size_t>(w) * static_cast<std::size_t>(h) * 2u, 0.0f);
  }

  float &dx(int x, int y) { return data[(static_cast<std::size_t>(y) * width + x) * 2u]; }
  float &dy(int x, int y) { return data[(static_cast<std::size_t>(y) * width + x) * 2u + 1u]; }
  float dx(int x, int y) const { return data[(static_cast<std::size_t>(y) * width + x) * 2u]; }
  float dy(int x, int y) const { return data[(static_cast<std::size_t>(y) * width + x) * 2u + 1u]; }
};

// Optional NVOFA-shaped cost map: higher cost => less accurate. 8-bit per pixel.
struct CostMap {
  int width = 0;
  int height = 0;
  std::vector<std::uint8_t> data;

  void allocate(int w, int h) {
    if (w <= 0 || h <= 0)
      throw std::invalid_argument("CostMap size must be positive");
    width = w;
    height = h;
    data.assign(static_cast<std::size_t>(w) * static_cast<std::size_t>(h), 0);
  }

  std::uint8_t &at(int x, int y) { return data[static_cast<std::size_t>(y) * width + x]; }
  std::uint8_t at(int x, int y) const { return data[static_cast<std::size_t>(y) * width + x]; }
};

} // namespace optical_flow_sdk
