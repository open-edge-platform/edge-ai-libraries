// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#pragma once

// OpenCL Farneback with polynomial neighborhood gradients (poly_n), matching
// the CPU Farneback-class path in src/cpu/farneback.cpp.
inline constexpr const char *kOpenCLFarnebackKernelSource = R"CLC(
__kernel void fb_u8_to_float(__global const uchar *src, __global float *dst,
                             const int width, const int height, const int src_stride) {
  const int x = get_global_id(0);
  const int y = get_global_id(1);
  if (x >= width || y >= height)
    return;
  dst[y * width + x] = (float)src[y * src_stride + x];
}

__kernel void fb_downsample2(__global const float *src, __global float *dst,
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

__kernel void fb_upsample_flow(__global const float *coarse, __global float *fine,
                               const int cw, const int ch, const int fw, const int fh) {
  const int x = get_global_id(0);
  const int y = get_global_id(1);
  if (x >= fw || y >= fh)
    return;
  const float sx = (float)cw / (float)fw;
  const float sy = (float)ch / (float)fh;
  float cx = ((float)x + 0.5f) * sx - 0.5f;
  float cy = ((float)y + 0.5f) * sy - 0.5f;
  cx = clamp(cx, 0.0f, (float)(cw - 1));
  cy = clamp(cy, 0.0f, (float)(ch - 1));
  const int x0 = (int)cx;
  const int y0 = (int)cy;
  const int x1 = min(x0 + 1, cw - 1);
  const int y1 = min(y0 + 1, ch - 1);
  const float dx = cx - (float)x0;
  const float dy = cy - (float)y0;
  const float u = (1.0f - dx) * (1.0f - dy) * coarse[(y0 * cw + x0) * 2] +
                  dx * (1.0f - dy) * coarse[(y0 * cw + x1) * 2] +
                  (1.0f - dx) * dy * coarse[(y1 * cw + x0) * 2] +
                  dx * dy * coarse[(y1 * cw + x1) * 2];
  const float v = (1.0f - dx) * (1.0f - dy) * coarse[(y0 * cw + x0) * 2 + 1] +
                  dx * (1.0f - dy) * coarse[(y0 * cw + x1) * 2 + 1] +
                  (1.0f - dx) * dy * coarse[(y1 * cw + x0) * 2 + 1] +
                  dx * dy * coarse[(y1 * cw + x1) * 2 + 1];
  fine[(y * fw + x) * 2] = u * 2.0f;
  fine[(y * fw + x) * 2 + 1] = v * 2.0f;
}

inline float fb_sample(__global const float *img, const int w, const int h, float x, float y) {
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

__kernel void fb_zero_flow(__global float *flow, const int n) {
  const int i = get_global_id(0);
  if (i < n)
    flow[i] = 0.0f;
}

// Polynomial-neighborhood gradients + windowed LK (matches CPU farneback_level).
// poly_sigma is Gaussian σ for the poly_n neighborhood (OpenCV dial).
__kernel void fb_poly_lk(__global const float *I0, __global const float *I1,
                         __global const float *flow_in, __global float *flow_out,
                         __global uchar *cost, const int width, const int height,
                         const int win_half, const int poly_n, const float poly_sigma,
                         const int max_step_x100) {
  const int x = get_global_id(0);
  const int y = get_global_id(1);
  if (x >= width || y >= height)
    return;
  const int out = (y * width + x) * 2;
  if (x < win_half || y < win_half || x >= width - win_half || y >= height - win_half) {
    flow_out[out] = flow_in[out];
    flow_out[out + 1] = flow_in[out + 1];
    cost[y * width + x] = (uchar)255;
    return;
  }
  const int poly_half = poly_n / 2;
  const float poly_var = max(poly_sigma * poly_sigma, 1e-6f);
  const float u0 = flow_in[out];
  const float v0 = flow_in[out + 1];
  float Gxx = 0.0f, Gxy = 0.0f, Gyy = 0.0f, bx = 0.0f, by = 0.0f, ssd = 0.0f;
  for (int wy = -win_half; wy <= win_half; ++wy) {
    for (int wx = -win_half; wx <= win_half; ++wx) {
      float Ix = 0.0f, Iy = 0.0f, wsum = 0.0f;
      for (int py = -poly_half; py <= poly_half; ++py) {
        for (int px = -poly_half; px <= poly_half; ++px) {
          const int xx = clamp(x + wx + px, 0, width - 1);
          const int yy = clamp(y + wy + py, 0, height - 1);
          const float w = exp(-0.5f * (float)(px * px + py * py) / poly_var);
          Ix += w * (float)px * I0[yy * width + xx];
          Iy += w * (float)py * I0[yy * width + xx];
          wsum += w;
        }
      }
      Ix /= (wsum + 1e-6f);
      Iy /= (wsum + 1e-6f);
      const int x1 = clamp(x + wx, 0, width - 1);
      const int y1 = clamp(y + wy, 0, height - 1);
      const float i0 = I0[y1 * width + x1];
      const float i1 = fb_sample(I1, width, height, (float)x1 + u0, (float)y1 + v0);
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
  float u = u0;
  float v = v0;
  if (fabs(det) >= 1e-4f) {
    float du = -(Gyy * bx - Gxy * by) / det;
    float dv = -(-Gxy * bx + Gxx * by) / det;
    const float max_step = (float)max_step_x100 * 0.01f;
    du = clamp(du, -max_step, max_step);
    dv = clamp(dv, -max_step, max_step);
    u = u0 + du;
    v = v0 + dv;
  }
  flow_out[out] = u;
  flow_out[out + 1] = v;
  const float norm = (float)((2 * win_half + 1) * (2 * win_half + 1));
  cost[y * width + x] = (uchar)clamp(sqrt(ssd / norm), 0.0f, 255.0f);
}
)CLC";
