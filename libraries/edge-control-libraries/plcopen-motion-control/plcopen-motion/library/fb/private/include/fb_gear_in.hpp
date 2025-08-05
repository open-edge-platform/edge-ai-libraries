// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_gear_in.hpp
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
 * @brief Function block MC_GearIn
 */
class FbGearIn : public FbAxisMotion
{
public:
  FbGearIn();
  ~FbGearIn() override;
  FbGearIn(const FbGearIn& other);
  FbGearIn& operator=(const FbGearIn& other);

  void setMaster(AXIS_REF master);
  void setSlave(AXIS_REF slave);
  void setRatioNumerator(mcINT numerator);
  void setRatioDenominator(mcUINT denominator);
  void setInGearThreshold(mcREAL threshold);

  mcBOOL getInGear();

  MC_ERROR_CODE onRisingEdgeExecution() override;
  MC_ERROR_CODE onExecution() override;
  MC_ERROR_CODE afterFallingEdgeExecution() override;

protected:
  VAR_IN_OUT AXIS_REF master_;
  VAR_IN_OUT AXIS_REF slave_;

  VAR_INPUT mcINT ratio_numerator_;
  VAR_INPUT mcUINT ratio_denominator_;

  VAR_OUTPUT mcBOOL in_gear_;

private:
  mcREAL ratio_;
  mcREAL in_gear_threshold_;
};
}  // namespace RTmotion