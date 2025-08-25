// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_gear_out.cpp
 *
 * Maintainer: Wu Xian <wu.xian@intel.com>
 *
 */

#include <fb/private/include/fb_gear_out.hpp>

namespace RTmotion
{
void FbGearOut::setSlave(AXIS_REF slave)
{
  axis_ = slave;
}

MC_ERROR_CODE FbGearOut::onRisingEdgeExecution()
{
  // change slave axis state from mcSynchronizedMotion
  axis_->setAxisState(mcContinuousMotion);
  // set slave velocity to current velocity
  velocity_     = axis_->toUserVel();
  acceleration_ = axis_->toUserAcc();
  buffer_mode_  = mcAborting;
  // mcMoveVelocityMode will check whether the actual slave speed reaches set
  // value
  axis_->addFBToQueue(this, mcSyncOutMode);
  busy_ = mcTRUE;

  return mcErrorCodeGood;
}

MC_ERROR_CODE FbGearOut::onExecution()
{
  if (axis_->getAxisState() == mcContinuousMotion)
  {
    done_ = mcTRUE;
    busy_ = mcFALSE;
  }

  return mcErrorCodeGood;
}

}  // namespace RTmotion