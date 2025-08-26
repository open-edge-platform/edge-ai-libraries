// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_read_command_velocity.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <fb/public/include/fb_read_command_velocity.hpp>

namespace RTmotion
{
mcLREAL FbReadCommandVelocity::getAxisValue()
{
  return axis_->toUserVelCmd();
}

}  // namespace RTmotion
