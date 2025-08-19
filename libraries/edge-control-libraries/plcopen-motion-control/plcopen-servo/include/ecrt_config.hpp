// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

#pragma once

#include <ecrt.h>
#include <stdio.h>
#ifndef NSEC_PER_SEC
#define NSEC_PER_SEC (1000000000L)
#endif

#ifndef TIMESPEC2NS
#define TIMESPEC2NS(T) ((uint64_t)(T).tv_sec * NSEC_PER_SEC + (T).tv_nsec)
#endif

#ifndef DIFF_NS
#define DIFF_NS(A, B)                                                          \
  (((B).tv_sec - (A).tv_sec) * NSEC_PER_SEC + ((B).tv_nsec) - (A).tv_nsec)
#endif

#ifndef CYCLE_COUNTER_PERSEC
#define CYCLE_COUNTER_PERSEC(X) (NSEC_PER_SEC / 1000 / X)
#endif

#define PER_CIRCLE_ENCODER 0x10000
