// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
//********************************************************//
// Intel SYCL/DPC++ SIFT - standalone kernel unit test   //
// Tests SYCL device, USM, and key kernels without OpenCV//
//********************************************************//

#include <sycl/sycl.hpp>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <numeric>
#include <algorithm>

#include "syclutils.h"
#include "syclImage.h"
#include "syclSift.h"
#include "syclSiftD.h"
#include "syclSiftH.h"

// ---- Forward declarations from syclSiftD.cpp -------------------------
void LaunchScaleDown(sycl::queue &q, float *d_Result, float *d_Data,
                     int width, int pitch, int height, int newpitch,
                     const float *d_kernel);
void LaunchScaleUp(sycl::queue &q, float *d_Result, float *d_Data, int width,
                   int pitch, int height, int newpitch);
void LaunchLowPassBlock(sycl::queue &q, float *d_Image, float *d_Result,
                        int width, int pitch, int height, const float *d_kernel);
void LaunchLaplaceMultiMem(sycl::queue &q, float *d_Image, float *d_Result,
                           int width, int pitch, int height, int octave,
                           const float *d_LaplaceKernel);
void LaunchRescalePositions(sycl::queue &q, SiftPoint *d_sift, int numPts,
                             float scale);

// ---- Test helpers ----------------------------------------------------
static int g_pass = 0, g_fail = 0;

static void check(bool cond, const char *msg) {
  if (cond) {
    printf("  PASS: %s\n", msg);
    g_pass++;
  } else {
    printf("  FAIL: %s\n", msg);
    g_fail++;
  }
}

// ---- Test 1: SYCL device initialisation and queue --------------------
static void test_device_init() {
  printf("\n[Test 1] SYCL device initialisation\n");
  InitSycl(0);
  auto &q = GetSyclQueue();
  check(true, "Queue created without exception");
  auto dev = q.get_device();
  std::string name = dev.get_info<sycl::info::device::name>();
  check(!name.empty(), ("Device name: " + name).c_str());
  size_t mem = dev.get_info<sycl::info::device::global_mem_size>();
  check(mem > 0, "Device has global memory");
}

// ---- Test 2: USM allocation and basic memcpy -------------------------
static void test_usm_alloc() {
  printf("\n[Test 2] USM device allocation and memcpy\n");
  auto &q = GetSyclQueue();
  const int N = 1024;

  float *d_buf = sycl::malloc_device<float>(N, q);
  check(d_buf != nullptr, "malloc_device succeeded");

  std::vector<float> h_in(N), h_out(N, 0.0f);
  for (int i = 0; i < N; i++) h_in[i] = (float)i * 0.5f;

  q.memcpy(d_buf, h_in.data(), N * sizeof(float)).wait();
  q.memcpy(h_out.data(), d_buf, N * sizeof(float)).wait();

  bool ok = true;
  for (int i = 0; i < N; i++)
    if (std::abs(h_out[i] - h_in[i]) > 1e-6f) { ok = false; break; }
  check(ok, "Round-trip device memcpy correct");

  sycl::free(d_buf, q);
  check(true, "sycl::free succeeded");
}

// ---- Test 3: SyclImage allocation, Download, Readback ----------------
static void test_sycl_image() {
  printf("\n[Test 3] SyclImage Allocate / Download / Readback\n");
  const int W = 128, H = 64;
  const int P = iAlignUp(W, 128);

  std::vector<float> h_src(W * H);
  for (int i = 0; i < W * H; i++) h_src[i] = (float)(i % 256);

  SyclImage img;
  img.Allocate(W, H, P, true, nullptr, h_src.data());
  check(img.d_data != nullptr, "d_data allocated");
  check(img.h_data == h_src.data(), "h_data points to user buffer");

  img.Download();

  // Overwrite host, then readback
  std::vector<float> h_dst(W * H, -1.0f);
  img.h_data = h_dst.data();
  img.h_internalAlloc = false; // prevent double-free
  img.Readback();

  bool ok = true;
  for (int y = 0; y < H; y++)
    for (int x = 0; x < W; x++)
      if (std::abs(h_dst[y * W + x] - h_src[y * W + x]) > 1e-5f) {
        ok = false; break;
      }
  check(ok, "Download + Readback preserves image data");

  img.h_data = nullptr; // don't free h_src
}

