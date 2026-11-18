// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-FileCopyrightText: Copyright (c) 2017 Mårten Björkman
// SPDX-License-Identifier: Apache-2.0 AND MIT
//********************************************************//
// Intel SYCL/DPC++ SIFT extractor                       //
// Device kernel implementations                         //
// SYCL reference backend (mechanics baseline).
//********************************************************//

#include "syclSiftD.h"
#include "syclutils.h"
#include "syclSift.h"
#include <sycl/sycl.hpp>
#include <cmath>

// ============================================================
// ScaleDown: 5-tap Gaussian downsample by factor 2
// SYCL: 1D work-group of (SCALEDOWN_W+4) items
// ============================================================
void LaunchScaleDown(sycl::queue &q, float *d_Result, float *d_Data,
                     int width, int pitch, int height, int newpitch,
                     const float *d_kernel) {
  const int BW = SCALEDOWN_W + 4;
  const int dx2 = SCALEDOWN_W / 2;
  int blocksX = iDivUp(width, SCALEDOWN_W);
  int blocksY = iDivUp(height, SCALEDOWN_H);

  q.submit([&](sycl::handler &cgh) {
    sycl::local_accessor<float, 1> inrow(BW, cgh);
    sycl::local_accessor<float, 1> brow(5 * dx2, cgh);
    sycl::local_accessor<int, 1> yRead(SCALEDOWN_H + 4, cgh);
    sycl::local_accessor<int, 1> yWrite(SCALEDOWN_H + 4, cgh);

    cgh.parallel_for(
        sycl::nd_range<2>(sycl::range<2>(blocksY * 1, blocksX * BW),
                          sycl::range<2>(1, BW)),
        [=](sycl::nd_item<2> item) {
          const int tx = item.get_local_id(1);
          const int xStart = item.get_group(1) * SCALEDOWN_W;
          const int yStart = item.get_group(0) * SCALEDOWN_H;
          const int xWrite = xStart / 2 + tx;

          float k0 = d_kernel[0];
          float k1 = d_kernel[1];
          float k2 = d_kernel[2];

          if (tx < SCALEDOWN_H + 4) {
            int y = yStart + tx - 2;
            y = (y < 0 ? 0 : y);
            y = (y >= height ? height - 1 : y);
            yRead[tx] = y * pitch;
            yWrite[tx] = (yStart + tx - 4) / 2 * newpitch;
          }
          item.barrier(sycl::access::fence_space::local_space);

          int xRead = xStart + tx - 2;
          xRead = (xRead < 0 ? 0 : xRead);
          xRead = (xRead >= width ? width - 1 : xRead);

              int maxtx = sycl::min(dx2, width / 2 - xStart / 2);
          const int out_h = height / 2;

          for (int dy = 0; dy < SCALEDOWN_H + 4; dy += 5) {
            {
              inrow[tx] = d_Data[yRead[dy + 0] + xRead];
              item.barrier(sycl::access::fence_space::local_space);
              if (tx < maxtx) {
                brow[tx + 4 * dx2] =
                    k0 * (inrow[2 * tx] + inrow[2 * tx + 4]) +
                    k1 * (inrow[2 * tx + 1] + inrow[2 * tx + 3]) +
                    k2 * inrow[2 * tx + 2];
                {
                  const int y_out = (yStart + dy + 0 - 4) / 2;
                  if (dy >= 4 && !(dy & 1) && xWrite < width / 2 &&
                      y_out >= 0 && y_out < out_h)
                    d_Result[yWrite[dy + 0] + xWrite] =
                        k2 * brow[tx + 2 * dx2] +
                        k0 * (brow[tx + 0 * dx2] + brow[tx + 4 * dx2]) +
                        k1 * (brow[tx + 1 * dx2] + brow[tx + 3 * dx2]);
                }
              }
              item.barrier(sycl::access::fence_space::local_space);
            }
            if (dy < (SCALEDOWN_H + 3)) {
              inrow[tx] = d_Data[yRead[dy + 1] + xRead];
              item.barrier(sycl::access::fence_space::local_space);
              if (tx < maxtx) {
                brow[tx + 0 * dx2] =
                    k0 * (inrow[2 * tx] + inrow[2 * tx + 4]) +
                    k1 * (inrow[2 * tx + 1] + inrow[2 * tx + 3]) +
                    k2 * inrow[2 * tx + 2];
                {
                  const int y_out = (yStart + dy + 1 - 4) / 2;
                  if (dy >= 3 && (dy & 1) && xWrite < width / 2 &&
                      y_out >= 0 && y_out < out_h)
                    d_Result[yWrite[dy + 1] + xWrite] =
                        k2 * brow[tx + 3 * dx2] +
                        k0 * (brow[tx + 1 * dx2] + brow[tx + 0 * dx2]) +
                        k1 * (brow[tx + 2 * dx2] + brow[tx + 4 * dx2]);
                }
              }
              item.barrier(sycl::access::fence_space::local_space);
            }
            if (dy < (SCALEDOWN_H + 2)) {
              inrow[tx] = d_Data[yRead[dy + 2] + xRead];
              item.barrier(sycl::access::fence_space::local_space);
              if (tx < maxtx) {
                brow[tx + 1 * dx2] =
                    k0 * (inrow[2 * tx] + inrow[2 * tx + 4]) +
                    k1 * (inrow[2 * tx + 1] + inrow[2 * tx + 3]) +
                    k2 * inrow[2 * tx + 2];
                {
                  const int y_out = (yStart + dy + 2 - 4) / 2;
                  if (dy >= 2 && !(dy & 1) && xWrite < width / 2 &&
                      y_out >= 0 && y_out < out_h)
                    d_Result[yWrite[dy + 2] + xWrite] =
                        k2 * brow[tx + 4 * dx2] +
                        k0 * (brow[tx + 2 * dx2] + brow[tx + 1 * dx2]) +
                        k1 * (brow[tx + 3 * dx2] + brow[tx + 0 * dx2]);
                }
              }
              item.barrier(sycl::access::fence_space::local_space);
            }
            if (dy < (SCALEDOWN_H + 1)) {
              inrow[tx] = d_Data[yRead[dy + 3] + xRead];
              item.barrier(sycl::access::fence_space::local_space);
              if (tx < maxtx) {
                brow[tx + 2 * dx2] =
                    k0 * (inrow[2 * tx] + inrow[2 * tx + 4]) +
                    k1 * (inrow[2 * tx + 1] + inrow[2 * tx + 3]) +
                    k2 * inrow[2 * tx + 2];
                {
                  const int y_out = (yStart + dy + 3 - 4) / 2;
                  if (dy >= 1 && (dy & 1) && xWrite < width / 2 &&
                      y_out >= 0 && y_out < out_h)
                    d_Result[yWrite[dy + 3] + xWrite] =
                        k2 * brow[tx + 0 * dx2] +
                        k0 * (brow[tx + 3 * dx2] + brow[tx + 2 * dx2]) +
                        k1 * (brow[tx + 4 * dx2] + brow[tx + 1 * dx2]);
                }
              }
              item.barrier(sycl::access::fence_space::local_space);
            }
            if (dy < SCALEDOWN_H) {
              inrow[tx] = d_Data[yRead[dy + 4] + xRead];
              item.barrier(sycl::access::fence_space::local_space);
              if (tx < dx2 && xWrite < width / 2) {
                brow[tx + 3 * dx2] =
                    k0 * (inrow[2 * tx] + inrow[2 * tx + 4]) +
                    k1 * (inrow[2 * tx + 1] + inrow[2 * tx + 3]) +
                    k2 * inrow[2 * tx + 2];
                {
                  const int y_out = (yStart + dy + 4 - 4) / 2;
                  if (!(dy & 1) && y_out >= 0 && y_out < out_h)
                    d_Result[yWrite[dy + 4] + xWrite] =
                        k2 * brow[tx + 1 * dx2] +
                        k0 * (brow[tx + 4 * dx2] + brow[tx + 3 * dx2]) +
                        k1 * (brow[tx + 0 * dx2] + brow[tx + 2 * dx2]);
                }
              }
              item.barrier(sycl::access::fence_space::local_space);
            }
          }
        });
  });
}

