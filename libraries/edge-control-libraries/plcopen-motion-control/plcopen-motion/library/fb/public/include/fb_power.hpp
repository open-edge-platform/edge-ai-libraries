// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_power.hpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#pragma once

#include <fb/common/include/fb_axis_admin.hpp>

namespace RTmotion
{
/**
 * @brief Function block base for single axis motion
 */
class FbPower : public FbAxisAdmin
{
public:
  FbPower();
  ~FbPower() override = default;

  // Functions for addressing inputs
  void setEnablePositive(mcBOOL enable_positive);
  void setEnableNegative(mcBOOL enable_negative);

  mcBOOL getPowerStatus();

  MC_ERROR_CODE onExecution() override;
  MC_ERROR_CODE onFallingEdgeExecution() override;

protected:
  /// Inputs
  VAR_INPUT mcBOOL enable_positive_;
  VAR_INPUT mcBOOL enable_negative_;
};
}  // namespace RTmotion
