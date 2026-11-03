// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-FileCopyrightText: Copyright (c) 2017 Mårten Björkman
// SPDX-License-Identifier: Apache-2.0 AND MIT
//********************************************************//
// Intel SYCL/DPC++ SIFT extractor                       //
// Device-side constants           //
// SYCL reference backend (mechanics baseline).
//********************************************************//

#ifndef SYCLSIFTD_H
#define SYCLSIFTD_H

#define NUM_SCALES      5

// Scale down thread block width
#define SCALEDOWN_W    64

// Scale down thread block height
#define SCALEDOWN_H    16

// Scale up thread block width
#define SCALEUP_W      64

// Scale up thread block height
#define SCALEUP_H       8

// Find point thread block width
#define MINMAX_W       30

// Find point thread block height
#define MINMAX_H        8

// Laplace thread block width
#define LAPLACE_W     128

// Laplace rows per thread
#define LAPLACE_H       4

// Number of laplace scales
#define LAPLACE_S   (NUM_SCALES + 3)

// Laplace filter kernel radius
#define LAPLACE_R       4

#define LOWPASS_W      24
#define LOWPASS_H      32
#define LOWPASS_R       4

// d_PointCounter layout: [2*octave] = current count, [2*octave+1] = total
// d_MaxNumPoints: cap on number of keypoints
#define MAX_OCTAVES     8
#define POINT_COUNTER_SIZE  (MAX_OCTAVES * 2 + 1)

#endif // SYCLSIFTD_H
