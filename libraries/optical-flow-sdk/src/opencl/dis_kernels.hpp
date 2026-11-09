// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#pragma once

// Device-resident DIS-lite kernels. Densify is patch-scattered with float
// atomics (much cheaper than per-pixel lattice walks on Intel iGPU).
inline constexpr const char *kOpenCLDisKernelSource = R"CLC(
inline void atomic_add_float(__global float *addr, float val) {
  volatile __global uint *uaddr = (__global uint *)addr;
  uint old = *uaddr;
  uint assumed;
  do {
    assumed = old;
    const float next = as_float(assumed) + val;
    old = atomic_cmpxchg(uaddr, assumed, as_uint(next));
  } while (assumed != old);
}

__kernel void u8_to_float(__global const uchar *src, __global float *dst,
                          const int width, const int height, const int src_stride) {
  const int x = get_global_id(0);
  const int y = get_global_id(1);
  if (x >= width || y >= height)
    return;
  dst[y * width + x] = (float)src[y * src_stride + x];
}

// Direct full-res u8 → half-res float (skips an intermediate full-res float pyramid level).
__kernel void u8_downsample2_to_float(__global const uchar *src, __global float *dst,
                                      const int src_w, const int src_h, const int dst_w,
                                      const int dst_h, const int src_stride) {
  const int x = get_global_id(0);
  const int y = get_global_id(1);
  if (x >= dst_w || y >= dst_h)
    return;
  const int x0 = x * 2;
  const int y0 = y * 2;
  const int x1 = min(x0 + 1, src_w - 1);
  const int y1 = min(y0 + 1, src_h - 1);
  const float s00 = (float)src[y0 * src_stride + x0];
  const float s10 = (float)src[y0 * src_stride + x1];
  const float s01 = (float)src[y1 * src_stride + x0];
  const float s11 = (float)src[y1 * src_stride + x1];
  dst[y * dst_w + x] = 0.25f * (s00 + s10 + s01 + s11);
}

// Full-res u8 → quarter-res float (2×2 box of 2×2 boxes) for Fast single-scale path.
__kernel void u8_downsample4_to_float(__global const uchar *src, __global float *dst,
                                      const int src_w, const int src_h, const int dst_w,
                                      const int dst_h, const int src_stride) {
  const int x = get_global_id(0);
  const int y = get_global_id(1);
  if (x >= dst_w || y >= dst_h)
    return;
  const int x0 = x * 4;
  const int y0 = y * 4;
  float sum = 0.0f;
  for (int dy = 0; dy < 4; ++dy) {
    const int yy = min(y0 + dy, src_h - 1);
    for (int dx = 0; dx < 4; ++dx) {
      const int xx = min(x0 + dx, src_w - 1);
      sum += (float)src[yy * src_stride + xx];
    }
  }
  dst[y * dst_w + x] = sum * (1.0f / 16.0f);
}

__kernel void downsample2(__global const float *src, __global float *dst,
                          const int src_w, const int src_h, const int dst_w, const int dst_h) {
  const int x = get_global_id(0);
  const int y = get_global_id(1);
  if (x >= dst_w || y >= dst_h)
    return;
  const int x0 = x * 2;
  const int y0 = y * 2;
  const int x1 = min(x0 + 1, src_w - 1);
  const int y1 = min(y0 + 1, src_h - 1);
  dst[y * dst_w + x] =
      0.25f * (src[y0 * src_w + x0] + src[y0 * src_w + x1] + src[y1 * src_w + x0] +
               src[y1 * src_w + x1]);
}

