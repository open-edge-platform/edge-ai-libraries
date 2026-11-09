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

double run_backend(optical_flow_sdk::Backend backend, optical_flow_sdk::Preset preset, int w, int h,
                   int warmup, int iters) {
  const auto prev = make_textured(w, h);
  const auto next = shift(prev, w, h, 3);
  optical_flow_sdk::OpticalFlow of(backend, preset);
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
  using optical_flow_sdk::Backend;
  using optical_flow_sdk::Preset;
  struct Case {
    int w;
    int h;
    double opencv_dis_fast_ms;
  };
  // OpenCV DIS-Fast baselines measured on Core Ultra 7 255H (re-timed 2026-11-09).
  const Case cases[] = {{1280, 720, 12.22}, {1920, 1080, 23.97}};
  for (const auto &c : cases) {
    const double sycl_ms = run_backend(Backend::Sycl, Preset::Fast, c.w, c.h, 8, 30);
#if OPTICALFLOW_HAS_OPENCL
    const double ocl_ms = run_backend(Backend::OpenCL, Preset::Fast, c.w, c.h, 8, 30);
#else
    const double ocl_ms = 0.0;
#endif
    const double vs_opencv_sycl = c.opencv_dis_fast_ms / sycl_ms;
    std::cout << c.w << "x" << c.h << " sycl_ms=" << sycl_ms << " fps~=" << (1000.0 / sycl_ms)
              << " sycl_vs_opencv=" << vs_opencv_sycl << "x";
    if (ocl_ms > 0.0) {
      std::cout << " opencl_ms=" << ocl_ms
                << " opencl_vs_opencv=" << (c.opencv_dis_fast_ms / ocl_ms) << "x";
    }
    std::cout << "\n";
  }
  return 0;
}
