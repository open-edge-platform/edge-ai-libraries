// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_move_additive.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <fb/public/include/fb_move_additive.hpp>

namespace RTmotion
{
FbMoveAdditive::FbMoveAdditive()
{
  distance_ = 0.0;
}

MC_ERROR_CODE FbMoveAdditive::onRisingEdgeExecution()
{
  if (velocity_ == 0 || acceleration_ == 0 || deceleration_ == 0 || jerk_ == 0)
    return mcErrorCodeMotionLimitUnset;
  axis_->addFBToQueue(this, mcMoveAdditiveMode);
  return mcErrorCodeGood;
}

}  // namespace RTmotion
