// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_read_command_acceleration.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <fb/public/include/fb_read_command_acceleration.hpp>

namespace RTmotion
{
mcLREAL FbReadCommandAcceleration::getAxisValue()
{
  return axis_->toUserAccCmd();
}

}  // namespace RTmotion
