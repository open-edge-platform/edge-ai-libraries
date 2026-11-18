// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "optical_flow_sdk/optical_flow.hpp"

#include <cmath>
#include <iostream>
#include <vector>

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

  optical_flow_sdk::OpticalFlow of(optical_flow_sdk::Backend::Cpu,
                                   optical_flow_sdk::Preset::Fast);
  optical_flow_sdk::FlowField flow;
  of.calc({prev.data(), kW, kH, 0}, {next.data(), kW, kH, 0}, flow);

  double mag = 0.0;
  int n = 0;
  for (int y = 8; y < kH - 8; ++y) {
    for (int x = 8; x < kW - 8; ++x) {
      mag += std::hypot(flow.dx(x, y), flow.dy(x, y));
      ++n;
    }
  }
  std::cout << "backend=" << optical_flow_sdk::backend_name(of.backend())
            << " mean |flow|=" << (mag / n) << "\n";
  return 0;
}
