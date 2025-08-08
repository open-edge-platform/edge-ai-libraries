// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_halt.hpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#pragma once

#include <fb/common/include/global.hpp>
#include <fb/common/include/fb_axis_motion.hpp>
#include <fb/common/include/planner.hpp>

#include <chrono>

namespace RTmotion
{
/**
 * @brief Function block MC_Halt
 */
class FbHalt : public FbAxisMotion
{
public:
  FbHalt();
  ~FbHalt() override = default;

  MC_ERROR_CODE onRisingEdgeExecution() override;

  void setDeceleration(mcLREAL deceleration) override;
};
}  // namespace RTmotion