// ============================================================
// ScaleUp: bilinear 2x upsample
// ============================================================
void LaunchScaleUp(sycl::queue &q, float *d_Result, float *d_Data, int width,
                   int pitch, int height, int newpitch) {
  int blocksX = iDivUp(2 * width, SCALEUP_W);
  int blocksY = iDivUp(2 * height, SCALEUP_H);
  q.submit([&](sycl::handler &cgh) {
    cgh.parallel_for(
        sycl::nd_range<2>(
            sycl::range<2>(blocksY * (SCALEUP_H / 2), blocksX * (SCALEUP_W / 2)),
            sycl::range<2>(SCALEUP_H / 2, SCALEUP_W / 2)),
        [=](sycl::nd_item<2> item) {
          int tx = (int)item.get_local_id(1);
          int ty = (int)item.get_local_id(0);
          int x = (int)item.get_group(1) * SCALEUP_W + 2 * tx;
          int y = (int)item.get_group(0) * SCALEUP_H + 2 * ty;
          if (x < 2 * width && y < 2 * height) {
            int xl = (int)item.get_group(1) * (SCALEUP_W / 2) + tx;
            int yu = (int)item.get_group(0) * (SCALEUP_H / 2) + ty;
            int xr = sycl::min(xl + 1, width - 1);
            int yd = sycl::min(yu + 1, height - 1);
            float vul = d_Data[yu * pitch + xl];
            float vur = d_Data[yu * pitch + xr];
            float vdl = d_Data[yd * pitch + xl];
            float vdr = d_Data[yd * pitch + xr];
            d_Result[(y + 0) * newpitch + x + 0] = vul;
            d_Result[(y + 0) * newpitch + x + 1] = 0.5f * (vul + vur);
            d_Result[(y + 1) * newpitch + x + 0] = 0.5f * (vul + vdl);
            d_Result[(y + 1) * newpitch + x + 1] =
                0.25f * (vul + vur + vdl + vdr);
          }
        });
  });
}

