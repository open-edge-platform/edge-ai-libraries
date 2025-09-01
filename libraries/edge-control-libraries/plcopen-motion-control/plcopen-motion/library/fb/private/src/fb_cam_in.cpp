// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_cam_in.hpp
 *
 * Maintainer: Yichong Tang <yichong.tang@intel.com>
 *
 */

#include <fb/private/include/fb_cam_in.hpp>

namespace RTmotion
{
FbCamIn::FbCamIn()
  : master_(nullptr)
  , slave_(nullptr)
  , master_offset_(0.0)
  , slave_offset_(0.0)
  , master_scaling_(1.0)
  , slave_scaling_(1.0)
  , start_mode_(mcAbsolute)
  , pointer_to_cam_table_id_(nullptr)
  , in_sync_(mcFALSE)
  , end_of_profile_(mcFALSE)
  , cam_table_id_()
  , master_velocity_(0.0)
  , master_position_(0.0)
  , slave_point_pointer_(nullptr)
  , in_segment_(mcFALSE)
  , enter_segment_(mcFALSE)
  , segment_id_(-1)
  , pointer_to_camxyva_(nullptr)
  , planner_()
  , planner_valid_(mcFALSE)
  , ramp_count_(5)
  , pos_threshold_(1.0)
  , vel_threshold_(20.0)
{
  buffer_mode_                      = mcAborting;
  cam_table_id_.pointer_to_element_ = nullptr;
}

FbCamIn::~FbCamIn()
{
  master_                           = nullptr;
  slave_                            = nullptr;
  pointer_to_cam_table_id_          = nullptr;
  pointer_to_camxyva_               = nullptr;
  slave_point_pointer_              = nullptr;
  cam_table_id_.pointer_to_element_ = nullptr;
}

FbCamIn::FbCamIn(const FbCamIn& other) : cam_table_id_(), planner_()
{
  copyMemberVar(other);
}

FbCamIn& FbCamIn::operator=(const FbCamIn& other)
{
  if (this != &other)
  {
    copyMemberVar(other);
  }
  return *this;
}

void FbCamIn::copyMemberVar(const FbCamIn& other)
{
  master_                  = other.master_;
  slave_                   = other.slave_;
  master_offset_           = other.master_offset_;
  slave_offset_            = other.slave_offset_;
  master_scaling_          = other.master_scaling_;
  slave_scaling_           = other.slave_scaling_;
  start_mode_              = other.start_mode_;
  pointer_to_cam_table_id_ = other.pointer_to_cam_table_id_;
  in_sync_                 = other.in_sync_;
  end_of_profile_          = other.end_of_profile_;
  copyMcCamId(cam_table_id_, other.cam_table_id_);
  master_velocity_     = other.master_velocity_;
  master_position_     = other.master_position_;
  slave_point_pointer_ = other.slave_point_pointer_;
  in_segment_          = other.in_segment_;
  enter_segment_       = other.enter_segment_;
  segment_id_          = other.segment_id_;
  pointer_to_camxyva_  = other.pointer_to_camxyva_;
  planner_valid_       = other.planner_valid_;
  ramp_count_          = other.ramp_count_;
  pos_threshold_       = other.pos_threshold_;
  vel_threshold_       = other.vel_threshold_;
}

MC_ERROR_CODE FbCamIn::onExecution()
{
  if (error_ == mcTRUE)
  {
    DEBUG_PRINT("FbCamIn %p got error. Axis halt.\n", (void*)this);
    error_ = mcFALSE;
    slave_->addFBToQueue(this, mcHaltMode);
  }

  if (axis_->getAxisState() == mcSynchronizedMotion)
  {
    master_position_ = master_->toUserPosCmd();
    master_velocity_ = master_->toUserVelCmd();
    if (cam_table_id_.master_absolute_ == mcTRUE)
      master_position_ -= floor(master_position_);

    if (in_segment_ == mcFALSE)
    {
      planner_valid_ = mcFALSE;
      in_sync_       = mcFALSE;
      enter_segment_ = mcFALSE;
      segment_id_    = findSegmentId(master_position_);
      if (segment_id_ > -1)
      {
        in_segment_ = mcTRUE;
      }
    }
    else if (in_segment_ == mcTRUE &&
             (scaleMasterPosition(master_position_) <
                  pointer_to_camxyva_[segment_id_].x ||
              scaleMasterPosition(master_position_) >=
                  pointer_to_camxyva_[segment_id_ + 1].x))
    {
      in_segment_    = mcFALSE;
      enter_segment_ = mcFALSE;
      planner_valid_ = mcFALSE;
      in_sync_       = mcFALSE;
      if ((segment_id_ == cam_table_id_.element_num_ - 2 &&
           master_velocity_ > 0) ||
          (segment_id_ == 0 && master_velocity_ < 0))
      {
        end_of_profile_ = mcTRUE;
        if (cam_table_id_.periodic_ == mcTRUE)
        {
          if (start_mode_ == mcRelative)
            slave_offset_ = slave_->toUserPos();
          if (cam_table_id_.master_absolute_ == mcFALSE)
            master_offset_ = (-1) * master_position_ * master_scaling_;
        }
        else
        {
          velocity_ = slave_->toUserVel();
          slave_->addFBToQueue(this, mcMoveVelocityMode);
        }
      }

      segment_id_ = findSegmentId(master_position_);
      if (segment_id_ > -1)
      {
        in_segment_ = mcTRUE;
      }
    }

    if (in_segment_ == mcTRUE)
    {
      end_of_profile_ = mcFALSE;
      findSlavePoint(master_position_, segment_id_);
      if (abs(slave_->toUserPosCmd() - slave_point_[mcPositionId]) <
              pos_threshold_ &&
          abs(slave_->toUserVelCmd() - slave_point_[mcSpeedId]) <
              vel_threshold_)
      {
        DEBUG_PRINT("In sync: slave actual pos: %f, command pos: %f\n",
                    slave_->toUserPos(), slave_point_[mcPositionId]);
        in_sync_ = mcTRUE;
        if (enter_segment_ == mcFALSE)
        {
          enter_segment_ = mcTRUE;
          slave_->addFBToQueue(this, mcCamInMode);
        }
        slave_->setMasterRefPos(scaleMasterPosition(master_position_) -
                                pointer_to_camxyva_[segment_id_].x);
        slave_->setMasterRefVel(master_velocity_ * master_scaling_);
        ramp_count_ = 5;
      }
      else
      {
        in_sync_         = mcFALSE;
        enter_segment_   = mcFALSE;
        target_position_ = slave_point_[mcPositionId];
        target_velocity_ = slave_point_[mcSpeedId];
        if (ramp_count_ >= 5)
        {
          slave_->addFBToQueue(this, mcMoveChaseMode);
          ramp_count_ = 0;
          DEBUG_PRINT("master_pos: %f, master_vel: %f, actualpos: %f, "
                      "actualvel: %f, targetpos: %f, targetvel: %f\n",
                      master_position_, master_velocity_, slave_->toUserPos(),
                      slave_->toUserVel(), slave_point_[mcPositionId],
                      slave_point_[mcSpeedId]);
        }
        ramp_count_++;
      }
    }
    active_ = busy_ = mcTRUE;
  }
  else
  {
    in_sync_ = mcFALSE;
  }

  return mcErrorCodeGood;
}

MC_ERROR_CODE FbCamIn::onRisingEdgeExecution()
{
  if (velocity_ == 0 || acceleration_ == 0 || deceleration_ == 0 || jerk_ == 0)
    return mcErrorCodeMotionLimitUnset;
  MC_ERROR_CODE error = axis_->setAxisState(mcSynchronizedMotion);
  if (error)
    return error;

  if (pointer_to_cam_table_id_->slave_ != slave_)
    return mcErrorCodeCamSlaveUnmatch;
  else
    cam_table_id_ = *pointer_to_cam_table_id_;

  if (start_mode_ == mcRelative || cam_table_id_.slave_absolute_ == mcFALSE)
    start_mode_ = mcRelative;
  if (start_mode_ == mcRelative)
    slave_offset_ = slave_->toUserPos();

  master_velocity_ = master_->toUserVelCmd();
  master_position_ = master_->toUserPosCmd();
  if (cam_table_id_.master_absolute_ == mcTRUE)
    master_position_ -= floor(master_position_);
  else
    master_offset_ = (-1) * master_position_ * master_scaling_;

  pointer_to_camxyva_ = (McCamXYVA*)cam_table_id_.pointer_to_element_;
  segment_id_         = -1;
  in_segment_         = mcFALSE;
  enter_segment_      = mcFALSE;
  in_sync_            = mcFALSE;

  return mcErrorCodeGood;
}

void FbCamIn::findSlavePoint(mcLREAL master_position, mcDINT segment_id)
{
  mcLREAL scale_master_position = scaleMasterPosition(master_position);

  double segment_x0, segment_x1, segment_y0, segment_y1, segment_v0, segment_v1;

  segment_x0 = pointer_to_camxyva_[segment_id].x;
  segment_y0 = pointer_to_camxyva_[segment_id].y;
  segment_x1 = pointer_to_camxyva_[segment_id + 1].x;
  segment_y1 = pointer_to_camxyva_[segment_id + 1].y;

  start_position_  = scaleSlavePosition(segment_y0);
  target_position_ = scaleSlavePosition(segment_y1);
  this->setDuration(master_scaling_ * (segment_x1 - segment_x0));

  if (pointer_to_camxyva_[segment_id].type == line)
  {
    planner_type_ = mcLine;
    slave_point_[mcPositionId] =
        ((segment_y1 - segment_y0) / (segment_x1 - segment_x0) *
             (scale_master_position - segment_x0) +
         segment_y0) *
            slave_scaling_ +
        slave_offset_;
    slave_point_[mcSpeedId] = (segment_y1 - segment_y0) /
                              (segment_x1 - segment_x0) * master_velocity_ *
                              master_scaling_ * slave_scaling_;
    return;
  }

  if (planner_valid_ == mcFALSE)
  {
    if (segment_id == 0)
      segment_v0 = 0;
    else
      segment_v0 = pointer_to_camxyva_[segment_id - 1].type == line ?
                       getSegmentVelByGradient(segment_id - 1) :
                       (getSegmentVelByGradient(segment_id - 1) +
                        getSegmentVelByGradient(segment_id)) /
                           2;

    if (pointer_to_camxyva_[segment_id + 1].type == noNextSegment)
    {
      if (cam_table_id_.periodic_ == mcTRUE)
        segment_v1 =
            (getSegmentVelByGradient(segment_id) + getSegmentVelByGradient(0)) /
            2;
      else
        segment_v1 = 0;
    }
    else
    {
      segment_v1 = (getSegmentVelByGradient(segment_id) +
                    getSegmentVelByGradient(segment_id + 1)) /
                   2;
    }

    start_velocity_      = slave_scaling_ * segment_v0;
    start_acceleration_  = 0;
    target_velocity_     = slave_scaling_ * segment_v1;
    target_acceleration_ = 0;

    planner_.setCondition(start_position_, target_position_, start_velocity_,
                          target_velocity_, start_acceleration_,
                          target_acceleration_, duration_, velocity_,
                          acceleration_, jerk_, mcPoly5);
    DEBUG_PRINT("Poly5::setCondition: s0: %f, s1: %f, v0: %f, v1: %f\n",
                start_position_, target_position_, segment_v0, segment_v1);
    planner_.onReplan();
    planner_valid_ = mcTRUE;

    planner_type_ = mcPoly5;
  }

  slave_point_pointer_ =
      planner_.getTrajectoryPoint(scale_master_position - segment_x0);

  slave_point_[mcPositionId]     = slave_point_pointer_[mcPositionId];
  slave_point_[mcSpeedId]        = slave_point_pointer_[mcSpeedId];
  slave_point_[mcAccelerationId] = slave_point_pointer_[mcAccelerationId];
  slave_point_[mcJerkId]         = slave_point_pointer_[mcJerkId];

  slave_point_[mcSpeedId] *= master_velocity_ * master_scaling_;
  slave_point_[mcAccelerationId] *=
      master_velocity_ * master_scaling_ * master_velocity_ * master_scaling_;

  DEBUG_PRINT("target pos: %f, target vel: %f\n", slave_point_[mcPositionId],
              slave_point_[mcSpeedId]);
}

MC_ERROR_CODE FbCamIn::afterFallingEdgeExecution()
{
  if (axis_->getAxisState() == mcSynchronizedMotion)
  {
    in_sync_ = mcFALSE;
    busy_ = active_ = mcTRUE;
  }
  else
  {
    in_sync_ = busy_ = active_ = mcFALSE;
  }

  return error_id_;
}

mcDINT FbCamIn::findSegmentId(mcLREAL master_position)
{
  double scale_master_position = scaleMasterPosition(master_position);

  uint16_t i = 0, j = cam_table_id_.element_num_ - 1;

  while (j - i > 1)
  {
    if (scale_master_position >= pointer_to_camxyva_[(i + j) / 2].x)
      i = (i + j) / 2;
    else
      j = (i + j) / 2;
  }

  if (scale_master_position >= pointer_to_camxyva_[i].x &&
      scale_master_position < pointer_to_camxyva_[i + 1].x)
    return i;
  else
    return -1;
}

mcLREAL FbCamIn::getSegmentVelByGradient(mcDINT segment_id)
{
  return (pointer_to_camxyva_[segment_id + 1].y -
          pointer_to_camxyva_[segment_id].y) /
         (pointer_to_camxyva_[segment_id + 1].x -
          pointer_to_camxyva_[segment_id].x);
}

mcLREAL FbCamIn::scaleMasterPosition(mcLREAL master_position)
{
  return master_scaling_ * master_position + master_offset_;
}

mcLREAL FbCamIn::scaleSlavePosition(mcLREAL slave_position)
{
  return slave_scaling_ * slave_position + slave_offset_;
}

void FbCamIn::setMaster(AXIS_REF master)
{
  master_ = master;
}

void FbCamIn::setSlave(AXIS_REF slave)
{
  slave_ = slave;
  axis_  = slave;
}

void FbCamIn::setMasterOffset(mcLREAL offset)
{
  master_offset_ = offset;
}

void FbCamIn::setSlaveOffset(mcLREAL offset)
{
  slave_offset_ = offset;
}

void FbCamIn::setMasterScaling(mcLREAL scaling)
{
  master_scaling_ = scaling;
}

void FbCamIn::setSlaveScaling(mcLREAL scaling)
{
  slave_scaling_ = scaling;
}

void FbCamIn::setStartMode(MC_START_MODE startMode)
{
  start_mode_ = startMode;
}

void FbCamIn::setCamTableID(McCamId* camTableId)
{
  pointer_to_cam_table_id_ = camTableId;
}

AXIS_REF FbCamIn::getMaster()
{
  return master_;
}

AXIS_REF FbCamIn::getSlave()
{
  return slave_;
}

mcBOOL FbCamIn::getInSync()
{
  return in_sync_;
}

mcBOOL FbCamIn::getEndOfProfile()
{
  return end_of_profile_;
}

void FbCamIn::setPosThreshold(mcLREAL threshold)
{
  pos_threshold_ = threshold;
}

void FbCamIn::setVelThreshold(mcLREAL threshold)
{
  vel_threshold_ = threshold;
}

}  // namespace RTmotion