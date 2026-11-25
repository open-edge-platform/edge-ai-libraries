// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#pragma once

// OpenCL Farneback: WLS quadratic coeffs in OpenCV channel order + UpdateMatrices/Flow.
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

__kernel void fb_zero_flow(__global float *flow, const int n) {
  const int i = get_global_id(0);
  if (i < n)
    flow[i] = 0.0f;
}

// WLS quadratic → OpenCV Farneback channels [cy, cx, cyy, cxx, cxy].
__kernel void fb_poly_expand(__global const float *I, __global float *R, const int width,
                             const int height, const int poly_n, const float poly_sigma) {
  const int x = get_global_id(0);
  const int y = get_global_id(1);
  if (x >= width || y >= height)
    return;
  const int rad = poly_n / 2;
  const float var = max(poly_sigma * poly_sigma, 1e-6f);
  float ATA[6][6];
  float ATb[6];
  for (int i = 0; i < 6; ++i) {
    ATb[i] = 0.0f;
    for (int j = 0; j < 6; ++j)
      ATA[i][j] = 0.0f;
  }
  for (int dy = -rad; dy <= rad; ++dy) {
    for (int dx = -rad; dx <= rad; ++dx) {
      const int xx = clamp(x + dx, 0, width - 1);
      const int yy = clamp(y + dy, 0, height - 1);
      const float w = exp(-0.5f * (float)(dx * dx + dy * dy) / var);
      const float X = (float)dx;
      const float Y = (float)dy;
      const float bv[6] = {1.0f, X, Y, X * X, Y * Y, X * Y};
      const float z = I[yy * width + xx];
      for (int i = 0; i < 6; ++i) {
        ATb[i] += w * bv[i] * z;
        for (int j = i; j < 6; ++j)
          ATA[i][j] += w * bv[i] * bv[j];
      }
    }
  }
  for (int i = 0; i < 6; ++i)
    for (int j = 0; j < i; ++j)
      ATA[i][j] = ATA[j][i];

  float M[6][7];
  for (int i = 0; i < 6; ++i) {
    for (int j = 0; j < 6; ++j)
      M[i][j] = ATA[i][j];
    M[i][6] = ATb[i];
  }
  for (int col = 0; col < 6; ++col) {
    int piv = col;
    for (int r = col + 1; r < 6; ++r)
      if (fabs(M[r][col]) > fabs(M[piv][col]))
        piv = r;
    if (fabs(M[piv][col]) < 1e-12f)
      continue;
    if (piv != col) {
      for (int c = col; c < 7; ++c) {
        const float tmp = M[piv][c];
        M[piv][c] = M[col][c];
        M[col][c] = tmp;
      }
    }
    const float inv = 1.0f / M[col][col];
    for (int c = col; c < 7; ++c)
      M[col][c] *= inv;
    for (int r = 0; r < 6; ++r) {
      if (r == col)
        continue;
      const float f = M[r][col];
      for (int c = col; c < 7; ++c)
        M[r][c] -= f * M[col][c];
    }
  }
  // c = [c0,c1,c2,c3,c4,c5]; OpenCV R = [c2,c1,c4,c3,c5]
  const int o = (y * width + x) * 5;
  R[o + 0] = M[2][6];
  R[o + 1] = M[1][6];
  R[o + 2] = M[4][6];
  R[o + 3] = M[3][6];
  R[o + 4] = M[5][6];
}

void fb_sample_poly(__global const float *R, const int w, const int h, float x, float y,
                    float *c /*5*/) {
  x = clamp(x, 0.0f, (float)(w - 1));
  y = clamp(y, 0.0f, (float)(h - 1));
  const int x0 = (int)x;
  const int y0 = (int)y;
  const int x1 = min(x0 + 1, w - 1);
  const int y1 = min(y0 + 1, h - 1);
  const float dx = x - (float)x0;
  const float dy = y - (float)y0;
  for (int k = 0; k < 5; ++k) {
    const float v00 = R[(y0 * w + x0) * 5 + k];
    const float v10 = R[(y0 * w + x1) * 5 + k];
    const float v01 = R[(y1 * w + x0) * 5 + k];
    const float v11 = R[(y1 * w + x1) * 5 + k];
    c[k] = (1.0f - dx) * (1.0f - dy) * v00 + dx * (1.0f - dy) * v10 + (1.0f - dx) * dy * v01 +
           dx * dy * v11;
  }
}

// Build OpenCV-style M = A^T A / A^T b (absolute flow form with A*f folded in).
__kernel void fb_update_matrices(__global const float *R0, __global const float *R1,
                                 __global const float *flow, __global float *M, const int width,
                                 const int height) {
  const int x = get_global_id(0);
  const int y = get_global_id(1);
  if (x >= width || y >= height)
    return;
  const float dx = flow[(y * width + x) * 2];
  const float dy = flow[(y * width + x) * 2 + 1];
  float r1[5];
  fb_sample_poly(R1, width, height, (float)x + dx, (float)y + dy, r1);
  const int i0 = (y * width + x) * 5;
  float r2 = (R0[i0 + 0] - r1[0]) * 0.5f;
  float r3 = (R0[i0 + 1] - r1[1]) * 0.5f;
  float r4 = (R0[i0 + 2] + r1[2]) * 0.5f;
  float r5 = (R0[i0 + 3] + r1[3]) * 0.5f;
  float r6 = (R0[i0 + 4] + r1[4]) * 0.25f;
  r2 += r4 * dy + r6 * dx;
  r3 += r6 * dy + r5 * dx;
  M[i0 + 0] = r4 * r4 + r6 * r6;
  M[i0 + 1] = (r4 + r5) * r6;
  M[i0 + 2] = r5 * r5 + r6 * r6;
  M[i0 + 3] = r4 * r2 + r6 * r3;
  M[i0 + 4] = r6 * r2 + r5 * r3;
}

__kernel void fb_farneback_update(__global const float *M, __global float *flow_out,
                                  __global uchar *cost, __global const float *flow_in,
                                  const int width, const int height, const int win_half) {
  const int x = get_global_id(0);
  const int y = get_global_id(1);
  if (x >= width || y >= height)
    return;
  const int winsize = 2 * win_half + 1;
  const float scale = 1.0f / (float)(winsize * winsize);
  float g11 = 0.0f, g12 = 0.0f, g22 = 0.0f, h1 = 0.0f, h2 = 0.0f;
  for (int wy = -win_half; wy <= win_half; ++wy) {
    const int yy = clamp(y + wy, 0, height - 1);
    for (int wx = -win_half; wx <= win_half; ++wx) {
      const int xx = clamp(x + wx, 0, width - 1);
      const int j = (yy * width + xx) * 5;
      g11 += M[j + 0];
      g12 += M[j + 1];
      g22 += M[j + 2];
      h1 += M[j + 3];
      h2 += M[j + 4];
    }
  }
  g11 *= scale;
  g12 *= scale;
  g22 *= scale;
  h1 *= scale;
  h2 *= scale;
  const float idet = 1.0f / (g11 * g22 - g12 * g12 + 1e-3f);
  const float fx = (g11 * h2 - g12 * h1) * idet;
  const float fy = (g22 * h1 - g12 * h2) * idet;
  const int o = (y * width + x) * 2;
  const float ou = flow_in[o];
  const float ov = flow_in[o + 1];
  flow_out[o] = fx;
  flow_out[o + 1] = fy;
  const float du = fx - ou;
  const float dv = fy - ov;
  cost[y * width + x] = (uchar)clamp(sqrt(du * du + dv * dv) * 16.0f, 0.0f, 255.0f);
}
)CLC";
