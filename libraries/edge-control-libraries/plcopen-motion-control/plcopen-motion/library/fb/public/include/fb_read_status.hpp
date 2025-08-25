// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_read_status.hpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#pragma once

#include <fb/common/include/fb_axis_read.hpp>

namespace RTmotion
{
/**
 * @brief Function block base for single axis motion
 */
class FbReadStatus : public FbAxisRead
{
public:
  FbReadStatus();
  ~FbReadStatus() override = default;

  mcBOOL isErrorStop();
  mcBOOL isDisabled();
  mcBOOL isStopping();
  mcBOOL isHoming();
  mcBOOL isStandStill();
  mcBOOL isDiscretMotion();
  mcBOOL isContinuousMotion();
  mcBOOL isSynchronizedMotion();

  MC_ERROR_CODE onExecution() override;

protected:
  VAR_OUTPUT mcBOOL error_stop_;
  VAR_OUTPUT mcBOOL disabled_;
  VAR_OUTPUT mcBOOL stopping_;
  VAR_OUTPUT mcBOOL homing_;
  VAR_OUTPUT mcBOOL standstill_;
  VAR_OUTPUT mcBOOL discrete_motion_;
  VAR_OUTPUT mcBOOL continuous_motion_;
  VAR_OUTPUT mcBOOL synchronized_motion_;
};
}  // namespace RTmotion
