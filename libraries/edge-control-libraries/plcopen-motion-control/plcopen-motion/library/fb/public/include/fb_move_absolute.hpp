// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_move_absolute.hpp
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
 * @brief Function block MC_MoveAbsolute
 */
class FbMoveAbsolute : public FbAxisMotion
{
public:
  FbMoveAbsolute();
  ~FbMoveAbsolute() override = default;

  MC_ERROR_CODE onRisingEdgeExecution() override;
};
}  // namespace RTmotion
