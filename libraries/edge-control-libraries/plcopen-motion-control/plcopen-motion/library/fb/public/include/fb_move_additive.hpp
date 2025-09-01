// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_move_relative.hpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#pragma once

#include <fb/common/include/global.hpp>
#include <fb/common/include/fb_axis_motion.hpp>

#include <chrono>

namespace RTmotion
{
/**
 * @brief Function block MC_MoveAdditive
 */
class FbMoveAdditive : public FbAxisMotion
{
public:
  FbMoveAdditive();
  ~FbMoveAdditive() override = default;

  void setDistance(mcLREAL distance)
  {
    distance_ = distance;
  }

  MC_ERROR_CODE onRisingEdgeExecution() override;

private:
  VAR_INPUT mcLREAL& distance_ = position_;
};
}  // namespace RTmotion
