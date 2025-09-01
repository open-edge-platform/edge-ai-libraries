// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_set_controller_mode.cpp
 *
 * Maintainer: He Kanghua <kanghua.he@intel.com>
 *
 */

#include <fb/private/include/fb_set_controller_mode.hpp>

namespace RTmotion
{
FbSetControllerMode::FbSetControllerMode()
  : cycle_counter_(0)
  , cycle_counter_timeout_(1000)
  , cur_mode_(mcServoControlModePosition)
  , mode_(mcServoControlModePosition)
{
}

void FbSetControllerMode::setMode(MC_SERVO_CONTROL_MODE mode)
{
  done_          = mcFALSE;
  mode_          = mode;
  cycle_counter_ = cycle_counter_timeout_;
}

MC_ERROR_CODE FbSetControllerMode::onExecution()
{
  cur_mode_ = (MC_SERVO_CONTROL_MODE)axis_->getControllerMode();
  /* check timeout */
  if (cycle_counter_)
  {
    cycle_counter_--;
    if (cycle_counter_ == 0)
    {
      error_id_ = mcErrorCodeSetControllerModeTimeout;
      error_    = mcTRUE;
      done_     = mcFALSE;
    }
    else
    {
      error_id_ = axis_->setControllerMode(mode_);
      if (error_id_ == mcErrorCodeSetControllerModeSuccess)
      {
        error_id_      = mcErrorCodeGood;
        error_         = mcFALSE;
        done_          = mcTRUE;
        cycle_counter_ = 0;
      }
      else if (error_id_ == mcErrorCodeGood)
      {
        error_ = mcFALSE;
        done_  = mcFALSE;
      }
      else
      {
        error_         = mcTRUE;
        done_          = mcFALSE;
        cycle_counter_ = 0;
      }
    }
  }
  return error_id_;
}

}  // namespace RTmotion
