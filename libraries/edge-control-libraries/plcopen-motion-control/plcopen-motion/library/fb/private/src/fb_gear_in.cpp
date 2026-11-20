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

mcBOOL FbGearIn::isReadyForBufferedHandoff()
{
  // Keep command following independent of the feedback-based public output.
  return in_gear_;
}

mcLREAL FbGearIn::getVelocity()
{
  // The execution node samples the live master target, not a queued snapshot.
  return master_->toUserVel() * ratio_;
}

MC_ERROR_CODE FbGearIn::onRisingEdgeExecution()
{
  if (ratio_denominator_ == 0)
    return mcErrorCodeGearRatioDenominatorSetZero;
  if (acceleration_ == 0 || deceleration_ == 0 || jerk_ == 0)
    return mcErrorCodeMotionLimitUnset;

  // Convert before division so fractional and negative ratios are preserved.
  ratio_   = static_cast<mcLREAL>(ratio_numerator_) / ratio_denominator_;
  in_gear_ = mcFALSE;
  busy_ = active_ = mcTRUE;
  // Retain aborting-only engagement; successors may be buffered after InGear.
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
  if (command_aborted_ == mcTRUE || error_ == mcTRUE ||
      slave_->getAxisState() != mcSynchronizedMotion)
  {
    in_gear_ = mcFALSE;
    return mcErrorCodeGood;
  }
  // check inGear
  in_gear_ = (active_ == mcTRUE &&
              fabs(getVelocity() - axis_->toUserVel()) < in_gear_threshold_) ?
                 mcTRUE :
                 mcFALSE;
  return mcErrorCodeGood;
}

MC_ERROR_CODE FbGearIn::onFallingEdgeExecution()
{
  // Execute falling does not stop gearing or defer axis-error detection.
  return onExecution();
}

MC_ERROR_CODE FbGearIn::afterFallingEdgeExecution()
{
  return onExecution();
}

void FbGearIn::onError(MC_ERROR_CODE error_code)
{
  FbAxisMotion::onError(error_code);
  // Axis errors can arrive before the execution node publishes its status.
  in_gear_ = active_ = done_ = command_aborted_ = mcFALSE;
}

}  // namespace RTmotion
