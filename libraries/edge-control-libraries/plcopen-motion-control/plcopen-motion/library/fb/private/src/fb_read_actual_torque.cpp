// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_read_actual_torque.cpp
 *
 * Maintainer: He Kanghua <kanghua.he@intel.com>
 *
 */

#include <fb/private/include/fb_read_actual_torque.hpp>

namespace RTmotion
{
mcLREAL FbReadActualTorque::getAxisValue()
{
  return axis_->toUserTorque();
}

}  // namespace RTmotion
