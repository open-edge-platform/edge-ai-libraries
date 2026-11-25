// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Minimal flow-based warp (P4 FRUC/warp demo seed). CPU path: estimate DIS
// flow on a synthetic shift, then bilinear-sample `prev` toward `next`.

#include "optical_flow_sdk/optical_flow.hpp"

#include <algorithm>
#include <cmath>
#include <iostream>
#include <vector>

namespace {

float sample(const std::vector<std::uint8_t> &img, int w, int h, float x, float y) {
  x = std::clamp(x, 0.0f, static_cast<float>(w - 1));
  y = std::clamp(y, 0.0f, static_cast<float>(h - 1));
  const int x0 = static_cast<int>(x);
  const int y0 = static_cast<int>(y);
  const int x1 = std::min(x0 + 1, w - 1);
  const int y1 = std::min(y0 + 1, h - 1);
  const float dx = x - static_cast<float>(x0);
  const float dy = y - static_cast<float>(y0);
  const auto at = [&](int xx, int yy) {
    return static_cast<float>(img[static_cast<std::size_t>(yy) * w + xx]);
  };
  return (1.0f - dx) * (1.0f - dy) * at(x0, y0) + dx * (1.0f - dy) * at(x1, y0) +
         (1.0f - dx) * dy * at(x0, y1) + dx * dy * at(x1, y1);
}

} // namespace

int main() {
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

  optical_flow_sdk::OpticalFlow of(optical_flow_sdk::Backend::Cpu, optical_flow_sdk::Preset::Fast);
  optical_flow_sdk::FlowField flow;
  of.calc({prev.data(), kW, kH, 0}, {next.data(), kW, kH, 0}, flow);

  // Mid-frame FRUC-ish warp: sample prev at x - 0.5 * flow.
  std::vector<std::uint8_t> mid(prev.size());
  double err = 0.0;
  int n = 0;
  for (int y = 4; y < kH - 4; ++y) {
    for (int x = 4; x < kW - 4; ++x) {
      const float dx = flow.dx(x, y);
      const float dy = flow.dy(x, y);
      const float v = sample(prev, kW, kH, static_cast<float>(x) - 0.5f * dx,
                             static_cast<float>(y) - 0.5f * dy);
      mid[static_cast<std::size_t>(y) * kW + x] =
          static_cast<std::uint8_t>(std::clamp(v + 0.5f, 0.0f, 255.0f));
      // Ideal mid for pure +kShift is halfway between prev and next gray.
      const float ideal = 0.5f * (static_cast<float>(prev[static_cast<std::size_t>(y) * kW + x]) +
                                  static_cast<float>(next[static_cast<std::size_t>(y) * kW + x]));
      err += std::fabs(v - ideal);
      ++n;
    }
  }

  std::cout << "warp_with_flow mean |mid-ideal|=" << (err / n) << " (synthetic shift=" << kShift
            << ")\n";
  return 0;
}
