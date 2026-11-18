// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// CPU-forced PyrLK. Prefer samples/track_points.cpp (Backend::Auto) for apps.
#include "optical_flow_sdk/sparse_pyrlk.hpp"

#include <algorithm>
#include <cmath>
#include <iostream>
#include <vector>

int main() {
  constexpr int kW = 160;
  constexpr int kH = 120;
  constexpr int kDx = 4;
  constexpr int kDy = -1;

  std::vector<std::uint8_t> prev(static_cast<std::size_t>(kW) * kH);
  for (int y = 0; y < kH; ++y)
    for (int x = 0; x < kW; ++x) {
      const float fx = 0.2f * x, fy = 0.15f * y;
      const float v = 128.0f + 55.0f * std::sin(fx) * std::cos(fy);
      prev[static_cast<std::size_t>(y) * kW + x] =
          static_cast<std::uint8_t>(std::clamp(v, 0.0f, 255.0f));
    }
  std::vector<std::uint8_t> next(prev.size(), 0);
  for (int y = 0; y < kH; ++y)
    for (int x = 0; x < kW; ++x) {
      const int sx = x - kDx, sy = y - kDy;
      if (sx >= 0 && sy >= 0 && sx < kW && sy < kH)
        next[static_cast<std::size_t>(y) * kW + x] = prev[static_cast<std::size_t>(sy) * kW + sx];
    }

  std::vector<optical_flow_sdk::Point2f> pts = {{40.f, 40.f}, {80.f, 60.f}, {120.f, 90.f}};
  std::vector<optical_flow_sdk::Point2f> tracked;
  std::vector<std::uint8_t> status;
  std::vector<float> err;

  optical_flow_sdk::SparsePyrLKOptions opts;
  opts.max_level = 2;
  opts.win_size = 15;
  optical_flow_sdk::SparsePyrLK lk(opts, optical_flow_sdk::Backend::Cpu);
  lk.calc({prev.data(), kW, kH, 0}, {next.data(), kW, kH, 0}, pts, tracked, status, err);

  for (std::size_t i = 0; i < pts.size(); ++i) {
    std::cout << "pt" << i << " (" << pts[i].x << "," << pts[i].y << ") -> (" << tracked[i].x
              << "," << tracked[i].y << ") status=" << static_cast<int>(status[i])
              << " err=" << err[i] << "\n";
  }
  return 0;
}
