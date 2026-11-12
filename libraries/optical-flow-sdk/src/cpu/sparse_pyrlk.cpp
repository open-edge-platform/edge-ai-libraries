// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "optical_flow_sdk/sparse_pyrlk.hpp"

#include "optical_flow_sdk/version.hpp"

#if OPTICALFLOW_HAS_OPENCL
#include "optical_flow_sdk/opencl_sparse_pyrlk.hpp"
#endif

#include <algorithm>
#include <cmath>
#include <memory>
#include <stdexcept>
#include <vector>

namespace optical_flow_sdk {
namespace {

struct GrayImage {
  int width = 0;
  int height = 0;
  std::vector<float> data;
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
      img.data[static_cast<std::size_t>(y) * view.width + x] = static_cast<float>(row[x]);
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
      const int x0 = x * 2, y0 = y * 2;
      const int x1 = std::min(x0 + 1, src.width - 1);
      const int y1 = std::min(y0 + 1, src.height - 1);
      dst.data[static_cast<std::size_t>(y) * dst.width + x] =
          0.25f * (src.at(x0, y0) + src.at(x1, y0) + src.at(x0, y1) + src.at(x1, y1));
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

bool track_point(const GrayImage &I0, const GrayImage &I1, float x, float y, float &u, float &v,
                 int win, int max_iters, float eps, float min_eig, float &err_out) {
  const int half = win / 2;
  if (x < half || y < half || x >= I0.width - half || y >= I0.height - half)
    return false;

  float Gxx = 0.0f, Gxy = 0.0f, Gyy = 0.0f;
  for (int wy = -half; wy <= half; ++wy) {
    for (int wx = -half; wx <= half; ++wx) {
      const float Ix = 0.5f * (sample(I0, x + wx + 1, y + wy) - sample(I0, x + wx - 1, y + wy));
      const float Iy = 0.5f * (sample(I0, x + wx, y + wy + 1) - sample(I0, x + wx, y + wy - 1));
      Gxx += Ix * Ix;
      Gxy += Ix * Iy;
      Gyy += Iy * Iy;
    }
  }
  const float det = Gxx * Gyy - Gxy * Gxy;
  const float eig_min = 0.5f * ((Gxx + Gyy) - std::sqrt((Gxx - Gyy) * (Gxx - Gyy) + 4 * Gxy * Gxy));
  if (std::fabs(det) < 1e-8f || eig_min < min_eig)
    return false;

  for (int it = 0; it < max_iters; ++it) {
    float bx = 0.0f, by = 0.0f, ssd = 0.0f;
    for (int wy = -half; wy <= half; ++wy) {
      for (int wx = -half; wx <= half; ++wx) {
        const float Ix = 0.5f * (sample(I0, x + wx + 1, y + wy) - sample(I0, x + wx - 1, y + wy));
        const float Iy = 0.5f * (sample(I0, x + wx, y + wy + 1) - sample(I0, x + wx, y + wy - 1));
        const float i0 = sample(I0, x + wx, y + wy);
        const float i1 = sample(I1, x + u + wx, y + v + wy);
        const float It = i0 - i1;
        bx += Ix * It;
        by += Iy * It;
        ssd += It * It;
      }
    }
    const float du = (Gyy * bx - Gxy * by) / det;
    const float dv = (-Gxy * bx + Gxx * by) / det;
    u += du;
    v += dv;
    err_out = std::sqrt(ssd / static_cast<float>(win * win));
    if (du * du + dv * dv < eps * eps)
      break;
  }
  return true;
}

} // namespace

SparsePyrLK::SparsePyrLK() : SparsePyrLK(SparsePyrLKOptions{}, Backend::Auto) {}

SparsePyrLK::SparsePyrLK(SparsePyrLKOptions options, Backend backend) : options_(options) {
  if (options_.win_size < 3 || (options_.win_size % 2) == 0)
    throw std::invalid_argument("SparsePyrLK win_size must be odd and >= 3");
  if (options_.max_level < 0)
    throw std::invalid_argument("SparsePyrLK max_level must be >= 0");
  if (backend == Backend::Auto) {
#if OPTICALFLOW_HAS_OPENCL
    backend_ = Backend::OpenCL;
#else
    backend_ = Backend::Cpu;
#endif
  } else {
    backend_ = backend;
  }
  if (backend_ == Backend::OpenCL && !OPTICALFLOW_HAS_OPENCL)
    throw std::runtime_error("SparsePyrLK OpenCL backend was not enabled at build time");
  if (backend_ == Backend::Sycl)
    throw std::runtime_error("SparsePyrLK has no SYCL path; use Cpu or OpenCL");
}

void SparsePyrLK::calc(const ImageView &prev, const ImageView &next,
                       const std::vector<Point2f> &prev_pts, std::vector<Point2f> &next_pts,
                       std::vector<std::uint8_t> &status, std::vector<float> &err) const {
#if OPTICALFLOW_HAS_OPENCL
  if (backend_ == Backend::OpenCL) {
    // Reconstruct lightweight device tracker with the same options (context is shared/static).
    OpenCLSparsePyrLK ocl(options_);
    ocl.calc(prev, next, prev_pts, next_pts, status, err);
    return;
  }
#endif
  calc_cpu(prev, next, prev_pts, next_pts, status, err);
}

void SparsePyrLK::calc_cpu(const ImageView &prev, const ImageView &next,
                           const std::vector<Point2f> &prev_pts, std::vector<Point2f> &next_pts,
                           std::vector<std::uint8_t> &status, std::vector<float> &err) const {
  if (prev.width != next.width || prev.height != next.height)
    throw std::invalid_argument("prev/next must share dimensions");

  std::vector<GrayImage> pyr0;
  std::vector<GrayImage> pyr1;
  pyr0.push_back(to_float(prev));
  pyr1.push_back(to_float(next));

  // Keep coarsest level large enough for the integration window.
  int max_level = options_.max_level;
  while (max_level > 0) {
    const int cw = std::max(1, prev.width >> max_level);
    const int ch = std::max(1, prev.height >> max_level);
    if (cw > options_.win_size && ch > options_.win_size)
      break;
    --max_level;
  }

  for (int l = 1; l <= max_level; ++l) {
    pyr0.push_back(downsample2(pyr0.back()));
    pyr1.push_back(downsample2(pyr1.back()));
  }

  next_pts.resize(prev_pts.size());
  status.assign(prev_pts.size(), 0);
  err.assign(prev_pts.size(), 0.0f);

  for (std::size_t i = 0; i < prev_pts.size(); ++i) {
    float x = prev_pts[i].x * std::ldexp(1.0f, -max_level);
    float y = prev_pts[i].y * std::ldexp(1.0f, -max_level);
    float u = 0.0f;
    float v = 0.0f;
    bool ok = true;
    float last_err = 0.0f;
    for (int level = max_level; level >= 0; --level) {
      if (level != max_level) {
        x *= 2.0f;
        y *= 2.0f;
        u *= 2.0f;
        v *= 2.0f;
      }
      ok = track_point(pyr0[level], pyr1[level], x, y, u, v, options_.win_size, options_.max_iters,
                       options_.epsilon, options_.min_eig, last_err);
      if (!ok)
        break;
    }
    if (ok) {
      next_pts[i] = {prev_pts[i].x + u, prev_pts[i].y + v};
      status[i] = 1;
      err[i] = last_err;
    } else {
      next_pts[i] = prev_pts[i];
      status[i] = 0;
      err[i] = 1e6f;
    }
  }
}

} // namespace optical_flow_sdk
