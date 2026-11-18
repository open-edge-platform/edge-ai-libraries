// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "optical_flow_sdk/sycl_optical_flow.hpp"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <vector>

int main() {
#if !OPTICALFLOW_HAS_SYCL
  return 0;
#else
  constexpr int kW = 64;
  constexpr int kH = 48;
  constexpr int kDx = 2;
  std::vector<std::uint8_t> prev(static_cast<std::size_t>(kW) * kH);
  std::vector<std::uint8_t> next(prev.size(), 0);
  for (int y = 0; y < kH; ++y) {
    for (int x = 0; x < kW; ++x) {
      const float v = 128.0f + 50.0f * std::sin(0.2f * x) * std::cos(0.15f * y);
      prev[static_cast<std::size_t>(y) * kW + x] =
          static_cast<std::uint8_t>(std::clamp(v, 0.0f, 255.0f));
    }
  }
  for (int y = 0; y < kH; ++y) {
    for (int x = kDx; x < kW; ++x)
      next[static_cast<std::size_t>(y) * kW + x] = prev[static_cast<std::size_t>(y) * kW + (x - kDx)];
  }

  optical_flow_sdk::SyclOpticalFlow of(optical_flow_sdk::Preset::Fast);
  auto d_prev = of.create_u8_image(kW, kH);
  auto d_next = of.create_u8_image(kW, kH);
  auto d_flow = of.create_flow_buffer(kW, kH);
  of.upload_u8(d_prev, {prev.data(), kW, kH, 0});
  of.upload_u8(d_next, {next.data(), kW, kH, 0});
  of.calc_device(d_prev, d_next, d_flow);
  of.finish();

  optical_flow_sdk::FlowField flow;
  of.download_flow(d_flow, flow);
  double epe = 0.0;
  int n = 0;
  for (int y = 8; y < kH - 8; ++y) {
    for (int x = 8; x < kW - 8; ++x) {
      const double eu = flow.dx(x, y) - kDx;
      const double ev = flow.dy(x, y);
      epe += std::sqrt(eu * eu + ev * ev);
      ++n;
    }
  }
  epe /= n;
  std::cout << "sycl calc_device synthetic EPE=" << epe << "\n";
  if (epe > 2.0) {
    std::cerr << "SYCL calc_device EPE too high\n";
    return EXIT_FAILURE;
  }
  return EXIT_SUCCESS;
#endif
}