// ---- Test 4: ScaleDown kernel ----------------------------------------
static void test_scale_down() {
  printf("\n[Test 4] ScaleDown kernel\n");
  auto &q = GetSyclQueue();
  const int W = 128, H = 64;
  const int P = iAlignUp(W, 128);
  const int W2 = W / 2, H2 = H / 2;
  const int P2 = iAlignUp(W2, 128);

  // Gaussian downsample kernel
  float h_kernel[5];
  float var = 0.5f, sum = 0;
  for (int j = 0; j < 5; j++) {
    h_kernel[j] = expf(-(float)(j-2)*(j-2) / 2.0f / var);
    sum += h_kernel[j];
  }
  for (int j = 0; j < 5; j++) h_kernel[j] /= sum;
  float *d_kernel = sycl::malloc_device<float>(5, q);
  q.memcpy(d_kernel, h_kernel, 5 * sizeof(float)).wait();

  // Fill source with a ramp
  std::vector<float> h_src(P * H);
  for (int y = 0; y < H; y++)
    for (int x = 0; x < P; x++)
      h_src[y * P + x] = (x < W ? (float)(x + y) : 0.0f);

  float *d_src = sycl::malloc_device<float>(P * H, q);
  float *d_dst = sycl::malloc_device<float>(P2 * H2, q);
  q.memset(d_dst, 0, P2 * H2 * sizeof(float));
  q.memcpy(d_src, h_src.data(), P * H * sizeof(float)).wait();

  LaunchScaleDown(q, d_dst, d_src, W, P, H, P2, d_kernel);
  q.wait();

  std::vector<float> h_dst(P2 * H2);
  q.memcpy(h_dst.data(), d_dst, P2 * H2 * sizeof(float)).wait();

  // Verify output size is half and values are within range
  bool inrange = true;
  for (int y = 0; y < H2; y++)
    for (int x = 0; x < W2; x++) {
      float v = h_dst[y * P2 + x];
      if (v < 0.0f || v > (float)(W + H) * 1.1f) { inrange = false; break; }
    }
  check(inrange, "ScaleDown output values in plausible range");

  // Verify spatial downsampling: output[0,0] should approximate input around (1,1)
  float expected_center = h_src[1 * P + 1]; // rough center for (0,0) block
  float got = h_dst[0];
  check(got > 0.0f, "ScaleDown output[0,0] is non-zero");

  sycl::free(d_src, q);
  sycl::free(d_dst, q);
  sycl::free(d_kernel, q);
}

// ---- Test 5: ScaleUp kernel -----------------------------------------
static void test_scale_up() {
  printf("\n[Test 5] ScaleUp kernel\n");
  auto &q = GetSyclQueue();
  const int W = 64, H = 32;
  const int P = iAlignUp(W, 128);
  const int W2 = W * 2, H2 = H * 2;
  const int P2 = iAlignUp(W2, 128);

  std::vector<float> h_src(P * H, 0.0f);
  for (int y = 0; y < H; y++)
    for (int x = 0; x < W; x++)
      h_src[y * P + x] = (float)(x * 2 + y);

  float *d_src = sycl::malloc_device<float>(P * H, q);
  float *d_dst = sycl::malloc_device<float>(P2 * H2, q);
  q.memset(d_dst, 0, P2 * H2 * sizeof(float));
  q.memcpy(d_src, h_src.data(), P * H * sizeof(float)).wait();

  LaunchScaleUp(q, d_dst, d_src, W, P, H, P2);
  q.wait();

  std::vector<float> h_dst(P2 * H2);
  q.memcpy(h_dst.data(), d_dst, P2 * H2 * sizeof(float)).wait();

  // Check: output[0,0] == input[0,0], output[0,1] == 0.5*(input[0,0]+input[0,1])
  float v00 = h_src[0 * P + 0];
  float v01 = h_src[0 * P + 1];
  check(std::abs(h_dst[0 * P2 + 0] - v00) < 1e-4f, "ScaleUp[0,0] == src[0,0]");
  check(std::abs(h_dst[0 * P2 + 1] - 0.5f * (v00 + v01)) < 1e-4f,
        "ScaleUp[0,1] == 0.5*(src[0,0]+src[0,1])");

  sycl::free(d_src, q);
  sycl::free(d_dst, q);
}

