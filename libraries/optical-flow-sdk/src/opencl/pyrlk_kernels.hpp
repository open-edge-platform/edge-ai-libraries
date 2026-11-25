// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#pragma once

// Sparse pyramidal LK — one work-item per tracked point at a single pyramid level.
inline constexpr const char *kOpenCLPyrLKKernelSource = R"CLC(
__kernel void lk_u8_to_float(__global const uchar *src, __global float *dst,
                             const int width, const int height, const int src_stride) {
  const int x = get_global_id(0);
  const int y = get_global_id(1);
  if (x >= width || y >= height)
    return;
  dst[y * width + x] = (float)src[y * src_stride + x];
}

__kernel void lk_downsample2(__global const float *src, __global float *dst,
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

inline float lk_sample(__global const float *img, const int w, const int h, float x, float y) {
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

// pts_xy: [N*2] current point positions at this level
// flow_uv: [N*2] cumulative flow at this level (updated in place)
// status: 1=ok, 0=lost
__kernel void lk_track_level(__global const float *I0, __global const float *I1,
                             __global float *pts_xy, __global float *flow_uv,
                             __global uchar *status, __global float *err, const int n_pts,
                             const int width, const int height, const int win_half,
                             const int max_iters, const float eps, const float min_eig) {
  const int i = get_global_id(0);
  if (i >= n_pts)
    return;
  if (status[i] == 0)
    return;

  float x = pts_xy[i * 2];
  float y = pts_xy[i * 2 + 1];
  float u = flow_uv[i * 2];
  float v = flow_uv[i * 2 + 1];

  if (x < (float)win_half || y < (float)win_half || x >= (float)(width - win_half) ||
      y >= (float)(height - win_half)) {
    status[i] = 0;
    err[i] = 1.0e6f;
    return;
  }

  float Gxx = 0.0f, Gxy = 0.0f, Gyy = 0.0f;
  for (int wy = -win_half; wy <= win_half; ++wy) {
    for (int wx = -win_half; wx <= win_half; ++wx) {
      const float Ix =
          0.5f * (lk_sample(I0, width, height, x + wx + 1, y + wy) -
                  lk_sample(I0, width, height, x + wx - 1, y + wy));
      const float Iy =
          0.5f * (lk_sample(I0, width, height, x + wx, y + wy + 1) -
                  lk_sample(I0, width, height, x + wx, y + wy - 1));
      Gxx += Ix * Ix;
      Gxy += Ix * Iy;
      Gyy += Iy * Iy;
    }
  }
  const float det = Gxx * Gyy - Gxy * Gxy;
  const float eig_min =
      0.5f * ((Gxx + Gyy) - sqrt((Gxx - Gyy) * (Gxx - Gyy) + 4.0f * Gxy * Gxy));
  if (fabs(det) < 1.0e-8f || eig_min < min_eig) {
    status[i] = 0;
    err[i] = 1.0e6f;
    return;
  }

  float last_err = 0.0f;
  for (int it = 0; it < max_iters; ++it) {
    float bx = 0.0f, by = 0.0f, ssd = 0.0f;
    for (int wy = -win_half; wy <= win_half; ++wy) {
      for (int wx = -win_half; wx <= win_half; ++wx) {
        const float Ix =
            0.5f * (lk_sample(I0, width, height, x + wx + 1, y + wy) -
                    lk_sample(I0, width, height, x + wx - 1, y + wy));
        const float Iy =
            0.5f * (lk_sample(I0, width, height, x + wx, y + wy + 1) -
                    lk_sample(I0, width, height, x + wx, y + wy - 1));
        const float i0 = lk_sample(I0, width, height, x + wx, y + wy);
        const float i1 = lk_sample(I1, width, height, x + u + wx, y + v + wy);
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
    last_err = sqrt(ssd / (float)((2 * win_half + 1) * (2 * win_half + 1)));
    if (du * du + dv * dv < eps * eps)
      break;
  }
  flow_uv[i * 2] = u;
  flow_uv[i * 2 + 1] = v;
  err[i] = last_err;
}

__kernel void lk_scale_pts(__global float *pts_xy, __global float *flow_uv, const int n_pts,
                           const float scale) {
  const int i = get_global_id(0);
  if (i >= n_pts)
    return;
  pts_xy[i * 2] *= scale;
  pts_xy[i * 2 + 1] *= scale;
  flow_uv[i * 2] *= scale;
  flow_uv[i * 2 + 1] *= scale;
}
)CLC";
