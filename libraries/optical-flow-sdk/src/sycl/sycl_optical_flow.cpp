// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "optical_flow_sdk/sycl_optical_flow.hpp"

#include <sycl/sycl.hpp>

#include <algorithm>
#include <cmath>
#include <cstring>
#include <mutex>
#include <stdexcept>
#include <vector>

namespace optical_flow_sdk {
namespace {

sycl::queue &shared_queue() {
  static std::once_flag once;
  static sycl::queue *q = nullptr;
  std::call_once(once, [] {
    try {
      q = new sycl::queue(sycl::gpu_selector_v, {sycl::property::queue::in_order{}});
    } catch (...) {
      try {
        q = new sycl::queue(sycl::aspect_selector(sycl::aspect::gpu),
                            {sycl::property::queue::in_order{}});
      } catch (...) {
        q = new sycl::queue(sycl::default_selector_v, {sycl::property::queue::in_order{}});
      }
    }
  });
  return *q;
}

float sample_bilinear_dev(const float *img, int w, int h, float x, float y) {
  x = sycl::clamp(x, 0.0f, static_cast<float>(w - 1));
  y = sycl::clamp(y, 0.0f, static_cast<float>(h - 1));
  const int x0 = static_cast<int>(x);
  const int y0 = static_cast<int>(y);
  const int x1 = sycl::min(x0 + 1, w - 1);
  const int y1 = sycl::min(y0 + 1, h - 1);
  const float dx = x - static_cast<float>(x0);
  const float dy = y - static_cast<float>(y0);
  return (1.0f - dx) * (1.0f - dy) * img[y0 * w + x0] + dx * (1.0f - dy) * img[y0 * w + x1] +
         (1.0f - dx) * dy * img[y1 * w + x0] + dx * dy * img[y1 * w + x1];
}

template <typename T>
void free_usm(T *&p, sycl::queue &q) {
  if (p) {
    sycl::free(p, q);
    p = nullptr;
  }
}

struct Workspace {
  int width = 0;
  int height = 0;
  int scales = 0;
  std::uint8_t *prev_u8 = nullptr;
  std::uint8_t *next_u8 = nullptr;
  std::vector<float *> pyr0;
  std::vector<float *> pyr1;
  std::vector<float *> flow;
  std::vector<float *> flow_tmp;
  std::vector<float *> flow_d2;
  std::vector<std::uint8_t *> cost;
  std::vector<float *> acc_u;
  std::vector<float *> acc_v;
  std::vector<float *> acc_c;
  std::vector<float *> acc_w;
  float *patch_u = nullptr;
  float *patch_v = nullptr;
  float *patch_c = nullptr;
  int patch_capacity = 0;
  std::vector<int> widths;
  std::vector<int> heights;

  void clear(sycl::queue &q) {
    free_usm(prev_u8, q);
    free_usm(next_u8, q);
    for (auto &p : pyr0)
      free_usm(p, q);
    for (auto &p : pyr1)
      free_usm(p, q);
    for (auto &p : flow)
      free_usm(p, q);
    for (auto &p : flow_tmp)
      free_usm(p, q);
    for (auto &p : flow_d2)
      free_usm(p, q);
    for (auto &p : cost)
      free_usm(p, q);
    for (auto &p : acc_u)
      free_usm(p, q);
    for (auto &p : acc_v)
      free_usm(p, q);
    for (auto &p : acc_c)
      free_usm(p, q);
    for (auto &p : acc_w)
      free_usm(p, q);
    free_usm(patch_u, q);
    free_usm(patch_v, q);
    free_usm(patch_c, q);
    pyr0.clear();
    pyr1.clear();
    flow.clear();
    flow_tmp.clear();
    flow_d2.clear();
    cost.clear();
    acc_u.clear();
    acc_v.clear();
    acc_c.clear();
    acc_w.clear();
    widths.clear();
    heights.clear();
    width = height = scales = patch_capacity = 0;
  }

  void ensure(sycl::queue &q, int w, int h, int nscales) {
    if (w == width && h == height && nscales == scales && !pyr0.empty())
      return;
    clear(q);
    width = w;
    height = h;
    scales = nscales;
    widths.resize(scales);
    heights.resize(scales);
    widths[0] = w;
    heights[0] = h;
    for (int s = 1; s < scales; ++s) {
      widths[s] = std::max(1, widths[s - 1] / 2);
      heights[s] = std::max(1, heights[s - 1] / 2);
    }
    const std::size_t nbytes = static_cast<std::size_t>(w) * h;
    prev_u8 = sycl::malloc_device<std::uint8_t>(nbytes, q);
    next_u8 = sycl::malloc_device<std::uint8_t>(nbytes, q);
    pyr0.resize(scales, nullptr);
    pyr1.resize(scales, nullptr);
    flow.resize(scales, nullptr);
    flow_tmp.resize(scales, nullptr);
    flow_d2.resize(scales, nullptr);
    cost.resize(scales, nullptr);
    acc_u.resize(scales, nullptr);
    acc_v.resize(scales, nullptr);
    acc_c.resize(scales, nullptr);
    acc_w.resize(scales, nullptr);
    for (int s = 0; s < scales; ++s) {
      const std::size_t pix = static_cast<std::size_t>(widths[s]) * heights[s];
      pyr0[s] = sycl::malloc_device<float>(pix, q);
      pyr1[s] = sycl::malloc_device<float>(pix, q);
      flow[s] = sycl::malloc_device<float>(pix * 2, q);
      flow_tmp[s] = sycl::malloc_device<float>(pix * 2, q);
      flow_d2[s] = sycl::malloc_device<float>(pix * 2, q);
      cost[s] = sycl::malloc_device<std::uint8_t>(pix, q);
      acc_u[s] = sycl::malloc_device<float>(pix, q);
      acc_v[s] = sycl::malloc_device<float>(pix, q);
      acc_c[s] = sycl::malloc_device<float>(pix, q);
      acc_w[s] = sycl::malloc_device<float>(pix, q);
    }
  }

