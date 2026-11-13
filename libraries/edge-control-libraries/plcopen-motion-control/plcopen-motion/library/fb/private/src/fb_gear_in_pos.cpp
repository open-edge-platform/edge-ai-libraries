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
  master_                  = other.master_;
  slave_                   = other.slave_;
  ratio_numerator_         = other.ratio_numerator_;
  ratio_denominator_       = other.ratio_denominator_;
  master_sync_position_    = other.master_sync_position_;
  slave_sync_position_     = other.slave_sync_position_;
  master_start_distance_   = other.master_start_distance_;
  start_sync_              = other.start_sync_;
  in_sync_                 = other.in_sync_;
  master_pos_              = other.master_pos_;
  last_master_pos_         = other.last_master_pos_;
  master_vel_              = other.master_vel_;
  synchronization_         = other.synchronization_;
  pending_synchronization_ = other.pending_synchronization_;
  pos_sync_factor_         = other.pos_sync_factor_;
  vel_sync_factor_         = other.vel_sync_factor_;
  slave_standby_           = other.slave_standby_;
  position_locked_         = other.position_locked_;
}

FbGearInPos& FbGearInPos::operator=(const FbGearInPos& other)
{
  if (this != &other)
  {
    master_                  = other.master_;
    slave_                   = other.slave_;
    ratio_numerator_         = other.ratio_numerator_;
    ratio_denominator_       = other.ratio_denominator_;
    master_sync_position_    = other.master_sync_position_;
    slave_sync_position_     = other.slave_sync_position_;
    master_start_distance_   = other.master_start_distance_;
    start_sync_              = other.start_sync_;
    in_sync_                 = other.in_sync_;
    master_pos_              = other.master_pos_;
    last_master_pos_         = other.last_master_pos_;
    master_vel_              = other.master_vel_;
    synchronization_         = other.synchronization_;
    pending_synchronization_ = other.pending_synchronization_;
    pos_sync_factor_         = other.pos_sync_factor_;
    vel_sync_factor_         = other.vel_sync_factor_;
    slave_standby_           = other.slave_standby_;
    position_locked_         = other.position_locked_;
  }
  return *this;
}

void FbGearInPos::runCycle()
{
  const mcBOOL was_active = active_;
  FbAxisMotion::runCycle();
  // The base rising-edge handler assumes immediate replacement. A pending
  // retrigger still owns its old node until the new boundary is reached.
  if (slave_standby_ == mcTRUE && busy_ == mcTRUE && error_ == mcFALSE &&
      was_active == mcTRUE)
    active_ = mcTRUE;
}