__kernel void upsample_flow(__global const float *coarse, __global float *fine,
                            const int cw, const int ch, const int fw, const int fh) {
  const int x = get_global_id(0);
  const int y = get_global_id(1);
  if (x >= fw || y >= fh)
    return;
  const float sx = (float)cw / (float)fw;
  const float sy = (float)ch / (float)fh;
  const float cx = ((float)x + 0.5f) * sx - 0.5f;
  const float cy = ((float)y + 0.5f) * sy - 0.5f;
  int x0 = (int)floor(cx);
  int y0 = (int)floor(cy);
  x0 = clamp(x0, 0, cw - 1);
  y0 = clamp(y0, 0, ch - 1);
  const int x1 = min(x0 + 1, cw - 1);
  const int y1 = min(y0 + 1, ch - 1);
  const float dx = cx - (float)x0;
  const float dy = cy - (float)y0;
  const int i00 = (y0 * cw + x0) * 2;
  const int i10 = (y0 * cw + x1) * 2;
  const int i01 = (y1 * cw + x0) * 2;
  const int i11 = (y1 * cw + x1) * 2;
  const float u = (1 - dx) * (1 - dy) * coarse[i00] + dx * (1 - dy) * coarse[i10] +
                  (1 - dx) * dy * coarse[i01] + dx * dy * coarse[i11];
  const float v = (1 - dx) * (1 - dy) * coarse[i00 + 1] + dx * (1 - dy) * coarse[i10 + 1] +
                  (1 - dx) * dy * coarse[i01 + 1] + dx * dy * coarse[i11 + 1];
  const int out = (y * fw + x) * 2;
  fine[out] = 2.0f * u;
  fine[out + 1] = 2.0f * v;
}

// Direct N× upsample with matching flow scale (scale_mul = fw/cw typically 4 or 8).
__kernel void upsample_flow_scaled(__global const float *coarse, __global float *fine,
                                   const int cw, const int ch, const int fw, const int fh,
                                   const float scale_mul) {
  const int x = get_global_id(0);
  const int y = get_global_id(1);
  if (x >= fw || y >= fh)
    return;
  const float sx = (float)cw / (float)fw;
  const float sy = (float)ch / (float)fh;
  const float cx = ((float)x + 0.5f) * sx - 0.5f;
  const float cy = ((float)y + 0.5f) * sy - 0.5f;
  int x0 = (int)floor(cx);
  int y0 = (int)floor(cy);
  x0 = clamp(x0, 0, cw - 1);
  y0 = clamp(y0, 0, ch - 1);
  const int x1 = min(x0 + 1, cw - 1);
  const int y1 = min(y0 + 1, ch - 1);
  const float dx = cx - (float)x0;
  const float dy = cy - (float)y0;
  const int i00 = (y0 * cw + x0) * 2;
  const int i10 = (y0 * cw + x1) * 2;
  const int i01 = (y1 * cw + x0) * 2;
  const int i11 = (y1 * cw + x1) * 2;
  const float u = (1 - dx) * (1 - dy) * coarse[i00] + dx * (1 - dy) * coarse[i10] +
                  (1 - dx) * dy * coarse[i01] + dx * dy * coarse[i11];
  const float v = (1 - dx) * (1 - dy) * coarse[i00 + 1] + dx * (1 - dy) * coarse[i10 + 1] +
                  (1 - dx) * dy * coarse[i01 + 1] + dx * dy * coarse[i11 + 1];
  const int out = (y * fw + x) * 2;
  fine[out] = scale_mul * u;
  fine[out + 1] = scale_mul * v;
}

// Direct quarter→full upsample with ×4 flow scale (one launch instead of two).
__kernel void upsample_flow_x4(__global const float *coarse, __global float *fine,
                               const int cw, const int ch, const int fw, const int fh) {
  const int x = get_global_id(0);
  const int y = get_global_id(1);
  if (x >= fw || y >= fh)
    return;
  const float sx = (float)cw / (float)fw;
  const float sy = (float)ch / (float)fh;
  const float cx = ((float)x + 0.5f) * sx - 0.5f;
  const float cy = ((float)y + 0.5f) * sy - 0.5f;
  int x0 = (int)floor(cx);
  int y0 = (int)floor(cy);
  x0 = clamp(x0, 0, cw - 1);
  y0 = clamp(y0, 0, ch - 1);
  const int x1 = min(x0 + 1, cw - 1);
  const int y1 = min(y0 + 1, ch - 1);
  const float dx = cx - (float)x0;
  const float dy = cy - (float)y0;
  const int i00 = (y0 * cw + x0) * 2;
  const int i10 = (y0 * cw + x1) * 2;
  const int i01 = (y1 * cw + x0) * 2;
  const int i11 = (y1 * cw + x1) * 2;
  const float u = (1 - dx) * (1 - dy) * coarse[i00] + dx * (1 - dy) * coarse[i10] +
                  (1 - dx) * dy * coarse[i01] + dx * dy * coarse[i11];
  const float v = (1 - dx) * (1 - dy) * coarse[i00 + 1] + dx * (1 - dy) * coarse[i10 + 1] +
                  (1 - dx) * dy * coarse[i01 + 1] + dx * dy * coarse[i11 + 1];
  const int out = (y * fw + x) * 2;
  fine[out] = 4.0f * u;
  fine[out + 1] = 4.0f * v;
}

