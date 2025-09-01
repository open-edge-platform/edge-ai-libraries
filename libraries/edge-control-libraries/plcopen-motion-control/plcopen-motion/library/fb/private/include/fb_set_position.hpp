// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_set_position.hpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#pragma once

#include <fb/common/include/fb_axis_admin.hpp>

namespace RTmotion
{
/**
 * @brief MC_SetPosition
 */

class FbSetPosition : public FbAxisAdmin
{
public:
  FbSetPosition();
  ~FbSetPosition() override = default;

  // Functions for addressing inputs
  void setPosition(mcLREAL position);
  void setMode(MC_SET_POSITION_MODE mode);

  // Functions for execution
  MC_ERROR_CODE onRisingEdgeExecution() override;
  MC_ERROR_CODE onExecution() override;

protected:
  /// Inputs
  VAR_INPUT mcLREAL position_;
  VAR_INPUT MC_SET_POSITION_MODE mode_;

private:
  mcBOOL set_offset_ret_;
};
}  // namespace RTmotion