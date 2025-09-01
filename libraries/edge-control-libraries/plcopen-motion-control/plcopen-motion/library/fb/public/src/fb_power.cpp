// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_power.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <fb/public/include/fb_power.hpp>

namespace RTmotion
{
FbPower::FbPower() : enable_positive_(mcFALSE), enable_negative_(mcFALSE)
{
}

void FbPower::setEnablePositive(mcBOOL enable_positive)
{
  enable_positive_ = enable_positive;
}

void FbPower::setEnableNegative(mcBOOL enable_negative)
{
  enable_negative_ = enable_negative;
}

mcBOOL FbPower::getPowerStatus()
{
  return axis_->powerOn();
}

MC_ERROR_CODE FbPower::onExecution()
{
  axis_->setPower(enable_, enable_positive_, enable_negative_);
  valid_ = axis_->powerTriggered();

  return axis_->getAxisError();
}

MC_ERROR_CODE FbPower::onFallingEdgeExecution()
{
  axis_->setPower(enable_, enable_positive_, enable_negative_);
  return axis_->getAxisError();
}

}  // namespace RTmotion
