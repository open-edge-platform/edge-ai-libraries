// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-FileCopyrightText: Copyright (c) 2017 Mårten Björkman
// SPDX-License-Identifier: Apache-2.0 AND MIT
//********************************************************//
// Intel SYCL/DPC++ SIFT extractor                       //
// SYCL reference backend (mechanics baseline).
//********************************************************//

#ifndef SYCLUTILS_H
#define SYCLUTILS_H

#include <sycl/sycl.hpp>
#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <chrono>

// ---- Global SYCL queue -----------------------------------------------
sycl::queue &GetSyclQueue();

// ---- Timing ----------------------------------------------------------
class TimerGPU {
public:
  std::chrono::high_resolution_clock::time_point start_;
  TimerGPU() { start_ = std::chrono::high_resolution_clock::now(); }
  float read() {
    GetSyclQueue().wait();
    auto end = std::chrono::high_resolution_clock::now();
    return std::chrono::duration<float, std::milli>(end - start_).count();
  }
};

class TimerCPU {
public:
  std::chrono::high_resolution_clock::time_point start_;
  TimerCPU() { start_ = std::chrono::high_resolution_clock::now(); }
  float read() {
    auto end = std::chrono::high_resolution_clock::now();
    return std::chrono::duration<float, std::milli>(end - start_).count();
  }
};

// ---- SYCL atomic helpers (device-side) --------------------------------
// atomicAdd equivalent for float local/shared memory
template <sycl::access::address_space AS = sycl::access::address_space::local_space>
inline void atomicAddFloat(float *ptr, float val) {
  sycl::atomic_ref<float, sycl::memory_order::relaxed,
                   sycl::memory_scope::work_group, AS>
      ref(*ptr);
  ref.fetch_add(val);
}

// Device atomicAdd on global USM memory
inline void atomicAddFloatGlobal(float *ptr, float val) {
  sycl::atomic_ref<float, sycl::memory_order::relaxed,
                   sycl::memory_scope::device,
                   sycl::access::address_space::global_space>
      ref(*ptr);
  ref.fetch_add(val);
}

// atomicInc equivalent: increment, wrapping to 0 when > wrap
inline unsigned int atomicInc(unsigned int *ptr, unsigned int wrap) {
  sycl::atomic_ref<unsigned int, sycl::memory_order::acq_rel,
                   sycl::memory_scope::device,
                   sycl::access::address_space::global_space>
      ref(*ptr);
  unsigned int old = ref.load(sycl::memory_order::relaxed);
  unsigned int desired;
  do {
    desired = (old >= wrap) ? 0u : old + 1u;
  } while (!ref.compare_exchange_weak(old, desired, sycl::memory_order::acq_rel,
                                      sycl::memory_order::relaxed));
  return old;
}

// atomicMax equivalent on unsigned int
inline void atomicMaxUint(unsigned int *ptr, unsigned int val) {
  sycl::atomic_ref<unsigned int, sycl::memory_order::relaxed,
                   sycl::memory_scope::device,
                   sycl::access::address_space::global_space>
      ref(*ptr);
  ref.fetch_max(val);
}

// atomicMax equivalent on int
inline void atomicMaxInt(int *ptr, int val) {
  sycl::atomic_ref<int, sycl::memory_order::relaxed,
                   sycl::memory_scope::device,
                   sycl::access::address_space::global_space>
      ref(*ptr);
  ref.fetch_max(val);
}

// atomicAdd equivalent on unsigned int (global)
inline unsigned int atomicAddUint(unsigned int *ptr, unsigned int val) {
  sycl::atomic_ref<unsigned int, sycl::memory_order::relaxed,
                   sycl::memory_scope::device,
                   sycl::access::address_space::global_space>
      ref(*ptr);
  return ref.fetch_add(val);
}

// ---- Bilinear texture sampling -----------------------------------------
// Linear-filter, unnormalized coords, clamp-mode sampling:
//   pixel center (i,j) is at coordinate (i+0.5, j+0.5)
//   tex2D(tex, x, y) samples at pixel coordinate (x-0.5, y-0.5)
inline float tex2D_bilinear(const float *img, int pitch, int width, int height,
                             float x, float y) {
  float px = x - 0.5f;
  float py = y - 0.5f;
  int x0 = (int)sycl::floor(px);
  int y0 = (int)sycl::floor(py);
  float fx = px - (float)x0;
  float fy = py - (float)y0;
  int x1 = x0 + 1;
  int y1 = y0 + 1;
  x0 = sycl::clamp(x0, 0, width - 1);
  x1 = sycl::clamp(x1, 0, width - 1);
  y0 = sycl::clamp(y0, 0, height - 1);
  y1 = sycl::clamp(y1, 0, height - 1);
  float v00 = img[y0 * pitch + x0];
  float v10 = img[y0 * pitch + x1];
  float v01 = img[y1 * pitch + x0];
  float v11 = img[y1 * pitch + x1];
  return (1.0f - fx) * (1.0f - fy) * v00 + fx * (1.0f - fy) * v10 +
         (1.0f - fx) * fy * v01 + fx * fy * v11;
}

// ---- Fast atan2 approximation ------------------------------------------
inline float FastAtan2(float y, float x) {
  float absx = sycl::fabs(x);
  float absy = sycl::fabs(y);
  float maxv = sycl::max(absx, absy);
  if (maxv == 0.0f)
    return 0.0f;
  float a = sycl::min(absx, absy) / maxv;
  float s = a * a;
  float r =
      ((-0.0464964749f * s + 0.15931422f) * s - 0.327622764f) * s * a + a;
  r = (absy > absx ? 1.57079637f - r : r);
  r = (x < 0 ? 3.14159274f - r : r);
  r = (y < 0 ? -r : r);
  return r;
}

#endif // SYCLUTILS_H
