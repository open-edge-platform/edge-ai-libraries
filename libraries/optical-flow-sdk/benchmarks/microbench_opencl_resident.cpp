// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "optical_flow_sdk/opencl_optical_flow.hpp"

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

} // namespace

int main() {
  using optical_flow_sdk::OpenCLOpticalFlow;
  using optical_flow_sdk::ImageView;
  using optical_flow_sdk::Preset;

  // OpenCV DIS-Fast baselines (live retimes on Core Ultra 7 255H, 2026-11-09).
  struct Case {
    int w;
    int h;
    double opencv_ms;
  };
  const Case cases[] = {{1280, 720, 11.9}, {1920, 1080, 24.0}};

  OpenCLOpticalFlow of(Preset::Fast);
  for (const auto &c : cases) {
    const auto prev = make_textured(c.w, c.h);
    const auto next = shift(prev, c.w, c.h, 3);
    auto d_prev = of.create_u8_image(c.w, c.h);
    auto d_next = of.create_u8_image(c.w, c.h);
    auto d_flow = of.create_flow_buffer(c.w, c.h);
    of.upload_u8(d_prev, ImageView{prev.data(), c.w, c.h, 0});
    of.upload_u8(d_next, ImageView{next.data(), c.w, c.h, 0});
    of.finish();

    for (int i = 0; i < 8; ++i)
      of.calc_device(d_prev, d_next, d_flow);

    const auto t0 = std::chrono::steady_clock::now();
    constexpr int kIters = 40;
    for (int i = 0; i < kIters; ++i)
      of.calc_device(d_prev, d_next, d_flow);
    const auto t1 = std::chrono::steady_clock::now();
    const double ms =
        std::chrono::duration<double, std::milli>(t1 - t0).count() / static_cast<double>(kIters);

    // Pipeline-like: upload new frames each call, keep flow on device (no D2H).
    double pipe_ms = 0.0;
    {
      for (int i = 0; i < 5; ++i) {
        of.upload_u8(d_prev, ImageView{prev.data(), c.w, c.h, 0});
        of.upload_u8(d_next, ImageView{next.data(), c.w, c.h, 0});
        of.calc_device(d_prev, d_next, d_flow);
      }
      const auto p0 = std::chrono::steady_clock::now();
      for (int i = 0; i < kIters; ++i) {
        of.upload_u8(d_prev, ImageView{prev.data(), c.w, c.h, 0});
        of.upload_u8(d_next, ImageView{next.data(), c.w, c.h, 0});
        of.calc_device(d_prev, d_next, d_flow);
      }
      const auto p1 = std::chrono::steady_clock::now();
      pipe_ms =
          std::chrono::duration<double, std::milli>(p1 - p0).count() / static_cast<double>(kIters);
    }

    std::cout << c.w << "x" << c.h << " resident_ms=" << ms << " fps~=" << (1000.0 / ms)
              << " vs_opencv=" << (c.opencv_ms / ms) << "x"
              << " pipeline_H2D_no_D2H_ms=" << pipe_ms
              << " pipeline_vs_opencv=" << (c.opencv_ms / pipe_ms) << "x\n";
  }
  return 0;
}
