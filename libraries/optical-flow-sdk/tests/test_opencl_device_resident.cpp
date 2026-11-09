// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "optical_flow_sdk/opencl_optical_flow.hpp"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <cstdlib>
#include <iostream>
#include <vector>

namespace {

std::vector<std::uint8_t> make_textured(int w, int h) {
  std::vector<std::uint8_t> img(static_cast<std::size_t>(w) * h);
  for (int y = 0; y < h; ++y) {
    for (int x = 0; x < w; ++x) {
      const float fx = static_cast<float>(x) * 0.21f;
      const float fy = static_cast<float>(y) * 0.17f;
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
  constexpr int kDx = 4;
  constexpr int kDy = -3;

  const auto prev = make_textured(kW, kH);
  const auto next = shift_image(prev, kW, kH, kDx, kDy);

  OpenCLOpticalFlow of(Preset::Fast);
  std::cout << "dmabuf_import_supported=" << (of.supports_dmabuf_import() ? "yes" : "no") << "\n";

  auto d_prev = of.create_u8_image(kW, kH);
  auto d_next = of.create_u8_image(kW, kH);
  auto d_flow = of.create_flow_buffer(kW, kH);
  of.upload_u8(d_prev, ImageView{prev.data(), kW, kH, 0});
  // Strided upload (simulate NV12 Y pitch = width + 16).
  constexpr int kPitch = kW + 16;
  std::vector<std::uint8_t> next_strided(static_cast<std::size_t>(kPitch) * kH, 0);
  for (int y = 0; y < kH; ++y)
    std::memcpy(next_strided.data() + static_cast<std::size_t>(y) * kPitch,
                next.data() + static_cast<std::size_t>(y) * kW, static_cast<std::size_t>(kW));
  of.upload_u8(d_next, ImageView{next_strided.data(), kW, kH, static_cast<std::size_t>(kPitch)});
  of.calc_device(d_prev, d_next, d_flow);

  FlowField flow;
  of.download_flow(d_flow, flow);

  double sum = 0.0;
  int count = 0;
  for (int y = 16; y < kH - 16; ++y) {
    for (int x = 16; x < kW - 16; ++x) {
      const double eu = flow.dx(x, y) - static_cast<double>(kDx);
      const double ev = flow.dy(x, y) - static_cast<double>(kDy);
      sum += std::sqrt(eu * eu + ev * ev);
      ++count;
    }
  }
  const double epe = sum / static_cast<double>(count);
  std::cout << "opencl device-resident synthetic-shift mean EPE=" << epe << "\n";
  if (epe > 1.0) {
    std::cerr << "OpenCL device-resident EPE too high\n";
    return EXIT_FAILURE;
  }
  return EXIT_SUCCESS;
}
