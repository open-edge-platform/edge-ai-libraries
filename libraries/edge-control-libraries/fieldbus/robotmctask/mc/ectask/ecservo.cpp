// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
#include "ecservo.h"
#define CONVEYOR_RATIO (2.0 * M_PI)

static uint32_t cycle_count =0;
EcServo::EcServo(servo_master* master, uint32_t id, bool use_virtual)
{
    if(!use_virtual)
    {
        servo_sc.setMaster(master);
        void* domain = motion_servo_get_domain_by_master(master->master);
        servo_sc.setDomain((mcUSINT*)motion_servo_domain_data(domain));
        servo_sc.initialize(0, id);
        servo = (Servo*)&servo_sc;
    }
    else
    {
        servo = new Servo();
    }
    config.encoder_count_per_unit_ = (1<<18) * 1.0/ CONVEYOR_RATIO;
    config.frequency_ = 1.0/1000 * 1000000;
    sc_enable = 1;

    axis.setAxisId(id);
    axis.setAxisConfig(&config);
    axis.setServo(servo);

    fbPower.setAxis(&axis);
    fbPower.setEnable(mcTRUE);
    fbPower.setEnablePositive(mcTRUE);
    fbPower.setEnableNegative(mcTRUE);

    readPos.setAxis(&axis);
    readPos.setEnable(mcTRUE);

    readVel.setAxis(&axis);
    readVel.setEnable(mcTRUE);

    readAcc.setAxis(&axis);
    readAcc.setEnable(mcTRUE);

    readToq.setAxis(&axis);
    readToq.setEnable(mcTRUE);
    
    fb_set_position.setAxis(&axis);
    fb_set_position.setMode(mcSetPositionModeRelative);
    fb_set_position.setEnable(mcFALSE);

    moveAbs.setAxis(&axis);
    moveAbs.setPosition(0.0);
    moveAbs.setVelocity(0.5); // 2.618
    moveAbs.setAcceleration(1.0); // 1.0
    moveAbs.setDeceleration(1.0); // 1.0
    moveAbs.setJerk(50.0);
    moveAbs.setBufferMode(RTmotion::mcAborting);

    fb_set_controller_mode.setAxis(&axis);
    fb_set_controller_mode.setEnable(mcFALSE);
    home_pos_radian = 0;
}

EcServo::~EcServo()
{
    if (servo)
    {
        delete []servo;
    }
}

void EcServo::SlaveSetEnable(bool enable)
{
    sc_enable = enable;
}

bool EcServo::SlaveGetEnable()
{
    return sc_enable;
}

void EcServo::UpdateServoConfig(unsigned long encode_accuracy, float gear_ratio, unsigned long cycle_us)
{
    config.encoder_count_per_unit_ = encode_accuracy * gear_ratio/ CONVEYOR_RATIO;
    config.frequency_ = 1.0/cycle_us * 1000000;
}

void EcServo::SlaveSetHomePosRadian(mcLREAL radian)
{
    home_pos_radian = radian;
}

mcLREAL EcServo::SlaveGetHomePosRadian()
{
    return home_pos_radian;
}

mcLREAL EcServo::getHomePos()
{
    return axis.getHomePos();
}

mcLREAL EcServo::getActPos()
{
    return readPos.getFloatValue();
}

mcLREAL EcServo::getActVel()
{
    return readVel.getFloatValue();
}

mcLREAL EcServo::getActAcc()
{
    return readAcc.getFloatValue();
}

mcLREAL EcServo::getActToq()
{
    return readToq.getFloatValue();
}

bool EcServo::SlavePowerGetStatus()
{
    if (fbPower.getPowerStatus() == mcTRUE)
    {
        return true;
    }
    else
    {
        return false;
    }
}

void EcServo::processRxFrames()
{
    axis.runCycle();
    fbPower.runCycle();
    fb_set_position.runCycle();
    fb_set_controller_mode.runCycle();
    readPos.runCycle();
    readVel.runCycle();
    readAcc.runCycle();
    readToq.runCycle();
}

void EcServo::processTxFrames()
{

}

void EcServo::setAbsPosition(mcLREAL position)
{
    moveAbs.setExecute(mcFALSE);
    moveAbs.runCycle();
    moveAbs.setPosition(position);
    moveAbs.setExecute(mcTRUE);
    moveAbs.runCycle();
}

void EcServo::setPosition(mcLREAL position)
{
    fb_set_position.setPosition(position);
    fb_set_position.setEnable(mcTRUE);
}

void EcServo::EnableSlavePowerMode()
{
    if (fb_set_controller_mode.isEnabled() == mcFALSE)
    {
        fb_set_controller_mode.setMode(mcServoControlModePosition);
        fb_set_controller_mode.setEnable(mcTRUE);
    }
}

void EcServo::setMoveExecute(bool on)
{
    if(on)
        moveAbs.setExecute(mcTRUE);
    else
        moveAbs.setExecute(mcFALSE);
}

bool EcServo::is_TrajDone()
{
    return (moveAbs.isDone() == mcTRUE);
}

bool EcServo::is_ControllerModeDone()
{
    return (fb_set_controller_mode.isDone() == mcTRUE);
}

bool EcServo::is_SetPositionDone()
{
    return (fb_set_position.isDone() == mcTRUE);
}

bool EcServo::is_SetPositionEnable()
{
    return (fb_set_position.isEnabled() == mcTRUE);
}
