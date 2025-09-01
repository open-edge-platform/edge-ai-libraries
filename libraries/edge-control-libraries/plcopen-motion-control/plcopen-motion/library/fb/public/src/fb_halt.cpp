// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_halt.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <fb/public/include/fb_halt.hpp>

namespace RTmotion
{
FbHalt::FbHalt()
{
}

MC_ERROR_CODE FbHalt::onRisingEdgeExecution()
{
  if (acceleration_ == 0)
    return mcErrorCodeMotionLimitUnset;
  axis_->addFBToQueue(this, mcHaltMode);
  return mcErrorCodeGood;
}

void FbHalt::setDeceleration(mcLREAL deceleration)
{
  acceleration_ = deceleration;
}

}  // namespace RTmotion