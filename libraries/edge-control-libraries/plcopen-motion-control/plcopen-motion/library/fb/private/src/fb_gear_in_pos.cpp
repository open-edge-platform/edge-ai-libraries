// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_gear_in_pos.cpp
 *
 * Maintainer: Yichong Tang <yichong.tang@intel.com>
 *
 */

#include <fb/private/include/fb_gear_in_pos.hpp>

namespace RTmotion
{
FbGearInPos::FbGearInPos()
  : master_(nullptr)
  , slave_(nullptr)
  , ratio_numerator_(0)
  , ratio_denominator_(1000)
  , master_sync_position_(0.0)
  , slave_sync_position_(0.0)
  , master_start_distance_(0.0)
  , start_sync_(mcFALSE)
  , in_sync_(mcFALSE)
  , master_pos_(0.0)
  , last_master_pos_(0.0)
  , master_vel_(0.0)
  , master_start_position_(0.0)
  , pos_sync_factor_(0.02)
  , vel_sync_factor_(0.2)
  , slave_standby_(mcFALSE)
{
}

FbGearInPos::~FbGearInPos()
{
  master_ = nullptr;
  slave_  = nullptr;
}

FbGearInPos::FbGearInPos(const FbGearInPos& other)
{
  master_                = other.master_;
  slave_                 = other.slave_;
  ratio_numerator_       = other.ratio_numerator_;
  ratio_denominator_     = other.ratio_denominator_;
  master_sync_position_  = other.master_sync_position_;
  slave_sync_position_   = other.slave_sync_position_;
  master_start_distance_ = other.master_start_distance_;
  start_sync_            = other.start_sync_;
  in_sync_               = other.in_sync_;
  master_pos_            = other.master_pos_;
  last_master_pos_       = other.last_master_pos_;
  master_vel_            = other.master_vel_;
  master_start_position_ = other.master_start_position_;
  pos_sync_factor_       = other.pos_sync_factor_;
  vel_sync_factor_       = other.vel_sync_factor_;
  slave_standby_         = other.slave_standby_;
}

FbGearInPos& FbGearInPos::operator=(const FbGearInPos& other)
{
  if (this != &other)
  {
    master_                = other.master_;
    slave_                 = other.slave_;
    ratio_numerator_       = other.ratio_numerator_;
    ratio_denominator_     = other.ratio_denominator_;
    master_sync_position_  = other.master_sync_position_;
    slave_sync_position_   = other.slave_sync_position_;
    master_start_distance_ = other.master_start_distance_;
    start_sync_            = other.start_sync_;
    in_sync_               = other.in_sync_;
    master_pos_            = other.master_pos_;
    last_master_pos_       = other.last_master_pos_;
    master_vel_            = other.master_vel_;
    master_start_position_ = other.master_start_position_;
    pos_sync_factor_       = other.pos_sync_factor_;
    vel_sync_factor_       = other.vel_sync_factor_;
    slave_standby_         = other.slave_standby_;
  }
  return *this;
}

MC_ERROR_CODE FbGearInPos::onRisingEdgeExecution()
{
  start_sync_ = mcFALSE;
  in_sync_    = mcFALSE;
  if (velocity_ == 0 || acceleration_ == 0 || deceleration_ == 0)
    return mcErrorCodeMotionLimitError;
  if (ratio_denominator_ == 0)
    return mcErrorCodeGearRatioDenominatorSetZero;

  slave_standby_   = mcTRUE;
  master_pos_      = master_->toUserPosCmd();
  last_master_pos_ = master_pos_;
  master_vel_      = master_->toUserVelCmd();

  if (buffer_mode_ != mcAborting)
  {
    master_start_distance_ = 0;

    // TODO - handle non mcAborting buffer mode

    return mcErrorCodeUnsupportedBufferMode;
  }

  if (master_start_distance_ == 0)
  {
    startGearProcess();
    master_start_position_ = master_pos_;
  }
  else
  {
    master_start_position_ = master_sync_position_ - master_start_distance_;

    if (master_pos_ > master_start_position_ &&
        master_pos_ < master_sync_position_)
    {
      if (master_vel_ > vel_sync_factor_)
      {
        startGearProcess();
        master_start_position_ = master_pos_;
      }
      else
      {
        return mcErrorCodeGearInPosInvalidDirection;
      }
    }
    else if (master_pos_ < master_start_position_ &&
             master_pos_ > master_sync_position_)
    {
      if (master_vel_ < (-1) * vel_sync_factor_)
      {
        startGearProcess();
        master_start_position_ = master_pos_;
      }
      else
      {
        return mcErrorCodeGearInPosInvalidDirection;
      }
    }
  }

  return mcErrorCodeGood;
}

MC_ERROR_CODE FbGearInPos::onExecution()
{
  master_pos_ = master_->toUserPosCmd();
  master_vel_ = master_->toUserVelCmd();
  slave_->setMasterRefPos(abs(master_pos_ - master_start_position_));
  slave_->setMasterRefVel(master_vel_);

  if (axis_->getAxisState() == mcStopping)
    slave_standby_ = mcFALSE;

  if (start_sync_ == mcFALSE && slave_standby_ == mcTRUE)
  {
    if (master_vel_ > vel_sync_factor_ &&
        last_master_pos_ <= master_start_position_ &&
        master_pos_ >= master_start_position_)
    {
      startGearProcess();
    }
    else if (master_vel_ < (-1) * vel_sync_factor_ &&
             last_master_pos_ >= master_start_position_ &&
             master_pos_ <= master_start_position_)
    {
      startGearProcess();
    }
  }

  if (axis_->getAxisState() == mcSynchronizedMotion)
  {
    if (in_sync_ == mcFALSE)
    {
      if (abs(master_pos_ - master_sync_position_) < pos_sync_factor_ &&
          abs(master_vel_ * ratio_numerator_ / ratio_denominator_ -
              slave_->toUserVelCmd()) < vel_sync_factor_)
      {
        in_sync_     = mcTRUE;
        velocity_    = master_vel_ * ratio_numerator_ / ratio_denominator_;
        buffer_mode_ = mcAborting;
        slave_->addFBToQueue(this, mcGearInMode);
      }

      if (master_start_position_ < master_sync_position_)
      {
        if (master_pos_ < master_start_position_ ||
            master_pos_ > (master_sync_position_ + pos_sync_factor_))
        {
          start_sync_ = mcFALSE;
          return mcErrorCodeGearInPosOutOfSyncRange;
        }
      }
      else
      {
        if (master_pos_ > master_start_position_ ||
            master_pos_ < (master_sync_position_ - pos_sync_factor_))
        {
          start_sync_ = mcFALSE;
          return mcErrorCodeGearInPosOutOfSyncRange;
        }
      }
    }
    else
    {
      velocity_    = master_vel_ * ratio_numerator_ / ratio_denominator_;
      buffer_mode_ = mcAborting;
      if (abs(velocity_ - slave_->toUserVel()) > vel_sync_factor_ &&
          done_ == mcTRUE)
        slave_->addFBToQueue(this, mcGearInMode);
    }
  }
  else
  {
    in_sync_ = mcFALSE;
  }

  last_master_pos_ = master_pos_;
  return mcErrorCodeGood;
}

MC_ERROR_CODE FbGearInPos::afterFallingEdgeExecution()
{
  if (slave_->getAxisState() == mcSynchronizedMotion)
  {
    in_sync_ =
        (abs(master_->toUserVel() * ratio_numerator_ / ratio_denominator_ -
             slave_->toUserVel()) < vel_sync_factor_) ?
            mcTRUE :
            mcFALSE;
  }
  else
  {
    in_sync_ = mcFALSE;
  }
  return error_id_;
}

void FbGearInPos::setMaster(AXIS_REF master)
{
  master_ = master;
}

void FbGearInPos::setSlave(AXIS_REF slave)
{
  slave_ = slave;
  axis_  = slave_;
}

void FbGearInPos::setRatioNumerator(mcINT ratio_numerator)
{
  ratio_numerator_ = ratio_numerator;
}

void FbGearInPos::setRatioDenominator(mcUINT ratio_denominator)
{
  ratio_denominator_ = ratio_denominator;
}

void FbGearInPos::setMasterSyncPosition(mcLREAL master_sync_position)
{
  master_sync_position_ = master_sync_position;
}

void FbGearInPos::setSlaveSyncPosition(mcLREAL slave_sync_position)
{
  slave_sync_position_ = slave_sync_position;
}

void FbGearInPos::setMasterStartDistance(mcLREAL master_start_distance)
{
  master_start_distance_ = master_start_distance;
}

void FbGearInPos::setPosSyncFactor(mcLREAL pos_sync_factor)
{
  pos_sync_factor_ = pos_sync_factor;
}

void FbGearInPos::setVelSyncFactor(mcLREAL vel_sync_factor)
{
  vel_sync_factor_ = vel_sync_factor;
}

AXIS_REF FbGearInPos::getMaster()
{
  return master_;
}

AXIS_REF FbGearInPos::getSlave()
{
  return slave_;
}

mcBOOL FbGearInPos::getStartSync()
{
  return start_sync_;
}

mcBOOL FbGearInPos::getInSync()
{
  return in_sync_;
}

MC_ERROR_CODE FbGearInPos::startGearProcess()
{
  start_sync_    = mcTRUE;
  slave_standby_ = mcFALSE;

  start_position_     = slave_->toUserPosCmd();
  start_velocity_     = slave_->toUserVelCmd() / master_vel_;
  start_acceleration_ = slave_->toUserAccCmd() / master_vel_ / master_vel_;
  this->setDuration(abs(master_sync_position_ - master_pos_));
  target_position_     = slave_sync_position_;
  target_velocity_     = (mcLREAL)ratio_numerator_ / ratio_denominator_;
  target_acceleration_ = 0;
  planner_type_        = mcPoly5;
  slave_->addFBToQueue(this, mcGearInPosMode);

  return mcErrorCodeGood;
}

}  // namespace RTmotion