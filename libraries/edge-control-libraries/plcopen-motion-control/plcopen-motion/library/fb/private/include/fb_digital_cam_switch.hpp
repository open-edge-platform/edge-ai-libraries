// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_digital_cam_switch.hpp
 *
 * Maintainer: Yichong Tang <yichong.tang@intel.com>
 *
 */

#pragma once

#include <fb/common/include/fb_axis_admin.hpp>

#define MAX_TRACK_NUMBER 32

namespace RTmotion
{
/**
 * @brief FbDigitalCamSwitch
 */

typedef mcDWORD* MC_OUTPUT_REF;

struct McCamSwitch
{
  mcUINT track_number_       = 0;
  mcLREAL first_on_position_ = 0;
  mcLREAL last_on_position_  = 0;
  mcINT axis_direction_ =
      0;  // 0 - both directions, 1 - positive direction, 2 - negative direction
  mcINT cam_switch_mode_ = 0;  // 0 - position based, 1 - time based
  mcLREAL duration_      = 0;

  mcBOOL on_           = mcFALSE;  // Record the current status of switch
  mcLREAL counter_off_ = 0;        // Time duration since last time switch is ON
};

struct McCamSwitchRef
{
  mcUSINT switch_number_;
  McCamSwitch* cam_switch_pointer_;
};

struct McTrack
{
  /* Cam positions are interpreted as modulo positions when TRUE */
  mcBOOL modulo_position_ = mcFALSE;
  /* The length of a modulo cycle in the positioning unit of the axis */
  mcLREAL modulo_factor_    = 1;
  mcLREAL on_compensation_  = 0;
  mcLREAL off_compensation_ = 0;
  mcLREAL hysteresis_       = 0;

  mcLREAL on_compensation_position_  = 0;
  mcLREAL off_compensation_position_ = 0;
};

typedef McTrack* MC_TRACK_REF;

class FbDigitalCamSwitch : public FbAxisAdmin
{
public:
  FbDigitalCamSwitch();
  ~FbDigitalCamSwitch() override = default;

  // Functions for addressing inputs
  void setSwitches(McCamSwitchRef switches);
  void setOutputs(MC_OUTPUT_REF outputs);
  void setTrackOptions(MC_TRACK_REF track_options);
  void setEnableMask(mcDWORD enable_mask);
  void setValueSource(MC_SOURCE value_source);

  // Functions for getting outputs
  McCamSwitchRef getSwitches();
  MC_OUTPUT_REF getOutputs();
  MC_TRACK_REF getTrackOptions();
  mcBOOL isInOperation();

  // Functions for execution
  MC_ERROR_CODE onExecution() override;
  MC_ERROR_CODE onRisingEdgeExecution() override;
  MC_ERROR_CODE onFallingEdgeExecution() override;

protected:
  /// Inouts
  VAR_IN_OUT McCamSwitchRef switches_;
  VAR_IN_OUT MC_OUTPUT_REF outputs_;
  VAR_IN_OUT MC_TRACK_REF track_options_;
  /// Inputs
  VAR_INPUT mcDWORD enable_mask_;
  VAR_INPUT MC_SOURCE value_source_;
  /// Outputs
  VAR_OUTPUT mcBOOL in_operation_;

private:
  mcLREAL last_position_;
  mcLREAL current_position_;
  mcLREAL last_position_in_track_;
  mcLREAL current_position_in_track_;
  mcLREAL current_velocity_;
  mcLREAL current_acceleration_;
  McCamSwitch* switch_pointer_;
  MC_TRACK_REF track_pointer_;
  mcLREAL first_pos_add_comp_;
  mcLREAL last_pos_add_comp_;
};
}  // namespace RTmotion