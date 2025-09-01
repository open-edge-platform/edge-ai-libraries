// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_read_actual_acceleration.hpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#pragma once

#include <fb/common/include/fb_axis_read.hpp>

namespace RTmotion
{
/**
 * @brief Function block base for single axis motion
 */
class FbReadActualAcceleration : public FbAxisRead
{
public:
  FbReadActualAcceleration()           = default;
  ~FbReadActualAcceleration() override = default;

  mcLREAL getAxisValue() override;
};
}  // namespace RTmotion