float sample_bilinear(__global const float *img, int w, int h, float x, float y) {
  x = clamp(x, 0.0f, (float)(w - 1));
  y = clamp(y, 0.0f, (float)(h - 1));
  const int x0 = (int)x;
  const int y0 = (int)y;
  const int x1 = min(x0 + 1, w - 1);
  const int y1 = min(y0 + 1, h - 1);
  const float dx = x - (float)x0;
  const float dy = y - (float)y0;
  return (1.0f - dx) * (1.0f - dy) * img[y0 * w + x0] + dx * (1.0f - dy) * img[y0 * w + x1] +
         (1.0f - dx) * dy * img[y1 * w + x0] + dx * dy * img[y1 * w + x1];
}

// One work-item per patch: inverse-compositional LK + scatter densify into
// weight / flow accumulators (atomics).
__kernel void estimate_and_scatter(__global const float *I0, __global const float *I1,
                                   __global const float *flow_in, __global float *acc_u,
                                   __global float *acc_v, __global float *acc_c,
                                   __global float *acc_w, const int width, const int height,
                                   const int patch_size, const int patch_stride, const int iters,
                                   const int n_gx) {
  const int gx = get_global_id(0);
  const int gy = get_global_id(1);
  const int ph = patch_size / 2;
  const int cx = ph + gx * patch_stride;
  const int cy = ph + gy * patch_stride;
  if (cx >= width - ph || cy >= height - ph)
    return;

  float H11 = 0.0f, H12 = 0.0f, H22 = 0.0f;
  const int max_ps = 16;
  float Ix[16 * 16];
  float Iy[16 * 16];
  float T[16 * 16];
  if (patch_size > max_ps)
    return;

  for (int py = 0; py < patch_size; ++py) {
    for (int px = 0; px < patch_size; ++px) {
      const int x = cx - ph + px;
      const int y = cy - ph + py;
      const float gxv =
          0.5f * (I0[y * width + min(x + 1, width - 1)] - I0[y * width + max(x - 1, 0)]);
      const float gyv =
          0.5f * (I0[min(y + 1, height - 1) * width + x] - I0[max(y - 1, 0) * width + x]);
      const int idx = py * patch_size + px;
      Ix[idx] = gxv;
      Iy[idx] = gyv;
      T[idx] = I0[y * width + x];
      H11 += gxv * gxv;
      H12 += gxv * gyv;
      H22 += gyv * gyv;
    }
  }

  const float det = H11 * H22 - H12 * H12;
  if (fabs(det) < 1e-3f)
    return;
  const float invH11 = H22 / det;
  const float invH12 = -H12 / det;
  const float invH22 = H11 / det;

  float u = flow_in[(cy * width + cx) * 2];
  float v = flow_in[(cy * width + cx) * 2 + 1];
  // Per-scale clamp — stops Medium/Slow runaway on large-motion Sintel Final.
  const float max_disp = 32.0f;
  const float max_step = 1.5f;
  u = clamp(u, -max_disp, max_disp);
  v = clamp(v, -max_disp, max_disp);
  float last_ssd = 1e30f;
  for (int it = 0; it < iters; ++it) {
    float b1 = 0.0f, b2 = 0.0f, ssd = 0.0f;
    for (int py = 0; py < patch_size; ++py) {
      for (int px = 0; px < patch_size; ++px) {
        const int x = cx - ph + px;
        const int y = cy - ph + py;
        const int idx = py * patch_size + px;
        const float warped = sample_bilinear(I1, width, height, (float)x + u, (float)y + v);
        const float err = warped - T[idx];
        ssd += err * err;
        b1 += Ix[idx] * err;
        b2 += Iy[idx] * err;
      }
    }
    if (it > 0 && ssd > last_ssd * 1.05f)
      break;
    last_ssd = ssd;
    float du = invH11 * b1 + invH12 * b2;
    float dv = invH12 * b1 + invH22 * b2;
    du = clamp(du, -max_step, max_step);
    dv = clamp(dv, -max_step, max_step);
    u = clamp(u - du, -max_disp, max_disp);
    v = clamp(v - dv, -max_disp, max_disp);
    if (du * du + dv * dv < 1e-8f)
      break;
  }

  const float patch_cost = sqrt(last_ssd / (float)(patch_size * patch_size));
  const int y0 = max(0, cy - ph);
  const int y1 = min(height - 1, cy + ph);
  const int x0 = max(0, cx - ph);
  const int x1 = min(width - 1, cx + ph);
  for (int y = y0; y <= y1; ++y) {
    for (int x = x0; x <= x1; ++x) {
      const float dx = (float)(x - cx);
      const float dy = (float)(y - cy);
      const float w = max(0.0f, 1.0f - sqrt(dx * dx + dy * dy) / (ph + 1e-3f));
      if (w <= 0.0f)
        continue;
      const int idx = y * width + x;
      atomic_add_float(acc_w + idx, w);
      atomic_add_float(acc_u + idx, w * u);
      atomic_add_float(acc_v + idx, w * v);
      atomic_add_float(acc_c + idx, w * patch_cost);
    }
  }
}

