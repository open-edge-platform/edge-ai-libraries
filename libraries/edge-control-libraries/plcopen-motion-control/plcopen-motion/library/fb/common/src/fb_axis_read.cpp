// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_axis_read.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <fb/common/include/fb_axis_read.hpp>

namespace RTmotion
{
FbAxisRead::FbAxisRead() : value_(0)
{
}

mcLREAL FbAxisRead::getFloatValue()
{
  return value_;
}

mcLREAL FbAxisRead::getAxisValue()
{
  return value_;
}

MC_ERROR_CODE FbAxisRead::onExecution()
{
  if (axis_->getAxisState() == mcErrorStop)
  {
    value_    = 0;
    error_    = mcTRUE;
    valid_    = mcFALSE;
    error_id_ = axis_->getAxisError();
    return mcErrorCodeAxisErrorStop;
  }

  error_ = mcFALSE;
  valid_ = mcTRUE;
  value_ = getAxisValue();
  return mcErrorCodeGood;
}

MC_ERROR_CODE FbAxisRead::onFallingEdgeExecution()
{
  value_ = 0;
  return mcErrorCodeGood;
}

}  // namespace RTmotion
