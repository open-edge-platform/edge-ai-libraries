// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file servo.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <fb/common/include/servo.hpp>

namespace RTmotion
{
Servo::Servo()
{
  // mImpl_ = new ServoImpl();
}

Servo::~Servo()
{
  // delete mImpl_;
}

MC_SERVO_ERROR_CODE Servo::setPower(mcBOOL /*powerStatus*/, mcBOOL& isDone)
{
  isDone = mcTRUE;
  return mcServoNoError;
}

MC_SERVO_ERROR_CODE Servo::setPos(mcDINT pos)
{
  mImpl_.mSubmitPos = pos;
  return mcServoNoError;
}

MC_SERVO_ERROR_CODE Servo::setVel(mcDINT vel)
{
  mImpl_.mVel = vel;
  return mcServoNoError;
}

MC_SERVO_ERROR_CODE Servo::setTorque(mcLREAL torque)
{
  mImpl_.mTorque = torque;
  return mcServoNoError;
}

MC_SERVO_ERROR_CODE Servo::setMaxProfileVel(mcDWORD vel)
{
  mImpl_.maxProfileVel = vel;
  return mcServoNoError;
}

MC_SERVO_ERROR_CODE Servo::setMode(mcSINT mode)
{
  mImpl_.mode = mode;
  return mcServoNoError;
}

MC_SERVO_ERROR_CODE Servo::setHomeEnable(mcBOOL enable)
{
  mImpl_.mHomeEnable = enable;
  return mcServoNoError;
}

mcDINT Servo::pos()
{
  return mImpl_.mPos;
}

mcDINT Servo::vel()
{
  return mImpl_.mVel;
}

mcDINT Servo::acc()
{
  return mImpl_.mAcc;
}

mcLREAL Servo::torque()
{
  return mImpl_.mTorque;
}

mcSINT Servo::mode()
{
  return mImpl_.mode;
}

mcBOOL Servo::getHomeState()
{
  return mImpl_.mHomeState;
}

mcBOOL Servo::readVal(mcDINT /*index*/, mcLREAL& /*value*/)
{
  return mcFALSE;
}

mcBOOL Servo::writeVal(mcDINT /*index*/, mcLREAL /*value*/)
{
  return mcFALSE;
}

mcBOOL Servo::readVal(mcUINT /*index*/, mcUSINT /*sub_index*/,
                      mcUSINT /*data_length*/, mcUDINT& /*value*/)
{
  return mcTRUE;
}

mcBOOL Servo::writeVal(mcUINT /*index*/, mcUSINT /*sub_index*/,
                       mcUSINT /*data_length*/, mcUDINT /*value*/)
{
  return mcTRUE;
}

MC_SERVO_ERROR_CODE Servo::resetError(mcBOOL& isDone)
{
  isDone = mcTRUE;
  return mcServoNoError;
}

void Servo::runCycle(mcLREAL freq)
{
  mcDINT pos_diff      = mImpl_.mSubmitPos - mImpl_.mPos;
  mcLREAL cur_vel      = pos_diff * freq;
  mImpl_.mAcc          = (cur_vel - mImpl_.mVel) * freq;
  mImpl_.mVel          = cur_vel;
  mImpl_.mPos          = mImpl_.mSubmitPos;
  mImpl_.mVirtualServo = mcTRUE;
  // printf("mImpl_.mSubmitPos: %d, mImpl_.mVel: %f, \n", mImpl_.mSubmitPos,
  // mImpl_.mVel);
}

void Servo::emergStop()
{
  mImpl_.mPos = mImpl_.mSubmitPos;
  mImpl_.mVel = mImpl_.mAcc = mImpl_.mTorque = 0;
}

mcBOOL Servo::getCommunicationReady()
{
  return mcFALSE;
}

mcBOOL Servo::getReadyForPowerOn()
{
  return mcFALSE;
}

mcBOOL Servo::isServoInSimulation()
{
  return mImpl_.mVirtualServo;
}
}  // namespace RTmotion
