// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file fb_jog.cpp
 *
 * Maintainer: He Kanghua <kanghua.he@intel.com>
 *
 */

#include <fb/private/include/fb_jog.hpp>

namespace RTmotion
{
FbJog::FbJog() : jog_forward_(mcFALSE), jog_backward_(mcFALSE)
{
  this->setBufferMode(mcAborting);
}

void FbJog::setJogForwardSignal(mcBOOL signal)
{
  jog_forward_ = signal;
}

void FbJog::setJogBackwardSignal(mcBOOL signal)
{
  jog_backward_ = signal;
}

MC_ERROR_CODE FbJog::onExecution()
{
  switch (jog_state_)
  {
    case mcJogStill: {
      if ((jog_forward_ == mcTRUE) && (jog_backward_ == mcFALSE))
      {
        jog_state_ = mcJogForward;
        busy_      = mcTRUE;
        this->setVelocity(this->getVelocity());
        axis_->addFBToQueue(this, mcMoveVelocityMode);
      }
      if ((jog_forward_ == mcFALSE) && (jog_backward_ == mcTRUE))
      {
        jog_state_ = mcJogBackward;
        busy_      = mcTRUE;
        this->setVelocity((-1) * this->getVelocity());
        axis_->addFBToQueue(this, mcMoveVelocityMode);
      }
    }
    break;
    case mcJogForward: {
      done_ = mcFALSE;
      if ((jog_forward_ == mcFALSE) || (jog_backward_ == mcTRUE))
      {
        jog_state_ = mcJogHalt;
        axis_->addFBToQueue(this, mcHaltMode);
      }
    }
    break;
    case mcJogBackward: {
      done_ = mcFALSE;
      if ((jog_forward_ == mcTRUE) || (jog_backward_ == mcFALSE))
      {
        jog_state_ = mcJogHalt;
        axis_->addFBToQueue(this, mcHaltMode);
      }
    }
    break;
    case mcJogHalt: {
      if (axis_->getAxisState() == mcStandstill)
      {
        jog_state_ = mcJogStill;
        busy_      = mcFALSE;
        done_      = mcTRUE;
      }
      else
        done_ = mcFALSE;
    }
    break;
  }
  return axis_->getAxisError();
}

}  // namespace RTmotion
