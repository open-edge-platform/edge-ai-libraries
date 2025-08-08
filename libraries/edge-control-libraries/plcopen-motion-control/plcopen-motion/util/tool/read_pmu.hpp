// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
/*******************************************************************************
Copyright 2020-2020 Intel Corporation.
This software and the related documents are Intel copyrighted materials, and
your use of them is governed by the express license under which they were
provided to you (License). Unless the License provides otherwise, you may not
use, modify, copy, publish, distribute, disclose or transmit this software or
the related documents without Intel's prior written permission. This software
and the related documents are provided as is, with no express or implied
warranties, other than those that are expressly stated in the License.

*******************************************************************************/

#include <stdio.h>
#include <stdint.h>
#include <inttypes.h>

/**
 * Get the PMU counter at index \a index
 * @param[in] index The PMU counter index to read
 * @return The value of the PMU counter at \a index
 */
__attribute__((always_inline)) inline uint64_t __rdpmc(uint32_t counter)
{
  volatile uint32_t high, low;
  asm volatile("rdpmc\n\t" : "=a"(low), "=d"(high) : "c"(counter));
  return (((uint64_t)high << 32) | low);
}