// ============================================================
// LowPassBlock: separable Gaussian low-pass filter
// SYCL: 2D work-group
// ============================================================
void LaunchLowPassBlock(sycl::queue &q, float *d_Image, float *d_Result,
                        int width, int pitch, int height,
                        const float *d_kernel) {
  const int TW = LOWPASS_W + 2 * LOWPASS_R; // 32
  const int TH = 4;
  const int N = 16;
  int blocksX = iDivUp(width, LOWPASS_W);
  int blocksY = iDivUp(height, LOWPASS_H);

  q.submit([&](sycl::handler &cgh) {
    // xrows[16][TW] = xrows[16][32]
    sycl::local_accessor<float, 1> xrows(N * TW, cgh);

    cgh.parallel_for(
        sycl::nd_range<2>(sycl::range<2>(blocksY * TH, blocksX * TW),
                          sycl::range<2>(TH, TW)),
        [=](sycl::nd_item<2> item) {
          int tx = (int)item.get_local_id(1);
          int ty = (int)item.get_local_id(0);
          int xp = (int)item.get_group(1) * LOWPASS_W + tx;
          int yp = (int)item.get_group(0) * LOWPASS_H + ty;
          int xl = sycl::max(sycl::min(xp, width - 1), 0);

          // Load columns [-8, -4) relative to yp+LOWPASS_H into shared xrows
          for (int l = -8; l < 4; l += 4) {
            int ly = l + ty;
            int yl = sycl::max(sycl::min(yp + l + 4, height - 1), 0);
            float val = d_Image[yl * pitch + xl];
            // Apply horizontal filter (row-direction = x) using the x-position
            // of this thread. The kernel is applied in the x-dimension here.
            float filtered =
                d_kernel[4] * val +
                d_kernel[3] *
                    (d_Image[yl * pitch +
                             sycl::max(sycl::min(xl - 1, width - 1), 0)] +
                     d_Image[yl * pitch +
                             sycl::max(sycl::min(xl + 1, width - 1), 0)]) +
                d_kernel[2] *
                    (d_Image[yl * pitch +
                             sycl::max(sycl::min(xl - 2, width - 1), 0)] +
                     d_Image[yl * pitch +
                             sycl::max(sycl::min(xl + 2, width - 1), 0)]) +
                d_kernel[1] *
                    (d_Image[yl * pitch +
                             sycl::max(sycl::min(xl - 3, width - 1), 0)] +
                     d_Image[yl * pitch +
                             sycl::max(sycl::min(xl + 3, width - 1), 0)]) +
                d_kernel[0] *
                    (d_Image[yl * pitch +
                             sycl::max(sycl::min(xl - 4, width - 1), 0)] +
                     d_Image[yl * pitch +
                             sycl::max(sycl::min(xl + 4, width - 1), 0)]);
            xrows[(ly + 8) * TW + tx] = filtered;
          }
          item.barrier(sycl::access::fence_space::local_space);

          for (int l = 4; l < LOWPASS_H; l += 4) {
            int ly = l + ty;
            int yl = sycl::min(yp + l + 4, height - 1);
            float val = d_Image[yl * pitch + xl];
            float filtered =
                d_kernel[4] * val +
                d_kernel[3] *
                    (d_Image[yl * pitch +
                             sycl::max(sycl::min(xl - 1, width - 1), 0)] +
                     d_Image[yl * pitch +
                             sycl::max(sycl::min(xl + 1, width - 1), 0)]) +
                d_kernel[2] *
                    (d_Image[yl * pitch +
                             sycl::max(sycl::min(xl - 2, width - 1), 0)] +
                     d_Image[yl * pitch +
                             sycl::max(sycl::min(xl + 2, width - 1), 0)]) +
                d_kernel[1] *
                    (d_Image[yl * pitch +
                             sycl::max(sycl::min(xl - 3, width - 1), 0)] +
                     d_Image[yl * pitch +
                             sycl::max(sycl::min(xl + 3, width - 1), 0)]) +
                d_kernel[0] *
                    (d_Image[yl * pitch +
                             sycl::max(sycl::min(xl - 4, width - 1), 0)] +
                     d_Image[yl * pitch +
                             sycl::max(sycl::min(xl + 4, width - 1), 0)]);
            xrows[((ly + 8) % N) * TW + tx] = filtered;

            int ys = yp + l - 4;
            if (xp < width && ys < height && tx < LOWPASS_W) {
              d_Result[ys * pitch + xp] =
                  d_kernel[4] * xrows[((ly + 0) % N) * TW + tx] +
                  d_kernel[3] * (xrows[((ly - 1 + N) % N) * TW + tx] +
                                 xrows[((ly + 1) % N) * TW + tx]) +
                  d_kernel[2] * (xrows[((ly - 2 + N) % N) * TW + tx] +
                                 xrows[((ly + 2) % N) * TW + tx]) +
                  d_kernel[1] * (xrows[((ly - 3 + N) % N) * TW + tx] +
                                 xrows[((ly + 3) % N) * TW + tx]) +
                  d_kernel[0] * (xrows[((ly - 4 + N) % N) * TW + tx] +
                                 xrows[((ly + 4) % N) * TW + tx]);
            }
            item.barrier(sycl::access::fence_space::local_space);
          }
          // Final rows
          int ly = LOWPASS_H + ty;
          int ys = yp + LOWPASS_H - 4;
          if (xp < width && ys < height && tx < LOWPASS_W) {
            d_Result[ys * pitch + xp] =
                d_kernel[4] * xrows[((ly + 0) % N) * TW + tx] +
                d_kernel[3] * (xrows[((ly - 1 + N) % N) * TW + tx] +
                               xrows[((ly + 1) % N) * TW + tx]) +
                d_kernel[2] * (xrows[((ly - 2 + N) % N) * TW + tx] +
                               xrows[((ly + 2) % N) * TW + tx]) +
                d_kernel[1] * (xrows[((ly - 3 + N) % N) * TW + tx] +
                               xrows[((ly + 3) % N) * TW + tx]) +
                d_kernel[0] * (xrows[((ly - 4 + N) % N) * TW + tx] +
                               xrows[((ly + 4) % N) * TW + tx]);
          }
        });
  });
}

