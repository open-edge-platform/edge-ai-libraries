// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_read_status.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <fb/public/include/fb_read_status.hpp>

namespace RTmotion
{
FbReadStatus::FbReadStatus()
  : error_stop_(mcFALSE)
  , disabled_(mcFALSE)
  , stopping_(mcFALSE)
  , homing_(mcFALSE)
  , standstill_(mcFALSE)
  , discrete_motion_(mcFALSE)
  , continuous_motion_(mcFALSE)
  , synchronized_motion_(mcFALSE)
{
}

mcBOOL FbReadStatus::isErrorStop()
{
  return error_stop_;
}
mcBOOL FbReadStatus::isDisabled()
{
  return disabled_;
}
mcBOOL FbReadStatus::isStopping()
{
  return stopping_;
}
mcBOOL FbReadStatus::isHoming()
{
  return homing_;
}
mcBOOL FbReadStatus::isStandStill()
{
  return standstill_;
}
mcBOOL FbReadStatus::isDiscretMotion()
{
  return discrete_motion_;
}
mcBOOL FbReadStatus::isContinuousMotion()
{
  return continuous_motion_;
}
mcBOOL FbReadStatus::isSynchronizedMotion()
{
  return synchronized_motion_;
}

MC_ERROR_CODE FbReadStatus::onExecution()
{
  switch (axis_->getAxisState())
  {
    case mcErrorStop: {
      error_stop_ = mcTRUE;
      disabled_ = stopping_ = homing_ = standstill_ = discrete_motion_ =
          continuous_motion_ = synchronized_motion_ = mcFALSE;
    }
    break;
    case mcDisabled: {
      disabled_   = mcTRUE;
      error_stop_ = stopping_ = homing_ = standstill_ = discrete_motion_ =
          continuous_motion_ = synchronized_motion_ = mcFALSE;
    }
    break;
    case mcStopping: {
      stopping_   = mcTRUE;
      error_stop_ = disabled_ = homing_ = standstill_ = discrete_motion_ =
          continuous_motion_ = synchronized_motion_ = mcFALSE;
    }
    break;
    case mcHoming: {
      homing_     = mcTRUE;
      error_stop_ = disabled_ = stopping_ = standstill_ = discrete_motion_ =
          continuous_motion_ = synchronized_motion_ = mcFALSE;
    }
    break;
    case mcStandstill: {
      standstill_ = mcTRUE;
      error_stop_ = disabled_ = stopping_ = homing_ = discrete_motion_ =
          continuous_motion_ = synchronized_motion_ = mcFALSE;
    }
    break;
    case mcDiscreteMotion: {
      discrete_motion_ = mcTRUE;
      error_stop_ = disabled_ = stopping_ = homing_ = standstill_ =
          continuous_motion_ = synchronized_motion_ = mcFALSE;
    }
    break;
    case mcContinuousMotion: {
      continuous_motion_ = mcTRUE;
      error_stop_ = disabled_ = stopping_ = homing_ = standstill_ =
          discrete_motion_ = synchronized_motion_ = mcFALSE;
    }
    break;
    case mcSynchronizedMotion: {
      synchronized_motion_ = mcTRUE;
      error_stop_ = disabled_ = stopping_ = homing_ = standstill_ =
          discrete_motion_ = continuous_motion_ = mcFALSE;
    }
    break;
    default:
      break;
  }

  return mcErrorCodeGood;
}

}  // namespace RTmotion
