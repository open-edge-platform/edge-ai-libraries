// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "optical_flow_sdk/sparse_pyrlk.hpp"

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
  constexpr int kW = 128;
  constexpr int kH = 96;
  constexpr int kDx = 3;
  constexpr int kDy = -2;
  const auto prev = make_textured(kW, kH);
  const auto next = shift_image(prev, kW, kH, kDx, kDy);

  std::vector<Point2f> pts = {{32.f, 32.f}, {64.f, 48.f}, {90.f, 60.f}, {40.f, 70.f}};
  std::vector<Point2f> tracked;
  std::vector<std::uint8_t> status;
  std::vector<float> err;

  SparsePyrLKOptions opts;
  opts.max_level = 2;
  opts.win_size = 11;
  SparsePyrLK lk(opts);
  lk.calc({prev.data(), kW, kH, 0}, {next.data(), kW, kH, 0}, pts, tracked, status, err);

  int ok = 0;
  double sum = 0.0;
  for (std::size_t i = 0; i < pts.size(); ++i) {
    if (!status[i])
      continue;
    const double eu = tracked[i].x - (pts[i].x + kDx);
    const double ev = tracked[i].y - (pts[i].y + kDy);
    sum += std::sqrt(eu * eu + ev * ev);
    ++ok;
  }
  if (ok < 3) {
    std::cerr << "too few tracked points: " << ok << "\n";
    return EXIT_FAILURE;
  }
  const double epe = sum / ok;
  std::cout << "sparse pyrlk point EPE=" << epe << " tracked=" << ok << "\n";
  if (epe > 1.0) {
    std::cerr << "PyrLK EPE too high\n";
    return EXIT_FAILURE;
  }
  return EXIT_SUCCESS;
}
