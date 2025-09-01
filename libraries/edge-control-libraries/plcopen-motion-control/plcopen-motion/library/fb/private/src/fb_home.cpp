// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_home.cpp
 *
 * Maintainer: He Kanghua <kanghua.he@intel.com>
 *
 */

#include <fb/private/include/fb_home.hpp>

namespace RTmotion
{
FbHome::FbHome()
{
}

MC_ERROR_CODE FbHome::onRisingEdgeExecution()
{
  if (axis_->getControllerMode() == mcServoControlModeHomeServo)
  {
    axis_->setHomeEnableCmd(mcTRUE);
    axis_->setAxisState(mcHoming);
    return mcErrorCodeGood;
  }
  else
    return mcErrorCodeHomeServoModeError;
}

MC_ERROR_CODE FbHome::onFallingEdgeExecution()
{
  axis_->setHomeEnableCmd(mcFALSE);
  return mcErrorCodeGood;
}

MC_ERROR_CODE FbHome::onExecution()
{
  if (axis_->getHomeState() == mcTRUE)
  {
    done_ = mcTRUE;
    busy_ = mcFALSE;
    this->setTargetVelocity(0);
    axis_->setHomePositionOffset();
    axis_->setAxisState(mcStandstill);
  }
  return axis_->getAxisError();
}

}  // namespace RTmotion
