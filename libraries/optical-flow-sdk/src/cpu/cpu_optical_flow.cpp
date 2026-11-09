// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "optical_flow_sdk/cpu_optical_flow.hpp"

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

GrayImage to_float_image(const ImageView &view) {
  view.validate();
  GrayImage img;
  img.width = view.width;
  img.height = view.height;
  img.data.resize(static_cast<std::size_t>(view.width) * view.height);
  for (int y = 0; y < view.height; ++y) {
    const std::uint8_t *row = view.row(y);
    for (int x = 0; x < view.width; ++x)
      img.at(x, y) = static_cast<float>(row[x]);
  }
  return img;
}

GrayImage downsample2(const GrayImage &src) {
  GrayImage dst;
  dst.width = std::max(1, src.width / 2);
  dst.height = std::max(1, src.height / 2);
  dst.data.resize(static_cast<std::size_t>(dst.width) * dst.height);
  for (int y = 0; y < dst.height; ++y) {
    for (int x = 0; x < dst.width; ++x) {
      const int x0 = x * 2;
      const int y0 = y * 2;
      const int x1 = std::min(x0 + 1, src.width - 1);
      const int y1 = std::min(y0 + 1, src.height - 1);
      dst.at(x, y) = 0.25f * (src.at(x0, y0) + src.at(x1, y0) + src.at(x0, y1) + src.at(x1, y1));
    }
  }
  return dst;
}

float sample_bilinear(const GrayImage &img, float x, float y) {
  x = std::clamp(x, 0.0f, static_cast<float>(img.width - 1));
  y = std::clamp(y, 0.0f, static_cast<float>(img.height - 1));
  const int x0 = static_cast<int>(x);
  const int y0 = static_cast<int>(y);
  const int x1 = std::min(x0 + 1, img.width - 1);
  const int y1 = std::min(y0 + 1, img.height - 1);
  const float dx = x - static_cast<float>(x0);
  const float dy = y - static_cast<float>(y0);
  return (1.0f - dx) * (1.0f - dy) * img.at(x0, y0) + dx * (1.0f - dy) * img.at(x1, y0) +
         (1.0f - dx) * dy * img.at(x0, y1) + dx * dy * img.at(x1, y1);
}

void upsample_flow(const FlowField &coarse, FlowField &fine) {
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
      fine.dx(x, y) = 2.0f * u;
      fine.dy(x, y) = 2.0f * v;
    }
  }
}

// Patch-based inverse-compositional LK on a stride grid, then densify — DIS-lite.
void estimate_level(const GrayImage &I0, const GrayImage &I1, FlowField &flow, CostMap &cost,
                    int patch_size, int patch_stride, int iters) {
  const int half = patch_size / 2;
  std::vector<float> weight(static_cast<std::size_t>(flow.width) * flow.height, 0.0f);
  std::vector<float> acc_u(weight.size(), 0.0f);
  std::vector<float> acc_v(weight.size(), 0.0f);
  std::vector<float> acc_c(weight.size(), 0.0f);

  for (int cy = half; cy < I0.height - half; cy += patch_stride) {
    for (int cx = half; cx < I0.width - half; cx += patch_stride) {
      float H11 = 0.0f, H12 = 0.0f, H22 = 0.0f;
      std::vector<float> Ix(static_cast<std::size_t>(patch_size) * patch_size);
      std::vector<float> Iy(Ix.size());
      std::vector<float> T(Ix.size());
      for (int py = 0; py < patch_size; ++py) {
        for (int px = 0; px < patch_size; ++px) {
          const int x = cx - half + px;
          const int y = cy - half + py;
          const float gx = 0.5f * (I0.at(std::min(x + 1, I0.width - 1), y) -
                                   I0.at(std::max(x - 1, 0), y));
          const float gy = 0.5f * (I0.at(x, std::min(y + 1, I0.height - 1)) -
                                   I0.at(x, std::max(y - 1, 0)));
          const std::size_t idx = static_cast<std::size_t>(py) * patch_size + px;
          Ix[idx] = gx;
          Iy[idx] = gy;
          T[idx] = I0.at(x, y);
          H11 += gx * gx;
          H12 += gx * gy;
          H22 += gy * gy;
        }
      }
      const float det = H11 * H22 - H12 * H12;
      if (std::fabs(det) < 1e-3f)
        continue;
      const float invH11 = H22 / det;
      const float invH12 = -H12 / det;
      const float invH22 = H11 / det;

      float u = flow.dx(cx, cy);
      float v = flow.dy(cx, cy);
      constexpr float kMaxDisp = 32.0f;
      constexpr float kMaxStep = 1.5f;
      u = std::clamp(u, -kMaxDisp, kMaxDisp);
      v = std::clamp(v, -kMaxDisp, kMaxDisp);
      float last_ssd = 1e30f;
      for (int it = 0; it < iters; ++it) {
        float b1 = 0.0f, b2 = 0.0f, ssd = 0.0f;
        for (int py = 0; py < patch_size; ++py) {
          for (int px = 0; px < patch_size; ++px) {
            const int x = cx - half + px;
            const int y = cy - half + py;
            const std::size_t idx = static_cast<std::size_t>(py) * patch_size + px;
            const float warped =
                sample_bilinear(I1, static_cast<float>(x) + u, static_cast<float>(y) + v);
            const float err = warped - T[idx];
            ssd += err * err;
            b1 += Ix[idx] * err;
            b2 += Iy[idx] * err;
          }
        }
        if (it > 0 && ssd > last_ssd * 1.05f)
          break;
        last_ssd = ssd;
        // Forward-additive style with template gradients and err = I(W)-T:
        // minimize ||I(W)-T|| => Δp from ∇T^T (I-T) then p ← p - Δp is equivalent
        // to p ← p + Δp when err = T-I. Use err=I-T and p ← p - Δp.
        float du = invH11 * b1 + invH12 * b2;
        float dv = invH12 * b1 + invH22 * b2;
        du = std::clamp(du, -kMaxStep, kMaxStep);
        dv = std::clamp(dv, -kMaxStep, kMaxStep);
        u = std::clamp(u - du, -kMaxDisp, kMaxDisp);
        v = std::clamp(v - dv, -kMaxDisp, kMaxDisp);
        if (du * du + dv * dv < 1e-8f)
          break;
      }

      const float patch_cost =
          std::sqrt(last_ssd / static_cast<float>(patch_size * patch_size));
      for (int y = std::max(0, cy - half); y <= std::min(flow.height - 1, cy + half); ++y) {
        for (int x = std::max(0, cx - half); x <= std::min(flow.width - 1, cx + half); ++x) {
          const float dx = static_cast<float>(x - cx);
          const float dy = static_cast<float>(y - cy);
          const float w = std::max(0.0f, 1.0f - std::sqrt(dx * dx + dy * dy) / (half + 1e-3f));
          if (w <= 0.0f)
            continue;
          const std::size_t idx = static_cast<std::size_t>(y) * flow.width + x;
          weight[idx] += w;
          acc_u[idx] += w * u;
          acc_v[idx] += w * v;
          acc_c[idx] += w * patch_cost;
        }
      }
    }
  }

  for (int y = 0; y < flow.height; ++y) {
    for (int x = 0; x < flow.width; ++x) {
      const std::size_t idx = static_cast<std::size_t>(y) * flow.width + x;
      if (weight[idx] > 1e-6f) {
        flow.dx(x, y) = acc_u[idx] / weight[idx];
        flow.dy(x, y) = acc_v[idx] / weight[idx];
        cost.at(x, y) =
            static_cast<std::uint8_t>(std::clamp(acc_c[idx] / weight[idx], 0.0f, 255.0f));
      } else {
        cost.at(x, y) = 255;
      }
    }
  }
}

} // namespace

