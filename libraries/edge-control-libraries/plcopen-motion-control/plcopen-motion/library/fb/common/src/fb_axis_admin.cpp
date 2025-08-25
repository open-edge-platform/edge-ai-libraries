// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_axis_admin.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <fb/common/include/fb_axis_admin.hpp>

namespace RTmotion
{
FbAxisAdmin::FbAxisAdmin()
  : enable_(mcFALSE)
  , done_(mcFALSE)
  , valid_(mcFALSE)
  , busy_(mcFALSE)
  , error_(mcFALSE)
  , error_id_(mcErrorCodeGood)
  , enabled_(mcFALSE)
{
}

void FbAxisAdmin::setEnable(mcBOOL enable)
{
  enable_ = enable;
}

mcBOOL FbAxisAdmin::isEnabled()
{
  return enable_;
}

mcBOOL FbAxisAdmin::isDone()
{
  return done_;
}

mcBOOL FbAxisAdmin::isValid()
{
  return valid_;
}

mcBOOL FbAxisAdmin::isBusy()
{
  return busy_;
}

mcBOOL FbAxisAdmin::isError()
{
  return axis_->getAxisError() != mcErrorCodeGood ? mcTRUE : mcFALSE;
}

MC_ERROR_CODE FbAxisAdmin::getErrorID()
{
  return axis_->getAxisError();
}

void FbAxisAdmin::runCycle()
{
  if (enable_ == mcTRUE && enabled_ == mcFALSE)  // `enable` rising edge
  {
    MC_ERROR_CODE err = onRisingEdgeExecution();
    if (err)
      onError(err);
    else
    {
      done_ = error_ = mcFALSE;
      valid_ = busy_ = mcTRUE;
    }

    DEBUG_PRINT("FbAxisAdmin::runCycle %s\n", "rising edge");
  }
  else if (enable_ == mcTRUE && enabled_ == mcTRUE)  // `enable` hold high value
  {
    MC_ERROR_CODE err = onExecution();
    if (err)
      onError(err);

    DEBUG_PRINT("FbAxisAdmin::runCycle %s\n", "hold high value");
  }
  else if (enable_ == mcFALSE && enabled_ == mcTRUE)  // `enable` falling edge
  {
    MC_ERROR_CODE err = onFallingEdgeExecution();
    if (err)
      onError(err);
    else
    {
      done_ = busy_ = valid_ = error_ = mcFALSE;
      error_id_                       = mcErrorCodeGood;
    }

    DEBUG_PRINT("FbAxisAdmin::runCycle %s\n", "falling edge");
  }  // `Execute` hold low value
  else
  {
    done_ = busy_ = valid_ = error_ = mcFALSE;
    error_id_                       = mcErrorCodeGood;
    DEBUG_PRINT("FbAxisMotion::runCycle %s\n", "hold low value");
  }

  enabled_ = enable_;
}

void FbAxisAdmin::onError(MC_ERROR_CODE error_code)
{
  busy_     = mcFALSE;
  error_    = mcTRUE;
  error_id_ = error_code;
}

}  // namespace RTmotion
