// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_torque_control.cpp
 *
 * Maintainer: He Kanghua <kanghua.he@intel.com>
 *
 */

#include <fb/private/include/fb_torque_control.hpp>

namespace RTmotion
{
FbTorqueControl::FbTorqueControl()
  : torque_(0), torque_ramp_(0), in_torque_(mcFALSE), toq_done_factor_(0.1)
{
}

MC_ERROR_CODE FbTorqueControl::onRisingEdgeExecution()
{
  return axis_->setAxisState(mcContinuousMotion);
}

MC_ERROR_CODE FbTorqueControl::onFallingEdgeExecution()
{
  busy_ = mcFALSE;
  return axis_->getAxisError();
}

MC_ERROR_CODE FbTorqueControl::onExecution()
{
  mcLREAL act_torque = axis_->toUserTorque();

  // set torque related PDO objects
  axis_->setTorqueCmd(torque_);
  axis_->setMaxProfileVelCmd(velocity_);

  // check done
  in_torque_ = mcFALSE;
  if (torque_)
  {
    if ((abs(act_torque - torque_) / abs(torque_)) <= toq_done_factor_)
      in_torque_ = mcTRUE;
  }
  done_ = in_torque_;
  return mcErrorCodeGood;
}

void FbTorqueControl::setTorque(mcLREAL torque)
{
  torque_ = torque;
}

void FbTorqueControl::setMaxProfileVelocity(mcLREAL velocity)
{
  velocity_ = velocity;
}

void FbTorqueControl::setTorqueDoneFactor(mcLREAL factor)
{
  toq_done_factor_ = factor;
}
}  // namespace RTmotion