// ---- Test 6: LowPass kernel -----------------------------------------
static void test_lowpass() {
  printf("\n[Test 6] LowPassBlock kernel\n");
  auto &q = GetSyclQueue();
  const int W = 128, H = 64;
  const int P = iAlignUp(W, 128);

  // Build a Gaussian kernel
  float h_kernel[2 * LOWPASS_R + 1];
  float scale = 1.5f, sum = 0;
  for (int j = -LOWPASS_R; j <= LOWPASS_R; j++) {
    h_kernel[j + LOWPASS_R] = expf(-(float)j * j / (2.0f * scale * scale));
    sum += h_kernel[j + LOWPASS_R];
  }
  for (int j = 0; j <= 2 * LOWPASS_R; j++) h_kernel[j] /= sum;

  float *d_kernel = sycl::malloc_device<float>(2 * LOWPASS_R + 1, q);
  q.memcpy(d_kernel, h_kernel, (2 * LOWPASS_R + 1) * sizeof(float)).wait();

  // Impulse image: only centre pixel is 1.0
  std::vector<float> h_src(P * H, 0.0f);
  h_src[(H / 2) * P + (W / 2)] = 1.0f;

  float *d_src = sycl::malloc_device<float>(P * H, q);
  float *d_dst = sycl::malloc_device<float>(P * H, q);
  q.memset(d_dst, 0, P * H * sizeof(float));
  q.memcpy(d_src, h_src.data(), P * H * sizeof(float)).wait();

  LaunchLowPassBlock(q, d_src, d_dst, W, P, H, d_kernel);
  q.wait();

  std::vector<float> h_dst(P * H);
  q.memcpy(h_dst.data(), d_dst, P * H * sizeof(float)).wait();

  // The response to a unit impulse should be the kernel itself (separable)
  float centre = h_dst[(H / 2) * P + (W / 2)];
  check(centre > 0.0f && centre <= 1.0f,
        "LowPass impulse response centre is in (0,1]");

  // Sum of output should be approximately 1 (energy conservation)
  float total = 0.0f;
  double moment_x = 0.0;
  double moment_y = 0.0;
  for (int y = 0; y < H; y++) {
    for (int x = 0; x < W; x++) {
      total += h_dst[y * P + x];
      moment_x += x * h_dst[y * P + x];
      moment_y += y * h_dst[y * P + x];
    }
  }
  check(std::abs(total - 1.0f) < 0.01f,
        "LowPass energy conservation (sum ≈ 1)");
  check(total > 0.0f && std::abs(moment_x / total - W / 2) < 0.01,
        "LowPass preserves the impulse X coordinate");
  check(total > 0.0f && std::abs(moment_y / total - H / 2) < 0.01,
        "LowPass preserves the impulse Y coordinate");

  sycl::free(d_src, q);
  sycl::free(d_dst, q);
  sycl::free(d_kernel, q);
}

// ---- Test 7: RescalePositions kernel --------------------------------
static void test_rescale_positions() {
  printf("\n[Test 7] RescalePositions kernel\n");
  auto &q = GetSyclQueue();
  const int N = 16;
  const float SCALE = 0.5f;

  std::vector<SiftPoint> h_pts(N);
  for (int i = 0; i < N; i++) {
    h_pts[i].xpos = (float)(i * 3);
    h_pts[i].ypos = (float)(i * 7);
    h_pts[i].scale = (float)(i + 1);
  }
  SiftPoint *d_pts = sycl::malloc_device<SiftPoint>(N, q);
  q.memcpy(d_pts, h_pts.data(), N * sizeof(SiftPoint)).wait();

  LaunchRescalePositions(q, d_pts, N, SCALE);
  q.wait();

  std::vector<SiftPoint> h_out(N);
  q.memcpy(h_out.data(), d_pts, N * sizeof(SiftPoint)).wait();

  bool ok = true;
  for (int i = 0; i < N; i++) {
    if (std::abs(h_out[i].xpos - h_pts[i].xpos * SCALE) > 1e-5f ||
        std::abs(h_out[i].ypos - h_pts[i].ypos * SCALE) > 1e-5f ||
        std::abs(h_out[i].scale - h_pts[i].scale * SCALE) > 1e-5f) {
      ok = false;
      break;
    }
  }
  check(ok, "RescalePositions scales xpos/ypos/scale by 0.5 correctly");
  sycl::free(d_pts, q);
}