// ============================================================
// LaplaceMultiMem: build DoG pyramid (multi-scale Laplacian)
// ============================================================
void LaunchLaplaceMultiMem(sycl::queue &q, float *d_Image, float *d_Result,
                           int width, int pitch, int height, int octave,
                           const float *d_LaplaceKernel) {
  const int THREADS = LAPLACE_W + 2 * LAPLACE_R;  // 136
  int blocksX = iDivUp(width, LAPLACE_W);
  int blocksY = height;

  q.submit([&](sycl::handler &cgh) {
    // buff[(LAPLACE_W + 2*LAPLACE_R)*LAPLACE_S]
    sycl::local_accessor<float, 1> buff(THREADS * LAPLACE_S, cgh);

    cgh.parallel_for(
        sycl::nd_range<2>(sycl::range<2>(blocksY, blocksX * THREADS),
                          sycl::range<2>(1, THREADS)),
        [=](sycl::nd_item<2> item) {
          int tx = (int)item.get_local_id(1);
          int xp = (int)item.get_group(1) * LAPLACE_W + tx;
          int yp = (int)item.get_group(0);

          const float *data =
              d_Image +
              sycl::max(sycl::min(xp - LAPLACE_R, width - 1), 0);
          float temp[2 * LAPLACE_R + 1];
          float kern[LAPLACE_S][LAPLACE_R + 1];

          if (xp < (width + 2 * LAPLACE_R)) {
            for (int i = 0; i <= 2 * LAPLACE_R; i++)
              temp[i] =
                  data[sycl::max(0, sycl::min(yp + i - LAPLACE_R,
                                              height - 1)) *
                       pitch];

            for (int scale = 0; scale < LAPLACE_S; scale++) {
              float *buf = buff.get_pointer() + THREADS * scale;
              const float *kernel =
                  d_LaplaceKernel + octave * 12 * 16 + scale * 16;
              for (int i = 0; i <= LAPLACE_R; i++)
                kern[scale][i] = kernel[i];
              float sum = kern[scale][0] * temp[LAPLACE_R];
              for (int j = 1; j <= LAPLACE_R; j++)
                sum += kern[scale][j] *
                       (temp[LAPLACE_R - j] + temp[LAPLACE_R + j]);
              buf[tx] = sum;
            }
          }
          item.barrier(sycl::access::fence_space::local_space);

          if (tx < LAPLACE_W && xp < width) {
            int scale = 0;
            float *buf0 = buff.get_pointer() + THREADS * scale;
            float oldRes = kern[scale][0] * buf0[tx + LAPLACE_R];
            for (int j = 1; j <= LAPLACE_R; j++)
              oldRes += kern[scale][j] *
                        (buf0[tx + LAPLACE_R - j] + buf0[tx + LAPLACE_R + j]);

            for (int scale = 1; scale < LAPLACE_S; scale++) {
              float *buf = buff.get_pointer() + THREADS * scale;
              float res = kern[scale][0] * buf[tx + LAPLACE_R];
              for (int j = 1; j <= LAPLACE_R; j++)
                res += kern[scale][j] *
                       (buf[tx + LAPLACE_R - j] + buf[tx + LAPLACE_R + j]);
              d_Result[(scale - 1) * height * pitch + yp * pitch + xp] =
                  res - oldRes;
              oldRes = res;
            }
          }
        });
  });
}

