// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_move_relative.hpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#pragma once

#include <fb/common/include/global.hpp>
#include <fb/common/include/fb_axis_motion.hpp>

#include <chrono>

namespace RTmotion
{
/**
 * @brief Function block MC_MoveVelocity
 */
class FbMoveVelocity : public FbAxisMotion
{
public:
  FbMoveVelocity();
  ~FbMoveVelocity() override = default;

  mcBOOL isInVelocity()
  {
    return in_velocity_;
  }

  MC_ERROR_CODE onRisingEdgeExecution() override;

private:
  VAR_OUTPUT mcBOOL& in_velocity_ = done_;
};
}  // namespace RTmotion