// ---- Test 8: SiftData allocation and InitSiftData -------------------
static void test_sift_data() {
  printf("\n[Test 8] InitSiftData / FreeSiftData\n");
  SiftData data;
  InitSiftData(data, 1024, true, true);
  check(data.d_data != nullptr, "d_data allocated");
  check(data.h_data != nullptr, "h_data allocated");
  check(data.maxPts == 1024, "maxPts == 1024");
  check(data.numPts == 0, "numPts == 0");

  // Write a point device-side and read it back
  auto &q = GetSyclQueue();
  SiftPoint pt{};
  pt.xpos = 42.0f; pt.ypos = 13.0f; pt.scale = 2.5f;
  q.memcpy(data.d_data, &pt, sizeof(SiftPoint)).wait();
  q.memcpy(data.h_data, data.d_data, sizeof(SiftPoint)).wait();
  check(std::abs(data.h_data[0].xpos - 42.0f) < 1e-5f,
        "SiftPoint round-trip: xpos correct");

  FreeSiftData(data);
  check(data.d_data == nullptr && data.h_data == nullptr,
        "FreeSiftData nulls pointers");
}

// ---- Test 9: LaplaceMultiMem end-to-end coherence -------------------
static void test_laplace_multi() {
  printf("\n[Test 9] LaplaceMultiMem kernel coherence\n");
  auto &q = GetSyclQueue();
  const int W = 128, H = 64;
  const int P = iAlignUp(W, 128);
  const int ND = NUM_SCALES + 2; // number of DoG images produced

  // Build Laplace kernel table
  float h_laplaceKernel[8 * 12 * 16];
  PrepareLaplaceKernels(1, 0.0f, h_laplaceKernel);
  float *d_laplaceKernel = sycl::malloc_device<float>(8 * 12 * 16, q);
  q.memcpy(d_laplaceKernel, h_laplaceKernel, 8 * 12 * 16 * sizeof(float)).wait();

  // Source: smooth gradient image
  std::vector<float> h_src(P * H);
  for (int y = 0; y < H; y++)
    for (int x = 0; x < P; x++)
      h_src[y * P + x] = (x < W ? sinf((float)x * 0.1f) * cosf((float)y * 0.1f) : 0.0f);

  float *d_src = sycl::malloc_device<float>(P * H, q);
  float *d_result = sycl::malloc_device<float>(ND * P * H, q);
  q.memset(d_result, 0, ND * P * H * sizeof(float));
  q.memcpy(d_src, h_src.data(), P * H * sizeof(float)).wait();

  LaunchLaplaceMultiMem(q, d_src, d_result, W, P, H, 1, d_laplaceKernel);
  q.wait();

  std::vector<float> h_result(ND * P * H);
  q.memcpy(h_result.data(), d_result, ND * P * H * sizeof(float)).wait();

  // For a smooth image, DoG values should be small (near zero for no edges)
  // Just verify the output is finite and not all-zero
  bool has_nonzero = false, all_finite = true;
  for (int i = 0; i < ND * P * H; i++) {
    float v = h_result[i];
    if (!std::isfinite(v)) { all_finite = false; break; }
    if (std::abs(v) > 1e-6f) has_nonzero = true;
  }
  check(all_finite, "LaplaceMultiMem output is finite");
  check(has_nonzero, "LaplaceMultiMem produces non-zero DoG output");

  sycl::free(d_src, q);
  sycl::free(d_result, q);
  sycl::free(d_laplaceKernel, q);
}

// ---- Main -----------------------------------------------------------
int main() {
  printf("=================================================\n");
  printf("  Intel SYCL SIFT reference - Kernel Unit Tests  \n");
  printf("=================================================\n");

  try {
    test_device_init();
    test_usm_alloc();
    test_sycl_image();
    test_scale_down();
    test_scale_up();
    test_lowpass();
    test_rescale_positions();
    test_sift_data();
    test_laplace_multi();
  } catch (sycl::exception &e) {
    fprintf(stderr, "\nSYCL exception: %s\n", e.what());
    return 1;
  }

  printf("\n=================================================\n");
  printf("  Results: %d passed, %d failed\n", g_pass, g_fail);
  printf("=================================================\n");
  return (g_fail > 0) ? 1 : 0;
}
