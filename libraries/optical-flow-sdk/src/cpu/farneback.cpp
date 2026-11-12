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

// OpenCV Farneback poly channels (5): [cy, cx, cyy, cxx, cxy] after moment inversion.
struct PolyField {
  int width = 0;
  int height = 0;
  std::vector<float> data; // width*height*5 interleaved
  void allocate(int w, int h) {
    width = w;
    height = h;
    data.assign(static_cast<std::size_t>(w) * h * 5, 0.f);
  }
  float *row(int y) { return data.data() + static_cast<std::size_t>(y) * width * 5; }
  const float *row(int y) const { return data.data() + static_cast<std::size_t>(y) * width * 5; }
};

GrayImage to_float(const ImageView &view) {
  view.validate();
  GrayImage img;
  img.width = view.width;
  img.height = view.height;
  img.data.resize(static_cast<std::size_t>(view.width) * view.height);
  for (int y = 0; y < view.height; ++y) {
    const auto *r = view.row(y);
    for (int x = 0; x < view.width; ++x)
      img.at(x, y) = static_cast<float>(r[x]);
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

void upsample_flow(const FlowField &coarse, FlowField &fine, float scale_inv) {
  fine.allocate(fine.width, fine.height);
  const float sx = static_cast<float>(coarse.width) / static_cast<float>(fine.width);
  const float sy = static_cast<float>(coarse.height) / static_cast<float>(fine.height);
  for (int y = 0; y < fine.height; ++y) {
    for (int x = 0; x < fine.width; ++x) {
      float cx = (static_cast<float>(x) + 0.5f) * sx - 0.5f;
      float cy = (static_cast<float>(y) + 0.5f) * sy - 0.5f;
      cx = std::clamp(cx, 0.0f, static_cast<float>(coarse.width - 1));
      cy = std::clamp(cy, 0.0f, static_cast<float>(coarse.height - 1));
      const int x0 = static_cast<int>(cx);
      const int y0 = static_cast<int>(cy);
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

// Separable Farneback polynomial expansion (OpenCV FarnebackPolyExp layout).
void poly_expand(const GrayImage &src, int poly_n, float poly_sigma, PolyField &dst) {
  const int n = poly_n / 2;
  if (n < 1)
    throw std::invalid_argument("poly_n must be >= 3");
  float sigma = poly_sigma;
  if (sigma < 1e-6f)
    sigma = static_cast<float>(n) * 0.3f;

  std::vector<float> g(static_cast<std::size_t>(2 * n + 1));
  std::vector<float> xg(g.size()), xxg(g.size());
  float *g0 = g.data() + n;
  float *xg0 = xg.data() + n;
  float *xxg0 = xxg.data() + n;

  double s = 0.0;
  for (int x = -n; x <= n; ++x) {
    g0[x] = static_cast<float>(std::exp(-x * x / (2.0 * sigma * sigma)));
    s += g0[x];
  }
  s = 1.0 / s;
  for (int x = -n; x <= n; ++x) {
    g0[x] = static_cast<float>(g0[x] * s);
    xg0[x] = static_cast<float>(x * g0[x]);
    xxg0[x] = static_cast<float>(x * x * g0[x]);
  }

  // Build 6x6 moment matrix G and invert (Cholesky via simple GE — G is SPD).
  double G[6][6] = {};
  for (int y = -n; y <= n; ++y) {
    for (int x = -n; x <= n; ++x) {
      const double w = static_cast<double>(g0[y]) * g0[x];
      G[0][0] += w;
      G[1][1] += w * x * x;
      G[3][3] += w * x * x * x * x;
      G[5][5] += w * x * x * y * y;
    }
  }
  G[2][2] = G[0][3] = G[0][4] = G[3][0] = G[4][0] = G[1][1];
  G[4][4] = G[3][3];
  G[3][4] = G[4][3] = G[5][5];

  double M[6][12] = {};
  for (int i = 0; i < 6; ++i) {
    for (int j = 0; j < 6; ++j)
      M[i][j] = G[i][j];
    M[i][6 + i] = 1.0;
  }
  for (int col = 0; col < 6; ++col) {
    int piv = col;
    for (int r = col + 1; r < 6; ++r)
      if (std::fabs(M[r][col]) > std::fabs(M[piv][col]))
        piv = r;
    if (std::fabs(M[piv][col]) < 1e-18)
      continue;
    if (piv != col)
      for (int c = 0; c < 12; ++c)
        std::swap(M[piv][c], M[col][c]);
    const double inv = 1.0 / M[col][col];
    for (int c = 0; c < 12; ++c)
      M[col][c] *= inv;
    for (int r = 0; r < 6; ++r) {
      if (r == col)
        continue;
      const double f = M[r][col];
      for (int c = 0; c < 12; ++c)
        M[r][c] -= f * M[col][c];
    }
  }
  const double ig11 = M[1][7];
  const double ig03 = M[0][9];
  const double ig33 = M[3][9];
  const double ig55 = M[5][11];

  dst.allocate(src.width, src.height);
  std::vector<float> row(static_cast<std::size_t>(src.width + 2 * n) * 3);
  float *row0 = row.data() + static_cast<std::size_t>(n) * 3;

  for (int y = 0; y < src.height; ++y) {
    const float gv0 = g0[0];
    for (int x = 0; x < src.width; ++x) {
      row0[x * 3] = src.at(x, y) * gv0;
      row0[x * 3 + 1] = 0.f;
      row0[x * 3 + 2] = 0.f;
    }
    for (int k = 1; k <= n; ++k) {
      const float gk = g0[k], xgk = xg0[k], xxgk = xxg0[k];
      const int y0 = std::max(y - k, 0);
      const int y1 = std::min(y + k, src.height - 1);
      for (int x = 0; x < src.width; ++x) {
        const float s0 = src.at(x, y0);
        const float s1 = src.at(x, y1);
        const float p = s0 + s1;
        row0[x * 3] += gk * p;
        row0[x * 3 + 1] += xgk * (s1 - s0);
        row0[x * 3 + 2] += xxgk * p;
      }
    }
    for (int x = 0; x < n * 3; ++x) {
      row0[-1 - x] = row0[2 - x];
      row0[src.width * 3 + x] = row0[src.width * 3 + x - 3];
    }

    float *drow = dst.row(y);
    for (int x = 0; x < src.width; ++x) {
      double b1 = row0[x * 3] * gv0, b2 = 0, b3 = row0[x * 3 + 1] * gv0, b4 = 0,
             b5 = row0[x * 3 + 2] * gv0, b6 = 0;
      for (int k = 1; k <= n; ++k) {
        const double tg = row0[(x + k) * 3] + row0[(x - k) * 3];
        const double gk = g0[k];
        b1 += tg * gk;
        b4 += tg * xxg0[k];
        b2 += (row0[(x + k) * 3] - row0[(x - k) * 3]) * xg0[k];
        b3 += (row0[(x + k) * 3 + 1] + row0[(x - k) * 3 + 1]) * gk;
        b6 += (row0[(x + k) * 3 + 1] - row0[(x - k) * 3 + 1]) * xg0[k];
        b5 += (row0[(x + k) * 3 + 2] + row0[(x - k) * 3 + 2]) * gk;
      }
      // OpenCV channel order: [cy, cx, cyy, cxx, cxy]
      drow[x * 5 + 0] = static_cast<float>(b3 * ig11);
      drow[x * 5 + 1] = static_cast<float>(b2 * ig11);
      drow[x * 5 + 2] = static_cast<float>(b1 * ig03 + b5 * ig33);
      drow[x * 5 + 3] = static_cast<float>(b1 * ig03 + b4 * ig33);
      drow[x * 5 + 4] = static_cast<float>(b6 * ig55);
    }
  }
}

void sample_poly5(const PolyField &R, float x, float y, float out[5]) {
  x = std::clamp(x, 0.0f, static_cast<float>(R.width - 1));
  y = std::clamp(y, 0.0f, static_cast<float>(R.height - 1));
  const int x0 = static_cast<int>(x);
  const int y0 = static_cast<int>(y);
  const int x1 = std::min(x0 + 1, R.width - 1);
  const int y1 = std::min(y0 + 1, R.height - 1);
  const float fx = x - static_cast<float>(x0);
  const float fy = y - static_cast<float>(y0);
  const float a00 = (1 - fx) * (1 - fy), a01 = fx * (1 - fy), a10 = (1 - fx) * fy, a11 = fx * fy;
  const float *p00 = R.row(y0) + x0 * 5;
  const float *p10 = R.row(y0) + x1 * 5;
  const float *p01 = R.row(y1) + x0 * 5;
  const float *p11 = R.row(y1) + x1 * 5;
  for (int k = 0; k < 5; ++k)
    out[k] = a00 * p00[k] + a01 * p10[k] + a10 * p01[k] + a11 * p11[k];
}

// OpenCV FarnebackUpdateMatrices + box-blur UpdateFlow (absolute flow).
void farneback_level(const GrayImage &I0, const GrayImage &I1, FlowField &flow, CostMap &cost,
                     int winsize, int iterations, int poly_n, float poly_sigma) {
  const int half = winsize / 2;
  PolyField R0, R1;
  poly_expand(I0, poly_n, poly_sigma, R0);
  poly_expand(I1, poly_n, poly_sigma, R1);

  const int W = I0.width, H = I0.height;
  std::vector<float> M(static_cast<std::size_t>(W) * H * 5);

  constexpr int kBorder = 5;
  static const float kBorderScale[kBorder] = {0.14f, 0.14f, 0.4472f, 0.4472f, 0.4472f};

  for (int it = 0; it < iterations; ++it) {
    for (int y = 0; y < H; ++y) {
      const float *r0 = R0.row(y);
      for (int x = 0; x < W; ++x) {
        const float dx = flow.dx(x, y);
        const float dy = flow.dy(x, y);
        float r1[5];
        sample_poly5(R1, static_cast<float>(x) + dx, static_cast<float>(y) + dy, r1);

        float r2 = (r0[x * 5 + 0] - r1[0]) * 0.5f;
        float r3 = (r0[x * 5 + 1] - r1[1]) * 0.5f;
        float r4 = (r0[x * 5 + 2] + r1[2]) * 0.5f;
        float r5 = (r0[x * 5 + 3] + r1[3]) * 0.5f;
        float r6 = (r0[x * 5 + 4] + r1[4]) * 0.25f;

        r2 += r4 * dy + r6 * dx;
        r3 += r6 * dy + r5 * dx;

        if (static_cast<unsigned>(x - kBorder) >= static_cast<unsigned>(W - kBorder * 2) ||
            static_cast<unsigned>(y - kBorder) >= static_cast<unsigned>(H - kBorder * 2)) {
          const float scale =
              (x < kBorder ? kBorderScale[x] : 1.f) *
              (x >= W - kBorder ? kBorderScale[W - x - 1] : 1.f) *
              (y < kBorder ? kBorderScale[y] : 1.f) *
              (y >= H - kBorder ? kBorderScale[H - y - 1] : 1.f);
          r2 *= scale;
          r3 *= scale;
          r4 *= scale;
          r5 *= scale;
          r6 *= scale;
        }

        float *m = M.data() + (static_cast<std::size_t>(y) * W + x) * 5;
        m[0] = r4 * r4 + r6 * r6;
        m[1] = (r4 + r5) * r6;
        m[2] = r5 * r5 + r6 * r6;
        m[3] = r4 * r2 + r6 * r3;
        m[4] = r6 * r2 + r5 * r3;
      }
    }

    // Box-average M over winsize, solve G [fy, fx] = h → store (fx, fy).
    const double scale = 1.0 / (static_cast<double>(winsize) * winsize);
    for (int y = 0; y < H; ++y) {
      for (int x = 0; x < W; ++x) {
        double g11 = 0, g12 = 0, g22 = 0, h1 = 0, h2 = 0;
        for (int wy = -half; wy <= half; ++wy) {
          const int yy = std::clamp(y + wy, 0, H - 1);
          for (int wx = -half; wx <= half; ++wx) {
            const int xx = std::clamp(x + wx, 0, W - 1);
            const float *m = M.data() + (static_cast<std::size_t>(yy) * W + xx) * 5;
            g11 += m[0];
            g12 += m[1];
            g22 += m[2];
            h1 += m[3];
            h2 += m[4];
          }
        }
        g11 *= scale;
        g12 *= scale;
        g22 *= scale;
        h1 *= scale;
        h2 *= scale;
        const double idet = 1.0 / (g11 * g22 - g12 * g12 + 1e-3);
        const float fx = static_cast<float>((g11 * h2 - g12 * h1) * idet);
        const float fy = static_cast<float>((g22 * h1 - g12 * h2) * idet);
        const float ou = flow.dx(x, y);
        const float ov = flow.dy(x, y);
        flow.dx(x, y) = fx;
        flow.dy(x, y) = fy;
        cost.at(x, y) = static_cast<std::uint8_t>(
            std::clamp(std::sqrt((fx - ou) * (fx - ou) + (fy - ov) * (fy - ov)) * 16.0f, 0.0f,
                       255.0f));
      }
    }
  }
  (void)I1;
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
