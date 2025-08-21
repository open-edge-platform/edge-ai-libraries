// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_set_position.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <fb/private/include/fb_set_position.hpp>

namespace RTmotion
{
FbSetPosition::FbSetPosition()
  : position_(0), mode_(mcSetPositionModeAbsolute), set_offset_ret_(mcFALSE)
{
}

MC_ERROR_CODE FbSetPosition::onRisingEdgeExecution()
{
  switch (mode_)
  {
    case mcSetPositionModeAbsolute:
      set_offset_ret_ = axis_->setHomePositionOffset(
          axis_->getPos() - (axis_->getHomePos() + position_));
      break;
    case mcSetPositionModeRelative:
      set_offset_ret_ = axis_->setHomePositionOffset(position_);
      break;
    default:
      break;
  }

  return mcErrorCodeGood;
}

MC_ERROR_CODE FbSetPosition::onExecution()
{
  if (set_offset_ret_ == mcTRUE)
    done_ = mcTRUE;
  return axis_->getAxisError();
}

void FbSetPosition::setPosition(mcLREAL position)
{
  position_ = position;
}

void FbSetPosition::setMode(MC_SET_POSITION_MODE mode)
{
  mode_ = mode;
}

}  // namespace RTmotion
