// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-FileCopyrightText: Copyright (c) 2017 Mårten Björkman
// SPDX-License-Identifier: Apache-2.0 AND MIT
//********************************************************//
// Intel SYCL/DPC++ SIFT extractor                       //
// Host-side SIFT orchestration                          //
// SYCL reference backend (mechanics baseline).
//********************************************************//

#include <cstdio>
#include <cstring>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <algorithm>

#include "syclutils.h"
#include "syclImage.h"
#include "syclSift.h"
#include "syclSiftD.h"
#include "syclSiftH.h"

// ---- Forward declarations of kernel launchers (defined in syclSiftD.cpp) ---
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
void LaunchFindPointsMultiNew(sycl::queue &q, float *d_Data0, SiftPoint *d_Sift,
                               int width, int pitch, int height,
                               float subsampling, float lowestScale,
                               float thresh, float factor, float edgeLimit,
                               int octave, unsigned int *d_PointCounter,
                               int d_MaxNumPoints);
void LaunchComputeOrientations(sycl::queue &q, SiftPoint *d_Sift, int octave,
                                const float *d_imgData, int imgWidth,
                                int imgPitch, int imgHeight,
                                unsigned int *d_PointCounter, int d_MaxNumPoints);
void LaunchExtractSiftDescriptors(sycl::queue &q, SiftPoint *d_Sift,
                                   float subsampling, int octave,
                                   const float *d_imgData, int imgWidth,
                                   int imgPitch, int imgHeight,
                                   unsigned int *d_PointCounter,
                                   int d_MaxNumPoints);
void LaunchRescalePositions(sycl::queue &q, SiftPoint *d_sift, int numPts,
                             float scale);

// ---- Persistent device buffers for kernels --------------------------------
// These mirror historical constant / device globals:
//   d_ScaleDownKernel[5]
//   d_LowPassKernel[2*LOWPASS_R+1]
//   d_LaplaceKernel[8*12*16]
//   d_PointCounter[POINT_COUNTER_SIZE]
//   d_MaxNumPoints (passed as value)
static float *g_d_ScaleDownKernel = nullptr;
static float *g_d_LowPassKernel = nullptr;
static float *g_d_LaplaceKernel = nullptr;
static unsigned int *g_d_PointCounter = nullptr;
static float g_lastScaleDownVariance = -1.0f;
static float g_lastLowPassScale = -1.0f;

static void WaitForStageIfRequested(sycl::queue &q, const char *stage) {
  if (!std::getenv("SIFT_SYCL_SYNC_EACH_STAGE"))
    return;

  try {
    q.wait_and_throw();
    std::fprintf(stderr, "SYCL stage complete: %s\n", stage);
  } catch (const sycl::exception &ex) {
    std::fprintf(stderr, "SYCL stage failed: %s: %s\n", stage, ex.what());
    throw;
  }
}

static void EnsureDeviceBuffers() {
  auto &q = GetSyclQueue();
  if (!g_d_ScaleDownKernel) {
    g_d_ScaleDownKernel = sycl::malloc_device<float>(5, q);
    g_d_LowPassKernel = sycl::malloc_device<float>(2 * LOWPASS_R + 1, q);
    g_d_LaplaceKernel = sycl::malloc_device<float>(8 * 12 * 16, q);
    g_d_PointCounter =
        sycl::malloc_device<unsigned int>(POINT_COUNTER_SIZE, q);
  }
}

// ---- Public API ----------------------------------------------------------

void InitSycl(int devNum) {
  // Re-initialise global queue if devNum != 0 (future: device selection)
  auto &q = GetSyclQueue();
  auto dev = q.get_device();
  printf("SYCL Device: %s\n", dev.get_info<sycl::info::device::name>().c_str());
  printf("  Vendor: %s\n",
         dev.get_info<sycl::info::device::vendor>().c_str());
  printf("  Max Compute Units: %lu\n",
         (unsigned long)dev.get_info<sycl::info::device::max_compute_units>());
  printf("  Global Memory: %lu MB\n",
         (unsigned long)(dev.get_info<sycl::info::device::global_mem_size>() /
                          (1024 * 1024)));
  printf("  Max Work Group Size: %lu\n\n",
         (unsigned long)dev.get_info<
             sycl::info::device::max_work_group_size>());
  EnsureDeviceBuffers();
}