// ============================================================
// FindPointsMultiNew: find local DoG extrema and fit subpixel
//       dim3 threads(MINMAX_W + 2)
// ============================================================
void LaunchFindPointsMultiNew(sycl::queue &q, float *d_Data0,
                               SiftPoint *d_Sift, int width, int pitch,
                               int height, float subsampling,
                               float lowestScale, float thresh, float factor,
                               float edgeLimit, int octave,
                               unsigned int *d_PointCounter,
                               int d_MaxNumPoints) {
  const int MEMWID = MINMAX_W + 2;
  int blocksX = iDivUp(width, MINMAX_W) * NUM_SCALES;
  int blocksY = iDivUp(height, MINMAX_H);

  q.submit([&](sycl::handler &cgh) {
    sycl::local_accessor<unsigned short, 1> points(2 * MEMWID, cgh);
    sycl::local_accessor<float, 1> reductionScratch(MEMWID, cgh);
    sycl::local_accessor<unsigned int, 1> scanScratch(MEMWID, cgh);

    cgh.parallel_for(
        sycl::nd_range<2>(sycl::range<2>(blocksY, blocksX * MEMWID),
                          sycl::range<2>(1, MEMWID)),
        [=](sycl::nd_item<2> item) {
          int tx = (int)item.get_local_id(1);
          int bx = (int)item.get_group(1);
          int by = (int)item.get_group(0);

          if (bx == 0 && by == 0 && tx == 0) {
            atomicMaxUint(&d_PointCounter[2 * octave + 0],
                          d_PointCounter[2 * octave - 1]);
            atomicMaxUint(&d_PointCounter[2 * octave + 1],
                          d_PointCounter[2 * octave - 1]);
          }

          int block = bx / NUM_SCALES;
          int scale = bx - NUM_SCALES * block;
          int minx = block * MINMAX_W;
          int maxx = sycl::min(minx + MINMAX_W, width);
          int xpos = minx + tx;
          int size = pitch * height;
          int ptr = size * scale +
                    sycl::max(sycl::min(xpos - 1, width - 1), 0);

          int yloops = sycl::min(height - MINMAX_H * by, MINMAX_H);

          // Quick threshold check
          float maxv = 0.0f;
          for (int y = 0; y < yloops; y++) {
            int ypos = MINMAX_H * by + y;
            int yptr1 = ptr + ypos * pitch;
            float val = d_Data0[yptr1 + 1 * size];
            maxv = sycl::fmax(maxv, sycl::fabs(val));
          }
          // The device may use subgroups smaller than this 32-item work-group.
          reductionScratch[tx] = maxv;
          item.barrier(sycl::access::fence_space::local_space);
          for (int stride = MEMWID / 2; stride > 0; stride >>= 1) {
            if (tx < stride)
              reductionScratch[tx] =
                  sycl::fmax(reductionScratch[tx], reductionScratch[tx + stride]);
            item.barrier(sycl::access::fence_space::local_space);
          }
          maxv = reductionScratch[0];

          if (maxv <= thresh)
            return;

          // Find candidate points
          int ptbits = 0;
          for (int y = 0; y < yloops; y++) {
            int ypos = MINMAX_H * by + y;
            int yptr1 = ptr + ypos * pitch;
            float d11 = d_Data0[yptr1 + 1 * size];

            // Check if any thread sees a value above threshold
            reductionScratch[tx] = sycl::fabs(d11) > thresh ? 1.0f : 0.0f;
            item.barrier(sycl::access::fence_space::local_space);
            for (int stride = MEMWID / 2; stride > 0; stride >>= 1) {
              if (tx < stride)
                reductionScratch[tx] =
                    sycl::fmax(reductionScratch[tx],
                               reductionScratch[tx + stride]);
              item.barrier(sycl::access::fence_space::local_space);
            }
            bool any_above = reductionScratch[0] != 0.0f;
            if (any_above) {
              int yptr0 = ptr + sycl::max(0, ypos - 1) * pitch;
              int yptr2 = ptr + sycl::min(height - 1, ypos + 1) * pitch;
              float d01 = d_Data0[yptr1];
              float d10 = d_Data0[yptr0 + 1 * size];
              float d12 = d_Data0[yptr2 + 1 * size];
              float d21 = d_Data0[yptr1 + 2 * size];
              float d00 = d_Data0[yptr0];
              float d02 = d_Data0[yptr2];
              float ymin1 = sycl::fmin(sycl::fmin(d00, d01), d02);
              float ymax1 = sycl::fmax(sycl::fmax(d00, d01), d02);
              float d20 = d_Data0[yptr0 + 2 * size];
              float d22 = d_Data0[yptr2 + 2 * size];
              float ymin3 = sycl::fmin(sycl::fmin(d20, d21), d22);
              float ymax3 = sycl::fmax(sycl::fmax(d20, d21), d22);
              float ymin2 =
                  sycl::fmin(sycl::fmin(ymin1, sycl::fmin(sycl::fmin(d10, d12), d11)), ymin3);
              float ymax2 =
                  sycl::fmax(sycl::fmax(ymax1, sycl::fmax(sycl::fmax(d10, d12), d11)), ymax3);

                reductionScratch[tx] = ymin2;
                item.barrier(sycl::access::fence_space::local_space);
                float nmin2 = sycl::fmin(
                  reductionScratch[tx > 0 ? tx - 1 : tx],
                  reductionScratch[tx + 1 < MEMWID ? tx + 1 : tx]);
                // Separate min-neighbor reads from max writes on the same
                // scratch slots so peers cannot observe a torn update.
                item.barrier(sycl::access::fence_space::local_space);
                reductionScratch[tx] = ymax2;
                item.barrier(sycl::access::fence_space::local_space);
                float nmax2 = sycl::fmax(
                  reductionScratch[tx > 0 ? tx - 1 : tx],
                  reductionScratch[tx + 1 < MEMWID ? tx + 1 : tx]);
              float minv = sycl::fmin(sycl::fmin(nmin2, ymin1), ymin3);
              minv = sycl::fmin(sycl::fmin(minv, d10), d12);
              float maxv2 = sycl::fmax(sycl::fmax(nmax2, ymax1), ymax3);
              maxv2 = sycl::fmax(sycl::fmax(maxv2, d10), d12);

              if (tx > 0 && tx < MINMAX_W + 1 && xpos <= maxx)
                ptbits |= ((d11 < sycl::fmin(-thresh, minv)) |
                           (d11 > sycl::fmax(thresh, maxv2)))
                          << y;
            }
            item.barrier(sycl::access::fence_space::local_space);
          }

          // Inclusive work-group scan compacts candidates independent of subgroup width.
          unsigned int numbits = sycl::popcount((unsigned int)ptbits);
          scanScratch[tx] = numbits;
          item.barrier(sycl::access::fence_space::local_space);
          for (int offset = 1; offset < MEMWID; offset <<= 1) {
            unsigned int add = tx >= offset ? scanScratch[tx - offset] : 0u;
            item.barrier(sycl::access::fence_space::local_space);
            scanScratch[tx] += add;
            item.barrier(sycl::access::fence_space::local_space);
          }
          unsigned int totbits = scanScratch[tx];
          int pos = (int)(totbits - numbits);
          for (int y = 0; y < yloops; y++) {
            int ypos = MINMAX_H * by + y;
            if ((ptbits & (1 << y)) && pos < MEMWID) {
              points[2 * pos + 0] = (unsigned short)(xpos - 1);
              points[2 * pos + 1] = (unsigned short)ypos;
              pos++;
            }
          }

          item.barrier(sycl::access::fence_space::local_space);
          totbits = scanScratch[MEMWID - 1];

          if (tx < (int)totbits) {
            int xpos2 = points[2 * tx + 0];
            int ypos2 = points[2 * tx + 1];
            int ptr2 = xpos2 + (ypos2 + (scale + 1) * height) * pitch;
            float val = d_Data0[ptr2];
            float *data1 = &d_Data0[ptr2];
            float dxx = 2.0f * val - data1[-1] - data1[1];
            float dyy = 2.0f * val - data1[-pitch] - data1[pitch];
            float dxy = 0.25f * (data1[+pitch + 1] + data1[-pitch - 1] -
                                  data1[-pitch + 1] - data1[+pitch - 1]);
            float tra = dxx + dyy;
            float det = dxx * dyy - dxy * dxy;
            if (tra * tra < edgeLimit * det) {
              float edge = tra * tra / det;
              float dx = 0.5f * (data1[1] - data1[-1]);
              float dy = 0.5f * (data1[pitch] - data1[-pitch]);
              float *data0 = d_Data0 + ptr2 - height * pitch;
              float *data2 = d_Data0 + ptr2 + height * pitch;
              float ds = 0.5f * (data0[0] - data2[0]);
              float dss = 2.0f * val - data2[0] - data0[0];
              float dxs = 0.25f * (data2[1] + data0[-1] - data0[1] - data2[-1]);
              float dys = 0.25f * (data2[pitch] + data0[-pitch] -
                                    data2[-pitch] - data0[pitch]);
              float idxx = dyy * dss - dys * dys;
              float idxy = dys * dxs - dxy * dss;
              float idxs = dxy * dys - dyy * dxs;
              float idet = 1.0f / (idxx * dxx + idxy * dxy + idxs * dxs);
              float idyy = dxx * dss - dxs * dxs;
              float idys = dxy * dxs - dxx * dys;
              float idss = dxx * dyy - dxy * dxy;
              float pdx = idet * (idxx * dx + idxy * dy + idxs * ds);
              float pdy = idet * (idxy * dx + idyy * dy + idys * ds);
              float pds = idet * (idxs * dx + idys * dy + idss * ds);
              if (pdx < -0.5f || pdx > 0.5f || pdy < -0.5f || pdy > 0.5f ||
                  pds < -0.5f || pds > 0.5f) {
                pdx = dx / dxx;
                pdy = dy / dyy;
                pds = ds / dss;
              }
              float dval = 0.5f * (dx * pdx + dy * pdy + ds * pds);
              float sc = sycl::pow(2.0f, (float)scale / NUM_SCALES) *
                         sycl::exp2(pds * factor);
              if (sc >= lowestScale) {
                atomicMaxUint(&d_PointCounter[2 * octave + 0],
                              d_PointCounter[2 * octave - 1]);
                unsigned int idx = atomicInc(&d_PointCounter[2 * octave + 0],
                                             0x7fffffff);
                // Skip writes past capacity instead of clobbering the last slot.
                if (idx < (unsigned int)d_MaxNumPoints) {
                  d_Sift[idx].xpos = xpos2 + pdx;
                  d_Sift[idx].ypos = ypos2 + pdy;
                  d_Sift[idx].scale = sc;
                  d_Sift[idx].sharpness = val + dval;
                  d_Sift[idx].edgeness = edge;
                  d_Sift[idx].subsampling = subsampling;
                }
              }
            }
          }
        });
  });
}

