// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
#pragma once

#include <ecrt_servo.hpp>
#include <fb/common/include/axis.hpp>
#include <fb/public/include/fb_power.hpp>
#include <fb/public/include/fb_read_actual_position.hpp>
#include <fb/public/include/fb_read_actual_velocity.hpp>
#include <fb/public/include/fb_read_actual_acceleration.hpp>
#include <fb/private/include/fb_read_actual_torque.hpp>
#include <fb/private/include/fb_set_position.hpp>
#include <fb/public/include/fb_move_absolute.hpp>
#include <fb/private/include/fb_set_controller_mode.hpp>


class EcServo
{
public:
    EcServo(servo_master* master, uint32_t id, bool use_virtual);
    virtual ~EcServo();

    void processRxFrames();
    void processTxFrames();
    bool SlavePowerGetStatus();
    void setPosition(mcLREAL position);
    bool is_TrajDone();
    void EnableSlavePowerMode();
    bool is_ControllerModeDone();
    void SlaveSetHomePosRadian(mcLREAL radian);
    mcLREAL SlaveGetHomePosRadian();
    mcLREAL getHomePos();
    bool is_SetPositionDone();
    void setMoveExecute(bool on);
    bool is_SetPositionEnable();
    void setAbsPosition(mcLREAL position);
    void UpdateServoConfig(unsigned long encode_accuracy, float gear_ratio, unsigned long cycle_us);
    void SlaveSetEnable(bool enable);
    bool SlaveGetEnable();

    mcLREAL getActPos();
    mcLREAL getActVel();
    mcLREAL getActAcc();
    mcLREAL getActToq();

private:
    Servo* servo;
    bool sc_enable;
    EcrtServo servo_sc;
    AxisConfig config;
    Axis axis;
    FbPower fbPower;
    FbReadActualPosition readPos;
    FbReadActualVelocity readVel;
    FbReadActualAcceleration readAcc;
    FbReadActualTorque readToq;
    FbSetPosition fb_set_position;
    FbMoveAbsolute moveAbs;
    FbSetControllerMode fb_set_controller_mode;
    mcLREAL home_pos_radian;
};
