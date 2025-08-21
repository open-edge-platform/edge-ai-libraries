// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_stop.hpp
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
 * @brief Function block MC_Stop
 */
class FbStop : public FbAxisMotion
{
public:
  FbStop();
  ~FbStop() override = default;

  MC_ERROR_CODE onRisingEdgeExecution() override;

  MC_ERROR_CODE onFallingEdgeExecution() override;

  void setDeceleration(mcLREAL deceleration) override;
};
}  // namespace RTmotion