float *AllocSiftTempMemory(int width, int height, int numOctaves, bool scaleUp) {
  TimerGPU timer;
  EnsureDeviceBuffers();
  const int nd = NUM_SCALES + 3;
  int w = width * (scaleUp ? 2 : 1);
  int h = height * (scaleUp ? 2 : 1);
  int p = iAlignUp(w, 128);
  int size = h * p;
  int sizeTmp = nd * h * p;
  for (int i = 0; i < numOctaves; i++) {
    w /= 2;
    h /= 2;
    p = iAlignUp(w, 128);
    size += h * p;
    sizeTmp += nd * h * p;
  }
  size += sizeTmp;
  auto &q = GetSyclQueue();
  float *memoryTmp = sycl::malloc_device<float>(size, q);
#ifdef VERBOSE
  printf("Allocated memory size: %d floats\n", size);
  printf("Memory allocation time =      %.2f ms\n\n", timer.read());
#endif
  return memoryTmp;
}

void FreeSiftTempMemory(float *memoryTmp) {
  if (memoryTmp)
    sycl::free(memoryTmp, GetSyclQueue());
}

void ExtractSift(SiftData &siftData, SyclImage &img, int numOctaves,
                 double initBlur, float thresh, float lowestScale,
                 bool scaleUp, float *tempMemory) {
  TimerGPU timer;
  EnsureDeviceBuffers();
  auto &q = GetSyclQueue();

  // Octave parameter is 1-based through ExtractSiftLoop (finest uses
  // numOctaves). Counters need [2*numOctaves+1] and Laplace kernels need
  // slots 1..numOctaves inside an 8*12*16 buffer — reject 8+.
  if (numOctaves < 1 || numOctaves > 7) {
    fprintf(stderr,
            "ExtractSift: numOctaves=%d unsupported (valid range 1..7)\n",
            numOctaves);
    siftData.numPts = 0;
    return;
  }

  // Reset point counter and upload maxPts
  q.memset(g_d_PointCounter, 0, POINT_COUNTER_SIZE * sizeof(unsigned int))
      .wait();

  const int nd = NUM_SCALES + 3;
  int w = img.width * (scaleUp ? 2 : 1);
  int h = img.height * (scaleUp ? 2 : 1);
  int p = iAlignUp(w, 128);
  int width = w, height = h;
  int size = h * p;
  int sizeTmp = nd * h * p;
  for (int i = 0; i < numOctaves; i++) {
    w /= 2;
    h /= 2;
    int pp = iAlignUp(w, 128);
    size += h * pp;
    sizeTmp += nd * h * pp;
  }
  float *memoryTmp = tempMemory;
  size += sizeTmp;
  if (!tempMemory)
    memoryTmp = sycl::malloc_device<float>(size, q);

  float *memorySub = memoryTmp + sizeTmp;

  SyclImage lowImg;
  lowImg.Allocate(width, height, iAlignUp(width, 128), false, memorySub);

  if (!scaleUp) {
    float kernel[8 * 12 * 16];
    PrepareLaplaceKernels(numOctaves, 0.0f, kernel);
    q.memcpy(g_d_LaplaceKernel, kernel, 8 * 12 * 16 * sizeof(float)).wait();
    LowPass(lowImg, img, std::max(initBlur, 0.001));
    TimerGPU timer1;
    ExtractSiftLoop(siftData, lowImg, numOctaves, 0.0f, thresh, lowestScale,
                    1.0f, memoryTmp,
                    memorySub + height * iAlignUp(width, 128));
    // Read back point count
    unsigned int hostCounter[POINT_COUNTER_SIZE];
    q.memcpy(hostCounter, g_d_PointCounter,
              POINT_COUNTER_SIZE * sizeof(unsigned int))
        .wait();
    // Orientations publish secondaries on [2*octave+1]; finest octave uses
    // octave==numOctaves, so the inclusive count is at 2*numOctaves+1.
    siftData.numPts = hostCounter[2 * numOctaves + 1];
    siftData.numPts =
        (siftData.numPts < siftData.maxPts ? siftData.numPts : siftData.maxPts);
    printf("SIFT extraction time =        %.2f ms %d\n", timer1.read(),
           siftData.numPts);
  } else {
    SyclImage upImg;
    upImg.Allocate(width, height, iAlignUp(width, 128), false, memoryTmp);
    TimerGPU timer1;
    ScaleUp(upImg, img);
    LowPass(lowImg, upImg, std::max(initBlur, 0.001));
    float kernel[8 * 12 * 16];
    PrepareLaplaceKernels(numOctaves, 0.0f, kernel);
    q.memcpy(g_d_LaplaceKernel, kernel, 8 * 12 * 16 * sizeof(float)).wait();
    ExtractSiftLoop(siftData, lowImg, numOctaves, 0.0f, thresh,
                    lowestScale * 2.0f, 1.0f, memoryTmp,
                    memorySub + height * iAlignUp(width, 128));
    unsigned int hostCounter[POINT_COUNTER_SIZE];
    q.memcpy(hostCounter, g_d_PointCounter,
              POINT_COUNTER_SIZE * sizeof(unsigned int))
        .wait();
    siftData.numPts = hostCounter[2 * numOctaves + 1];
    siftData.numPts =
        (siftData.numPts < siftData.maxPts ? siftData.numPts : siftData.maxPts);
    RescalePositions(siftData, 0.5f);
    printf("SIFT extraction time =        %.2f ms\n", timer1.read());
  }

  if (!tempMemory)
    sycl::free(memoryTmp, q);

  // Copy device results to host
  if (siftData.h_data && siftData.d_data)
    q.memcpy(siftData.h_data, siftData.d_data,
              sizeof(SiftPoint) * siftData.numPts)
        .wait();

  double totTime = timer.read();
  printf("Incl prefiltering & memcpy =  %.2f ms %d\n\n", totTime,
         siftData.numPts);
}

