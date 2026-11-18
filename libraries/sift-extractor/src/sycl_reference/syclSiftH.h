// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-FileCopyrightText: Copyright (c) 2017 Mårten Björkman
// SPDX-License-Identifier: Apache-2.0 AND MIT
//********************************************************//
// Intel SYCL/DPC++ SIFT extractor                       //
// Internal host-side API          //
// SYCL reference backend (mechanics baseline).
//********************************************************//

#ifndef SYCLSIFTH_H
#define SYCLSIFTH_H

#include "syclutils.h"
#include "syclImage.h"
#include "syclSift.h"

// ---- Internal host API -----------------------------------------------
int ExtractSiftLoop(SiftData &siftData, SyclImage &img, int numOctaves,
                    double initBlur, float thresh, float lowestScale,
                    float subsampling, float *memoryTmp, float *memorySub);

void ExtractSiftOctave(SiftData &siftData, SyclImage &img, int octave,
                       float thresh, float lowestScale, float subsampling,
                       float *memoryTmp);

double ScaleDown(SyclImage &res, SyclImage &src, float variance);
double ScaleUp(SyclImage &res, SyclImage &src);
double ComputeOrientations(SyclImage &src, SiftData &siftData, int octave);
double ExtractSiftDescriptors(SyclImage &src, SiftData &siftData,
                               float subsampling, int octave);
double RescalePositions(SiftData &siftData, float scale);
double LowPass(SyclImage &res, SyclImage &src, float scale);
void PrepareLaplaceKernels(int numOctaves, float initBlur, float *kernel);
double LaplaceMulti(SyclImage &baseImage, SyclImage *results, int octave);
double FindPointsMulti(SyclImage *sources, SiftData &siftData, float thresh,
                       float edgeLimit, float factor, float lowestScale,
                       float subsampling, int octave);

#endif // SYCLSIFTH_H
