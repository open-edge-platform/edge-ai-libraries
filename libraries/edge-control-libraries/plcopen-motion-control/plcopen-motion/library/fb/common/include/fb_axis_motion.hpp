// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_axis_motion.hpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#pragma once

#include <fb/common/include/fb_base.hpp>
#include <fb/common/include/fb_axis_node.hpp>

#include <chrono>

namespace RTmotion
{
typedef enum
{
  fbIdle             = 0,
  fbRisingEdge       = 1,
  fbExecution        = 2,
  fbFallingEdge      = 3,
  fbAfterFallingEdge = 4
} FUNCTION_BLOCK_STATE;

/**
 * @brief Function block base for single axis motion
 */
class FbAxisMotion : public FunctionBlock, public FbAxisNode
{
public:
  FbAxisMotion();
  ~FbAxisMotion() override = default;

  void runCycle() override;

  // Functions for addressing inputs
  virtual void setExecute(mcBOOL execute);
  virtual void setContinuousUpdate(mcBOOL continuous_update);
  virtual void setPosition(mcLREAL position);
  virtual void setVelocity(mcLREAL velocity);
  virtual void setTorque(mcLREAL torque);
  virtual void setMaxProfileVelocity(mcLREAL velocity);
  virtual void setAcceleration(mcLREAL acceleration);
  virtual void setDeceleration(mcLREAL deceleration);
  virtual void setJerk(mcLREAL jerk);
  virtual void setDuration(mcLREAL duration);
  virtual void setDirection(MC_DIRECTION direction);
  virtual void setBufferMode(MC_BUFFER_MODE mode);
  virtual void setTargetAcceleration(mcLREAL acc);
  virtual void setTargetVelocity(mcLREAL vel);
  virtual void setTargetPosition(mcLREAL pos);
  virtual void setStartAcceleration(mcLREAL acc);
  virtual void setStartVelocity(mcLREAL vel);
  virtual void setStartPosition(mcLREAL pos);
  virtual void setPlannerType(PLANNER_TYPE planner_type);

  mcBOOL isError() override;
  MC_ERROR_CODE getErrorID() override;

  mcLREAL getPosition() override;
  mcLREAL getVelocity() override;
  mcLREAL getTorque() override;
  mcLREAL getMaxProfileVel() override;
  mcLREAL getAcceleration() override;
  mcLREAL getDeceleration() override;
  mcLREAL getJerk() override;
  mcLREAL getDuration() override;
  MC_DIRECTION getDirection() override;
  MC_BUFFER_MODE getBufferMode() override;
  mcLREAL getTargetPosition() override;
  mcLREAL getTargetVelocity() override;
  mcLREAL getTargetAcceleration() override;
  mcLREAL getStartPosition() override;
  mcLREAL getStartVelocity() override;
  mcLREAL getStartAcceleration() override;

  PLANNER_TYPE getPlannerType() override;

  // Functions for execution
  MC_ERROR_CODE onRisingEdgeExecution() override;
  MC_ERROR_CODE onFallingEdgeExecution() override;
  MC_ERROR_CODE onExecution() override;
  MC_ERROR_CODE afterFallingEdgeExecution() override;
  void onError(MC_ERROR_CODE error_code) override;

protected:
  /// Inputs
  VAR_INPUT mcBOOL continuous_update_;
  VAR_INPUT mcLREAL position_;
  VAR_INPUT mcLREAL velocity_;
  VAR_INPUT mcLREAL torque_;
  VAR_INPUT mcLREAL max_profile_vel_;
  VAR_INPUT mcLREAL acceleration_;
  VAR_INPUT mcLREAL deceleration_;
  VAR_INPUT mcLREAL jerk_;
  VAR_INPUT mcLREAL duration_;
  VAR_INPUT MC_DIRECTION direction_;

  VAR_INPUT mcLREAL target_position_;
  VAR_INPUT mcLREAL target_velocity_;
  VAR_INPUT mcLREAL target_acceleration_;
  VAR_INPUT mcLREAL start_position_;
  VAR_INPUT mcLREAL start_velocity_;
  VAR_INPUT mcLREAL start_acceleration_;

  /// Flags to control the process
  FUNCTION_BLOCK_STATE state_;
  PLANNER_TYPE planner_type_;
};
}  // namespace RTmotion
