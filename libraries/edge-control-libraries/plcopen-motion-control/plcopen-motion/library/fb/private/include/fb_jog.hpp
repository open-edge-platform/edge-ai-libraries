// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_jog.hpp
 *
 * Maintainer: Kanghua He <kanghua.he@intel.com>
 *
 */

#pragma once

#include <fb/common/include/global.hpp>
#include <fb/common/include/fb_axis_motion.hpp>

#include <chrono>

namespace RTmotion
{
/**
 * @brief Function block MC_Jog
 */
class FbJog : public FbAxisMotion
{
public:
  FbJog();
  ~FbJog() override = default;

  typedef enum
  {
    mcJogStill = 0,
    mcJogForward,
    mcJogBackward,
    mcJogHalt
  } MC_JOG_STATE;

  virtual void setJogForwardSignal(mcBOOL signal);
  virtual void setJogBackwardSignal(mcBOOL signal);

  MC_ERROR_CODE onExecution() override;

private:
  VAR_INPUT mcBOOL jog_forward_;
  VAR_INPUT mcBOOL jog_backward_;

  MC_JOG_STATE jog_state_ = mcJogStill;
};
}  // namespace RTmotion