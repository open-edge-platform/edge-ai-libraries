// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file logging.hpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#pragma once

namespace RTmotion
{
#ifdef DEBUG
#define DEBUG_TEST 1
#else
#define DEBUG_TEST 0
#endif

// clang-format off
#define DEBUG_PRINT(fmt, ...) \
            do { if (DEBUG_TEST) fprintf(stderr, "%s:%d:%s(): \n" fmt, __FILE__, __LINE__, __func__, ##__VA_ARGS__); } while (0)

#define INFO_PRINT(fmt, ...) \
            do { fprintf(stderr, fmt, ##__VA_ARGS__); } while (0)
// clang-format on

}  // namespace RTmotion