// Fast path: inverse-compositional LK writing sparse patch centers only (no atomics).
__kernel void estimate_centers(__global const float *I0, __global const float *I1,
                               __global const float *flow_in, __global float *patch_u,
                               __global float *patch_v, __global float *patch_c,
                               const int width, const int height, const int patch_size,
                               const int patch_stride, const int iters, const int n_gx) {
  const int gx = get_global_id(0);
  const int gy = get_global_id(1);
  const int ph = patch_size / 2;
  const int cx = ph + gx * patch_stride;
  const int cy = ph + gy * patch_stride;
  const int pidx = gy * n_gx + gx;
  if (cx >= width - ph || cy >= height - ph) {
    if (gx < n_gx) {
      patch_u[pidx] = 0.0f;
      patch_v[pidx] = 0.0f;
      patch_c[pidx] = 255.0f;
    }
    return;
  }

  float H11 = 0.0f, H12 = 0.0f, H22 = 0.0f;
  float Ix[64];
  float Iy[64];
  float T[64];
  if (patch_size != 8)
    return;

  for (int py = 0; py < 8; ++py) {
    for (int px = 0; px < 8; ++px) {
      const int x = cx - ph + px;
      const int y = cy - ph + py;
      const float gxv =
          0.5f * (I0[y * width + min(x + 1, width - 1)] - I0[y * width + max(x - 1, 0)]);
      const float gyv =
          0.5f * (I0[min(y + 1, height - 1) * width + x] - I0[max(y - 1, 0) * width + x]);
      const int idx = py * 8 + px;
      Ix[idx] = gxv;
      Iy[idx] = gyv;
      T[idx] = I0[y * width + x];
      H11 += gxv * gxv;
      H12 += gxv * gyv;
      H22 += gyv * gyv;
    }
  }

  const float det = H11 * H22 - H12 * H12;
  if (fabs(det) < 1e-3f) {
    patch_u[pidx] = 0.0f;
    patch_v[pidx] = 0.0f;
    patch_c[pidx] = 255.0f;
    return;
  }
  const float invH11 = H22 / det;
  const float invH12 = -H12 / det;
  const float invH22 = H11 / det;

  float u = flow_in[(cy * width + cx) * 2];
  float v = flow_in[(cy * width + cx) * 2 + 1];
  const float max_disp = 32.0f;
  const float max_step = 1.5f;
  u = clamp(u, -max_disp, max_disp);
  v = clamp(v, -max_disp, max_disp);
  float last_ssd = 1e30f;
  for (int it = 0; it < iters; ++it) {
    float b1 = 0.0f, b2 = 0.0f, ssd = 0.0f;
    for (int py = 0; py < 8; ++py) {
      for (int px = 0; px < 8; ++px) {
        const int x = cx - ph + px;
        const int y = cy - ph + py;
        const int idx = py * 8 + px;
        const float warped = sample_bilinear(I1, width, height, (float)x + u, (float)y + v);
        const float err = warped - T[idx];
        ssd += err * err;
        b1 += Ix[idx] * err;
        b2 += Iy[idx] * err;
      }
    }
    if (it > 0 && ssd > last_ssd * 1.05f)
      break;
    last_ssd = ssd;
    float du = invH11 * b1 + invH12 * b2;
    float dv = invH12 * b1 + invH22 * b2;
    du = clamp(du, -max_step, max_step);
    dv = clamp(dv, -max_step, max_step);
    u = clamp(u - du, -max_disp, max_disp);
    v = clamp(v - dv, -max_disp, max_disp);
    if (du * du + dv * dv < 1e-8f)
      break;
  }

  patch_u[pidx] = u;
  patch_v[pidx] = v;
  patch_c[pidx] = sqrt(last_ssd / 64.0f);
}

