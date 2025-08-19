// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_torque_control.hpp
 *
 * Maintainer: He Kanghua <kanghua.he@intel.com>
 *
 */

#pragma once

#include <fb/common/include/global.hpp>
#include <fb/common/include/fb_axis_motion.hpp>

namespace RTmotion
{
/**
 * @brief Function block MC_TorqueControl
 */
class FbTorqueControl : public FbAxisMotion
{
public:
  FbTorqueControl();
  ~FbTorqueControl() override = default;

  MC_ERROR_CODE onRisingEdgeExecution() override;
  MC_ERROR_CODE onFallingEdgeExecution() override;
  MC_ERROR_CODE onExecution() override;

  // Functions for addressing inputs
  void setTorque(mcLREAL torque) override;
  void setMaxProfileVelocity(mcLREAL velocity) override;
  virtual void setTorqueDoneFactor(mcLREAL factor);

protected:
  // Inputs
  VAR_INPUT mcLREAL torque_;
  VAR_INPUT mcLREAL torque_ramp_;
  // Outputs
  VAR_OUTPUT mcBOOL in_torque_;

private:
  mcLREAL toq_done_factor_;
};
}  // namespace RTmotion