int ExtractSiftLoop(SiftData &siftData, SyclImage &img, int numOctaves,
                    double initBlur, float thresh, float lowestScale,
                    float subsampling, float *memoryTmp, float *memorySub) {
#ifdef VERBOSE
  TimerGPU timer;
#endif
  int w = img.width;
  int h = img.height;
  if (numOctaves > 1) {
    SyclImage subImg;
    int pp = iAlignUp(w / 2, 128);
    subImg.Allocate(w / 2, h / 2, pp, false, memorySub);
    ScaleDown(subImg, img, 0.5f);
    float totInitBlur =
        (float)std::sqrt(initBlur * initBlur + 0.5 * 0.5) / 2.0f;
    ExtractSiftLoop(siftData, subImg, numOctaves - 1, totInitBlur, thresh,
                    lowestScale, subsampling * 2.0f, memoryTmp,
                    memorySub + (h / 2) * pp);
  }
  ExtractSiftOctave(siftData, img, numOctaves, thresh, lowestScale, subsampling,
                    memoryTmp);
#ifdef VERBOSE
  double totTime = timer.read();
  printf("ExtractSift time total =      %.2f ms %d\n\n", totTime, numOctaves);
#endif
  return 0;
}

void ExtractSiftOctave(SiftData &siftData, SyclImage &img, int octave,
                       float thresh, float lowestScale, float subsampling,
                       float *memoryTmp) {
  const int nd = NUM_SCALES + 3;
  auto &q = GetSyclQueue();

#ifdef VERBOSE
  unsigned int hostCounter[POINT_COUNTER_SIZE];
  q.memcpy(hostCounter, g_d_PointCounter,
            POINT_COUNTER_SIZE * sizeof(unsigned int))
      .wait();
  unsigned int fstPts = hostCounter[2 * octave - 1];
  TimerGPU timer0;
#endif

  SyclImage diffImg[nd - 1];
  int w = img.width;
  int h = img.height;
  int pp = iAlignUp(w, 128);
  for (int i = 0; i < nd - 1; i++)
    diffImg[i].Allocate(w, h, pp, false, memoryTmp + i * pp * h);

#ifdef VERBOSE
  TimerGPU timer1;
#endif

  LaplaceMulti(img, diffImg, octave);
  WaitForStageIfRequested(q, "dog");
  FindPointsMulti(diffImg, siftData, thresh, 10.0f, 1.0f / NUM_SCALES,
                  lowestScale / subsampling, subsampling, octave);
  WaitForStageIfRequested(q, "extrema");

#ifdef VERBOSE
  double gpuTimeDoG = timer1.read();
  TimerGPU timer4;
#endif

  ComputeOrientations(img, siftData, octave);
  WaitForStageIfRequested(q, "orientation");
  ExtractSiftDescriptors(img, siftData, subsampling, octave);
  WaitForStageIfRequested(q, "descriptors");

  q.wait();

#ifdef VERBOSE
  double gpuTimeSift = timer4.read();
  double totTime = timer0.read();
  printf("GPU time : %.2f ms + %.2f ms + %.2f ms = %.2f ms\n",
         totTime - gpuTimeDoG - gpuTimeSift, gpuTimeDoG, gpuTimeSift, totTime);
  q.memcpy(hostCounter, g_d_PointCounter,
            POINT_COUNTER_SIZE * sizeof(unsigned int))
      .wait();
  unsigned int totPts = hostCounter[2 * octave + 1];
  totPts = (totPts < (unsigned int)siftData.maxPts ? totPts
                                                    : (unsigned int)siftData.maxPts);
  if (totPts > fstPts)
    printf("           %.2f ms / DoG,  %.4f ms / Sift,  #Sift = %d\n",
           gpuTimeDoG / NUM_SCALES,
           gpuTimeSift / (float)(totPts - fstPts),
           (int)(totPts - fstPts));
#endif
}

