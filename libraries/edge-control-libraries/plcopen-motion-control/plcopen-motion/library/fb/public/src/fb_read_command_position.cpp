// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_read_command_position.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <fb/public/include/fb_read_command_position.hpp>

namespace RTmotion
{
mcLREAL FbReadCommandPosition::getAxisValue()
{
  return axis_->toUserPosCmd();
}

}  // namespace RTmotion
