// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_read_actual_acceleration.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <fb/public/include/fb_read_actual_acceleration.hpp>

namespace RTmotion
{
mcLREAL FbReadActualAcceleration::getAxisValue()
{
  return axis_->toUserAcc();
}
}  // namespace RTmotion
