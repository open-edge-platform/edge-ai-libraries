// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_axis_node.hpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#pragma once

#include <fb/common/include/global.hpp>

namespace RTmotion
{
/**
 * @brief Function block base for single axis motion
 */
class FbAxisNode
{
public:
  FbAxisNode();
  virtual ~FbAxisNode() = default;

  // Functions for addressing outputs
  virtual void syncStatus(mcBOOL done, mcBOOL busy, mcBOOL active,
                          mcBOOL cmd_aborted, mcBOOL error,
                          MC_ERROR_CODE error_id);

  mcBOOL isEnabled();
  mcBOOL isDone();
  mcBOOL isBusy();
  mcBOOL isActive();
  mcBOOL isAborted();
  virtual mcBOOL isError();
  virtual MC_ERROR_CODE getErrorID();

  virtual mcLREAL getPosition()           = 0;
  virtual mcLREAL getVelocity()           = 0;
  virtual mcLREAL getTorque()             = 0;
  virtual mcLREAL getMaxProfileVel()      = 0;
  virtual mcLREAL getAcceleration()       = 0;
  virtual mcLREAL getDeceleration()       = 0;
  virtual mcLREAL getJerk()               = 0;
  virtual mcLREAL getDuration()           = 0;
  virtual MC_DIRECTION getDirection()     = 0;
  virtual MC_BUFFER_MODE getBufferMode()  = 0;
  virtual mcLREAL getTargetPosition()     = 0;
  virtual mcLREAL getTargetVelocity()     = 0;
  virtual mcLREAL getTargetAcceleration() = 0;
  virtual mcLREAL getStartPosition()      = 0;
  virtual mcLREAL getStartVelocity()      = 0;
  virtual mcLREAL getStartAcceleration()  = 0;
  virtual PLANNER_TYPE getPlannerType()   = 0;

protected:
  VAR_INPUT mcBOOL execute_;

  /// Outputs
  VAR_OUTPUT mcBOOL done_;
  VAR_OUTPUT mcBOOL busy_;
  VAR_OUTPUT mcBOOL active_;
  VAR_OUTPUT mcBOOL command_aborted_;
  VAR_OUTPUT mcBOOL error_;
  VAR_OUTPUT MC_ERROR_CODE error_id_;
  VAR_OUTPUT MC_BUFFER_MODE buffer_mode_;

  mcBOOL output_flag_;  /// Hold the output for another cycle
};
}  // namespace RTmotion
