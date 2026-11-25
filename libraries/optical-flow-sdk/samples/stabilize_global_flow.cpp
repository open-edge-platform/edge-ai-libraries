// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

// Toy stabilisation: estimate global translation from dense flow median and
// report the compensating shift. Full warp demo needs an image I/O dependency;
// this sample stays header-light and validates the flow→motion path.

#include "optical_flow_sdk/optical_flow.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <vector>

namespace {

std::vector<std::uint8_t> make_textured(int w, int h) {
  std::vector<std::uint8_t> img(static_cast<std::size_t>(w) * h);
  for (int y = 0; y < h; ++y)
    for (int x = 0; x < w; ++x) {
      const float fx = 0.21f * static_cast<float>(x);
      const float fy = 0.17f * static_cast<float>(y);
      const float v = 128.0f + 60.0f * std::sin(fx) * std::cos(fy) +
                      40.0f * std::sin(fx * 2.3f + fy * 1.7f);
      img[static_cast<std::size_t>(y) * w + x] =
          static_cast<std::uint8_t>(std::clamp(v, 0.0f, 255.0f));
    }
  return img;
}

} // namespace

int main() {
  constexpr int kW = 160;
  constexpr int kH = 120;
  constexpr int kShakeX = 5;
  constexpr int kShakeY = -3;

  const auto prev = make_textured(kW, kH);
  std::vector<std::uint8_t> next(prev.size(), 0);
  for (int y = 0; y < kH; ++y) {
    for (int x = 0; x < kW; ++x) {
      const int sx = x - kShakeX;
      const int sy = y - kShakeY;
      if (sx >= 0 && sy >= 0 && sx < kW && sy < kH)
        next[static_cast<std::size_t>(y) * kW + x] = prev[static_cast<std::size_t>(sy) * kW + sx];
    }
  }

  optical_flow_sdk::OpticalFlow of(optical_flow_sdk::Backend::Cpu,
                                   optical_flow_sdk::Preset::Medium);
  optical_flow_sdk::FlowField flow;
  of.calc({prev.data(), kW, kH, 0}, {next.data(), kW, kH, 0}, flow);

  std::vector<float> xs;
  std::vector<float> ys;
  xs.reserve(static_cast<std::size_t>(kW * kH));
  ys.reserve(xs.capacity());
  for (int y = 10; y < kH - 10; ++y) {
    for (int x = 10; x < kW - 10; ++x) {
      xs.push_back(flow.dx(x, y));
      ys.push_back(flow.dy(x, y));
    }
  }
  const auto mid = xs.size() / 2;
  std::nth_element(xs.begin(), xs.begin() + static_cast<std::ptrdiff_t>(mid), xs.end());
  std::nth_element(ys.begin(), ys.begin() + static_cast<std::ptrdiff_t>(mid), ys.end());
  const float med_x = xs[mid];
  const float med_y = ys[mid];

  std::cout << "induced_shake=(" << kShakeX << "," << kShakeY << ")\n"
            << "median_flow=(" << med_x << "," << med_y << ")\n"
            << "compensate_shift=(" << -med_x << "," << -med_y << ")\n";
  if (std::fabs(med_x - kShakeX) > 2.0f || std::fabs(med_y - kShakeY) > 2.0f) {
    std::cerr << "stabilisation median too far from induced shake\n";
    return 1;
  }
  return 0;
}
