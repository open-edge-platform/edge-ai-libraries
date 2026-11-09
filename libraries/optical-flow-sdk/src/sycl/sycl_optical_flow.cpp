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
    // Prefer OpenCL GPU on hosts where Level Zero UR init fails (common with
    // partial user-local oneAPI installs). Fall back to default selector.
    try {
      q = new sycl::queue(sycl::gpu_selector_v,
                          {sycl::property::queue::in_order{}});
    } catch (...) {
      try {
        q = new sycl::queue(
            sycl::aspect_selector(sycl::aspect::gpu),
            {sycl::property::queue::in_order{}});
      } catch (...) {
        q = new sycl::queue(sycl::default_selector_v,
                            {sycl::property::queue::in_order{}});
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

} // namespace

struct SyclOpticalFlow::Impl {
  Preset preset = Preset::Fast;
  int patch_size = 8;
  int patch_stride = 8;
  int coarsest_scale = 2;
  int finest_scale = 0;
  int gradient_descent_iters = 6;
  mutable std::mutex mutex;
};

SyclOpticalFlow::SyclOpticalFlow(Preset preset) : impl_(std::make_unique<Impl>()) {
  impl_->preset = preset;
  switch (preset) {
  case Preset::Fast:
    impl_->patch_size = 8;
    impl_->patch_stride = 8;
    impl_->coarsest_scale = 2;
    impl_->finest_scale = 2;
    impl_->gradient_descent_iters = 2;
    break;
  case Preset::Medium:
    impl_->patch_size = 8;
    impl_->patch_stride = 3;
    impl_->coarsest_scale = 3;
    impl_->finest_scale = 0;
    impl_->gradient_descent_iters = 12;
    break;
  case Preset::Slow:
    impl_->patch_size = 12;
    impl_->patch_stride = 3;
    impl_->coarsest_scale = 3;
    impl_->finest_scale = 0;
    impl_->gradient_descent_iters = 16;
    break;
  }
  (void)shared_queue();
}

SyclOpticalFlow::~SyclOpticalFlow() = default;
SyclOpticalFlow::SyclOpticalFlow(SyclOpticalFlow &&) noexcept = default;
SyclOpticalFlow &SyclOpticalFlow::operator=(SyclOpticalFlow &&) noexcept = default;

Preset SyclOpticalFlow::preset() const { return impl_->preset; }

void SyclOpticalFlow::calc(const ImageView &prev, const ImageView &next, FlowField &flow) const {
  CostMap cost;
  calc(prev, next, flow, cost);
}

void SyclOpticalFlow::calc(const ImageView &prev, const ImageView &next, FlowField &flow,
                           CostMap &cost) const {
  prev.validate();
  next.validate();
  if (prev.width != next.width || prev.height != next.height)
    throw std::invalid_argument("prev/next must share dimensions");

  std::lock_guard<std::mutex> lock(impl_->mutex);
  sycl::queue &q = shared_queue();

  flow.allocate(prev.width, prev.height);
  cost.allocate(prev.width, prev.height);

  const int scales = impl_->coarsest_scale + 1;
  std::vector<int> widths(scales), heights(scales);
  widths[0] = prev.width;
  heights[0] = prev.height;
  for (int s = 1; s < scales; ++s) {
    widths[s] = std::max(1, widths[s - 1] / 2);
    heights[s] = std::max(1, heights[s - 1] / 2);
  }

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

  std::uint8_t *d_prev_u8 = sycl::malloc_device<std::uint8_t>(nbytes, q);
  std::uint8_t *d_next_u8 = sycl::malloc_device<std::uint8_t>(nbytes, q);
  q.memcpy(d_prev_u8, prev_pack.data(), nbytes);
  q.memcpy(d_next_u8, next_pack.data(), nbytes);

  std::vector<float *> pyr0(scales, nullptr), pyr1(scales, nullptr);
  std::vector<float *> flow_bufs(scales, nullptr);
  std::vector<std::uint8_t *> cost_bufs(scales, nullptr);
  std::vector<float *> acc_u(scales, nullptr), acc_v(scales, nullptr), acc_c(scales, nullptr),
      acc_w(scales, nullptr);

  auto free_all = [&] {
    sycl::free(d_prev_u8, q);
    sycl::free(d_next_u8, q);
    for (int s = 0; s < scales; ++s) {
      sycl::free(pyr0[s], q);
      sycl::free(pyr1[s], q);
      sycl::free(flow_bufs[s], q);
      sycl::free(cost_bufs[s], q);
      sycl::free(acc_u[s], q);
      sycl::free(acc_v[s], q);
      sycl::free(acc_c[s], q);
      sycl::free(acc_w[s], q);
    }
  };

  try {
    for (int s = 0; s < scales; ++s) {
      const std::size_t pix = static_cast<std::size_t>(widths[s]) * heights[s];
      pyr0[s] = sycl::malloc_device<float>(pix, q);
      pyr1[s] = sycl::malloc_device<float>(pix, q);
      flow_bufs[s] = sycl::malloc_device<float>(pix * 2, q);
      cost_bufs[s] = sycl::malloc_device<std::uint8_t>(pix, q);
      acc_u[s] = sycl::malloc_device<float>(pix, q);
      acc_v[s] = sycl::malloc_device<float>(pix, q);
      acc_c[s] = sycl::malloc_device<float>(pix, q);
      acc_w[s] = sycl::malloc_device<float>(pix, q);
    }

    auto u8_to_float = [&](std::uint8_t *src, float *dst, int w, int h) {
      q.parallel_for(sycl::range<2>(h, w), [=](sycl::id<2> id) {
        const int y = static_cast<int>(id[0]);
        const int x = static_cast<int>(id[1]);
        dst[y * w + x] = static_cast<float>(src[y * w + x]);
      });
    };
    u8_to_float(d_prev_u8, pyr0[0], widths[0], heights[0]);
    u8_to_float(d_next_u8, pyr1[0], widths[0], heights[0]);

    for (int s = 1; s < scales; ++s) {
      const int sw = widths[s - 1], sh = heights[s - 1], dw = widths[s], dh = heights[s];
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
      down(pyr0[s - 1], pyr0[s]);
      down(pyr1[s - 1], pyr1[s]);
    }

    {
      const int n = widths[impl_->coarsest_scale] * heights[impl_->coarsest_scale] * 2;
      float *f = flow_bufs[impl_->coarsest_scale];
      q.fill(f, 0.0f, static_cast<std::size_t>(n));
    }

    const int patch_size = impl_->patch_size;
    const int patch_stride = impl_->patch_stride;
    const int iters = impl_->gradient_descent_iters;

    for (int scale = impl_->coarsest_scale; scale >= impl_->finest_scale; --scale) {
      const int w = widths[scale];
      const int h = heights[scale];
      if (scale != impl_->coarsest_scale) {
        const int cw = widths[scale + 1];
        const int ch = heights[scale + 1];
        float *coarse = flow_bufs[scale + 1];
        float *fine = flow_bufs[scale];
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
      float *I0 = pyr0[scale];
      float *I1 = pyr1[scale];
      float *flow_in = flow_bufs[scale];
      float *fout = flow_bufs[scale];
      std::uint8_t *cout = cost_bufs[scale];
      const bool fast_atomic_free = impl_->preset == Preset::Fast && patch_size == 8;

      if (fast_atomic_free) {
        float *patch_u = sycl::malloc_device<float>(static_cast<std::size_t>(n_gx * n_gy), q);
        float *patch_v = sycl::malloc_device<float>(static_cast<std::size_t>(n_gx * n_gy), q);
        float *patch_c = sycl::malloc_device<float>(static_cast<std::size_t>(n_gx * n_gy), q);
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
              H11 += gxv * gxv;
              H12 += gxv * gyv;
              H22 += gyv * gyv;
            }
          }
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
            for (int py = 0; py < 8; ++py) {
              for (int px = 0; px < 8; ++px) {
                const int x = cx - ph + px;
                const int y = cy - ph + py;
                const int idx = py * 8 + px;
                const float warped = sample_bilinear_dev(
                    I1, w, h, static_cast<float>(x) + u, static_cast<float>(y) + v);
                const float err = warped - T[idx];
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
          const float u = (1.0f - tx) * (1.0f - ty) * u00 + tx * (1.0f - ty) * u10 +
                          (1.0f - tx) * ty * u01 + tx * ty * u11;
          const float v = (1.0f - tx) * (1.0f - ty) * v00 + tx * (1.0f - ty) * v10 +
                          (1.0f - tx) * ty * v01 + tx * ty * v11;
          const float c = (1.0f - tx) * (1.0f - ty) * c00 + tx * (1.0f - ty) * c10 +
                          (1.0f - tx) * ty * c01 + tx * ty * c11;
          fout[(y * w + x) * 2] = u;
          fout[(y * w + x) * 2 + 1] = v;
          cout[y * w + x] = static_cast<std::uint8_t>(sycl::clamp(c, 0.0f, 255.0f));
        });
        q.wait();
        sycl::free(patch_u, q);
        sycl::free(patch_v, q);
        sycl::free(patch_c, q);
        continue;
      }

      q.fill(acc_u[scale], 0.0f, pix);
      q.fill(acc_v[scale], 0.0f, pix);
      q.fill(acc_c[scale], 0.0f, pix);
      q.fill(acc_w[scale], 0.0f, pix);

      float *au = acc_u[scale];
      float *av = acc_v[scale];
      float *ac = acc_c[scale];
      float *aw = acc_w[scale];

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
            H11 += gxv * gxv;
            H12 += gxv * gyv;
            H22 += gyv * gyv;
          }
        }
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
          for (int py = 0; py < patch_size; ++py) {
            for (int px = 0; px < patch_size; ++px) {
              const int x = cx - ph + px;
              const int y = cy - ph + py;
              const int idx = py * patch_size + px;
              const float warped =
                  sample_bilinear_dev(I1, w, h, static_cast<float>(x) + u, static_cast<float>(y) + v);
              const float err = warped - T[idx];
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
    }

    if (impl_->finest_scale >= 2) {
      const int fs = impl_->finest_scale;
      const int cw = widths[fs];
      const int ch = heights[fs];
      const int fw = widths[0];
      const int fh = heights[0];
      const float scale_mul = static_cast<float>(1 << fs);
      float *coarse = flow_bufs[fs];
      float *fine = flow_bufs[0];
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
      for (int scale = impl_->finest_scale - 1; scale >= 0; --scale) {
        const int cw = widths[scale + 1];
        const int ch = heights[scale + 1];
        const int fw = widths[scale];
        const int fh = heights[scale];
        float *coarse = flow_bufs[scale + 1];
        float *fine = flow_bufs[scale];
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

    q.memcpy(flow.data.data(), flow_bufs[0], flow.data.size() * sizeof(float));
    if (impl_->finest_scale == 0)
      q.memcpy(cost.data.data(), cost_bufs[0], cost.data.size());
    else
      std::fill(cost.data.begin(), cost.data.end(), static_cast<std::uint8_t>(128));
    q.wait();
  } catch (...) {
    free_all();
    throw;
  }
  free_all();
}

} // namespace optical_flow_sdk
