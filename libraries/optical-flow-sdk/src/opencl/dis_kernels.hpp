// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#pragma once

// Device-resident DIS-lite kernels (pyramid helpers + patch inverse search + densify).
inline constexpr const char *kOpenCLDisKernelSource = R"CLC(
__kernel void u8_to_float(__global const uchar *src, __global float *dst,
                          const int width, const int height, const int src_stride) {
  const int x = get_global_id(0);
  const int y = get_global_id(1);
  if (x >= width || y >= height)
    return;
  dst[y * width + x] = (float)src[y * src_stride + x];
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

// One work-item per patch on the lattice. Writes sparse patch flow + cost.
__kernel void estimate_patches(__global const float *I0, __global const float *I1,
                               __global const float *flow_in, __global float *patch_u,
                               __global float *patch_v, __global float *patch_cost,
                               __global int *patch_cx, __global int *patch_cy,
                               const int width, const int height, const int patch_size,
                               const int patch_stride, const int iters, const int n_gx) {
  const int gx = get_global_id(0);
  const int gy = get_global_id(1);
  const int ph = patch_size / 2;
  const int cx = ph + gx * patch_stride;
  const int cy = ph + gy * patch_stride;
  if (cx >= width - ph || cy >= height - ph)
    return;

  const int pidx = gy * n_gx + gx;
  float H11 = 0.0f, H12 = 0.0f, H22 = 0.0f;
  // Patch footprint is small (≤12); keep grads in private memory.
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
  patch_cx[pidx] = cx;
  patch_cy[pidx] = cy;
  if (fabs(det) < 1e-3f) {
    patch_u[pidx] = 0.0f;
    patch_v[pidx] = 0.0f;
    patch_cost[pidx] = 255.0f;
    return;
  }
  const float invH11 = H22 / det;
  const float invH12 = -H12 / det;
  const float invH22 = H11 / det;

  float u = flow_in[(cy * width + cx) * 2];
  float v = flow_in[(cy * width + cx) * 2 + 1];
  float last_ssd = 0.0f;
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
  patch_cost[pidx] = sqrt(last_ssd / (float)(patch_size * patch_size));
}

// Densify sparse patch flow onto the pixel grid (local lattice neighborhood).
__kernel void densify_flow(__global const float *patch_u, __global const float *patch_v,
                           __global const float *patch_cost, __global const int *patch_cx,
                           __global const int *patch_cy, __global float *flow,
                           __global uchar *cost, const int width, const int height,
                           const int patch_size, const int patch_stride, const int n_gx,
                           const int n_gy) {
  const int x = get_global_id(0);
  const int y = get_global_id(1);
  if (x >= width || y >= height)
    return;

  const int ph = patch_size / 2;
  float wsum = 0.0f, au = 0.0f, av = 0.0f, ac = 0.0f;

  // Patches whose centers can influence this pixel lie within |dx|,|dy| <= ph.
  const int min_cx = max(ph, x - ph);
  const int max_cx = min(width - ph - 1, x + ph);
  const int min_cy = max(ph, y - ph);
  const int max_cy = min(height - ph - 1, y + ph);

  for (int cy = ph; cy <= max_cy; cy += patch_stride) {
    if (cy < min_cy)
      continue;
    for (int cx = ph; cx <= max_cx; cx += patch_stride) {
      if (cx < min_cx)
        continue;
      const int gx = (cx - ph) / patch_stride;
      const int gy = (cy - ph) / patch_stride;
      if (gx < 0 || gy < 0 || gx >= n_gx || gy >= n_gy)
        continue;
      const int pidx = gy * n_gx + gx;
      // Guard against lattice holes / failed patches.
      if (patch_cx[pidx] != cx || patch_cy[pidx] != cy)
        continue;
      const float dx = (float)(x - cx);
      const float dy = (float)(y - cy);
      const float w = max(0.0f, 1.0f - sqrt(dx * dx + dy * dy) / (ph + 1e-3f));
      if (w <= 0.0f)
        continue;
      wsum += w;
      au += w * patch_u[pidx];
      av += w * patch_v[pidx];
      ac += w * patch_cost[pidx];
    }
  }

  const int out = (y * width + x) * 2;
  if (wsum > 1e-6f) {
    flow[out] = au / wsum;
    flow[out + 1] = av / wsum;
    cost[y * width + x] = (uchar)clamp(ac / wsum, 0.0f, 255.0f);
  } else {
    flow[out] = 0.0f;
    flow[out + 1] = 0.0f;
    cost[y * width + x] = (uchar)255;
  }
}

__kernel void zero_flow(__global float *flow, const int n) {
  const int i = get_global_id(0);
  if (i < n)
    flow[i] = 0.0f;
}
)CLC";
