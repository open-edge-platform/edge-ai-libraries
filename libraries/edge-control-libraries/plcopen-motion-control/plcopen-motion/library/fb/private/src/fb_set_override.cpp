// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_set_override.cpp
 *
 * Maintainer: Xian Wu <xian.wu@intel.com>
 *
 */

#include <fb/private/include/fb_set_override.hpp>

namespace RTmotion
{
FbSetOverride::FbSetOverride()
  : vel_factor_(1), acc_factor_(1), jerk_factor_(1), threshold_(0.01)
{
}

void FbSetOverride::setVelFactor(mcREAL vel_factor)
{
  vel_factor_ = vel_factor;
}

void FbSetOverride::setAccFactor(mcREAL acc_factor)
{
  acc_factor_ = acc_factor;
}

void FbSetOverride::setJerkFactor(mcREAL jerk_factor)
{
  jerk_factor_ = jerk_factor;
}

void FbSetOverride::setThreshold(mcREAL threshold)
{
  threshold_ = threshold;
}

MC_ERROR_CODE FbSetOverride::onExecution()
{
  // validate input factors
  if (vel_factor_ < 0 || vel_factor_ > 1)
  {
    return mcErrorCodeVelocityOverrideValueInvalid;
  }
  if (acc_factor_ <= 0 || acc_factor_ > 1)
  {
    return mcErrorCodeAccelerationOverrideValueInvalid;
  }
  if (jerk_factor_ <= 0 || jerk_factor_ > 1)
  {
    return mcErrorCodeJerkOverrideValueInvalid;
  }

  axis_->setAxisOverrideFactors(vel_factor_, acc_factor_, jerk_factor_,
                                threshold_);
  return mcErrorCodeGood;
}

}  // namespace RTmotion
