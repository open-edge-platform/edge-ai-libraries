// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_reset.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <fb/public/include/fb_reset.hpp>

namespace RTmotion
{
MC_ERROR_CODE FbReset::onExecution()
{
  if (!axis_->getAxisError())
  {
    done_ = mcTRUE;
  }
  else
  {
    DEBUG_PRINT("FbReset::onExecution, reset error\n");
    axis_->resetError(enable_);

    if (axis_->powerTriggered() == mcTRUE && axis_->powerOn() == mcTRUE)
      if (axis_->getAxisState() == mcStandstill)
        done_ = mcTRUE;

    if (axis_->powerOn() == mcFALSE)
      if (axis_->getAxisState() == mcDisabled)
        done_ = mcTRUE;
  }

  return mcErrorCodeGood;
  ;
}

}  // namespace RTmotion
