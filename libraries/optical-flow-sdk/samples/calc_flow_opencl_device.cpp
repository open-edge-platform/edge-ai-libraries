// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Advanced escape hatch: device-resident buffers for zero-copy pipelines.
// Prefer OpticalFlow(Backend::Auto, ...) for normal apps (docs/backend-selection.md).

#include "optical_flow_sdk/opencl_optical_flow.hpp"
#include "optical_flow_sdk/version.hpp"

#include <cmath>
#include <iostream>
#include <vector>

#if !OPTICALFLOW_HAS_OPENCL
#error "Build with -DOPTICALFLOW_ENABLE_OPENCL=ON"
#endif

int main() {
  constexpr int kW = 64;
  constexpr int kH = 48;
  std::vector<std::uint8_t> prev(static_cast<std::size_t>(kW) * kH);
  std::vector<std::uint8_t> next(prev.size());
  for (int y = 0; y < kH; ++y) {
    for (int x = 0; x < kW; ++x) {
      prev[static_cast<std::size_t>(y) * kW + x] = static_cast<std::uint8_t>(x + y);
      const int sx = std::max(0, x - 2);
      next[static_cast<std::size_t>(y) * kW + x] = prev[static_cast<std::size_t>(y) * kW + sx];
    }
  }

  optical_flow_sdk::OpenCLOpticalFlow of(optical_flow_sdk::Preset::Fast);
  auto d_prev = of.create_u8_image(kW, kH);
  auto d_next = of.create_u8_image(kW, kH);
  auto d_flow = of.create_flow_buffer(kW, kH);

  optical_flow_sdk::ImageView prev_view{prev.data(), kW, kH, 0};
  optical_flow_sdk::ImageView next_view{next.data(), kW, kH, 0};
  of.upload_u8(d_prev, prev_view);
  of.upload_u8(d_next, next_view);
  of.calc_device(d_prev, d_next, d_flow);

  optical_flow_sdk::FlowField flow;
  of.download_flow(d_flow, flow); // only for this sample printout

  double mag = 0.0;
  int n = 0;
  for (int y = 8; y < kH - 8; ++y) {
    for (int x = 8; x < kW - 8; ++x) {
      mag += std::hypot(flow.dx(x, y), flow.dy(x, y));
      ++n;
    }
  }
  std::cout << "backend=opencl path=calc_device mean |flow|=" << (mag / n) << "\n";
  return 0;
}