  void ensure_patches(sycl::queue &q, int n) {
    if (n <= patch_capacity && patch_u)
      return;
    free_usm(patch_u, q);
    free_usm(patch_v, q);
    free_usm(patch_c, q);
    patch_capacity = std::max(n, 1);
    patch_u = sycl::malloc_device<float>(static_cast<std::size_t>(patch_capacity), q);
    patch_v = sycl::malloc_device<float>(static_cast<std::size_t>(patch_capacity), q);
    patch_c = sycl::malloc_device<float>(static_cast<std::size_t>(patch_capacity), q);
  }
};

} // namespace

SyclU8Image::SyclU8Image(void *handle, int width, int height, bool owns)
    : handle_(handle), width_(width), height_(height), owns_(owns) {}

SyclU8Image::~SyclU8Image() {
  if (owns_ && handle_) {
    sycl::free(handle_, shared_queue());
    handle_ = nullptr;
  }
}

SyclU8Image::SyclU8Image(SyclU8Image &&other) noexcept
    : handle_(other.handle_), width_(other.width_), height_(other.height_), owns_(other.owns_) {
  other.handle_ = nullptr;
  other.width_ = other.height_ = 0;
  other.owns_ = false;
}

SyclU8Image &SyclU8Image::operator=(SyclU8Image &&other) noexcept {
  if (this != &other) {
    if (owns_ && handle_)
      sycl::free(handle_, shared_queue());
    handle_ = other.handle_;
    width_ = other.width_;
    height_ = other.height_;
    owns_ = other.owns_;
    other.handle_ = nullptr;
    other.width_ = other.height_ = 0;
    other.owns_ = false;
  }
  return *this;
}

SyclFlowBuffer::SyclFlowBuffer(void *handle, int width, int height, bool owns)
    : handle_(handle), width_(width), height_(height), owns_(owns) {}

SyclFlowBuffer::~SyclFlowBuffer() {
  if (owns_ && handle_) {
    sycl::free(handle_, shared_queue());
    handle_ = nullptr;
  }
}

SyclFlowBuffer::SyclFlowBuffer(SyclFlowBuffer &&other) noexcept
    : handle_(other.handle_), width_(other.width_), height_(other.height_), owns_(other.owns_) {
  other.handle_ = nullptr;
  other.width_ = other.height_ = 0;
  other.owns_ = false;
}

SyclFlowBuffer &SyclFlowBuffer::operator=(SyclFlowBuffer &&other) noexcept {
  if (this != &other) {
    if (owns_ && handle_)
      sycl::free(handle_, shared_queue());
    handle_ = other.handle_;
    width_ = other.width_;
    height_ = other.height_;
    owns_ = other.owns_;
    other.handle_ = nullptr;
    other.width_ = other.height_ = 0;
    other.owns_ = false;
  }
  return *this;
}

struct SyclOpticalFlow::Impl {
  Preset preset = Preset::Fast;
  int patch_size = 8;
  int patch_stride = 8;
  int coarsest_scale = 2;
  int finest_scale = 0;
  int gradient_descent_iters = 6;
  bool variational_refinement = true;
  int var_outer_iters = 5;
  int var_inner_iters = 5;
  float var_alpha = 20.0f;
  float var_delta = 5.0f;
  float var_gamma = 10.0f;
  float var_omega = 1.0f;
  mutable std::mutex mutex;
  mutable Workspace ws;
};

SyclOpticalFlow::SyclOpticalFlow(Preset preset) : impl_(std::make_unique<Impl>()) {
  impl_->preset = preset;
  switch (preset) {
  case Preset::Fast:
    // NVOFA-competitive quality under ≥6× budget (match OpenCL Fast).
    impl_->patch_size = 8;
    impl_->patch_stride = 6;
    impl_->coarsest_scale = 5;
    impl_->finest_scale = 2;
    impl_->gradient_descent_iters = 8;
    impl_->variational_refinement = false;
    impl_->var_outer_iters = 1;
    impl_->var_inner_iters = 5;
    impl_->var_alpha = 20.0f;
    impl_->var_delta = 5.0f;
    impl_->var_gamma = 10.0f;
    impl_->var_omega = 1.0f;
    break;
  case Preset::Medium:
    impl_->patch_size = 8;
    impl_->patch_stride = 3;
    impl_->coarsest_scale = 5;
    impl_->finest_scale = 1;
    impl_->gradient_descent_iters = 25;
    impl_->variational_refinement = false;
    impl_->var_outer_iters = 2;
    impl_->var_inner_iters = 5;
    impl_->var_alpha = 20.0f;
    impl_->var_delta = 5.0f;
    impl_->var_gamma = 10.0f;
    impl_->var_omega = 1.0f;
    break;
  case Preset::Slow:
    impl_->patch_size = 8;
    impl_->patch_stride = 3;
    impl_->coarsest_scale = 5;
    impl_->finest_scale = 0;
    impl_->gradient_descent_iters = 25;
    impl_->variational_refinement = false;
    impl_->var_outer_iters = 2;
    impl_->var_inner_iters = 5;
    impl_->var_alpha = 20.0f;
    impl_->var_delta = 5.0f;
    impl_->var_gamma = 10.0f;
    impl_->var_omega = 1.0f;
    break;
  }
  (void)shared_queue();
}

SyclOpticalFlow::~SyclOpticalFlow() {
  if (impl_) {
    try {
      impl_->ws.clear(shared_queue());
    } catch (...) {
    }
  }
}
SyclOpticalFlow::SyclOpticalFlow(SyclOpticalFlow &&) noexcept = default;
SyclOpticalFlow &SyclOpticalFlow::operator=(SyclOpticalFlow &&) noexcept = default;

Preset SyclOpticalFlow::preset() const { return impl_->preset; }

SyclU8Image SyclOpticalFlow::create_u8_image(int width, int height) const {
  if (width <= 0 || height <= 0)
    throw std::invalid_argument("SyclU8Image size must be positive");
  sycl::queue &q = shared_queue();
  auto *p = sycl::malloc_device<std::uint8_t>(static_cast<std::size_t>(width) * height, q);
  return SyclU8Image(p, width, height, true);
}

SyclFlowBuffer SyclOpticalFlow::create_flow_buffer(int width, int height) const {
  if (width <= 0 || height <= 0)
    throw std::invalid_argument("SyclFlowBuffer size must be positive");
  sycl::queue &q = shared_queue();
  auto *p = sycl::malloc_device<float>(static_cast<std::size_t>(width) * height * 2, q);
  return SyclFlowBuffer(p, width, height, true);
}

void SyclOpticalFlow::upload_u8(SyclU8Image &dst, const ImageView &src) const {
  src.validate();
  if (dst.empty() || dst.width() != src.width || dst.height() != src.height)
    throw std::invalid_argument("upload_u8 size mismatch");
  sycl::queue &q = shared_queue();
  const std::size_t nbytes = dst.bytes();
  auto *d = static_cast<std::uint8_t *>(dst.handle());
  if (src.row_stride() == static_cast<std::size_t>(src.width)) {
    q.memcpy(d, src.data, nbytes).wait();
  } else {
    std::vector<std::uint8_t> pack(nbytes);
    for (int y = 0; y < src.height; ++y)
      std::memcpy(pack.data() + static_cast<std::size_t>(y) * src.width, src.row(y),
                  static_cast<std::size_t>(src.width));
    q.memcpy(d, pack.data(), nbytes).wait();
  }
}

void SyclOpticalFlow::download_flow(const SyclFlowBuffer &src, FlowField &dst) const {
  if (src.empty())
    throw std::invalid_argument("download_flow empty buffer");
  dst.allocate(src.width(), src.height());
  shared_queue()
      .memcpy(dst.data.data(), static_cast<float *>(src.handle()), src.bytes())
      .wait();
}

void SyclOpticalFlow::finish() const { shared_queue().wait(); }

namespace {

void run_variational_refine_sycl(sycl::queue &q, Workspace &ws, int scale, int outer_iters,
                                 int inner_iters, float alpha, float delta, float gamma,
                                 float omega) {
  const int w = ws.widths[scale];
  const int h = ws.heights[scale];
  const std::size_t n2 = static_cast<std::size_t>(w) * h * 2;
  float *I0 = ws.pyr0[scale];
  float *I1 = ws.pyr1[scale];
  float *base = ws.flow[scale];
  float *d_a = ws.flow_tmp[scale];
  float *d_b = ws.flow_d2[scale];
  (void)delta;
  (void)gamma;
  for (int outer = 0; outer < outer_iters; ++outer) {
    q.fill(d_a, 0.0f, n2);
    for (int inner = 0; inner < inner_iters; ++inner) {
      float *din = d_a;
      float *dout = d_b;
      q.parallel_for(sycl::range<2>(h, w), [=](sycl::id<2> id) {
        const int y = static_cast<int>(id[0]);
        const int x = static_cast<int>(id[1]);
        const int idx = y * w + x;
        const float u0 = base[idx * 2];
        const float v0 = base[idx * 2 + 1];
        const float du = din[idx * 2];
        const float dv = din[idx * 2 + 1];
        const int xm = sycl::max(x - 1, 0);
        const int xp = sycl::min(x + 1, w - 1);
        const int ym = sycl::max(y - 1, 0);
        const int yp = sycl::min(y + 1, h - 1);
        const float du_avg =
            0.25f * (din[(y * w + xm) * 2] + din[(y * w + xp) * 2] + din[(ym * w + x) * 2] +
                     din[(yp * w + x) * 2]);
        const float dv_avg =
            0.25f * (din[(y * w + xm) * 2 + 1] + din[(y * w + xp) * 2 + 1] +
                     din[(ym * w + x) * 2 + 1] + din[(yp * w + x) * 2 + 1]);
        const float Ix = 0.5f * (I0[y * w + xp] - I0[y * w + xm]);
        const float Iy = 0.5f * (I0[yp * w + x] - I0[ym * w + x]);
        const float I1w = sample_bilinear_dev(I1, w, h, static_cast<float>(x) + u0 + du,
                                              static_cast<float>(y) + v0 + dv);
        const float Iz = I1w - I0[idx];
        const float num = Ix * du_avg + Iy * dv_avg + Iz;
        const float den = alpha + Ix * Ix + Iy * Iy;
        const float du_hat = du_avg - Ix * num / den;
        const float dv_hat = dv_avg - Iy * num / den;
        dout[idx * 2] = sycl::clamp(du + omega * (du_hat - du), -2.0f, 2.0f);
        dout[idx * 2 + 1] = sycl::clamp(dv + omega * (dv_hat - dv), -2.0f, 2.0f);
      });
      std::swap(d_a, d_b);
    }
    float *d_final = d_a;
    q.parallel_for(sycl::range<1>(n2), [=](sycl::id<1> id) {
      const int i = static_cast<int>(id[0]);
      base[i] += d_final[i];
    });
  }
  q.wait();
}

void run_sycl_dis(sycl::queue &q, Workspace &ws, Preset preset, int patch_size, int patch_stride,
                  int coarsest_scale, int finest_scale, int iters, bool variational, int var_outer,
                  int var_inner, float var_alpha, float var_delta, float var_gamma, float var_omega,
                  int width, int height, std::uint8_t *d_prev_u8, std::uint8_t *d_next_u8,
                  float *d_flow_out) {
  const int scales = coarsest_scale + 1;
  ws.ensure(q, width, height, scales);

  auto u8_to_float = [&](std::uint8_t *src, float *dst, int w, int h) {
    q.parallel_for(sycl::range<2>(h, w), [=](sycl::id<2> id) {
      const int y = static_cast<int>(id[0]);
      const int x = static_cast<int>(id[1]);
      dst[y * w + x] = static_cast<float>(src[y * w + x]);
    });
  };

  u8_to_float(d_prev_u8, ws.pyr0[0], ws.widths[0], ws.heights[0]);
  u8_to_float(d_next_u8, ws.pyr1[0], ws.widths[0], ws.heights[0]);

  for (int s = 1; s < scales; ++s) {
    const int sw = ws.widths[s - 1], sh = ws.heights[s - 1], dw = ws.widths[s], dh = ws.heights[s];
    auto down = [&](float *src, float *dst) {
      q.parallel_for(sycl::range<2>(dh, dw), [=](sycl::id<2> id) {
        const int y = static_cast<int>(id[0]);
        const int x = static_cast<int>(id[1]);
        const int x0 = x * 2;
        const int y0 = y * 2;
        const int x1 = sycl::min(x0 + 1, sw - 1);
        const int y1 = sycl::min(y0 + 1, sh - 1);
        dst[y * dw + x] =
            0.25f * (src[y0 * sw + x0] + src[y0 * sw + x1] + src[y1 * sw + x0] + src[y1 * sw + x1]);
      });
    };
    down(ws.pyr0[s - 1], ws.pyr0[s]);
    down(ws.pyr1[s - 1], ws.pyr1[s]);
  }

  {
    const int n = ws.widths[coarsest_scale] * ws.heights[coarsest_scale] * 2;
    float *f = ws.flow[coarsest_scale];
    q.fill(f, 0.0f, static_cast<std::size_t>(n));
  }

  for (int scale = coarsest_scale; scale >= finest_scale; --scale) {
    const int w = ws.widths[scale];
    const int h = ws.heights[scale];
    if (scale != coarsest_scale) {
      const int cw = ws.widths[scale + 1];
      const int ch = ws.heights[scale + 1];
      float *coarse = ws.flow[scale + 1];
      float *fine = ws.flow[scale];
      q.parallel_for(sycl::range<2>(h, w), [=](sycl::id<2> id) {
        const int y = static_cast<int>(id[0]);
        const int x = static_cast<int>(id[1]);
        const float sx = static_cast<float>(cw) / static_cast<float>(w);
        const float sy = static_cast<float>(ch) / static_cast<float>(h);
        const float cx = (static_cast<float>(x) + 0.5f) * sx - 0.5f;
        const float cy = (static_cast<float>(y) + 0.5f) * sy - 0.5f;
        int x0 = static_cast<int>(sycl::floor(cx));
        int y0 = static_cast<int>(sycl::floor(cy));
        x0 = sycl::clamp(x0, 0, cw - 1);
        y0 = sycl::clamp(y0, 0, ch - 1);
        const int x1 = sycl::min(x0 + 1, cw - 1);
        const int y1 = sycl::min(y0 + 1, ch - 1);
        const float dx = cx - static_cast<float>(x0);
        const float dy = cy - static_cast<float>(y0);
        const int i00 = (y0 * cw + x0) * 2;
        const int i10 = (y0 * cw + x1) * 2;
        const int i01 = (y1 * cw + x0) * 2;
        const int i11 = (y1 * cw + x1) * 2;
        const float u = (1 - dx) * (1 - dy) * coarse[i00] + dx * (1 - dy) * coarse[i10] +
                        (1 - dx) * dy * coarse[i01] + dx * dy * coarse[i11];
        const float v = (1 - dx) * (1 - dy) * coarse[i00 + 1] + dx * (1 - dy) * coarse[i10 + 1] +
                        (1 - dx) * dy * coarse[i01 + 1] + dx * dy * coarse[i11 + 1];
        fine[(y * w + x) * 2] = 2.0f * u;
        fine[(y * w + x) * 2 + 1] = 2.0f * v;
      });
    }

    const int half = patch_size / 2;
    if (w <= 2 * half || h <= 2 * half)
      continue;
    const int n_gx = (w - 2 * half + patch_stride - 1) / patch_stride;
    const int n_gy = (h - 2 * half + patch_stride - 1) / patch_stride;
    if (n_gx <= 0 || n_gy <= 0)
      continue;

    const std::size_t pix = static_cast<std::size_t>(w) * h;
    float *I0 = ws.pyr0[scale];
    float *I1 = ws.pyr1[scale];
    float *flow_in = ws.flow[scale];
    float *fout = ws.flow[scale];
    std::uint8_t *cout = ws.cost[scale];
    const bool fast_atomic_free = preset == Preset::Fast && patch_size == 8;

    if (fast_atomic_free) {
      ws.ensure_patches(q, n_gx * n_gy);
      float *patch_u = ws.patch_u;
      float *patch_v = ws.patch_v;
      float *patch_c = ws.patch_c;
      q.parallel_for(sycl::range<2>(n_gy, n_gx), [=](sycl::id<2> id) {
        const int gy = static_cast<int>(id[0]);
        const int gx = static_cast<int>(id[1]);
        const int ph = 4;
        const int cx = ph + gx * patch_stride;
        const int cy = ph + gy * patch_stride;
        const int pidx = gy * n_gx + gx;
        if (cx >= w - ph || cy >= h - ph) {
          patch_u[pidx] = 0.0f;
          patch_v[pidx] = 0.0f;
          patch_c[pidx] = 255.0f;
          return;
        }
        float H11 = 0.0f, H12 = 0.0f, H22 = 0.0f;
        float Ix[64], Iy[64], T[64];
        float mean_t = 0.0f;
        for (int py = 0; py < 8; ++py) {
          for (int px = 0; px < 8; ++px) {
            const int x = cx - ph + px;
            const int y = cy - ph + py;
            const float gxv =
                0.5f * (I0[y * w + sycl::min(x + 1, w - 1)] - I0[y * w + sycl::max(x - 1, 0)]);
            const float gyv =
                0.5f * (I0[sycl::min(y + 1, h - 1) * w + x] - I0[sycl::max(y - 1, 0) * w + x]);
            const int idx = py * 8 + px;
            Ix[idx] = gxv;
            Iy[idx] = gyv;
            T[idx] = I0[y * w + x];
            mean_t += T[idx];
            H11 += gxv * gxv;
            H12 += gxv * gyv;
            H22 += gyv * gyv;
          }
        }
        mean_t *= (1.0f / 64.0f);
        for (int i = 0; i < 64; ++i)
          T[i] -= mean_t;
        const float det = H11 * H22 - H12 * H12;
        if (sycl::fabs(det) < 1e-3f) {
          patch_u[pidx] = 0.0f;
          patch_v[pidx] = 0.0f;
          patch_c[pidx] = 255.0f;
          return;
        }
        const float invH11 = H22 / det;
        const float invH12 = -H12 / det;
        const float invH22 = H11 / det;
        float u = flow_in[(cy * w + cx) * 2];
        float v = flow_in[(cy * w + cx) * 2 + 1];
        float last_ssd = 0.0f;
        for (int it = 0; it < iters; ++it) {
          float b1 = 0.0f, b2 = 0.0f, ssd = 0.0f;
          float mean_w = 0.0f;
          float Wbuf[64];
          for (int py = 0; py < 8; ++py) {
            for (int px = 0; px < 8; ++px) {
              const int x = cx - ph + px;
              const int y = cy - ph + py;
              const int idx = py * 8 + px;
              Wbuf[idx] = sample_bilinear_dev(I1, w, h, static_cast<float>(x) + u,
                                              static_cast<float>(y) + v);
              mean_w += Wbuf[idx];
            }
          }
          mean_w *= (1.0f / 64.0f);
          for (int py = 0; py < 8; ++py) {
            for (int px = 0; px < 8; ++px) {
              const int idx = py * 8 + px;
              const float err = (Wbuf[idx] - mean_w) - T[idx];
              ssd += err * err;
              b1 += Ix[idx] * err;
              b2 += Iy[idx] * err;
            }
          }
          last_ssd = ssd;
          const float du = invH11 * b1 + invH12 * b2;
          const float dv = invH12 * b1 + invH22 * b2;
          u -= du;
          v -= dv;
          if (du * du + dv * dv < 1e-8f)
            break;
        }
        patch_u[pidx] = u;
        patch_v[pidx] = v;
        patch_c[pidx] = sycl::sqrt(last_ssd / 64.0f);
      });
      q.parallel_for(sycl::range<2>(h, w), [=](sycl::id<2> id) {
        const int y = static_cast<int>(id[0]);
        const int x = static_cast<int>(id[1]);
        const int ph = 4;
        const float gx = (static_cast<float>(x) - static_cast<float>(ph)) /
                         static_cast<float>(patch_stride);
        const float gy = (static_cast<float>(y) - static_cast<float>(ph)) /
                         static_cast<float>(patch_stride);
        const int gx0 = static_cast<int>(sycl::floor(gx));
        const int gy0 = static_cast<int>(sycl::floor(gy));
        const float tx = gx - static_cast<float>(gx0);
        const float ty = gy - static_cast<float>(gy0);
        const int ax0 = sycl::clamp(gx0, 0, n_gx - 1);
        const int ay0 = sycl::clamp(gy0, 0, n_gy - 1);
        const int ax1 = sycl::clamp(gx0 + 1, 0, n_gx - 1);
        const int ay1 = sycl::clamp(gy0 + 1, 0, n_gy - 1);
        const float u00 = patch_u[ay0 * n_gx + ax0];
        const float v00 = patch_v[ay0 * n_gx + ax0];
        const float c00 = patch_c[ay0 * n_gx + ax0];
        const float u10 = patch_u[ay0 * n_gx + ax1];
        const float v10 = patch_v[ay0 * n_gx + ax1];
        const float c10 = patch_c[ay0 * n_gx + ax1];
        const float u01 = patch_u[ay1 * n_gx + ax0];
        const float v01 = patch_v[ay1 * n_gx + ax0];
        const float c01 = patch_c[ay1 * n_gx + ax0];
        const float u11 = patch_u[ay1 * n_gx + ax1];
        const float v11 = patch_v[ay1 * n_gx + ax1];
        const float c11 = patch_c[ay1 * n_gx + ax1];
        const float a00 = (1.0f - tx) * (1.0f - ty);
        const float a10 = tx * (1.0f - ty);
        const float a01 = (1.0f - tx) * ty;
        const float a11 = tx * ty;
        const float w00 = a00 / (c00 * c00 + 1.0f);
        const float w10 = a10 / (c10 * c10 + 1.0f);
        const float w01 = a01 / (c01 * c01 + 1.0f);
        const float w11 = a11 / (c11 * c11 + 1.0f);
        const float wsum = w00 + w10 + w01 + w11 + 1.0e-6f;
        const float u = (w00 * u00 + w10 * u10 + w01 * u01 + w11 * u11) / wsum;
        const float v = (w00 * v00 + w10 * v10 + w01 * v01 + w11 * v11) / wsum;
        const float c = a00 * c00 + a10 * c10 + a01 * c01 + a11 * c11;
        fout[(y * w + x) * 2] = u;
        fout[(y * w + x) * 2 + 1] = v;
        cout[y * w + x] = static_cast<std::uint8_t>(sycl::clamp(c, 0.0f, 255.0f));
      });
      q.wait();
      if (variational)
        run_variational_refine_sycl(q, ws, scale, var_outer, var_inner, var_alpha, var_delta,
                                    var_gamma, var_omega);
      continue;
    }

    q.fill(ws.acc_u[scale], 0.0f, pix);
    q.fill(ws.acc_v[scale], 0.0f, pix);
    q.fill(ws.acc_c[scale], 0.0f, pix);
    q.fill(ws.acc_w[scale], 0.0f, pix);

    float *au = ws.acc_u[scale];
    float *av = ws.acc_v[scale];
    float *ac = ws.acc_c[scale];
    float *aw = ws.acc_w[scale];

    q.parallel_for(sycl::range<2>(n_gy, n_gx), [=](sycl::id<2> id) {
      const int gy = static_cast<int>(id[0]);
      const int gx = static_cast<int>(id[1]);
      const int ph = patch_size / 2;
      const int cx = ph + gx * patch_stride;
      const int cy = ph + gy * patch_stride;
      if (cx >= w - ph || cy >= h - ph)
        return;

      float H11 = 0.0f, H12 = 0.0f, H22 = 0.0f;
      float Ix[16 * 16];
      float Iy[16 * 16];
      float T[16 * 16];
      if (patch_size > 16)
        return;
      float mean_t = 0.0f;
      const float inv_n = 1.0f / static_cast<float>(patch_size * patch_size);
      for (int py = 0; py < patch_size; ++py) {
        for (int px = 0; px < patch_size; ++px) {
          const int x = cx - ph + px;
          const int y = cy - ph + py;
          const float gxv =
              0.5f * (I0[y * w + sycl::min(x + 1, w - 1)] - I0[y * w + sycl::max(x - 1, 0)]);
          const float gyv =
              0.5f * (I0[sycl::min(y + 1, h - 1) * w + x] - I0[sycl::max(y - 1, 0) * w + x]);
          const int idx = py * patch_size + px;
          Ix[idx] = gxv;
          Iy[idx] = gyv;
          T[idx] = I0[y * w + x];
          mean_t += T[idx];
          H11 += gxv * gxv;
          H12 += gxv * gyv;
          H22 += gyv * gyv;
        }
      }
      mean_t *= inv_n;
      for (int i = 0; i < patch_size * patch_size; ++i)
        T[i] -= mean_t;
      const float det = H11 * H22 - H12 * H12;
      if (sycl::fabs(det) < 1e-3f)
        return;
      const float invH11 = H22 / det;
      const float invH12 = -H12 / det;
      const float invH22 = H11 / det;
      float u = flow_in[(cy * w + cx) * 2];
      float v = flow_in[(cy * w + cx) * 2 + 1];
      float last_ssd = 0.0f;
      for (int it = 0; it < iters; ++it) {
        float b1 = 0.0f, b2 = 0.0f, ssd = 0.0f;
        float mean_w = 0.0f;
        float Wbuf[16 * 16];
        for (int py = 0; py < patch_size; ++py) {
          for (int px = 0; px < patch_size; ++px) {
            const int x = cx - ph + px;
            const int y = cy - ph + py;
            const int idx = py * patch_size + px;
            Wbuf[idx] =
                sample_bilinear_dev(I1, w, h, static_cast<float>(x) + u, static_cast<float>(y) + v);
            mean_w += Wbuf[idx];
          }
        }
        mean_w *= inv_n;
        for (int py = 0; py < patch_size; ++py) {
          for (int px = 0; px < patch_size; ++px) {
            const int idx = py * patch_size + px;
            const float err = (Wbuf[idx] - mean_w) - T[idx];
            ssd += err * err;
            b1 += Ix[idx] * err;
            b2 += Iy[idx] * err;
          }
        }
        last_ssd = ssd;
        const float du = invH11 * b1 + invH12 * b2;
        const float dv = invH12 * b1 + invH22 * b2;
        u -= du;
        v -= dv;
        if (du * du + dv * dv < 1e-8f)
          break;
      }
      const float patch_cost =
          sycl::sqrt(last_ssd / static_cast<float>(patch_size * patch_size));
      const int y0 = sycl::max(0, cy - ph);
      const int y1 = sycl::min(h - 1, cy + ph);
      const int x0 = sycl::max(0, cx - ph);
      const int x1 = sycl::min(w - 1, cx + ph);
      for (int y = y0; y <= y1; ++y) {
        for (int x = x0; x <= x1; ++x) {
          const float dx = static_cast<float>(x - cx);
          const float dy = static_cast<float>(y - cy);
          const float wt =
              sycl::max(0.0f, 1.0f - sycl::sqrt(dx * dx + dy * dy) / (ph + 1e-3f));
          if (wt <= 0.0f)
            continue;
          const int idx = y * w + x;
          sycl::atomic_ref<float, sycl::memory_order::relaxed, sycl::memory_scope::device,
                           sycl::access::address_space::global_space>
              rw(aw[idx]);
          sycl::atomic_ref<float, sycl::memory_order::relaxed, sycl::memory_scope::device,
                           sycl::access::address_space::global_space>
              ru(au[idx]);
          sycl::atomic_ref<float, sycl::memory_order::relaxed, sycl::memory_scope::device,
                           sycl::access::address_space::global_space>
              rv(av[idx]);
          sycl::atomic_ref<float, sycl::memory_order::relaxed, sycl::memory_scope::device,
                           sycl::access::address_space::global_space>
              rc(ac[idx]);
          rw.fetch_add(wt);
          ru.fetch_add(wt * u);
          rv.fetch_add(wt * v);
          rc.fetch_add(wt * patch_cost);
        }
      }
    });

    q.parallel_for(sycl::range<1>(pix), [=](sycl::id<1> id) {
      const int i = static_cast<int>(id[0]);
      const float wsum = aw[i];
      if (wsum > 1e-6f) {
        fout[i * 2] = au[i] / wsum;
        fout[i * 2 + 1] = av[i] / wsum;
        cout[i] = static_cast<std::uint8_t>(
            sycl::clamp(ac[i] / wsum, 0.0f, 255.0f));
      } else {
        fout[i * 2] = 0.0f;
        fout[i * 2 + 1] = 0.0f;
        cout[i] = 255;
      }
    });
    q.wait();
    if (variational)
      run_variational_refine_sycl(q, ws, scale, var_outer, var_inner, var_alpha, var_delta,
                                  var_gamma, var_omega);
  }

  if (finest_scale >= 2) {
    const int fs = finest_scale;
    const int cw = ws.widths[fs];
    const int ch = ws.heights[fs];
    const int fw = ws.widths[0];
    const int fh = ws.heights[0];
    const float scale_mul = static_cast<float>(1 << fs);
    float *coarse = ws.flow[fs];
    float *fine = ws.flow[0];
    q.parallel_for(sycl::range<2>(fh, fw), [=](sycl::id<2> id) {
      const int y = static_cast<int>(id[0]);
      const int x = static_cast<int>(id[1]);
      const float sx = static_cast<float>(cw) / static_cast<float>(fw);
      const float sy = static_cast<float>(ch) / static_cast<float>(fh);
      const float cx = (static_cast<float>(x) + 0.5f) * sx - 0.5f;
      const float cy = (static_cast<float>(y) + 0.5f) * sy - 0.5f;
      int x0 = static_cast<int>(sycl::floor(cx));
      int y0 = static_cast<int>(sycl::floor(cy));
      x0 = sycl::clamp(x0, 0, cw - 1);
      y0 = sycl::clamp(y0, 0, ch - 1);
      const int x1 = sycl::min(x0 + 1, cw - 1);
      const int y1 = sycl::min(y0 + 1, ch - 1);
      const float dx = cx - static_cast<float>(x0);
      const float dy = cy - static_cast<float>(y0);
      const int i00 = (y0 * cw + x0) * 2;
      const int i10 = (y0 * cw + x1) * 2;
      const int i01 = (y1 * cw + x0) * 2;
      const int i11 = (y1 * cw + x1) * 2;
      const float u = (1 - dx) * (1 - dy) * coarse[i00] + dx * (1 - dy) * coarse[i10] +
                      (1 - dx) * dy * coarse[i01] + dx * dy * coarse[i11];
      const float v = (1 - dx) * (1 - dy) * coarse[i00 + 1] + dx * (1 - dy) * coarse[i10 + 1] +
                      (1 - dx) * dy * coarse[i01 + 1] + dx * dy * coarse[i11 + 1];
      fine[(y * fw + x) * 2] = scale_mul * u;
      fine[(y * fw + x) * 2 + 1] = scale_mul * v;
    });
  } else {
    for (int scale = finest_scale - 1; scale >= 0; --scale) {
      const int cw = ws.widths[scale + 1];
      const int ch = ws.heights[scale + 1];
      const int fw = ws.widths[scale];
      const int fh = ws.heights[scale];
      float *coarse = ws.flow[scale + 1];
      float *fine = ws.flow[scale];
      q.parallel_for(sycl::range<2>(fh, fw), [=](sycl::id<2> id) {
        const int y = static_cast<int>(id[0]);
        const int x = static_cast<int>(id[1]);
        const float sx = static_cast<float>(cw) / static_cast<float>(fw);
        const float sy = static_cast<float>(ch) / static_cast<float>(fh);
        const float cx = (static_cast<float>(x) + 0.5f) * sx - 0.5f;
        const float cy = (static_cast<float>(y) + 0.5f) * sy - 0.5f;
        int x0 = static_cast<int>(sycl::floor(cx));
        int y0 = static_cast<int>(sycl::floor(cy));
        x0 = sycl::clamp(x0, 0, cw - 1);
        y0 = sycl::clamp(y0, 0, ch - 1);
        const int x1 = sycl::min(x0 + 1, cw - 1);
        const int y1 = sycl::min(y0 + 1, ch - 1);
        const float dx = cx - static_cast<float>(x0);
        const float dy = cy - static_cast<float>(y0);
        const int i00 = (y0 * cw + x0) * 2;
        const int i10 = (y0 * cw + x1) * 2;
        const int i01 = (y1 * cw + x0) * 2;
        const int i11 = (y1 * cw + x1) * 2;
        const float u = (1 - dx) * (1 - dy) * coarse[i00] + dx * (1 - dy) * coarse[i10] +
                        (1 - dx) * dy * coarse[i01] + dx * dy * coarse[i11];
        const float v = (1 - dx) * (1 - dy) * coarse[i00 + 1] + dx * (1 - dy) * coarse[i10 + 1] +
                        (1 - dx) * dy * coarse[i01 + 1] + dx * dy * coarse[i11 + 1];
        fine[(y * fw + x) * 2] = 2.0f * u;
        fine[(y * fw + x) * 2 + 1] = 2.0f * v;
      });
    }
  }


  if (d_flow_out != ws.flow[0]) {
    q.memcpy(d_flow_out, ws.flow[0],
             static_cast<std::size_t>(ws.width) * ws.height * 2 * sizeof(float));
  }
  q.wait();
}

} // namespace

void SyclOpticalFlow::calc_device(const SyclU8Image &prev, const SyclU8Image &next,
                                 SyclFlowBuffer &flow) const {
  if (prev.empty() || next.empty() || flow.empty())
    throw std::invalid_argument("calc_device requires non-empty device buffers");
  if (prev.width() != next.width() || prev.height() != next.height() ||
      prev.width() != flow.width() || prev.height() != flow.height())
    throw std::invalid_argument("calc_device buffer sizes must match");
  std::lock_guard<std::mutex> lock(impl_->mutex);
  sycl::queue &q = shared_queue();
  const int scales = impl_->coarsest_scale + 1;
  impl_->ws.width = prev.width();
  impl_->ws.height = prev.height();
  impl_->ws.ensure(q, prev.width(), prev.height(), scales);
  run_sycl_dis(q, impl_->ws, impl_->preset, impl_->patch_size, impl_->patch_stride,
               impl_->coarsest_scale, impl_->finest_scale, impl_->gradient_descent_iters,
               impl_->variational_refinement, impl_->var_outer_iters, impl_->var_inner_iters,
               impl_->var_alpha, impl_->var_delta, impl_->var_gamma, impl_->var_omega,
               prev.width(), prev.height(), static_cast<std::uint8_t *>(prev.handle()),
               static_cast<std::uint8_t *>(next.handle()), static_cast<float *>(flow.handle()));
}

void SyclOpticalFlow::calc(const ImageView &prev, const ImageView &next, FlowField &flow) const {
  CostMap unused;
  calc_impl(prev, next, flow, unused, false);
}

void SyclOpticalFlow::calc(const ImageView &prev, const ImageView &next, FlowField &flow,
                           CostMap &cost) const {
  calc_impl(prev, next, flow, cost, true);
}

void SyclOpticalFlow::calc_impl(const ImageView &prev, const ImageView &next, FlowField &flow,
                                CostMap &cost, bool want_cost) const {
  prev.validate();
  next.validate();
  if (prev.width != next.width || prev.height != next.height)
    throw std::invalid_argument("prev/next must share dimensions");

  std::lock_guard<std::mutex> lock(impl_->mutex);
  sycl::queue &q = shared_queue();
  const int scales = impl_->coarsest_scale + 1;
  impl_->ws.ensure(q, prev.width, prev.height, scales);

  const std::size_t nbytes = static_cast<std::size_t>(prev.width) * prev.height;
  std::vector<std::uint8_t> prev_pack(nbytes), next_pack(nbytes);
  if (prev.row_stride() == static_cast<std::size_t>(prev.width)) {
    std::memcpy(prev_pack.data(), prev.data, nbytes);
  } else {
    for (int y = 0; y < prev.height; ++y)
      std::memcpy(prev_pack.data() + static_cast<std::size_t>(y) * prev.width, prev.row(y),
                  static_cast<std::size_t>(prev.width));
  }
  if (next.row_stride() == static_cast<std::size_t>(next.width)) {
    std::memcpy(next_pack.data(), next.data, nbytes);
  } else {
    for (int y = 0; y < next.height; ++y)
      std::memcpy(next_pack.data() + static_cast<std::size_t>(y) * next.width, next.row(y),
                  static_cast<std::size_t>(next.width));
  }

  q.memcpy(impl_->ws.prev_u8, prev_pack.data(), nbytes);
  q.memcpy(impl_->ws.next_u8, next_pack.data(), nbytes);
  q.wait();
  run_sycl_dis(q, impl_->ws, impl_->preset, impl_->patch_size, impl_->patch_stride,
               impl_->coarsest_scale, impl_->finest_scale, impl_->gradient_descent_iters,
               impl_->variational_refinement, impl_->var_outer_iters, impl_->var_inner_iters,
               impl_->var_alpha, impl_->var_delta, impl_->var_gamma, impl_->var_omega, prev.width,
               prev.height, impl_->ws.prev_u8, impl_->ws.next_u8, impl_->ws.flow[0]);
  // run_sycl_dis already wrote flow[0]; avoid a redundant device memcpy by reading it out.
  flow.allocate(prev.width, prev.height);
  q.memcpy(flow.data.data(), impl_->ws.flow[0], flow.data.size() * sizeof(float)).wait();
  if (want_cost) {
    cost.allocate(prev.width, prev.height);
    if (impl_->finest_scale == 0) {
      q.memcpy(cost.data.data(), impl_->ws.cost[0], cost.data.size()).wait();
    } else {
      std::fill(cost.data.begin(), cost.data.end(), static_cast<std::uint8_t>(128));
    }
  }
}

} // namespace optical_flow_sdk
