// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_homing.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <fb/public/include/fb_homing.hpp>

namespace RTmotion
{
FbHoming::FbHoming()
  : abs_switch_signal_(mcFALSE)
  , limit_switch_neg_signal_(mcFALSE)
  , limit_switch_pos_signal_(mcFALSE)
  , limit_offset_(0.00001)
  , homing_reset_(mcFALSE)
  , reach_neg_limit_(mcFALSE)
  , reach_pos_limit_(mcFALSE)
  , neg_limit_(0.0)
  , pos_limit_(0.0)
  , homing_state_(mcHomingStill)
{
}

void FbHoming::setRefSignal(mcBOOL signal)
{
  if (homing_state_ == mcHomingSearch)
  {
    if ((abs_switch_signal_ == mcFALSE) && (signal == mcTRUE))
    {
      homing_reset_ = mcTRUE;
      axis_->setHomePositionOffset();
      DEBUG_PRINT("FbHoming:: Find ref signal in mcHomingSearch\n");
    }
  }
  else if (homing_state_ == mcHomingSearchBack)
  {
    if ((abs_switch_signal_ == mcTRUE) && (signal == mcFALSE))
    {
      homing_reset_ = mcTRUE;
      axis_->setHomePositionOffset();
      DEBUG_PRINT("FbHoming:: Find ref signal in mcHomingSearchBack\n");
    }
  }
  abs_switch_signal_ = signal;
  axis_->setAxisHomeAbsSwitch(signal);
}

void FbHoming::setLimitNegSignal(mcBOOL signal)
{
  if ((limit_switch_neg_signal_ == mcFALSE) && (signal == mcTRUE))
  {
    reach_neg_limit_ = mcTRUE;
    neg_limit_       = axis_->toUserPos() + limit_offset_;
    homing_state_ =
        (homing_state_ == mcHomingSearch ? mcHomingSearchBack : mcHomingHalt);
    DEBUG_PRINT("FbHoming::setLimitNegSignal\n");
  }

  limit_switch_neg_signal_ = signal;
  axis_->setAxisLimitSwitchNeg(signal);
}

void FbHoming::setLimitPosSignal(mcBOOL signal)
{
  if ((limit_switch_pos_signal_ == mcFALSE) && (signal == mcTRUE))
  {
    reach_pos_limit_ = mcTRUE;
    pos_limit_       = axis_->toUserPos() - limit_offset_;
    homing_state_ =
        (homing_state_ == mcHomingSearch ? mcHomingSearchBack : mcHomingHalt);
    DEBUG_PRINT("FbHoming::setLimitPosSignal\n");
  }

  limit_switch_pos_signal_ = signal;
  axis_->setAxisLimitSwitchPos(signal);
}

void FbHoming::setLimitOffset(mcLREAL offset)
{
  limit_offset_ = fabs(offset);
}

MC_ERROR_CODE FbHoming::onRisingEdgeExecution()
{
  if (velocity_ == 0 || acceleration_ == 0 || deceleration_ == 0 || jerk_ == 0)
    return mcErrorCodeMotionLimitUnset;
  if (abs_switch_signal_ == mcFALSE)
  {
    position_     = NAN;
    homing_state_ = mcHomingSearch;
    axis_->addFBToQueue(this, mcHomingMode);
  }
  else
  {
    position_     = NAN;
    direction_    = (direction_ == mcPositiveDirection ? mcNegativeDirection :
                                                         mcPositiveDirection);
    homing_state_ = mcHomingSearchBack;
    axis_->addFBToQueue(this, mcHomingMode);
  }
  return mcErrorCodeGood;
}

MC_ERROR_CODE FbHoming::onExecution()
{
  if (reach_neg_limit_ == mcTRUE)
  {
    if (homing_state_ == mcHomingSearchBack)
      position_ = NAN;
    else if (homing_state_ == mcHomingHalt)
      position_ = neg_limit_;
    buffer_mode_ = mcAborting;
    direction_   = mcPositiveDirection;
    axis_->addFBToQueue(this, mcHomingMode);
    reach_neg_limit_ = mcFALSE;
  }

  if (reach_pos_limit_ == mcTRUE)
  {
    if (homing_state_ == mcHomingSearchBack)
      position_ = NAN;
    else if (homing_state_ == mcHomingHalt)
      position_ = pos_limit_;
    buffer_mode_ = mcAborting;
    direction_   = mcNegativeDirection;
    axis_->addFBToQueue(this, mcHomingMode);
    reach_pos_limit_ = mcFALSE;
  }

  if (homing_reset_ == mcTRUE)
  {
    position_    = 0.0;
    buffer_mode_ = mcAborting;
    axis_->addFBToQueue(this, mcHomingMode);
    homing_reset_ = mcFALSE;
    homing_state_ = mcHomingFinish;
  }
  return mcErrorCodeGood;
}

MC_ERROR_CODE FbHoming::onFallingEdgeExecution()
{
  buffer_mode_ = mcAborting;
  velocity_    = 0;
  axis_->addFBToQueue(this, mcHaltMode);

  abs_switch_signal_       = mcFALSE;
  limit_switch_neg_signal_ = mcFALSE;
  limit_switch_pos_signal_ = mcFALSE;
  reach_neg_limit_         = mcFALSE;
  reach_pos_limit_         = mcFALSE;
  homing_reset_            = mcFALSE;
  homing_state_            = mcHomingStill;
  return mcErrorCodeGood;
}

void FbHoming::syncStatus(mcBOOL done, mcBOOL busy, mcBOOL active,
                          mcBOOL cmd_aborted, mcBOOL error,
                          MC_ERROR_CODE error_id)
{
  done_   = mcBOOL(done == mcTRUE && (homing_state_ == mcHomingFinish));
  busy_   = busy;
  active_ = active;
  command_aborted_ = cmd_aborted;
  error_           = error;
  error_id_        = error_id;

  output_flag_ = execute_ == mcTRUE ? mcFALSE : mcTRUE;
  DEBUG_PRINT("FbAxisNode::syncStatus %s\n",
              done_ == mcTRUE ? "mcTRUE" : "mcFALSE");
}

}  // namespace RTmotion
