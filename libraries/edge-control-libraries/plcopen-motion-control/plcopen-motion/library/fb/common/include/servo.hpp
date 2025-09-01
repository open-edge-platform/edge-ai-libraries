// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file servo.hpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#pragma once

#include <fb/common/include/global.hpp>

namespace RTmotion
{
class Servo
{
public:
  Servo();
  virtual ~Servo();
  virtual MC_SERVO_ERROR_CODE setPower(mcBOOL powerStatus, mcBOOL& isDone);
  virtual MC_SERVO_ERROR_CODE setPos(mcDINT pos);
  virtual MC_SERVO_ERROR_CODE setVel(mcDINT vel);
  virtual MC_SERVO_ERROR_CODE setTorque(mcLREAL torque);
  virtual MC_SERVO_ERROR_CODE setMaxProfileVel(mcDWORD vel);
  virtual MC_SERVO_ERROR_CODE setMode(mcSINT mode);
  virtual MC_SERVO_ERROR_CODE setHomeEnable(mcBOOL enable);
  virtual mcDINT pos();
  virtual mcDINT vel();
  virtual mcDINT acc();
  virtual mcLREAL torque();
  virtual mcSINT mode();
  virtual mcBOOL getHomeState();
  virtual mcBOOL readVal(mcDINT index, mcLREAL& value);
  virtual mcBOOL writeVal(mcDINT index, mcLREAL value);
  virtual mcBOOL readVal(mcUINT index, mcUSINT sub_index, mcUSINT data_length,
                         mcUDINT& value);
  virtual mcBOOL writeVal(mcUINT index, mcUSINT sub_index, mcUSINT data_length,
                          mcUDINT value);
  virtual MC_SERVO_ERROR_CODE resetError(mcBOOL& isDone);
  virtual void runCycle(mcLREAL freq);
  virtual void emergStop();
  virtual mcBOOL getCommunicationReady();
  virtual mcBOOL getReadyForPowerOn();
  virtual mcBOOL isServoInSimulation();

private:
  class ServoImpl
  {
  public:
    mcDINT mSubmitPos     = 0;
    mcDINT mPos           = 0;
    mcLREAL mVel          = 0;
    mcLREAL mAcc          = 0;
    mcLREAL mTorque       = 0;
    mcLREAL maxProfileVel = 0;
    mcSINT mode           = 0;
    mcBOOL mHomeEnable    = mcFALSE;
    mcBOOL mHomeState     = mcFALSE;
    mcBOOL mVirtualServo  = mcFALSE;
  };
  ServoImpl mImpl_;
};
}  // namespace RTmotion
