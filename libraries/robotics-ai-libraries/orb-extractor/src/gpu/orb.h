// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
#ifndef __ORB_H__
#define __ORB_H__

namespace gpu
{


    /*
typedef struct _point {
    int x;
    int y;
} Point;
*/


//fast kernel
typedef struct _ptGPUBuffer {
    Point pt;
} PtGPUBuffer;

//fast nms kernel
typedef struct _keyGPUBuffer {
    int x;
    int y;
    int response;
    float angle;
} KeypointGPUBuffer;

typedef struct _keyGPUBufferFloat {
    float x;
    float y;
    float response;
    float angle;
} KeypointGPUBufferFloat;


}

#endif // __ORB_H__
