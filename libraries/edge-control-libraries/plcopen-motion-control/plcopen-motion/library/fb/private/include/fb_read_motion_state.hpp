// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_read_motion_state.hpp
 *
 * Maintainer: Wu Xian <xian.wu@intel.com>
 *
 */

#pragma once

#include <fb/common/include/fb_axis_read.hpp>

namespace RTmotion
{
/**
 * @brief Function block base for axis motion state read
 */
class FbReadMotionState : public FbAxisRead
{
public:
  FbReadMotionState();
  ~FbReadMotionState() override = default;

  void setSource(MC_SOURCE source);
  void setConstantVelocityThreshold(mcREAL threshold);

  mcBOOL getConstantVelocity();
  mcBOOL getAccelerating();
  mcBOOL getDecelerating();
  mcBOOL getDirectionPositive();
  mcBOOL getDirectionNegative();

  MC_ERROR_CODE onRisingEdgeExecution() override;
  MC_ERROR_CODE onExecution() override;

private:
  MC_SOURCE source_;
  mcREAL cons_vel_threshold_;
  mcBOOL constant_velocity_;
  mcBOOL accelerating_;
  mcBOOL decelerating_;
  mcBOOL direction_positive_;
  mcBOOL direction_negative_;
};
}  // namespace RTmotion