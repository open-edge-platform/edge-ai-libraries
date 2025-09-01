// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_cam_out.cpp
 *
 * Maintainer: Yichong Tang <yichong.tang@intel.com>
 *
 */

#include <fb/private/include/fb_cam_out.hpp>

namespace RTmotion
{
MC_ERROR_CODE FbCamOut::onRisingEdgeExecution()
{
  axis_->setAxisState(mcContinuousMotion);
  velocity_     = axis_->toUserVel();
  acceleration_ = axis_->toUserAcc() < 10 ? 10 : axis_->toUserAcc();
  buffer_mode_  = mcAborting;
  axis_->addFBToQueue(this, mcSyncOutMode);
  return mcErrorCodeGood;
}

void FbCamOut::setSlave(AXIS_REF slave)
{
  axis_ = slave;
}
}  // namespace RTmotion