// Fast-path spatial propagation: re-seed each patch from self + 4-neighbors,
// keep the candidate with lowest SSD after a short LK refine.
__kernel void propagate_refine_centers(__global const float *I0, __global const float *I1,
                                       __global const float *patch_u_in,
                                       __global const float *patch_v_in,
                                       __global float *patch_u_out, __global float *patch_v_out,
                                       __global float *patch_c_out, const int width,
                                       const int height, const int patch_size,
                                       const int patch_stride, const int iters, const int n_gx,
                                       const int n_gy) {
  const int gx = get_global_id(0);
  const int gy = get_global_id(1);
  if (gx >= n_gx || gy >= n_gy)
    return;
  const int ph = patch_size / 2;
  const int cx = ph + gx * patch_stride;
  const int cy = ph + gy * patch_stride;
  const int pidx = gy * n_gx + gx;
  if (cx >= width - ph || cy >= height - ph || patch_size != 8) {
    patch_u_out[pidx] = 0.0f;
    patch_v_out[pidx] = 0.0f;
    patch_c_out[pidx] = 255.0f;
    return;
  }

  float H11 = 0.0f, H12 = 0.0f, H22 = 0.0f;
  float Ix[64];
  float Iy[64];
  float T[64];
  for (int py = 0; py < 8; ++py) {
    for (int px = 0; px < 8; ++px) {
      const int x = cx - ph + px;
      const int y = cy - ph + py;
      const float gxv =
          0.5f * (I0[y * width + min(x + 1, width - 1)] - I0[y * width + max(x - 1, 0)]);
      const float gyv =
          0.5f * (I0[min(y + 1, height - 1) * width + x] - I0[max(y - 1, 0) * width + x]);
      const int idx = py * 8 + px;
      Ix[idx] = gxv;
      Iy[idx] = gyv;
      T[idx] = I0[y * width + x];
      H11 += gxv * gxv;
      H12 += gxv * gyv;
      H22 += gyv * gyv;
    }
  }
  const float det = H11 * H22 - H12 * H12;
  if (fabs(det) < 1e-3f) {
    patch_u_out[pidx] = patch_u_in[pidx];
    patch_v_out[pidx] = patch_v_in[pidx];
    patch_c_out[pidx] = 255.0f;
    return;
  }
  const float invH11 = H22 / det;
  const float invH12 = -H12 / det;
  const float invH22 = H11 / det;

  const int nbs_dx[5] = {0, -1, 1, 0, 0};
  const int nbs_dy[5] = {0, 0, 0, -1, 1};
  float best_u = patch_u_in[pidx];
  float best_v = patch_v_in[pidx];
  float best_ssd = 1e30f;
  const float max_disp = 32.0f;
  const float max_step = 1.5f;

  for (int n = 0; n < 5; ++n) {
    const int ngx = clamp(gx + nbs_dx[n], 0, n_gx - 1);
    const int ngy = clamp(gy + nbs_dy[n], 0, n_gy - 1);
    float u = patch_u_in[ngy * n_gx + ngx];
    float v = patch_v_in[ngy * n_gx + ngx];
    u = clamp(u, -max_disp, max_disp);
    v = clamp(v, -max_disp, max_disp);
    float last_ssd = 1e30f;
    for (int it = 0; it < iters; ++it) {
      float b1 = 0.0f, b2 = 0.0f, ssd = 0.0f;
      for (int py = 0; py < 8; ++py) {
        for (int px = 0; px < 8; ++px) {
          const int x = cx - ph + px;
          const int y = cy - ph + py;
          const int idx = py * 8 + px;
          const float warped = sample_bilinear(I1, width, height, (float)x + u, (float)y + v);
          const float err = warped - T[idx];
          ssd += err * err;
          b1 += Ix[idx] * err;
          b2 += Iy[idx] * err;
        }
      }
      if (it > 0 && ssd > last_ssd * 1.05f)
        break;
      last_ssd = ssd;
      float du = invH11 * b1 + invH12 * b2;
      float dv = invH12 * b1 + invH22 * b2;
      du = clamp(du, -max_step, max_step);
      dv = clamp(dv, -max_step, max_step);
      u = clamp(u - du, -max_disp, max_disp);
      v = clamp(v - dv, -max_disp, max_disp);
      if (du * du + dv * dv < 1e-8f)
        break;
    }
    if (last_ssd < best_ssd) {
      best_ssd = last_ssd;
      best_u = u;
      best_v = v;
    }
  }

  patch_u_out[pidx] = best_u;
  patch_v_out[pidx] = best_v;
  patch_c_out[pidx] = sqrt(best_ssd / 64.0f);
}