CpuOpticalFlow::CpuOpticalFlow(Preset preset) : preset_(preset) {
  switch (preset_) {
  case Preset::Fast:
    patch_size_ = 8;
    patch_stride_ = 4;
    coarsest_scale_ = 2;
    finest_scale_ = 0;
    gradient_descent_iters_ = 10;
    variational_refinement_ = false;
    break;
  case Preset::Medium:
    patch_size_ = 8;
    patch_stride_ = 3;
    coarsest_scale_ = 3;
    finest_scale_ = 0;
    gradient_descent_iters_ = 14;
    variational_refinement_ = false;
    break;
  case Preset::Slow:
    patch_size_ = 12;
    patch_stride_ = 3;
    coarsest_scale_ = 3;
    finest_scale_ = 0;
    gradient_descent_iters_ = 18;
    variational_refinement_ = false;
    break;
  }
}

void CpuOpticalFlow::calc(const ImageView &prev, const ImageView &next, FlowField &flow) const {
  CostMap unused;
  calc(prev, next, flow, unused);
}

void CpuOpticalFlow::calc(const ImageView &prev, const ImageView &next, FlowField &flow,
                          CostMap &cost) const {
  prev.validate();
  next.validate();
  if (prev.width != next.width || prev.height != next.height)
    throw std::invalid_argument("prev/next must share dimensions");

  flow.allocate(prev.width, prev.height);
  cost.allocate(prev.width, prev.height);

  std::vector<GrayImage> pyr0;
  std::vector<GrayImage> pyr1;
  pyr0.push_back(to_float_image(prev));
  pyr1.push_back(to_float_image(next));
  for (int s = 1; s <= coarsest_scale_; ++s) {
    pyr0.push_back(downsample2(pyr0.back()));
    pyr1.push_back(downsample2(pyr1.back()));
  }

  FlowField level_flow;
  level_flow.allocate(pyr0[coarsest_scale_].width, pyr0[coarsest_scale_].height);

  for (int scale = coarsest_scale_; scale >= finest_scale_; --scale) {
    if (scale != coarsest_scale_) {
      FlowField up;
      up.width = pyr0[scale].width;
      up.height = pyr0[scale].height;
      upsample_flow(level_flow, up);
      level_flow = std::move(up);
    }

    CostMap level_cost;
    level_cost.allocate(level_flow.width, level_flow.height);
    estimate_level(pyr0[scale], pyr1[scale], level_flow, level_cost, patch_size_, patch_stride_,
                   gradient_descent_iters_);

    if (scale == finest_scale_) {
      flow = std::move(level_flow);
      cost = std::move(level_cost);
    }
  }
}

} // namespace optical_flow_sdk
