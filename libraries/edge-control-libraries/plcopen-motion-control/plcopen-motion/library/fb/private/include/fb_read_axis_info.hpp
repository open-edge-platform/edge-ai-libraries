// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_read_axis_info.hpp
 *
 * Maintainer: He Kanghua <kanghua.he@intel.com>
 *
 */

#pragma once

#include <fb/common/include/fb_axis_read.hpp>

namespace RTmotion
{
/**
 * @brief Function block base for single axis motion
 */
class FbReadAxisInfo : public FbAxisRead
{
public:
  FbReadAxisInfo();
  ~FbReadAxisInfo() override = default;

  mcBOOL getAxisHomeAbsSwitch();
  mcBOOL getAxisLimitSwitchPos();
  mcBOOL getAxisLimitSwitchNeg();
  mcBOOL getAxisSimulation();
  mcBOOL getAxisCommunicationReady();
  mcBOOL getAxisReadyForPowerOn();
  mcBOOL getAxisPowerOn();
  mcBOOL getAxisIsHomed();
  mcBOOL getAxisWarning();
};
}  // namespace RTmotion