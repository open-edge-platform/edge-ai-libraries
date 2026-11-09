// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "optical_flow_sdk/farneback.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <vector>

namespace optical_flow_sdk {
namespace {

struct GrayImage {
  int width = 0;
  int height = 0;
  std::vector<float> data;
  float &at(int x, int y) { return data[static_cast<std::size_t>(y) * width + x]; }
  float at(int x, int y) const { return data[static_cast<std::size_t>(y) * width + x]; }
};

GrayImage to_float(const ImageView &view) {
  view.validate();
  GrayImage img;
  img.width = view.width;
  img.height = view.height;
  img.data.resize(static_cast<std::size_t>(view.width) * view.height);
  for (int y = 0; y < view.height; ++y) {
    const auto *row = view.row(y);
    for (int x = 0; x < view.width; ++x)
      img.at(x, y) = static_cast<float>(row[x]);
  }
  return img;
}

GrayImage downsample(const GrayImage &src, double scale) {
  GrayImage dst;
  dst.width = std::max(1, static_cast<int>(std::lround(src.width * scale)));
  dst.height = std::max(1, static_cast<int>(std::lround(src.height * scale)));
  dst.data.resize(static_cast<std::size_t>(dst.width) * dst.height);
  const float sx = static_cast<float>(src.width) / static_cast<float>(dst.width);
  const float sy = static_cast<float>(src.height) / static_cast<float>(dst.height);
  for (int y = 0; y < dst.height; ++y) {
    for (int x = 0; x < dst.width; ++x) {
      const float fx = (static_cast<float>(x) + 0.5f) * sx - 0.5f;
      const float fy = (static_cast<float>(y) + 0.5f) * sy - 0.5f;
      const int x0 = std::clamp(static_cast<int>(std::floor(fx)), 0, src.width - 1);
      const int y0 = std::clamp(static_cast<int>(std::floor(fy)), 0, src.height - 1);
      const int x1 = std::min(x0 + 1, src.width - 1);
      const int y1 = std::min(y0 + 1, src.height - 1);
      const float dx = fx - static_cast<float>(x0);
      const float dy = fy - static_cast<float>(y0);
      dst.at(x, y) = (1 - dx) * (1 - dy) * src.at(x0, y0) + dx * (1 - dy) * src.at(x1, y0) +
                     (1 - dx) * dy * src.at(x0, y1) + dx * dy * src.at(x1, y1);
    }
  }
  return dst;
}

float sample(const GrayImage &img, float x, float y) {
  x = std::clamp(x, 0.0f, static_cast<float>(img.width - 1));
  y = std::clamp(y, 0.0f, static_cast<float>(img.height - 1));
  const int x0 = static_cast<int>(x);
  const int y0 = static_cast<int>(y);
  const int x1 = std::min(x0 + 1, img.width - 1);
  const int y1 = std::min(y0 + 1, img.height - 1);
  const float dx = x - static_cast<float>(x0);
  const float dy = y - static_cast<float>(y0);
  return (1 - dx) * (1 - dy) * img.at(x0, y0) + dx * (1 - dy) * img.at(x1, y0) +
         (1 - dx) * dy * img.at(x0, y1) + dx * dy * img.at(x1, y1);
}

void upsample_flow(const FlowField &coarse, FlowField &fine, float scale_inv) {
  fine.allocate(fine.width, fine.height);
  const float sx = static_cast<float>(coarse.width) / static_cast<float>(fine.width);
  const float sy = static_cast<float>(coarse.height) / static_cast<float>(fine.height);
  for (int y = 0; y < fine.height; ++y) {
    for (int x = 0; x < fine.width; ++x) {
      const float cx = (static_cast<float>(x) + 0.5f) * sx - 0.5f;
      const float cy = (static_cast<float>(y) + 0.5f) * sy - 0.5f;
      const int x0 = std::clamp(static_cast<int>(std::floor(cx)), 0, coarse.width - 1);
      const int y0 = std::clamp(static_cast<int>(std::floor(cy)), 0, coarse.height - 1);
      const int x1 = std::min(x0 + 1, coarse.width - 1);
      const int y1 = std::min(y0 + 1, coarse.height - 1);
      const float dx = cx - static_cast<float>(x0);
      const float dy = cy - static_cast<float>(y0);
      const float u = (1 - dx) * (1 - dy) * coarse.dx(x0, y0) + dx * (1 - dy) * coarse.dx(x1, y0) +
                      (1 - dx) * dy * coarse.dx(x0, y1) + dx * dy * coarse.dx(x1, y1);
      const float v = (1 - dx) * (1 - dy) * coarse.dy(x0, y0) + dx * (1 - dy) * coarse.dy(x1, y0) +
                      (1 - dx) * dy * coarse.dy(x0, y1) + dx * dy * coarse.dy(x1, y1);
      fine.dx(x, y) = u * scale_inv;
      fine.dy(x, y) = v * scale_inv;
    }
  }
}

// Dense windowed polynomial / LK hybrid (Farneback-class operating points).
// poly_sigma is the Gaussian σ for the poly_n neighborhood (OpenCV dial).
void farneback_level(const GrayImage &I0, const GrayImage &I1, FlowField &flow, CostMap &cost,
                     int winsize, int iterations, int poly_n, float poly_sigma) {
  const int half = winsize / 2;
  const int poly_half = poly_n / 2;
  const float poly_var = std::max(poly_sigma * poly_sigma, 1e-6f);
  FlowField updated = flow;

  for (int it = 0; it < iterations; ++it) {
    for (int y = half; y < I0.height - half; ++y) {
      for (int x = half; x < I0.width - half; ++x) {
        float Gxx = 0.0f, Gxy = 0.0f, Gyy = 0.0f, bx = 0.0f, by = 0.0f, ssd = 0.0f;
        const float u0 = flow.dx(x, y);
        const float v0 = flow.dy(x, y);
        for (int wy = -half; wy <= half; ++wy) {
          for (int wx = -half; wx <= half; ++wx) {
            // Local polynomial gradient proxy from poly_n × poly_sigma neighborhood.
            float Ix = 0.0f, Iy = 0.0f, wsum = 0.0f;
            for (int py = -poly_half; py <= poly_half; ++py) {
              for (int px = -poly_half; px <= poly_half; ++px) {
                const int xx = std::clamp(x + wx + px, 0, I0.width - 1);
                const int yy = std::clamp(y + wy + py, 0, I0.height - 1);
                const float w =
                    std::exp(-0.5f * static_cast<float>(px * px + py * py) / poly_var);
                Ix += w * px * I0.at(xx, yy);
                Iy += w * py * I0.at(xx, yy);
                wsum += w;
              }
            }
            Ix /= (wsum + 1e-6f);
            Iy /= (wsum + 1e-6f);
            const int x1 = std::clamp(x + wx, 0, I0.width - 1);
            const int y1 = std::clamp(y + wy, 0, I0.height - 1);
            const float i0 = I0.at(x1, y1);
            const float i1 = sample(I1, static_cast<float>(x1) + u0, static_cast<float>(y1) + v0);
            const float It = i1 - i0;
            Gxx += Ix * Ix;
            Gxy += Ix * Iy;
            Gyy += Iy * Iy;
            bx += Ix * It;
            by += Iy * It;
            ssd += It * It;
          }
        }
        const float det = Gxx * Gyy - Gxy * Gxy;
        if (std::fabs(det) < 1e-4f) {
          cost.at(x, y) = 255;
          continue;
        }
        const float du = -(Gyy * bx - Gxy * by) / det;
        const float dv = -(-Gxy * bx + Gxx * by) / det;
        updated.dx(x, y) = u0 + du;
        updated.dy(x, y) = v0 + dv;
        const float norm = static_cast<float>(winsize * winsize);
        cost.at(x, y) = static_cast<std::uint8_t>(
            std::clamp(std::sqrt(ssd / norm), 0.0f, 255.0f));
      }
    }
    flow = updated;
  }

  // Fill borders from nearest interior.
  for (int y = 0; y < flow.height; ++y) {
    for (int x = 0; x < flow.width; ++x) {
      const int xi = std::clamp(x, half, flow.width - half - 1);
      const int yi = std::clamp(y, half, flow.height - half - 1);
      if (x != xi || y != yi) {
        flow.dx(x, y) = flow.dx(xi, yi);
        flow.dy(x, y) = flow.dy(xi, yi);
        cost.at(x, y) = cost.at(xi, yi);
      }
    }
  }
}

} // namespace

FarnebackOpticalFlow::FarnebackOpticalFlow(Preset preset) : preset_(preset) {
  switch (preset_) {
  case Preset::Fast:
    pyr_scale_ = 0.5;
    levels_ = 2;
    winsize_ = 9;
    iterations_ = 2;
    poly_n_ = 5;
    poly_sigma_ = 1.1;
    break;
  case Preset::Medium:
    pyr_scale_ = 0.5;
    levels_ = 3;
    winsize_ = 13;
    iterations_ = 3;
    poly_n_ = 5;
    poly_sigma_ = 1.2;
    break;
  case Preset::Slow:
    pyr_scale_ = 0.5;
    levels_ = 4;
    winsize_ = 15;
    iterations_ = 5;
    poly_n_ = 7;
    poly_sigma_ = 1.5;
    break;
  }
}

void FarnebackOpticalFlow::calc(const ImageView &prev, const ImageView &next,
                                FlowField &flow) const {
  CostMap unused;
  calc(prev, next, flow, unused);
}

void FarnebackOpticalFlow::calc(const ImageView &prev, const ImageView &next, FlowField &flow,
                                CostMap &cost) const {
  prev.validate();
  next.validate();
  if (prev.width != next.width || prev.height != next.height)
    throw std::invalid_argument("prev/next must share dimensions");

  std::vector<GrayImage> pyr0;
  std::vector<GrayImage> pyr1;
  pyr0.push_back(to_float(prev));
  pyr1.push_back(to_float(next));
  for (int s = 1; s < levels_; ++s) {
    pyr0.push_back(downsample(pyr0.back(), pyr_scale_));
    pyr1.push_back(downsample(pyr1.back(), pyr_scale_));
  }

  FlowField level_flow;
  level_flow.allocate(pyr0.back().width, pyr0.back().height);
  CostMap level_cost;
  level_cost.allocate(level_flow.width, level_flow.height);

  const float scale_inv = static_cast<float>(1.0 / pyr_scale_);
  for (int scale = levels_ - 1; scale >= 0; --scale) {
    if (scale != levels_ - 1) {
      FlowField up;
      up.width = pyr0[scale].width;
      up.height = pyr0[scale].height;
      upsample_flow(level_flow, up, scale_inv);
      level_flow = std::move(up);
      level_cost.allocate(level_flow.width, level_flow.height);
    }
    farneback_level(pyr0[scale], pyr1[scale], level_flow, level_cost, winsize_, iterations_,
                    poly_n_, static_cast<float>(poly_sigma_));
  }

  flow = std::move(level_flow);
  cost = std::move(level_cost);
}

} // namespace optical_flow_sdk
