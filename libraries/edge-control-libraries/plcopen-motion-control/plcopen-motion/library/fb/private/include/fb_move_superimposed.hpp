// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_move_superimposed.hpp
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
 * @brief Function block MC_MoveSuperimposed
 */
class FbMoveSuperimposed : public FbAxisMotion
{
public:
  FbMoveSuperimposed();
  ~FbMoveSuperimposed() override = default;

  // Functions for addressing inputs
  void setDistance(mcLREAL position)
  {
    distance_diff_ = position;
  }
  void setVelocityDiff(mcLREAL velocity)
  {
    velocity_diff_ = velocity;
  }

  // Functions for addressing output
  mcLREAL getCoveredDistance();

  MC_ERROR_CODE onRisingEdgeExecution() override;
  MC_ERROR_CODE onFallingEdgeExecution() override;
  MC_ERROR_CODE onExecution() override;

protected:
  // Inputs
  VAR_INPUT mcLREAL& distance_diff_ = position_;
  VAR_INPUT mcLREAL& velocity_diff_ = velocity_;

  // Outputs
  VAR_OUTPUT mcLREAL covered_distance_;

private:
  mcBOOL superimposed_without_underlying_motion_;
};
}  // namespace RTmotion
