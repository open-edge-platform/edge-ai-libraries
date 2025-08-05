// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_move_superimposed.cpp
 *
 * Maintainer: He Kanghua <kanghua.he@intel.com>
 *
 */

#include <fb/private/include/fb_move_superimposed.hpp>

namespace RTmotion
{
FbMoveSuperimposed::FbMoveSuperimposed()
  : covered_distance_(0), superimposed_without_underlying_motion_(mcFALSE)
{
  distance_diff_ = 0;
  velocity_diff_ = 0;
}

mcLREAL FbMoveSuperimposed::getCoveredDistance()
{
  return covered_distance_;
}

MC_ERROR_CODE FbMoveSuperimposed::onRisingEdgeExecution()
{
  // Checking input params
  if (position_ == 0 || velocity_ == 0 || acceleration_ == 0 ||
      deceleration_ == 0 || jerk_ == 0)
    return mcErrorCodeMotionLimitUnset;
  switch (axis_->getAxisState())
  {
    // MC_MoveSuperimposed issued in state Standstill brings the axis to state
    // DiscreteMotion.
    case mcStandstill:
      axis_->setAxisState(mcDiscreteMotion);
      superimposed_without_underlying_motion_ = mcTRUE;
      break;
    case mcDisabled:
    case mcHoming:
    case mcStopping:
    case mcErrorStop:
      return mcErrorCodeAxisStateViolation;
      break;
    default:
      break;
  }
  axis_->addMoveSupFB(this, distance_diff_, velocity_diff_);
  axis_->setAxisSuperimposedState(mcTRUE);
  return axis_->getAxisError();
}

MC_ERROR_CODE FbMoveSuperimposed::onFallingEdgeExecution()
{
  if (done_ == mcTRUE)
    done_ = mcFALSE;
  else if (command_aborted_ == mcFALSE)
  {
    // Replan underlying motion after this FB power off
    axis_->replanUnderlyingMotion();
    axis_->setAxisSuperimposedState(mcFALSE);
  }
  if (superimposed_without_underlying_motion_ == mcTRUE)
  {
    axis_->setAxisState(mcStandstill);
    superimposed_without_underlying_motion_ = mcFALSE;
  }
  return axis_->getAxisError();
}

MC_ERROR_CODE FbMoveSuperimposed::onExecution()
{
  // new move superimposed FB will abort ongoing one
  if (command_aborted_ == mcTRUE)
    return axis_->getAxisError();

  // update move superimposed FB covered distance
  covered_distance_ = axis_->getMoveSupCoveredDistance();

  // monitor done condition
  if (done_ == mcFALSE)
  {
    if (distance_diff_ >= 0.0)
    {
      if (covered_distance_ >= distance_diff_)
      {
        done_ = mcTRUE;
        busy_ = mcFALSE;
        axis_->replanUnderlyingMotion();
        axis_->setAxisSuperimposedState(mcFALSE);
      }
    }
    else
    {
      if (covered_distance_ <= distance_diff_)
      {
        done_ = mcTRUE;
        busy_ = mcFALSE;
        axis_->replanUnderlyingMotion();
        axis_->setAxisSuperimposedState(mcFALSE);
      }
    }
  }
  return axis_->getAxisError();
}

}  // namespace RTmotion
