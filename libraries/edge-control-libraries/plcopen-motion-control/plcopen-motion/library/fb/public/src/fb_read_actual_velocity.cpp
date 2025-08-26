// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_read_actual_velocity.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <fb/public/include/fb_read_actual_velocity.hpp>

namespace RTmotion
{
mcLREAL FbReadActualVelocity::getAxisValue()
{
  return axis_->toUserVel();
}

}  // namespace RTmotion
