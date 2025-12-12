/*
 * Copyright (C) 2025 Intel Corporation
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#ifndef __ORB_H__
#define __ORB_H__

#include "device_array.h"
#include "device_impl.h"

namespace gpu
{

typedef struct _point
{
  int x;
  int y;
} Point;

// fast kernel
typedef struct _ptGPUBuffer
{
  Point pt;
} PtGPUBuffer;

// fast nms kernel
typedef struct _keyGPUBuffer
{
  int x;
  int y;
  int response;
  float angle;
} KeypointGPUBuffer;

typedef struct _keyGPUBufferFloat
{
  float x;
  float y;
  float response;
  float angle;
} KeypointGPUBufferFloat;

typedef struct _partKey
{
  Point pt;
  int response;
  float angle;
} PartKey;

enum InterpolationType
{
  kInterpolationLinear,
  kInterpolationNearest,
  kInterpolationCubic,
  kInterpolationArea
};

enum BorderTypes
{
  BORDER_CONSTANT = 0,
  BORDER_REPLICATE = 1,
  BORDER_REFLECT = 2,
  BORDER_WRAP = 3,
  BORDER_REFLECT_101 = 4,
  BORDER_TRANSPARENT = 5,
};

}  // namespace gpu

#endif  // __ORB_H__
