// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_read_axis_info.cpp
 *
 * Maintainer: He Kanghua <kanghua.he@intel.com>
 *
 */

#include <fb/private/include/fb_read_axis_info.hpp>

namespace RTmotion
{
FbReadAxisInfo::FbReadAxisInfo()
{
}

mcBOOL FbReadAxisInfo::getAxisHomeAbsSwitch()
{
  return axis_->isAxisHomeAbsSwitchActive();
}

mcBOOL FbReadAxisInfo::getAxisLimitSwitchPos()
{
  return axis_->isAxisLimitSwitchPosActive();
}

mcBOOL FbReadAxisInfo::getAxisLimitSwitchNeg()
{
  return axis_->isAxisLimitSwitchNegActive();
}

mcBOOL FbReadAxisInfo::getAxisSimulation()
{
  return axis_->isAxisInSimulationMode();
}

mcBOOL FbReadAxisInfo::getAxisCommunicationReady()
{
  return axis_->isAxisCommunicationReady();
}

mcBOOL FbReadAxisInfo::getAxisReadyForPowerOn()
{
  return axis_->isAxisReadyForPowerOn();
}

mcBOOL FbReadAxisInfo::getAxisPowerOn()
{
  return axis_->powerOn();
}

mcBOOL FbReadAxisInfo::getAxisIsHomed()
{
  return axis_->getHomeState();
}

mcBOOL FbReadAxisInfo::getAxisWarning()
{
  return axis_->getAxisWarning();
}

}  // namespace RTmotion
