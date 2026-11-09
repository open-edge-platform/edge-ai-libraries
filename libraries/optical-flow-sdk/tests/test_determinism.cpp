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
      const float v = 128.0f + 60.0f * std::sin(fx) * std::cos(fy);
      img[static_cast<std::size_t>(y) * w + x] =
          static_cast<std::uint8_t>(std::clamp(v, 0.0f, 255.0f));
    }
  }
  return img;
}

bool same_flow(const optical_flow_sdk::FlowField &a, const optical_flow_sdk::FlowField &b) {
  if (a.width != b.width || a.height != b.height || a.data.size() != b.data.size())
    return false;
  for (std::size_t i = 0; i < a.data.size(); ++i) {
    if (a.data[i] != b.data[i])
      return false;
  }
  return true;
}

} // namespace

int main() {
  using namespace optical_flow_sdk;
  constexpr int kW = 64;
  constexpr int kH = 48;
  auto prev = make_textured(kW, kH);
  auto next = prev;
  for (int y = 0; y < kH; ++y)
    for (int x = 2; x < kW; ++x)
      next[static_cast<std::size_t>(y) * kW + x] = prev[static_cast<std::size_t>(y) * kW + x - 2];

  ImageView p{prev.data(), kW, kH, 0};
  ImageView n{next.data(), kW, kH, 0};
  OpticalFlow of(Backend::Cpu, Preset::Fast, Algorithm::Dis);

  FlowField first;
  of.calc(p, n, first);
  for (int run = 0; run < 4; ++run) {
    FlowField again;
    of.calc(p, n, again);
    if (!same_flow(first, again)) {
      std::cerr << "determinism failure on run " << run << "\n";
      return EXIT_FAILURE;
    }
  }

  FlowField fwd, bwd;
  of.calcBoth(p, n, fwd, bwd);
  // Forward should match standalone calc; backward should be roughly opposite
  // on a pure translation (median check).
  if (!same_flow(first, fwd)) {
    std::cerr << "calcBoth forward mismatch\n";
    return EXIT_FAILURE;
  }

  double med_bx = 0.0, med_by = 0.0;
  int count = 0;
  for (int y = 8; y < kH - 8; ++y) {
    for (int x = 8; x < kW - 8; ++x) {
      med_bx += bwd.dx(x, y);
      med_by += bwd.dy(x, y);
      ++count;
    }
  }
  med_bx /= count;
  med_by /= count;
  std::cout << "determinism ok; mean_bwd=(" << med_bx << "," << med_by << ")\n";
  if (std::fabs(med_bx - (-2.0)) > 1.5 || std::fabs(med_by) > 1.0) {
    std::cerr << "calcBoth backward not opposite of +2x translation\n";
    return EXIT_FAILURE;
  }
  return EXIT_SUCCESS;
}
