// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "optical_flow_sdk/optical_flow.hpp"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <vector>

namespace {

std::vector<std::uint8_t> make_textured(int w, int h) {
  std::vector<std::uint8_t> img(static_cast<std::size_t>(w) * h);
  for (int y = 0; y < h; ++y) {
    for (int x = 0; x < w; ++x) {
      const float fx = 0.21f * x, fy = 0.17f * y;
      const float v = 128.0f + 60.0f * std::sin(fx) * std::cos(fy) +
                      40.0f * std::sin(fx * 2.3f + fy * 1.7f);
      img[static_cast<std::size_t>(y) * w + x] =
          static_cast<std::uint8_t>(std::clamp(v, 0.0f, 255.0f));
    }
  }
  return img;
}

std::vector<std::uint8_t> shift_image(const std::vector<std::uint8_t> &src, int w, int h, int dx,
                                      int dy) {
  std::vector<std::uint8_t> dst(src.size(), 0);
  for (int y = 0; y < h; ++y) {
    for (int x = 0; x < w; ++x) {
      const int sx = x - dx;
      const int sy = y - dy;
      if (sx >= 0 && sy >= 0 && sx < w && sy < h)
        dst[static_cast<std::size_t>(y) * w + x] = src[static_cast<std::size_t>(sy) * w + sx];
    }
  }
  return dst;
}

} // namespace

int main() {
  using namespace optical_flow_sdk;
  constexpr int kW = 96;
  constexpr int kH = 72;
  constexpr int kDx = 2;
  constexpr int kDy = -1;
  const auto prev = make_textured(kW, kH);
  const auto next = shift_image(prev, kW, kH, kDx, kDy);

  OpticalFlow of(Backend::Cpu, Preset::Fast, Algorithm::Farneback);
  FlowField flow;
  of.calc({prev.data(), kW, kH, 0}, {next.data(), kW, kH, 0}, flow);

  double sum = 0.0;
  int n = 0;
  for (int y = 16; y < kH - 16; ++y) {
    for (int x = 16; x < kW - 16; ++x) {
      const double eu = flow.dx(x, y) - kDx;
      const double ev = flow.dy(x, y) - kDy;
      sum += std::sqrt(eu * eu + ev * ev);
      ++n;
    }
  }
  const double epe = sum / n;
  std::cout << "farneback synthetic EPE=" << epe << "\n";
  if (epe > 1.5) {
    std::cerr << "Farneback EPE too high\n";
    return EXIT_FAILURE;
  }
  return EXIT_SUCCESS;
}