MC_ERROR_CODE FbGearInPos::onRisingEdgeExecution()
{
  if (!std::isfinite(velocity_) || !std::isfinite(acceleration_) ||
      !std::isfinite(deceleration_) || !std::isfinite(jerk_) ||
      velocity_ <= 0 || acceleration_ <= 0 || deceleration_ <= 0 || jerk_ <= 0)
    return mcErrorCodeMotionLimitError;
  if (ratio_denominator_ == 0)
    return mcErrorCodeGearRatioDenominatorSetZero;

  pending_synchronization_ = { static_cast<mcLREAL>(ratio_numerator_) /
                                   ratio_denominator_,
                               master_sync_position_, slave_sync_position_,
                               master_sync_position_ - master_start_distance_ };
  slave_standby_           = mcTRUE;
  master_pos_              = master_->toUserPosCmd();
  last_master_pos_         = master_pos_;
  master_vel_              = master_->toUserVelCmd();

  if (buffer_mode_ != mcAborting)
  {
    master_start_distance_ = 0;

    // TODO - handle non mcAborting buffer mode

    return mcErrorCodeUnsupportedBufferMode;
  }

  if (master_start_distance_ == 0)
  {
    return startGearProcess();
  }
  else
  {
    const mcLREAL start = pending_synchronization_.master_start_position;

    if (master_pos_ > start && master_pos_ < master_sync_position_)
    {
      if (master_vel_ > vel_sync_factor_)
      {
        return startGearProcess();
      }
      else
      {
        return mcErrorCodeGearInPosInvalidDirection;
      }
    }
    else if (master_pos_ < start && master_pos_ > master_sync_position_)
    {
      if (master_vel_ < (-1) * vel_sync_factor_)
      {
        return startGearProcess();
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
  if (master_->getAxisError() != mcErrorCodeGood)
    return master_->getAxisError();
  if (slave_->getAxisError() != mcErrorCodeGood)
    return slave_->getAxisError();
  if (command_aborted_ == mcTRUE || error_ == mcTRUE)
  {
    start_sync_ = in_sync_ = position_locked_ = slave_standby_ = mcFALSE;
    return mcErrorCodeGood;
  }
  if (active_ == mcFALSE && busy_ == mcFALSE)
    return mcErrorCodeGood;

  master_pos_ = master_->toUserPosCmd();
  master_vel_ = master_->toUserVelCmd();

  if (axis_->getAxisState() == mcStopping)
    slave_standby_ = mcFALSE;

  if (slave_standby_ == mcTRUE)
  {
    const mcLREAL start = pending_synchronization_.master_start_position;
    if ((master_vel_ > vel_sync_factor_ && last_master_pos_ <= start &&
         master_pos_ >= start) ||
        (master_vel_ < -vel_sync_factor_ && last_master_pos_ >= start &&
         master_pos_ <= start))
      return startGearProcess();
  }
  last_master_pos_ = master_pos_;

  if (position_locked_ == mcTRUE)
  {
    // InSync describes the commanded position relationship, not servo tracking.
    in_sync_ =
        (active_ == mcTRUE && slave_->getAxisState() == mcSynchronizedMotion &&
         fabs(slave_->getPosCmd() - getTargetPosition()) <= pos_sync_factor_ &&
         fabs(slave_->toUserVelCmd() - getTargetVelocity()) <=
             vel_sync_factor_) ?
            mcTRUE :
            mcFALSE;
    if (in_sync_ == mcTRUE)
      start_sync_ = mcFALSE;
    return mcErrorCodeGood;
  }
  if (active_ == mcTRUE && axis_->getAxisState() == mcSynchronizedMotion)
  {
    if (in_sync_ == mcFALSE)
    {
      const auto& sync = synchronization_;
      const bool reached_sync =
          sync.master_start_position < sync.master_sync_position ?
              master_pos_ >= sync.master_sync_position :
              master_pos_ <= sync.master_sync_position;
      if (reached_sync &&
          abs(master_vel_ * sync.ratio - slave_->toUserVelCmd()) <
              vel_sync_factor_ &&
          fabs(slave_->toUserPosCmd() -
               (sync.slave_sync_position +
                (master_pos_ - sync.master_sync_position) * sync.ratio)) <=
              pos_sync_factor_)
      {
        in_sync_         = mcTRUE;
        position_locked_ = mcTRUE;
        start_sync_      = mcFALSE;
        return mcErrorCodeGood;
      }

      if (sync.master_start_position < sync.master_sync_position)
      {
        if (master_pos_ < sync.master_start_position ||
            master_pos_ > (sync.master_sync_position + pos_sync_factor_))
        {
          start_sync_ = mcFALSE;
          return mcErrorCodeGearInPosOutOfSyncRange;
        }
      }
      else
      {
        if (master_pos_ > sync.master_start_position ||
            master_pos_ < (sync.master_sync_position - pos_sync_factor_))
        {
          start_sync_ = mcFALSE;
          return mcErrorCodeGearInPosOutOfSyncRange;
        }
      }
    }
  }
  else
  {
    in_sync_ = mcFALSE;
  }

  return mcErrorCodeGood;
}

MC_ERROR_CODE FbGearInPos::onFallingEdgeExecution()
{
  return onExecution();
}

MC_ERROR_CODE FbGearInPos::afterFallingEdgeExecution()
{
  return onExecution();
}

void FbGearInPos::onError(MC_ERROR_CODE error_code)
{
  FbAxisMotion::onError(error_code);
  start_sync_ = in_sync_ = position_locked_ = slave_standby_ = active_ = done_ =
      mcFALSE;
}

mcBOOL FbGearInPos::isPositionCoupled()
{
  return position_locked_;
}

void FbGearInPos::getMasterReference(mcLREAL& position, mcLREAL& velocity,
                                     mcLREAL& acceleration)
{
  const mcLREAL direction = synchronization_.master_sync_position >
                                    synchronization_.master_start_position ?
                                1 :
                                -1;
  position =
      (master_->toUserPosCmd() - synchronization_.master_start_position) *
      direction;
  velocity     = master_->toUserVelCmd() * direction;
  acceleration = master_->toUserAccCmd() * direction;
}

mcBOOL FbGearInPos::isReadyForBufferedHandoff()
{
  return in_sync_;
}

mcLREAL FbGearInPos::getTargetPosition()
{
  // Execution nodes use absolute coordinates; sync positions use user
  // coordinates.
  return position_locked_ == mcTRUE ?
             slave_->getHomePos() + synchronization_.slave_sync_position +
                 (master_->toUserPosCmd() -
                  synchronization_.master_sync_position) *
                     synchronization_.ratio :
             target_position_;
}

mcLREAL FbGearInPos::getTargetVelocity()
{
  return position_locked_ == mcTRUE ?
             master_->toUserVelCmd() * synchronization_.ratio :
             target_velocity_;
}

mcLREAL FbGearInPos::getTargetAcceleration()
{
  return position_locked_ == mcTRUE ?
             master_->toUserAccCmd() * synchronization_.ratio :
             target_acceleration_;
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
  position_locked_ = in_sync_ = mcFALSE;
  start_sync_                 = mcTRUE;
  slave_standby_              = mcFALSE;
  synchronization_            = pending_synchronization_;
  // The start-distance boundary can fall between two master samples.
  synchronization_.master_start_position = master_pos_;

  const mcLREAL direction =
      synchronization_.master_sync_position > master_pos_ ? 1 : -1;
  const mcLREAL reference_velocity = master_vel_ * direction;
  start_position_                  = slave_->toUserPosCmd();
  start_velocity_ = slave_->toUserVelCmd() / reference_velocity;
  start_acceleration_ =
      (slave_->toUserAccCmd() -
       start_velocity_ * master_->toUserAccCmd() * direction) /
      (reference_velocity * reference_velocity);
  this->setDuration(abs(synchronization_.master_sync_position - master_pos_));
  target_position_     = synchronization_.slave_sync_position;
  target_velocity_     = synchronization_.ratio * direction;
  target_acceleration_ = 0;
  planner_type_        = mcPoly5;
  syncStatus(mcFALSE, mcTRUE, mcFALSE, mcFALSE, mcFALSE, mcErrorCodeGood);
  slave_->addFBToQueue(this, mcGearInPosMode);
  if (slave_->getAxisError() != mcErrorCodeGood)
    return slave_->getAxisError();
  if (error_ == mcTRUE)
    return error_id_;
  // Replacing this FB's own node must not expose the old node's abort.
  syncStatus(mcFALSE, mcTRUE, mcFALSE, mcFALSE, mcFALSE, mcErrorCodeGood);
  return mcErrorCodeGood;
}

}  // namespace RTmotion