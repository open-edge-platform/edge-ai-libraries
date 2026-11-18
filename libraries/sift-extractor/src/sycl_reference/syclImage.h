// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-FileCopyrightText: Copyright (c) 2017 Mårten Björkman
// SPDX-License-Identifier: Apache-2.0 AND MIT
//********************************************************//
// Intel SYCL/DPC++ SIFT extractor                       //
// SyclImage: GPU image class using SYCL USM memory      //
// SYCL reference backend (mechanics baseline).
//********************************************************//

#ifndef SYCLIMAGE_H
#define SYCLIMAGE_H

#include "syclutils.h"

class SyclImage {
public:
  int width, height;
  int pitch;       // Allocated row width in floats (>= width, aligned to 128)
  float *h_data;   // Host data (CPU)
  float *d_data;   // Device data (USM device allocation)

  bool d_internalAlloc;
  bool h_internalAlloc;

  SyclImage();
  ~SyclImage();

  SyclImage(const SyclImage &) = delete;
  SyclImage &operator=(const SyclImage &) = delete;
  SyclImage(SyclImage &&other) noexcept;
  SyclImage &operator=(SyclImage &&other) noexcept;

  void Allocate(int width, int height, int pitch, bool withHost,
                float *devMem = nullptr, float *hostMem = nullptr);
  double Download();   // Copy h_data -> d_data
  double Readback();   // Copy d_data -> h_data
};

// Integer utility functions
int iDivUp(int a, int b);
int iDivDown(int a, int b);
int iAlignUp(int a, int b);
int iAlignDown(int a, int b);

#endif // SYCLIMAGE_H