void InitSiftData(SiftData &data, int num, bool host, bool dev) {
  data.numPts = 0;
  data.maxPts = num;
  int sz = (int)sizeof(SiftPoint) * num;
  data.h_data = nullptr;
  if (host)
    data.h_data = (SiftPoint *)malloc(sz);
  data.d_data = nullptr;
  if (dev) {
    auto &q = GetSyclQueue();
    data.d_data = sycl::malloc_device<SiftPoint>(num, q);
  }
}

void FreeSiftData(SiftData &data) {
  if (data.d_data)
    sycl::free(data.d_data, GetSyclQueue());
  data.d_data = nullptr;
  if (data.h_data)
    free(data.h_data);
  data.h_data = nullptr;
  data.numPts = 0;
  data.maxPts = 0;
}

void PrintSiftData(SiftData &data) {
  SiftPoint *h_data = data.h_data;
  bool localAlloc = false;
  if (!h_data) {
    h_data = (SiftPoint *)malloc(sizeof(SiftPoint) * data.maxPts);
    localAlloc = true;
    GetSyclQueue()
        .memcpy(h_data, data.d_data, sizeof(SiftPoint) * data.numPts)
        .wait();
  }
  for (int i = 0; i < data.numPts; i++) {
    printf("xpos = %.2f  ypos = %.2f  scale = %.2f  orientation = %.2f\n",
           h_data[i].xpos, h_data[i].ypos, h_data[i].scale,
           h_data[i].orientation);
  }
  printf("Number of available points: %d\n", data.numPts);
  printf("Number of allocated points: %d\n", data.maxPts);
  if (localAlloc)
    free(h_data);
}

// ---- Internal kernel wrappers --------------------------------------------

double ScaleDown(SyclImage &res, SyclImage &src, float variance) {
  EnsureDeviceBuffers();
  auto &q = GetSyclQueue();
  if (res.d_data == nullptr || src.d_data == nullptr) {
    printf("ScaleDown: missing data\n");
    return 0.0;
  }
  if (g_lastScaleDownVariance != variance) {
    float h_Kernel[5];
    float kernelSum = 0.0f;
    for (int j = 0; j < 5; j++) {
      h_Kernel[j] = expf(-(float)(j - 2) * (j - 2) / 2.0f / variance);
      kernelSum += h_Kernel[j];
    }
    for (int j = 0; j < 5; j++)
      h_Kernel[j] /= kernelSum;
    q.memcpy(g_d_ScaleDownKernel, h_Kernel, 5 * sizeof(float)).wait();
    g_lastScaleDownVariance = variance;
  }
  LaunchScaleDown(q, res.d_data, src.d_data, src.width, src.pitch, src.height,
                  res.pitch, g_d_ScaleDownKernel);
  return 0.0;
}

double ScaleUp(SyclImage &res, SyclImage &src) {
  auto &q = GetSyclQueue();
  if (res.d_data == nullptr || src.d_data == nullptr) {
    printf("ScaleUp: missing data\n");
    return 0.0;
  }
  LaunchScaleUp(q, res.d_data, src.d_data, src.width, src.pitch, src.height,
                res.pitch);
  return 0.0;
}

