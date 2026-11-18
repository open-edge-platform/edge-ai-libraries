// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// OpenCL FRUC seed: calc_device → warp_u8(t=0.5) on synthetic shift (no host flow).

#include "optical_flow_sdk/opencl_optical_flow.hpp"

#include <algorithm>
#include <cmath>
#include <iostream>
#include <vector>

int main() {
#if !OPTICALFLOW_HAS_OPENCL
  std::cerr << "OpenCL not enabled\n";
  return 1;
#else
  constexpr int kW = 96;
  constexpr int kH = 64;
  constexpr int kShift = 3;
  std::vector<std::uint8_t> prev(static_cast<std::size_t>(kW) * kH);
  std::vector<std::uint8_t> next(prev.size());
  for (int y = 0; y < kH; ++y) {
    for (int x = 0; x < kW; ++x) {
      const float v = 128.0f + 60.0f * std::sin(0.21f * x) * std::cos(0.17f * y);
      prev[static_cast<std::size_t>(y) * kW + x] =
          static_cast<std::uint8_t>(std::clamp(v, 0.0f, 255.0f));
    }
  }
  for (int y = 0; y < kH; ++y) {
    for (int x = 0; x < kW; ++x) {
      const int sx = std::max(0, x - kShift);
      next[static_cast<std::size_t>(y) * kW + x] = prev[static_cast<std::size_t>(y) * kW + sx];
    }
  }

  optical_flow_sdk::OpenCLOpticalFlow of(optical_flow_sdk::Preset::Fast);
  auto d_prev = of.create_u8_image(kW, kH);
  auto d_next = of.create_u8_image(kW, kH);
  auto d_flow = of.create_flow_buffer(kW, kH);
  auto d_mid = of.create_u8_image(kW, kH);
  of.upload_u8(d_prev, {prev.data(), kW, kH, 0});
  of.upload_u8(d_next, {next.data(), kW, kH, 0});
  of.calc_device(d_prev, d_next, d_flow);
  of.warp_u8(d_prev, d_flow, d_mid, /*t=*/0.5f);
  of.finish();

  std::vector<std::uint8_t> mid(prev.size());
  of.download_u8(d_mid, mid.data(), mid.size());

  double err = 0.0;
  int n = 0;
  for (int y = 4; y < kH - 4; ++y) {
    for (int x = 4; x < kW - 4; ++x) {
      const float v = static_cast<float>(mid[static_cast<std::size_t>(y) * kW + x]);
      const float ideal = 0.5f * (static_cast<float>(prev[static_cast<std::size_t>(y) * kW + x]) +
                                  static_cast<float>(next[static_cast<std::size_t>(y) * kW + x]));
      err += std::fabs(v - ideal);
      ++n;
    }
  }

  std::cout << "fruc_opencl path=calc_device+warp_u8 mean |mid-ideal|=" << (err / n)
            << " (synthetic shift=" << kShift << ")\n";
  return 0;
#endif
}