// Bilinear densify from sparse patch grid — O(pixels), no atomics.
__kernel void densify_from_patches(__global const float *patch_u, __global const float *patch_v,
                                   __global const float *patch_c, __global float *flow,
                                   __global uchar *cost, const int width, const int height,
                                   const int patch_size, const int patch_stride, const int n_gx,
                                   const int n_gy) {
  const int x = get_global_id(0);
  const int y = get_global_id(1);
  if (x >= width || y >= height)
    return;
  const int ph = patch_size / 2;
  const float gx = ((float)x - (float)ph) / (float)patch_stride;
  const float gy = ((float)y - (float)ph) / (float)patch_stride;
  const int gx0 = (int)floor(gx);
  const int gy0 = (int)floor(gy);
  const int gx1 = gx0 + 1;
  const int gy1 = gy0 + 1;
  const float tx = gx - (float)gx0;
  const float ty = gy - (float)gy0;

  int ax0 = clamp(gx0, 0, n_gx - 1);
  int ay0 = clamp(gy0, 0, n_gy - 1);
  int ax1 = clamp(gx1, 0, n_gx - 1);
  int ay1 = clamp(gy1, 0, n_gy - 1);
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
  const int out = (y * width + x) * 2;
  flow[out] = u;
  flow[out + 1] = v;
  cost[y * width + x] = (uchar)clamp(c, 0.0f, 255.0f);
}

__kernel void normalize_flow(__global const float *acc_u, __global const float *acc_v,
                             __global const float *acc_c, __global const float *acc_w,
                             __global float *flow, __global uchar *cost, const int n) {
  const int i = get_global_id(0);
  if (i >= n)
    return;
  const float w = acc_w[i];
  if (w > 1e-6f) {
    flow[i * 2] = acc_u[i] / w;
    flow[i * 2 + 1] = acc_v[i] / w;
    cost[i] = (uchar)clamp(acc_c[i] / w, 0.0f, 255.0f);
  } else {
    flow[i * 2] = 0.0f;
    flow[i * 2 + 1] = 0.0f;
    cost[i] = (uchar)255;
  }
}

__kernel void zero_float(__global float *buf, const int n) {
  const int i = get_global_id(0);
  if (i < n)
    buf[i] = 0.0f;
}

__kernel void zero_flow(__global float *flow, const int n) {
  const int i = get_global_id(0);
  if (i < n)
    flow[i] = 0.0f;
}
)CLC";
