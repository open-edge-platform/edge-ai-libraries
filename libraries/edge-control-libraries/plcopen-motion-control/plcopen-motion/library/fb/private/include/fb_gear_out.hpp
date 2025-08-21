// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_gear_out.hpp
 *
 * Maintainer: Wu Xian <wu.xian@intel.com>
 *
 */

#pragma once

#include <fb/common/include/global.hpp>
#include <fb/common/include/fb_axis_motion.hpp>

namespace RTmotion
{
/**
 * @brief Function block MC_GearOut
 */
class FbGearOut : public FbAxisMotion
{
public:
  FbGearOut()           = default;
  ~FbGearOut() override = default;

  void setSlave(AXIS_REF slave);

  MC_ERROR_CODE onRisingEdgeExecution() override;
  MC_ERROR_CODE onExecution() override;
};
}  // namespace RTmotion