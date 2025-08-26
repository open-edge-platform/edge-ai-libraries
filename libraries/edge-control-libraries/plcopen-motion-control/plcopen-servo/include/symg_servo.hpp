// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

#pragma once

#include <cstddef>
#include <cstdint>

#include <symg_config.hpp>

#include <fb/common/include/servo.hpp>
using namespace RTmotion;

#define EPSILON 0.00001

#pragma pack(push)
#pragma pack(4)

inline int64_t toDevRaw(double x)
{
  return (int64_t)(x * PER_CIRCLE_ENCODER);
}

inline double toSystemLogic(double x)
{
  return x / PER_CIRCLE_ENCODER;
}

class EcrtServo : public Servo
{
public:
  EcrtServo();
  ~EcrtServo() override;

  MC_SERVO_ERROR_CODE setPower(mcBOOL powerStatus, mcBOOL& isDone) override;
  MC_SERVO_ERROR_CODE setVel(mcDINT vel) override;
  mcDINT vel() override;
  MC_SERVO_ERROR_CODE resetError(mcBOOL& isDone) override;
  void runCycle(mcLREAL freq) override;
  void emergStop() override;

  void setDomain(mcUSINT* domain_pd)
  {
    domain_pd_ = domain_pd;
  }
  void setId(Wheel_Id id)
  {
    id_        = id;
    vel_scale_ = (id % 2) ? 1 : -1;
  }
  void setControlSlaveData(Ctrl_Data* ctrl, Slave_Data* slave)
  {
    ec_motor0_ = ctrl;
    ec_slave0_ = slave;
  }

private:
  class ServoImpl;
  ServoImpl* mImpl_;

  mcUSINT* domain_pd_;
  Slave_Data* ec_slave0_;
  Ctrl_Data* ec_motor0_;
  Wheel_Id id_;
  mcBOOL move_;
  mcDINT vel_cmd_;
  mcDINT vel_scale_;
};

#pragma pack(pop)