// ============================================================
// ComputeOrientationsCONST: compute keypoint orientations
// SYCL: 1 work-group of 121 items per keypoint
// ============================================================
void LaunchComputeOrientations(sycl::queue &q, SiftPoint *d_Sift, int octave,
                                const float *d_imgData, int imgWidth,
                                int imgPitch, int imgHeight,
                                unsigned int *d_PointCounter,
                                int d_MaxNumPoints) {
  const int NBLOCKS = 512;
  const int NTHREADS = 121; // 11*11

  q.submit([&](sycl::handler &cgh) {
    sycl::local_accessor<float, 1> hist(64, cgh);
    sycl::local_accessor<float, 1> gauss(11, cgh);

    cgh.parallel_for(
        sycl::nd_range<1>(sycl::range<1>(NBLOCKS * NTHREADS),
                          sycl::range<1>(NTHREADS)),
        [=](sycl::nd_item<1> item) {
          int tx = (int)item.get_local_id(0);

          int fstPts =
              sycl::min(d_PointCounter[2 * octave - 1],
                        (unsigned int)d_MaxNumPoints);
          int totPts =
              sycl::min(d_PointCounter[2 * octave + 0],
                        (unsigned int)d_MaxNumPoints);

          for (int bx = (int)item.get_group(0) + fstPts; bx < totPts;
               bx += NBLOCKS) {
            float i2sigma2 =
                -1.0f /
                (2.0f * 1.5f * 1.5f * d_Sift[bx].scale * d_Sift[bx].scale);
            if (tx < 11)
              gauss[tx] = sycl::exp(i2sigma2 * (float)((tx - 5) * (tx - 5)));
            if (tx < 64)
              hist[tx] = 0.0f;
            item.barrier(sycl::access::fence_space::local_space);

            float xp = d_Sift[bx].xpos - 4.5f;
            float yp = d_Sift[bx].ypos - 4.5f;
            int yd = tx / 11;
            int xd = tx - yd * 11;
            float xf = xp + xd;
            float yf = yp + yd;
            if (yd < 11) {
              float dx = tex2D_bilinear(d_imgData, imgPitch, imgWidth,
                                        imgHeight, xf + 1.0f, yf) -
                         tex2D_bilinear(d_imgData, imgPitch, imgWidth,
                                        imgHeight, xf - 1.0f, yf);
              float dy = tex2D_bilinear(d_imgData, imgPitch, imgWidth,
                                        imgHeight, xf, yf + 1.0f) -
                         tex2D_bilinear(d_imgData, imgPitch, imgWidth,
                                        imgHeight, xf, yf - 1.0f);
              int bin =
                  (int)(16.0f * sycl::atan2(dy, dx) / 3.1416f + 16.5f);
              if (bin > 31)
                bin = 0;
              float grad = sycl::sqrt(dx * dx + dy * dy);
              sycl::atomic_ref<float, sycl::memory_order::relaxed,
                               sycl::memory_scope::work_group,
                               sycl::access::address_space::local_space>
                  aref(hist[bin]);
              aref.fetch_add(grad * gauss[xd] * gauss[yd]);
            }
            item.barrier(sycl::access::fence_space::local_space);

            int x1m = (tx >= 1 ? tx - 1 : tx + 31);
            int x1p = (tx <= 30 ? tx + 1 : tx - 31);
            if (tx < 32) {
              int x2m = (tx >= 2 ? tx - 2 : tx + 30);
              int x2p = (tx <= 29 ? tx + 2 : tx - 30);
              hist[tx + 32] = 6.0f * hist[tx] +
                              4.0f * (hist[x1m] + hist[x1p]) +
                              (hist[x2m] + hist[x2p]);
            }
            item.barrier(sycl::access::fence_space::local_space);

            if (tx < 32) {
              float v = hist[32 + tx];
              hist[tx] =
                  (v > hist[32 + x1m] && v >= hist[32 + x1p] ? v : 0.0f);
            }
            item.barrier(sycl::access::fence_space::local_space);

            if (tx == 0) {
              float maxval1 = 0.0f, maxval2 = 0.0f;
              int i1 = -1, i2 = -1;
              for (int i = 0; i < 32; i++) {
                float v = hist[i];
                if (v > maxval1) {
                  maxval2 = maxval1;
                  maxval1 = v;
                  i2 = i1;
                  i1 = i;
                } else if (v > maxval2) {
                  maxval2 = v;
                  i2 = i;
                }
              }
              float val1 = hist[32 + ((i1 + 1) & 31)];
              float val2 = hist[32 + ((i1 + 31) & 31)];
              float peak =
                  i1 + 0.5f * (val1 - val2) / (2.0f * maxval1 - val1 - val2);
              d_Sift[bx].orientation =
                  11.25f * (peak < 0.0f ? peak + 32.0f : peak);
              atomicMaxUint(&d_PointCounter[2 * octave + 1],
                            d_PointCounter[2 * octave + 0]);

              if (maxval2 > 0.8f * maxval1 && i2 >= 0) {
                float val1b = hist[32 + ((i2 + 1) & 31)];
                float val2b = hist[32 + ((i2 + 31) & 31)];
                float peak2 = i2 + 0.5f * (val1b - val2b) /
                                       (2.0f * maxval2 - val1b - val2b);
                unsigned int idx =
                    atomicInc(&d_PointCounter[2 * octave + 1], 0x7fffffff);
                if (idx < (unsigned int)d_MaxNumPoints) {
                  d_Sift[idx].xpos = d_Sift[bx].xpos;
                  d_Sift[idx].ypos = d_Sift[bx].ypos;
                  d_Sift[idx].scale = d_Sift[bx].scale;
                  d_Sift[idx].sharpness = d_Sift[bx].sharpness;
                  d_Sift[idx].edgeness = d_Sift[bx].edgeness;
                  d_Sift[idx].orientation =
                      11.25f * (peak2 < 0.0f ? peak2 + 32.0f : peak2);
                  d_Sift[idx].subsampling = d_Sift[bx].subsampling;
                }
              }
            }
            item.barrier(sycl::access::fence_space::local_space);
          }
        });
  });
}