double ComputeOrientations(SyclImage &src, SiftData &siftData, int octave) {
  EnsureDeviceBuffers();
  auto &q = GetSyclQueue();
  LaunchComputeOrientations(q, siftData.d_data, octave, src.d_data, src.width,
                             src.pitch, src.height, g_d_PointCounter,
                             siftData.maxPts);
  return 0.0;
}

double ExtractSiftDescriptors(SyclImage &src, SiftData &siftData,
                               float subsampling, int octave) {
  EnsureDeviceBuffers();
  auto &q = GetSyclQueue();
  LaunchExtractSiftDescriptors(q, siftData.d_data, subsampling, octave,
                                src.d_data, src.width, src.pitch, src.height,
                                g_d_PointCounter, siftData.maxPts);
  return 0.0;
}

double RescalePositions(SiftData &siftData, float scale) {
  auto &q = GetSyclQueue();
  LaunchRescalePositions(q, siftData.d_data, siftData.numPts, scale);
  return 0.0;
}

double LowPass(SyclImage &res, SyclImage &src, float scale) {
  EnsureDeviceBuffers();
  auto &q = GetSyclQueue();
  if (g_lastLowPassScale != scale) {
    float kernel[2 * LOWPASS_R + 1];
    float kernelSum = 0.0f;
    float ivar2 = 1.0f / (2.0f * scale * scale);
    for (int j = -LOWPASS_R; j <= LOWPASS_R; j++) {
      kernel[j + LOWPASS_R] = expf(-(float)j * j * ivar2);
      kernelSum += kernel[j + LOWPASS_R];
    }
    for (int j = -LOWPASS_R; j <= LOWPASS_R; j++)
      kernel[j + LOWPASS_R] /= kernelSum;
    q.memcpy(g_d_LowPassKernel, kernel, (2 * LOWPASS_R + 1) * sizeof(float))
        .wait();
    g_lastLowPassScale = scale;
  }
  LaunchLowPassBlock(q, src.d_data, res.d_data, res.width, res.pitch,
                     res.height, g_d_LowPassKernel);
  return 0.0;
}

void PrepareLaplaceKernels(int numOctaves, float initBlur, float *kernel) {
  if (numOctaves > 1) {
    float totInitBlur =
        (float)std::sqrt(initBlur * initBlur + 0.5f * 0.5f) / 2.0f;
    PrepareLaplaceKernels(numOctaves - 1, totInitBlur, kernel);
  }
  float scale = powf(2.0f, -1.0f / NUM_SCALES);
  float diffScale = powf(2.0f, 1.0f / NUM_SCALES);
  for (int i = 0; i < NUM_SCALES + 3; i++) {
    float kernelSum = 0.0f;
    float var = scale * scale - initBlur * initBlur;
    for (int j = 0; j <= LAPLACE_R; j++) {
      kernel[numOctaves * 12 * 16 + 16 * i + j] =
          expf(-(float)j * j / 2.0f / var);
      kernelSum += (j == 0 ? 1.0f : 2.0f) *
                   kernel[numOctaves * 12 * 16 + 16 * i + j];
    }
    for (int j = 0; j <= LAPLACE_R; j++)
      kernel[numOctaves * 12 * 16 + 16 * i + j] /= kernelSum;
    scale *= diffScale;
  }
}

double LaplaceMulti(SyclImage &baseImage, SyclImage *results, int octave) {
  EnsureDeviceBuffers();
  auto &q = GetSyclQueue();
  int width = results[0].width;
  int pitch = results[0].pitch;
  int height = results[0].height;
  LaunchLaplaceMultiMem(q, baseImage.d_data, results[0].d_data, width, pitch,
                        height, octave, g_d_LaplaceKernel);
  return 0.0;
}

double FindPointsMulti(SyclImage *sources, SiftData &siftData, float thresh,
                       float edgeLimit, float factor, float lowestScale,
                       float subsampling, int octave) {
  EnsureDeviceBuffers();
  auto &q = GetSyclQueue();
  if (sources->d_data == nullptr) {
    printf("FindPointsMulti: missing data\n");
    return 0.0;
  }
  LaunchFindPointsMultiNew(q, sources->d_data, siftData.d_data, sources->width,
                            sources->pitch, sources->height, subsampling,
                            lowestScale, thresh, factor, edgeLimit, octave,
                            g_d_PointCounter, siftData.maxPts);
  return 0.0;
}
