// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-FileCopyrightText: Copyright (c) 2017 Mårten Björkman
// SPDX-License-Identifier: Apache-2.0 AND MIT
//********************************************************//
// Intel SYCL/DPC++ SIFT extractor                       //
// Public API header                //
// SYCL reference backend (mechanics baseline).
//********************************************************//

#ifndef SYCLSIFT_H
#define SYCLSIFT_H

#include "syclImage.h"

// SiftPoint and SiftData layout retained for reference-backend interoperability
typedef struct {
  float xpos;
  float ypos;
  float scale;
  float sharpness;
  float edgeness;
  float orientation;
  float score;
  float ambiguity;
  int match;
  float match_xpos;
  float match_ypos;
  float match_error;
  float subsampling;
  float empty[3];
  float data[128];
} SiftPoint;

typedef struct {
  int numPts;  // Number of detected SIFT points
  int maxPts;  // Maximum allocated SIFT points
  SiftPoint *h_data;  // Host (CPU) data
  SiftPoint *d_data;  // Device (GPU) USM data
} SiftData;

// ---- Public API -------------------------------------------------------
void InitSycl(int devNum = 0);

float *AllocSiftTempMemory(int width, int height, int numOctaves,
                           bool scaleUp = false);
void FreeSiftTempMemory(float *memoryTmp);

void ExtractSift(SiftData &siftData, SyclImage &img, int numOctaves,
                 double initBlur, float thresh, float lowestScale = 0.0f,
                 bool scaleUp = false, float *tempMemory = nullptr);

void InitSiftData(SiftData &data, int num = 1024, bool host = false,
                  bool dev = true);
void FreeSiftData(SiftData &data);
void PrintSiftData(SiftData &data);

double MatchSiftData(SiftData &data1, SiftData &data2);
// FindHomography is intentionally not advertised until a linked
// implementation ships with this component.

#endif // SYCLSIFT_H