// ============================================================
// ExtractSiftDescriptorsCONSTNew: extract 128D SIFT descriptors
// SYCL: work-group of (16, 8) = 128 items
// ============================================================
void LaunchExtractSiftDescriptors(sycl::queue &q, SiftPoint *d_Sift,
                                   float subsampling, int octave,
                                   const float *d_imgData, int imgWidth,
                                   int imgPitch, int imgHeight,
                                   unsigned int *d_PointCounter,
                                   int d_MaxNumPoints) {
  const int NBLOCKS = 512;
  const int TX = 16, TY = 8;

  q.submit([&](sycl::handler &cgh) {
    sycl::local_accessor<float, 1> gauss(16, cgh);
    sycl::local_accessor<float, 1> buffer(4 * 128, cgh);
    sycl::local_accessor<float, 1> sums(4, cgh);
    sycl::local_accessor<float, 1> reduce_tmp(128, cgh);

    cgh.parallel_for(
        sycl::nd_range<2>(sycl::range<2>(NBLOCKS * TY, TX),
                          sycl::range<2>(TY, TX)),
        [=](sycl::nd_item<2> item) {
          int tx = (int)item.get_local_id(1);  // 0..15
          int ty = (int)item.get_local_id(0);  // 0..7
          int idx = ty * 16 + tx;

          if (ty == 0)
            gauss[tx] =
                sycl::exp(-(tx - 7.5f) * (tx - 7.5f) / 128.0f);

          int fstPts =
              sycl::min(d_PointCounter[2 * octave - 1],
                        (unsigned int)d_MaxNumPoints);
          int totPts =
              sycl::min(d_PointCounter[2 * octave + 1],
                        (unsigned int)d_MaxNumPoints);

          for (int bx = (int)item.get_group(0) + fstPts; bx < totPts;
               bx += NBLOCKS) {
            for (int bank = 0; bank < 4; ++bank)
              buffer[bank * 128 + idx] = 0.0f;
            item.barrier(sycl::access::fence_space::local_space);

            float theta =
                2.0f * 3.1415f / 360.0f * d_Sift[bx].orientation;
            float sina = sycl::sin(theta);
            float cosa = sycl::cos(theta);
            float scale = 12.0f / 16.0f * d_Sift[bx].scale;
            float ssina = scale * sina;
            float scosa = scale * cosa;

            for (int y = ty; y < 16; y += 8) {
              float xpos =
                  d_Sift[bx].xpos + (tx - 7.5f) * scosa - (y - 7.5f) * ssina + 0.5f;
              float ypos =
                  d_Sift[bx].ypos + (tx - 7.5f) * ssina + (y - 7.5f) * scosa + 0.5f;
              float dx =
                  tex2D_bilinear(d_imgData, imgPitch, imgWidth, imgHeight,
                                  xpos + cosa, ypos + sina) -
                  tex2D_bilinear(d_imgData, imgPitch, imgWidth, imgHeight,
                                  xpos - cosa, ypos - sina);
              float dy =
                  tex2D_bilinear(d_imgData, imgPitch, imgWidth, imgHeight,
                                  xpos - sina, ypos + cosa) -
                  tex2D_bilinear(d_imgData, imgPitch, imgWidth, imgHeight,
                                  xpos + sina, ypos - cosa);
              float grad = gauss[y] * gauss[tx] * sycl::sqrt(dx * dx + dy * dy);
              // Skip angle binning for vanishing gradients (FastAtan2 0/0).
              if (grad <= 0.0f)
                continue;

              float angf = 4.0f / 3.1415f * FastAtan2(dy, dx) + 4.0f;

              int hori = (tx + 2) / 4 - 1;
              float horf = (tx - 1.5f) / 4.0f - hori;
              float ihorf = 1.0f - horf;
              int veri = (y + 2) / 4 - 1;
              float verf = (y - 1.5f) / 4.0f - veri;
              float iverf = 1.0f - verf;
              int angi = (int)angf;
              int angp = (angi < 7 ? angi + 1 : 0);
              angf -= angi;
              float iangf = 1.0f - angf;

              int hist_base = 8 * (4 * veri + hori);
              int p1 = angi + hist_base;
              int p2 = angp + hist_base;

              auto atomic_add_local = [&](int pos, float val) {
                sycl::atomic_ref<
                    float, sycl::memory_order::relaxed,
                    sycl::memory_scope::work_group,
                    sycl::access::address_space::local_space>
                    ref(buffer[(idx / 32) * 128 + pos]);
                ref.fetch_add(val);
              };

              if (tx >= 2) {
                float grad1 = ihorf * grad;
                if (y >= 2) {
                  float grad2 = iverf * grad1;
                  atomic_add_local(p1, iangf * grad2);
                  atomic_add_local(p2, angf * grad2);
                }
                if (y <= 13) {
                  float grad2 = verf * grad1;
                  atomic_add_local(p1 + 32, iangf * grad2);
                  atomic_add_local(p2 + 32, angf * grad2);
                }
              }
              if (tx <= 13) {
                float grad1 = horf * grad;
                if (y >= 2) {
                  float grad2 = iverf * grad1;
                  atomic_add_local(p1 + 8, iangf * grad2);
                  atomic_add_local(p2 + 8, angf * grad2);
                }
                if (y <= 13) {
                  float grad2 = verf * grad1;
                  atomic_add_local(p1 + 40, iangf * grad2);
                  atomic_add_local(p2 + 40, angf * grad2);
                }
              }
            }
            item.barrier(sycl::access::fence_space::local_space);

            const float combined = buffer[idx] + buffer[128 + idx] +
                                   buffer[256 + idx] + buffer[384 + idx];
            item.barrier(sycl::access::fence_space::local_space);
            buffer[idx] = combined;
            item.barrier(sycl::access::fence_space::local_space);

            // Normalize twice, suppress peaks first time. Use local-memory
            // reduction within each 32-lane bank (subgroup-width independent).
            reduce_tmp[idx] = buffer[idx] * buffer[idx];
            item.barrier(sycl::access::fence_space::local_space);
            for (int stride = 16; stride > 0; stride >>= 1) {
              if ((idx & 31) < stride)
                reduce_tmp[idx] += reduce_tmp[idx + stride];
              item.barrier(sycl::access::fence_space::local_space);
            }
            if ((idx & 31) == 0)
              sums[idx / 32] = reduce_tmp[idx];
            item.barrier(sycl::access::fence_space::local_space);

            float tsum1 = sums[0] + sums[1] + sums[2] + sums[3];
            tsum1 = sycl::min(buffer[idx] * sycl::rsqrt(tsum1), 0.2f);

            reduce_tmp[idx] = tsum1 * tsum1;
            item.barrier(sycl::access::fence_space::local_space);
            for (int stride = 16; stride > 0; stride >>= 1) {
              if ((idx & 31) < stride)
                reduce_tmp[idx] += reduce_tmp[idx + stride];
              item.barrier(sycl::access::fence_space::local_space);
            }
            if ((idx & 31) == 0)
              sums[idx / 32] = reduce_tmp[idx];
            item.barrier(sycl::access::fence_space::local_space);

            float tsum2 = sums[0] + sums[1] + sums[2] + sums[3];
            d_Sift[bx].data[idx] = tsum1 * sycl::rsqrt(tsum2);
            if (idx == 0) {
              d_Sift[bx].xpos *= subsampling;
              d_Sift[bx].ypos *= subsampling;
              d_Sift[bx].scale *= subsampling;
            }
            item.barrier(sycl::access::fence_space::local_space);
          }
        });
  });
}

// ============================================================
// RescalePositions: scale xpos/ypos/scale of all keypoints
// ============================================================
void LaunchRescalePositions(sycl::queue &q, SiftPoint *d_sift, int numPts,
                             float scale) {
  q.submit([&](sycl::handler &cgh) {
    cgh.parallel_for(sycl::range<1>(numPts), [=](sycl::id<1> id) {
      int num = (int)id[0];
      d_sift[num].xpos *= scale;
      d_sift[num].ypos *= scale;
      d_sift[num].scale *= scale;
    });
  });
}
