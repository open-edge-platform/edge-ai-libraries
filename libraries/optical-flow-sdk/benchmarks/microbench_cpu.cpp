// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "optical_flow_sdk/optical_flow.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <iostream>
#include <vector>

namespace {

std::vector<std::uint8_t> make_textured(int w, int h) {
  std::vector<std::uint8_t> img(static_cast<std::size_t>(w) * h);
  for (int y = 0; y < h; ++y) {
    for (int x = 0; x < w; ++x) {
      const float v = 128.0f + 60.0f * std::sin(0.21f * x) * std::cos(0.17f * y);
      img[static_cast<std::size_t>(y) * w + x] =
          static_cast<std::uint8_t>(std::clamp(v, 0.0f, 255.0f));
    }
  }
  return img;
}

std::vector<std::uint8_t> shift(const std::vector<std::uint8_t> &src, int w, int h, int dx) {
  std::vector<std::uint8_t> dst(src.size(), 0);
  for (int y = 0; y < h; ++y) {
    for (int x = std::max(0, dx); x < w; ++x)
      dst[static_cast<std::size_t>(y) * w + x] = src[static_cast<std::size_t>(y) * w + (x - dx)];
  }
  return dst;
}

double run_preset(optical_flow_sdk::Preset preset, int w, int h, int warmup, int iters) {
  const auto prev = make_textured(w, h);
  const auto next = shift(prev, w, h, 3);
  optical_flow_sdk::OpticalFlow of(optical_flow_sdk::Backend::Cpu, preset);
  optical_flow_sdk::FlowField flow;
  optical_flow_sdk::ImageView p{prev.data(), w, h, 0};
  optical_flow_sdk::ImageView n{next.data(), w, h, 0};
  for (int i = 0; i < warmup; ++i)
    of.calc(p, n, flow);
  const auto t0 = std::chrono::steady_clock::now();
  for (int i = 0; i < iters; ++i)
    of.calc(p, n, flow);
  const auto t1 = std::chrono::steady_clock::now();
  return std::chrono::duration<double, std::milli>(t1 - t0).count() / iters;
}

} // namespace

int main() {
  struct Case {
    int w;
    int h;
  };
  const Case cases[] = {{640, 360}, {1280, 720}};
  for (const auto &c : cases) {
    for (auto preset : {optical_flow_sdk::Preset::Fast, optical_flow_sdk::Preset::Medium,
                        optical_flow_sdk::Preset::Slow}) {
      const double ms = run_preset(preset, c.w, c.h, 2, 5);
      std::cout << c.w << "x" << c.h << " preset=" << optical_flow_sdk::preset_name(preset)
                << " medianish_ms=" << ms << " fps~=" << (1000.0 / ms) << "\n";
    }
  }
  return 0;
}
