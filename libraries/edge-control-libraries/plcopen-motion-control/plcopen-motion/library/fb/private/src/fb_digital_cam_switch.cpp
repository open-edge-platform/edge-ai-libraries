// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_digital_cam_switch.cpp
 *
 * Maintainer: Yichong Tang <yichong.tang@intel.com>
 *
 */

#include <fb/private/include/fb_digital_cam_switch.hpp>

namespace RTmotion
{
FbDigitalCamSwitch::FbDigitalCamSwitch()
  : outputs_(nullptr)
  , track_options_(nullptr)
  , enable_mask_(0xFFFFFFFF)
  , value_source_(mcSetValue)
  , in_operation_(mcFALSE)
  , last_position_(0)
  , current_position_(0)
  , last_position_in_track_(0)
  , current_position_in_track_(0)
  , current_velocity_(0)
  , current_acceleration_(0)
  , switch_pointer_(nullptr)
  , track_pointer_(nullptr)
  , first_pos_add_comp_(0)
  , last_pos_add_comp_(0)
{
  switches_.switch_number_      = 0;
  switches_.cam_switch_pointer_ = nullptr;
}

MC_ERROR_CODE FbDigitalCamSwitch::onExecution()
{
  if (axis_->getAxisError())
    return axis_->getAxisError();

  if (value_source_ == mcActualValue)
  {
    current_position_     = axis_->toUserPos();
    current_velocity_     = axis_->toUserVel();
    current_acceleration_ = axis_->toUserAcc();
  }
  else if (value_source_ == mcSetValue)
  {
    current_position_     = axis_->toUserPosCmd();
    current_velocity_     = axis_->toUserVelCmd();
    current_acceleration_ = axis_->toUserAccCmd();
  }

  for (mcUINT i = 0; i < MAX_TRACK_NUMBER; i++)
  {
    if (enable_mask_ >> i & 0x1)
    {
      track_options_[i].on_compensation_position_ =
          track_options_[i].on_compensation_ * current_velocity_ +
          0.5 * current_acceleration_ * track_options_[i].on_compensation_ *
              track_options_[i].on_compensation_;
      track_options_[i].off_compensation_position_ =
          track_options_[i].off_compensation_ * current_velocity_ +
          0.5 * current_acceleration_ * track_options_[i].off_compensation_ *
              track_options_[i].off_compensation_;
      if (abs(track_options_[i].on_compensation_position_) >
              track_options_[i].modulo_factor_ * 2 ||
          abs(track_options_[i].off_compensation_position_) >
              track_options_[i].modulo_factor_ * 2)
        return mcErrorCodeEdgePositionOutOfTwoModuloRanges;
    }
  }

  for (mcUINT i = 0; i < switches_.switch_number_; i++)
  {
    switch_pointer_ = &switches_.cam_switch_pointer_[i];
    track_pointer_  = track_options_ + (switch_pointer_->track_number_ - 1);
    if (track_pointer_->modulo_position_ == mcTRUE)
    {
      last_position_in_track_ =
          fmod(last_position_, track_pointer_->modulo_factor_);
      current_position_in_track_ =
          fmod(current_position_, track_pointer_->modulo_factor_);
      if (last_position_ < 0)
        last_position_in_track_ += track_pointer_->modulo_factor_;
      if (current_position_ < 0)
        current_position_in_track_ += track_pointer_->modulo_factor_;
    }
    else
    {
      last_position_in_track_    = last_position_;
      current_position_in_track_ = current_position_;
    }

    if (switch_pointer_->on_ == mcTRUE)
    {
      switch_pointer_->counter_off_ += axis_->getDeltaTime();
    }

    if (axis_->toUserVelCmd() > 0)
    {
      first_pos_add_comp_ = switch_pointer_->first_on_position_ +
                            track_pointer_->on_compensation_position_;
      last_pos_add_comp_ = switch_pointer_->last_on_position_ +
                           track_pointer_->off_compensation_position_;
      if (track_pointer_->modulo_position_ == mcTRUE)
      {
        first_pos_add_comp_ =
            fmod(first_pos_add_comp_, track_pointer_->modulo_factor_);
        if (first_pos_add_comp_ < 0)
        {
          first_pos_add_comp_ += track_pointer_->modulo_factor_;
        }
        last_pos_add_comp_ =
            fmod(last_pos_add_comp_, track_pointer_->modulo_factor_);
        if (last_pos_add_comp_ < 0)
          last_pos_add_comp_ += track_pointer_->modulo_factor_;
      }
      if ((switch_pointer_->cam_switch_mode_ == 0 &&
           last_position_in_track_ < last_pos_add_comp_ &&
           current_position_in_track_ >= last_pos_add_comp_) ||
          (switch_pointer_->cam_switch_mode_ == 1 &&
           switch_pointer_->counter_off_ > switch_pointer_->duration_ / 1000))
      {
        switch_pointer_->on_ = mcFALSE;
      }

      if (last_position_in_track_ < first_pos_add_comp_ &&
          current_position_in_track_ >= first_pos_add_comp_ &&
          (switch_pointer_->axis_direction_ == 0 ||
           switch_pointer_->axis_direction_ == 1) &&
          switch_pointer_->on_ == mcFALSE)
      {
        switch_pointer_->on_          = mcTRUE;
        switch_pointer_->counter_off_ = 0;
      }
    }
    else  // current_velocity_ <= 0
    {
      first_pos_add_comp_ = switch_pointer_->first_on_position_ -
                            track_pointer_->off_compensation_position_;
      last_pos_add_comp_ = switch_pointer_->last_on_position_ -
                           track_pointer_->on_compensation_position_;
      if (track_pointer_->modulo_position_ == mcTRUE)
      {
        first_pos_add_comp_ =
            fmod(first_pos_add_comp_, track_pointer_->modulo_factor_);
        if (first_pos_add_comp_ < 0)
        {
          first_pos_add_comp_ += track_pointer_->modulo_factor_;
        }
        last_pos_add_comp_ =
            fmod(last_pos_add_comp_, track_pointer_->modulo_factor_);
        if (last_pos_add_comp_ < 0)
          last_pos_add_comp_ += track_pointer_->modulo_factor_;
      }
      if ((switch_pointer_->cam_switch_mode_ == 0 &&
           last_position_in_track_ > first_pos_add_comp_ &&
           current_position_in_track_ <= first_pos_add_comp_) ||
          (switch_pointer_->cam_switch_mode_ == 1 &&
           switch_pointer_->counter_off_ > switch_pointer_->duration_ / 1000))
      {
        switch_pointer_->on_ = mcFALSE;
      }

      if (switch_pointer_->cam_switch_mode_ == 0 &&
          last_position_in_track_ > last_pos_add_comp_ &&
          current_position_in_track_ <= last_pos_add_comp_ &&
          (switch_pointer_->axis_direction_ == 0 ||
           switch_pointer_->axis_direction_ == 2) &&
          switch_pointer_->on_ == mcFALSE)
      {
        switch_pointer_->on_          = mcTRUE;
        switch_pointer_->counter_off_ = 0;
      }

      if (switch_pointer_->cam_switch_mode_ == 1 &&
          last_position_in_track_ > switch_pointer_->first_on_position_ &&
          current_position_in_track_ <= switch_pointer_->first_on_position_ &&
          (switch_pointer_->axis_direction_ == 0 ||
           switch_pointer_->axis_direction_ == 2) &&
          switch_pointer_->on_ == mcFALSE)
      {
        switch_pointer_->on_          = mcTRUE;
        switch_pointer_->counter_off_ = 0;
      }
    }
  }

  *outputs_ = 0;
  for (mcUINT i = 0; i < switches_.switch_number_; i++)
    *outputs_ |= (uint32_t)switches_.cam_switch_pointer_[i].on_
                 << (switches_.cam_switch_pointer_[i].track_number_ - 1);

  *outputs_ &= enable_mask_;

  if (*outputs_ != 0)
    in_operation_ = mcTRUE;
  else
    in_operation_ = mcFALSE;

  last_position_ = current_position_;
  return mcErrorCodeGood;
}

MC_ERROR_CODE FbDigitalCamSwitch::onRisingEdgeExecution()
{
  for (mcUINT i = 0; i < MAX_TRACK_NUMBER; i++)
  {
    if (enable_mask_ >> i & 0x1)
    {
      if (track_options_ == nullptr || track_options_ + i == nullptr)
        return mcErrorCodeFaultyTrackOptions;
      if (track_options_[i].modulo_position_ == mcTRUE &&
          track_options_[i].modulo_factor_ <= 0)
        return mcErrorCodeFaultyTrackOptions;
    }
  }

  for (mcUINT i = 0; i < switches_.switch_number_; i++)
  {
    if (switches_.cam_switch_pointer_ == nullptr ||
        switches_.cam_switch_pointer_ + i == nullptr)
      return mcErrorCodeFaultyCamSwitch;

    mcUINT track_number = switches_.cam_switch_pointer_[i].track_number_;

    if (track_number > MAX_TRACK_NUMBER)
      return mcErrorCodeFaultyCamSwitch;

    if (track_options_ == nullptr ||
        track_options_ + (track_number - 1) == nullptr)
      return mcErrorCodeFaultyTrackOptions;

    if (track_options_[track_number].modulo_position_ == mcTRUE)
    {
      mcLREAL modulo_factor = track_options_[track_number].modulo_factor_;
      if (switches_.cam_switch_pointer_[i].first_on_position_ < 0 ||
          switches_.cam_switch_pointer_[i].first_on_position_ > modulo_factor ||
          switches_.cam_switch_pointer_[i].last_on_position_ < 0 ||
          switches_.cam_switch_pointer_[i].last_on_position_ > modulo_factor)
        return mcErrorCodeFaultyCamSwitch;
    }
  }

  if (value_source_ == mcActualValue)
  {
    current_position_     = axis_->toUserPos();
    current_velocity_     = axis_->toUserVel();
    current_acceleration_ = axis_->toUserAcc();
  }
  else if (value_source_ == mcSetValue)
  {
    current_position_     = axis_->toUserPosCmd();
    current_velocity_     = axis_->toUserVelCmd();
    current_acceleration_ = axis_->toUserAccCmd();
  }

  last_position_ = current_position_;
  in_operation_  = mcFALSE;
  if (outputs_ == nullptr)
    return mcErrorCodeOutputRefNotInitialized;
  else
    *outputs_ = 0;

  return mcErrorCodeGood;
}

MC_ERROR_CODE FbDigitalCamSwitch::onFallingEdgeExecution()
{
  in_operation_ = mcFALSE;
  *outputs_     = 0;
  return mcErrorCodeGood;
}

void FbDigitalCamSwitch::setSwitches(McCamSwitchRef switches)
{
  switches_ = switches;
}

void FbDigitalCamSwitch::setOutputs(MC_OUTPUT_REF outputs)
{
  outputs_ = outputs;
}

void FbDigitalCamSwitch::setTrackOptions(MC_TRACK_REF track_options)
{
  track_options_ = track_options;
}

void FbDigitalCamSwitch::setEnableMask(mcDWORD enable_mask)
{
  enable_mask_ = enable_mask;
}

void FbDigitalCamSwitch::setValueSource(MC_SOURCE value_source)
{
  value_source_ = value_source;
}

McCamSwitchRef FbDigitalCamSwitch::getSwitches()
{
  return switches_;
}

MC_OUTPUT_REF FbDigitalCamSwitch::getOutputs()
{
  return outputs_;
}

MC_TRACK_REF FbDigitalCamSwitch::getTrackOptions()
{
  return track_options_;
}

mcBOOL FbDigitalCamSwitch::isInOperation()
{
  return in_operation_;
}

}  // namespace RTmotion