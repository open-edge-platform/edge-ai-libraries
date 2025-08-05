// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_move_absolute.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <fb/public/include/fb_move_absolute.hpp>

namespace RTmotion
{
FbMoveAbsolute::FbMoveAbsolute()
{
}

MC_ERROR_CODE FbMoveAbsolute::onRisingEdgeExecution()
{
  if (velocity_ == 0 || acceleration_ == 0 || deceleration_ == 0 || jerk_ == 0)
    return mcErrorCodeMotionLimitUnset;
  if (axis_->getHomeState() == mcTRUE)
  {
    axis_->addFBToQueue(this, mcMoveAbsoluteMode);
    return mcErrorCodeGood;
  }
  else
    return mcErrorCodeHomeStateError;
}

}  // namespace RTmotion
