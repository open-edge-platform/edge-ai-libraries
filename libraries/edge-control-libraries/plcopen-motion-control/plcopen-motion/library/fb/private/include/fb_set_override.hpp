// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_set_override.hpp
 *
 * Maintainer: Xian Wu <xian.wu@intel.com>
 *
 */

#pragma once

#include <fb/common/include/fb_axis_admin.hpp>

namespace RTmotion
{
/**
 * @brief MC_SetOverride
 */

class FbSetOverride : public FbAxisAdmin
{
public:
  FbSetOverride();
  ~FbSetOverride() override = default;

  // Functions for addressing inputs
  void setVelFactor(mcREAL vel_factor);
  void setAccFactor(mcREAL acc_factor);
  void setJerkFactor(mcREAL jerk_factor);
  void setThreshold(mcREAL threshold);

  // Functions for execution
  MC_ERROR_CODE onExecution() override;

protected:
  /// Inputs
  VAR_INPUT mcREAL vel_factor_;
  VAR_INPUT mcREAL acc_factor_;
  VAR_INPUT mcREAL jerk_factor_;
  VAR_INPUT mcREAL threshold_;

private:
};
}  // namespace RTmotion