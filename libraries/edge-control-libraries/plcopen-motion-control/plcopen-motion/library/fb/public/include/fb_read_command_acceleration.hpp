// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_read_command_acceleration.hpp
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
class FbReadCommandAcceleration : public FbAxisRead
{
public:
  FbReadCommandAcceleration()           = default;
  ~FbReadCommandAcceleration() override = default;

  mcLREAL getAxisValue() override;
};
}  // namespace RTmotion