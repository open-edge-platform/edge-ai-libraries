// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_move_velocity.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <fb/public/include/fb_move_velocity.hpp>

namespace RTmotion
{
FbMoveVelocity::FbMoveVelocity()
{
  in_velocity_ = mcFALSE;
}

MC_ERROR_CODE FbMoveVelocity::onRisingEdgeExecution()
{
  if (velocity_ == 0 || acceleration_ == 0 || deceleration_ == 0 || jerk_ == 0)
    return mcErrorCodeMotionLimitUnset;
  axis_->addFBToQueue(this, mcMoveVelocityMode);
  return mcErrorCodeGood;
}

}  // namespace RTmotion
