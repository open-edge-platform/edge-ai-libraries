// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_gear_in.cpp
 *
 * Maintainer: Wu Xian <xian.wu@intel.com>
 *
 */

#include <fb/private/include/fb_gear_in.hpp>

namespace RTmotion
{
FbGearIn::FbGearIn()
  : master_()
  , slave_()
  , ratio_numerator_(0)
  , ratio_denominator_(0)
  , in_gear_(mcFALSE)
  , ratio_(0)
  , in_gear_threshold_(2)
{
}

FbGearIn::~FbGearIn()
{
  master_ = nullptr;
  slave_  = nullptr;
}

FbGearIn::FbGearIn(const FbGearIn& other)
  : ratio_numerator_(), ratio_denominator_(), in_gear_(mcFALSE), ratio_(0)
{
  master_            = other.master_;
  slave_             = other.slave_;
  in_gear_threshold_ = other.in_gear_threshold_;
}

FbGearIn& FbGearIn::operator=(const FbGearIn& other)
{
  if (this != &other)
  {
    master_            = other.master_;
    slave_             = other.slave_;
    ratio_numerator_   = other.ratio_numerator_;
    ratio_denominator_ = other.ratio_denominator_;
    in_gear_           = other.in_gear_;
    ratio_             = other.ratio_;
    in_gear_threshold_ = other.in_gear_threshold_;
  }
  return *this;
}

void FbGearIn::setMaster(AXIS_REF master)
{
  master_ = master;
}

void FbGearIn::setSlave(AXIS_REF slave)
{
  slave_ = slave;
  axis_  = slave;
}

void FbGearIn::setRatioNumerator(mcINT numerator)
{
  ratio_numerator_ = numerator;
}

void FbGearIn::setRatioDenominator(mcUINT denominator)
{
  /* check if input denominator is 0 */
  if (denominator == 0)
  {
    error_    = mcTRUE;
    error_id_ = mcErrorCodeGearRatioDenominatorSetZero;
    return;
  }
  ratio_denominator_ = denominator;
}

void FbGearIn::setInGearThreshold(mcREAL threshold)
{
  if (threshold < 0)
  {
    error_    = mcTRUE;
    error_id_ = mcErrorCodeInGearThresholdSetError;
    return;
  }
  in_gear_threshold_ = threshold;
}

mcBOOL FbGearIn::getInGear()
{
  return in_gear_;
}

MC_ERROR_CODE FbGearIn::onRisingEdgeExecution()
{
  if (acceleration_ == 0 || deceleration_ == 0 || jerk_ == 0)
    return mcErrorCodeMotionLimitUnset;

  /* change node buffer size to 3 in case of adding mcGearInMode and calling
   * FbGearOut in the same cycle*/
  axis_->setNodeQueueSize(3);

  ratio_   = ratio_numerator_ / ratio_denominator_;
  in_gear_ = mcFALSE;
  busy_ = active_ = mcTRUE;
  /* set slave velocity */
  velocity_    = master_->toUserVel() * ratio_;
  buffer_mode_ = mcAborting;
  axis_->addFBToQueue(this, mcGearInMode);
  axis_->setAxisState(mcSynchronizedMotion);

  return mcErrorCodeGood;
}

MC_ERROR_CODE FbGearIn::onExecution()
{
  /* check whether master/slave aixs has error */
  if (master_->getAxisError() != mcErrorCodeGood)
  {
    DEBUG_PRINT("GearIn: master axis error!\n");
    return master_->getAxisError();
  }
  if (slave_->getAxisError() != mcErrorCodeGood)
  {
    DEBUG_PRINT("GearIn: slave axis error! ErrorID:%d\n",
                slave_->getAxisError());
    return slave_->getAxisError();
  }
  /* check whether axis state of the slave is GearOut */
  if (slave_->getAxisState() != mcSynchronizedMotion)
  {
    in_gear_ = mcFALSE;
    return mcErrorCodeGood;
  }
  /* update slave velocity after previous node is done */
  if (done_ == mcTRUE)
  {
    velocity_    = master_->toUserVel() * ratio_;
    buffer_mode_ = mcAborting;
    axis_->addFBToQueue(this, mcGearInMode);
  }

  busy_ = active_ = mcTRUE;
  // check inGear
  in_gear_ = (abs(master_->toUserVel() * ratio_ - axis_->toUserVel()) <
              in_gear_threshold_) ?
                 mcTRUE :
                 mcFALSE;
  return mcErrorCodeGood;
}

MC_ERROR_CODE FbGearIn::afterFallingEdgeExecution()
{
  if (slave_->getAxisState() == mcSynchronizedMotion)
  {
    in_gear_ = (abs(master_->toUserVel() * ratio_ - axis_->toUserVel()) <
                in_gear_threshold_) ?
                   mcTRUE :
                   mcFALSE;
    busy_ = active_ = mcTRUE;
  }
  else
  {
    in_gear_ = busy_ = active_ = mcFALSE;
  }
  return error_id_;
}

}  // namespace RTmotion
