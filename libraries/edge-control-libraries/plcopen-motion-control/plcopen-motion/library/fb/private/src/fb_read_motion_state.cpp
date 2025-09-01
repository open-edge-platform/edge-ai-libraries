// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_read_motion_state.cpp
 *
 * Maintainer: Wu Xian <xian.wu@intel.com>
 *
 */

#include <fb/private/include/fb_read_motion_state.hpp>

namespace RTmotion
{
FbReadMotionState::FbReadMotionState()
  : source_(mcNullValue)
  , cons_vel_threshold_(0.1)
  , constant_velocity_(mcTRUE)
  , accelerating_(mcFALSE)
  , decelerating_(mcFALSE)
  , direction_positive_(mcFALSE)
  , direction_negative_(mcFALSE)
{
}

void FbReadMotionState::setSource(MC_SOURCE source)
{
  source_ = source;
}

void FbReadMotionState::setConstantVelocityThreshold(mcREAL threshold)
{
  cons_vel_threshold_ = threshold;
}

mcBOOL FbReadMotionState::getConstantVelocity()
{
  return constant_velocity_;
}

mcBOOL FbReadMotionState::getAccelerating()
{
  return accelerating_;
}

mcBOOL FbReadMotionState::getDecelerating()
{
  return decelerating_;
}

mcBOOL FbReadMotionState::getDirectionPositive()
{
  return direction_positive_;
}

mcBOOL FbReadMotionState::getDirectionNegative()
{
  return direction_negative_;
}

MC_ERROR_CODE FbReadMotionState::onRisingEdgeExecution()
{
  // check axis state
  if (!axis_)
    return mcErrorCodeSetAxisError;
  // check set source
  if (source_ != mcSetValue && source_ != mcActualValue &&
      source_ != mcCommandedValue)
    return mcErrorCodeSetSourceError;

  return mcErrorCodeGood;
}

MC_ERROR_CODE FbReadMotionState::onExecution()
{
  if (!axis_)
    return mcErrorCodeSetAxisError;

  // get set value from fbs or execution node is not supported yet
  if (source_ == mcSetValue)
  {
    DEBUG_PRINT("Error: not supported by the current version");
    return mcErrorCodeSetSourceError;
  }

  if (source_ == mcActualValue)
  {
    // default acc threshold is 0.1
    constant_velocity_ =
        abs(axis_->toUserAcc()) < cons_vel_threshold_ ? mcTRUE : mcFALSE;
    accelerating_       = axis_->toUserAcc() > 0 ? mcTRUE : mcFALSE;
    decelerating_       = axis_->toUserAcc() < 0 ? mcTRUE : mcFALSE;
    direction_positive_ = axis_->toUserVel() > 0 ? mcTRUE : mcFALSE;
    direction_negative_ = axis_->toUserVel() < 0 ? mcTRUE : mcFALSE;
  }
  else if (source_ == mcCommandedValue)
  {
    // default acc threshold is 0.1
    constant_velocity_ =
        abs(axis_->toUserAccCmd()) < cons_vel_threshold_ ? mcTRUE : mcFALSE;
    accelerating_       = axis_->toUserAccCmd() > 0 ? mcTRUE : mcFALSE;
    decelerating_       = axis_->toUserAccCmd() < 0 ? mcTRUE : mcFALSE;
    direction_positive_ = axis_->toUserVelCmd() > 0 ? mcTRUE : mcFALSE;
    direction_negative_ = axis_->toUserVelCmd() < 0 ? mcTRUE : mcFALSE;
  }
  else
    return mcErrorCodeSetSourceError;

  return mcErrorCodeGood;
}

}  // namespace RTmotion