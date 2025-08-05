// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_axis_motion.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <fb/common/include/fb_axis_motion.hpp>

namespace RTmotion
{
FbAxisMotion::FbAxisMotion()
  : continuous_update_(mcFALSE)
  , position_(0)
  , velocity_(0)
  , torque_(0)
  , max_profile_vel_(0)
  , acceleration_(0)
  , deceleration_(0)
  , jerk_(5000)
  , duration_(1000000.0)
  , direction_(mcCurrentDirection)
  , target_position_(0.0)
  , target_velocity_(0.0)
  , target_acceleration_(0.0)
  , start_position_(0.0)
  , start_velocity_(0.0)
  , start_acceleration_(0.0)
  , state_(fbIdle)
  , planner_type_(mcOffLine)
{
}

void FbAxisMotion::runCycle()
{
  if ((state_ == fbIdle || state_ == fbAfterFallingEdge) &&
      execute_ == mcTRUE)  // `Execute` rising edge
  {
    MC_ERROR_CODE err = onRisingEdgeExecution();
    if (err)
      onError(err);
    else
    {
      active_ = done_ = error_ = command_aborted_ = mcFALSE;
      busy_                                       = mcTRUE;
    }
    state_ = fbExecution;
    DEBUG_PRINT("FbAxisMotion::runCycle %s\n", "rising edge");
  }
  else if (state_ == fbExecution &&
           execute_ == mcTRUE)  // `Execute` hold high value
  {
    MC_ERROR_CODE err = onExecution();
    if (err)
      onError(err);
    DEBUG_PRINT("FbAxisMotion::runCycle %s\n", "hold high value");
  }
  else if (state_ == fbExecution &&
           execute_ == mcFALSE)  // `Execute` falling edge
  {
    MC_ERROR_CODE err = onFallingEdgeExecution();
    if (err)
      onError(err);
    else
    {
      if ((done_ == mcTRUE || command_aborted_ == mcTRUE || error_ == mcTRUE) &&
          busy_ == mcFALSE)
      {
        done_ = command_aborted_ = error_ = busy_ = active_ = mcFALSE;
        error_id_                                           = mcErrorCodeGood;
      }
    }

    output_flag_ = mcFALSE;
    state_       = fbAfterFallingEdge;
    DEBUG_PRINT("FbAxisMotion::runCycle %s\n", "falling edge");
  }
  else if (state_ == fbAfterFallingEdge)  // `enable` after falling edge
  {
    MC_ERROR_CODE err = afterFallingEdgeExecution();
    if (err)
      onError(err);
    else
    {
      if (busy_ == mcFALSE && output_flag_ == mcFALSE)
      {
        active_ = done_ = command_aborted_ = error_ = mcFALSE;
        error_id_                                   = mcErrorCodeGood;
      }
      output_flag_ = mcFALSE;
      DEBUG_PRINT("FbAxisMotion::runCycle %s\n", "after falling edge");
    }
  }  // `Execute` hold low value
}

MC_ERROR_CODE FbAxisMotion::onRisingEdgeExecution()
{
  return mcErrorCodeGood;
}

MC_ERROR_CODE FbAxisMotion::onFallingEdgeExecution()
{
  return mcErrorCodeGood;
}

MC_ERROR_CODE FbAxisMotion::onExecution()
{
  return mcErrorCodeGood;
}

MC_ERROR_CODE FbAxisMotion::afterFallingEdgeExecution()
{
  return mcErrorCodeGood;
}

void FbAxisMotion::onError(MC_ERROR_CODE error_code)
{
  busy_     = mcFALSE;
  error_    = mcTRUE;
  error_id_ = error_code;
}

void FbAxisMotion::setExecute(mcBOOL execute)
{
  execute_ = execute;
}

void FbAxisMotion::setContinuousUpdate(mcBOOL continuous_update)
{
  continuous_update_ = continuous_update;
}

void FbAxisMotion::setPosition(mcLREAL position)
{
  position_ = position;
}

void FbAxisMotion::setVelocity(mcLREAL velocity)
{
  if (velocity == 0)
  {
    error_    = mcTRUE;
    error_id_ = mcErrorCodeVelocitySetValueError;
  }
  else
    velocity_ = velocity;
}

void FbAxisMotion::setTorque(mcLREAL torque)
{
  torque_ = torque;
}

void FbAxisMotion::setMaxProfileVelocity(mcLREAL velocity)
{
  max_profile_vel_ = velocity;
}

void FbAxisMotion::setAcceleration(mcLREAL acceleration)
{
  if (acceleration == 0)
  {
    error_    = mcTRUE;
    error_id_ = mcErrorCodeAccelerationSetValueError;
  }
  else
    acceleration_ = acceleration;
}

void FbAxisMotion::setDeceleration(mcLREAL deceleration)
{
  if (deceleration == 0)
  {
    error_    = mcTRUE;
    error_id_ = mcErrorCodeDecelerationSetValueError;
  }
  else
    deceleration_ = deceleration;
}

void FbAxisMotion::setJerk(mcLREAL jerk)
{
  if (jerk == 0)
  {
    error_    = mcTRUE;
    error_id_ = mcErrorCodeJerkSetValueError;
  }
  else
    jerk_ = jerk;
}

void FbAxisMotion::setDuration(mcLREAL duration)
{
  if (duration == 0)
  {
    error_    = mcTRUE;
    error_id_ = mcErrorCodeDurationSetValueError;
  }
  else
    duration_ = duration;
}

void FbAxisMotion::setDirection(MC_DIRECTION direction)
{
  direction_ = direction;
}

void FbAxisMotion::setBufferMode(MC_BUFFER_MODE mode)
{
  buffer_mode_ = mode;
}

void FbAxisMotion::setTargetAcceleration(mcLREAL acc)
{
  target_acceleration_ = acc;
}

void FbAxisMotion::setTargetVelocity(mcLREAL vel)
{
  target_velocity_ = vel;
}

void FbAxisMotion::setTargetPosition(mcLREAL pos)
{
  target_position_ = pos;
}

void FbAxisMotion::setStartAcceleration(mcLREAL acc)
{
  start_acceleration_ = acc;
}

void FbAxisMotion::setStartVelocity(mcLREAL vel)
{
  start_velocity_ = vel;
}

void FbAxisMotion::setStartPosition(mcLREAL pos)
{
  start_position_ = pos;
}

void FbAxisMotion::setPlannerType(PLANNER_TYPE planner_type)
{
  planner_type_ = planner_type;
}

mcBOOL FbAxisMotion::isError()
{
  return axis_->getAxisError() ? (mcBOOL)axis_->getAxisError() : error_;
}

MC_ERROR_CODE FbAxisMotion::getErrorID()
{
  return axis_->getAxisError() ? axis_->getAxisError() : error_id_;
}

mcLREAL FbAxisMotion::getPosition()
{
  return position_;
}

mcLREAL FbAxisMotion::getVelocity()
{
  return velocity_;
}

mcLREAL FbAxisMotion::getTorque()
{
  return torque_;
}

mcLREAL FbAxisMotion::getMaxProfileVel()
{
  return max_profile_vel_;
}

mcLREAL FbAxisMotion::getAcceleration()
{
  return acceleration_;
}

mcLREAL FbAxisMotion::getDeceleration()
{
  return deceleration_;
}

mcLREAL FbAxisMotion::getJerk()
{
  return jerk_;
}

mcLREAL FbAxisMotion::getDuration()
{
  return duration_;
}

MC_DIRECTION FbAxisMotion::getDirection()
{
  return direction_;
}

MC_BUFFER_MODE FbAxisMotion::getBufferMode()
{
  return buffer_mode_;
}

mcLREAL FbAxisMotion::getTargetPosition()
{
  return target_position_;
}

mcLREAL FbAxisMotion::getTargetVelocity()
{
  return target_velocity_;
}

mcLREAL FbAxisMotion::getTargetAcceleration()
{
  return target_acceleration_;
}

mcLREAL FbAxisMotion::getStartPosition()
{
  return start_position_;
}

mcLREAL FbAxisMotion::getStartVelocity()
{
  return start_velocity_;
}

mcLREAL FbAxisMotion::getStartAcceleration()
{
  return start_acceleration_;
}

PLANNER_TYPE FbAxisMotion::getPlannerType()
{
  return planner_type_;
}

}  // namespace RTmotion
