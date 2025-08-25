// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_set_controller_mode.hpp
 *
 * Maintainer: He Kanghua <kanghua.he@intel.com>
 *
 */

#pragma once

#include <fb/common/include/global.hpp>
#include <fb/common/include/fb_axis_admin.hpp>

namespace RTmotion
{
/**
 * @brief MC_SetControllerMode
 */

class FbSetControllerMode : public FbAxisAdmin
{
public:
  FbSetControllerMode();
  ~FbSetControllerMode() override = default;

  // Functions for addressing inputs
  void setMode(MC_SERVO_CONTROL_MODE mode);

  // Functions for execution
  MC_ERROR_CODE onExecution() override;

private:
  mcDWORD cycle_counter_;
  mcDWORD cycle_counter_timeout_;
  MC_SERVO_CONTROL_MODE cur_mode_;

protected:
  /// Inputs
  VAR_INPUT MC_SERVO_CONTROL_MODE mode_;
};
}  // namespace RTmotion