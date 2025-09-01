// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_cam_in.hpp
 *
 * Maintainer: Yichong Tang <yichong.tang@intel.com>
 *
 */

#pragma once

#include <fb/common/include/global.hpp>
#include <fb/common/include/fb_axis_motion.hpp>
#include <fb/private/include/fb_cam_table_select.hpp>

namespace RTmotion
{
/**
 * @brief MC_CamIn
 */

typedef enum
{
  mcAbsolute = 0,
  mcRelative = 1,
} MC_START_MODE;

class FbCamIn : public FbAxisMotion
{
public:
  FbCamIn();
  ~FbCamIn() override;
  FbCamIn(const FbCamIn& other);
  FbCamIn& operator=(const FbCamIn& other);

  MC_ERROR_CODE onExecution() override;
  MC_ERROR_CODE onRisingEdgeExecution() override;
  MC_ERROR_CODE afterFallingEdgeExecution() override;

  void setMaster(AXIS_REF master);
  void setSlave(AXIS_REF slave);
  void setMasterOffset(mcLREAL offset);
  void setSlaveOffset(mcLREAL offset);
  void setMasterScaling(mcLREAL scaling);
  void setSlaveScaling(mcLREAL scaling);
  void setStartMode(MC_START_MODE startMode);
  void setCamTableID(McCamId* camTableId);

  AXIS_REF getMaster();
  AXIS_REF getSlave();
  mcBOOL getInSync();
  mcBOOL getEndOfProfile();

  void findSlavePoint(mcLREAL master_position, mcDINT segment_id);
  mcLREAL getSegmentVelByGradient(mcDINT segment_id);
  mcDINT findSegmentId(mcLREAL master_position);
  mcLREAL scaleMasterPosition(mcLREAL master_position);
  mcLREAL scaleSlavePosition(mcLREAL slave_position);

  void setPosThreshold(mcLREAL threshold);
  void setVelThreshold(mcLREAL threshold);

protected:
  // In_Out
  VAR_IN_OUT AXIS_REF master_;
  VAR_IN_OUT AXIS_REF slave_;
  // Inputs
  VAR_INPUT mcLREAL master_offset_;
  VAR_INPUT mcLREAL slave_offset_;
  VAR_INPUT mcLREAL master_scaling_;
  VAR_INPUT mcLREAL slave_scaling_;
  VAR_INPUT MC_START_MODE start_mode_;
  VAR_INPUT McCamId* pointer_to_cam_table_id_;
  // Outputs
  VAR_OUTPUT mcBOOL in_sync_;
  VAR_OUTPUT mcBOOL end_of_profile_;

  McCamId cam_table_id_;
  mcLREAL master_velocity_;
  mcLREAL master_position_;
  mcLREAL slave_point_[4] = { 0 };
  mcLREAL* slave_point_pointer_;
  mcBOOL in_segment_;
  mcBOOL enter_segment_;
  mcDINT segment_id_;
  McCamXYVA* pointer_to_camxyva_;
  trajectory_processing::AxisPlanner planner_;
  mcBOOL planner_valid_;
  mcDINT ramp_count_;
  mcLREAL pos_threshold_;
  mcLREAL vel_threshold_;

private:
  void copyMemberVar(const FbCamIn& other);
};
}  // namespace RTmotion