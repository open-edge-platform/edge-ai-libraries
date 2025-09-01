// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_stop.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <fb/public/include/fb_stop.hpp>

namespace RTmotion
{
FbStop::FbStop()
{
  buffer_mode_ = mcAborting;
}

MC_ERROR_CODE FbStop::onRisingEdgeExecution()
{
  if (acceleration_ == 0)
    return mcErrorCodeMotionLimitUnset;
  axis_->addFBToQueue(this, mcStopMode);
  return mcErrorCodeGood;
}

MC_ERROR_CODE FbStop::onFallingEdgeExecution()
{
  if (done_ == mcTRUE)
    return axis_->setAxisState(mcStandstill);

  return mcErrorCodeGood;
}

void FbStop::setDeceleration(mcLREAL deceleration)
{
  acceleration_ = deceleration;
}

}  // namespace RTmotion