// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file function_block_test.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <thread>
#include "gtest/gtest.h"
#include <fb/common/include/axis.hpp>
#include <fb/common/include/global.hpp>
#include <fb/public/include/fb_move_relative.hpp>
#include <fb/public/include/fb_move_velocity.hpp>
#include <fb/public/include/fb_move_absolute.hpp>
#include <fb/public/include/fb_move_additive.hpp>
#include <fb/public/include/fb_halt.hpp>
#include <fb/public/include/fb_stop.hpp>
#include <fb/public/include/fb_homing.hpp>
#include <fb/public/include/fb_power.hpp>
#include <fb/private/include/fb_set_position.hpp>
#include <fb/public/include/fb_read_actual_position.hpp>
#include <fb/private/include/fb_jog.hpp>
#include <fb/private/include/fb_cam_in.hpp>
#include <fb/private/include/fb_cam_out.hpp>
#include <fb/private/include/fb_cam_ref.hpp>
#include <fb/private/include/fb_cam_table_select.hpp>
#include <fb/private/include/fb_gear_in.hpp>
#include <fb/private/include/fb_gear_out.hpp>
#include <fb/private/include/fb_gear_in_pos.hpp>
#include <fb/private/include/fb_read_motion_state.hpp>
#include <fb/private/include/fb_set_override.hpp>
#include <fb/private/include/fb_move_superimposed.hpp>
#include <fb/private/include/fb_digital_cam_switch.hpp>

#ifdef PLOT
#include <tool/fb_debug_tool.hpp>
#endif

using namespace RTmotion;

class FunctionBlockTest : public ::testing::Test
{
protected:
  // You can remove any or all of the following functions if their bodies would
  // be empty.

  FunctionBlockTest()
  {
    // You can do set-up work for each test here.
  }

  ~FunctionBlockTest() override
  {
    // You can do clean-up work that doesn't throw exceptions here.
  }

  // If the constructor and destructor are not enough for setting up
  // and cleaning up each test, you can define the following methods:

  void SetUp() override
  {
    // Code here will be called immediately after the constructor (right
    // before each test).
  }

  void TearDown() override
  {
    // Code here will be called immediately after each test (right
    // before the destructor).
  }
#ifdef PLOT
  AxisProfile axis_profile_;
  FBDigitalProfile fb_profile_;
#endif
};

// Test MC_MoveRelative
TEST_F(FunctionBlockTest, DemoRelative)
{
#ifdef PLOT
  fb_profile_.reset();
  axis_profile_.reset();
#endif

  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbMoveRelative fb_move_rel;
  fb_move_rel.setAxis(axis);
  fb_move_rel.setExecute(mcFALSE);
  fb_move_rel.setContinuousUpdate(mcFALSE);
  fb_move_rel.setDistance(3.14);
  fb_move_rel.setVelocity(1.57);
  fb_move_rel.setAcceleration(3.14);
  fb_move_rel.setDeceleration(3.14);
  fb_move_rel.setJerk(50);
  printf("Function block initialized.\n");

  double timeout = 0;
  while (fb_move_rel.isDone() == mcFALSE && timeout < 5)
  {
    axis->runCycle();
    fb_power.runCycle();
    fb_move_rel.runCycle();
    timeout += 0.001;
#ifdef PLOT
    axis_profile_.addState(axis->toUserPos(), axis->toUserVel(),
                           axis->toUserAccCmd(), timeout);
#endif

    if (fb_move_rel.isEnabled() == mcFALSE &&
        fb_power.getPowerStatus() == mcTRUE)
    {
      fb_move_rel.setExecute(mcTRUE);
      // printf("Axis powered on %d\n", fb_power.getPowerStatus() == mcTRUE);
    }

    // printf("Run time: %f, pos: %lf, vel: %lf\n", timeout, axis->toUserPos(),
    //        axis->toUserVel());
  }
#ifdef PLOT
  axis_profile_.plot("DemoRelative.png");
#endif
  ASSERT_TRUE(fb_move_rel.isDone() == mcTRUE);
  ASSERT_LT(fabs(axis->toUserPos() - 3.14), 0.01);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_MoveVelocity
TEST_F(FunctionBlockTest, DemoVelocity)
{
#ifdef PLOT
  fb_profile_.reset();
  axis_profile_.reset();
#endif

  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbMoveVelocity fb_move_vel;
  fb_move_vel.setAxis(axis);
  fb_move_vel.setExecute(mcFALSE);
  fb_move_vel.setContinuousUpdate(mcFALSE);
  fb_move_vel.setVelocity(1.57);
  fb_move_vel.setAcceleration(3.14);
  fb_move_vel.setDeceleration(3.14);
  fb_move_vel.setJerk(50);
  printf("Function block initialized.\n");

  double timeout = 0;
  while (fb_move_vel.isInVelocity() == mcFALSE && timeout < 5.0)
  {
    axis->runCycle();
    fb_power.runCycle();
    fb_move_vel.runCycle();
    timeout += 0.001;

#ifdef PLOT
    axis_profile_.addState(axis->toUserPos(), axis->toUserVel(),
                           axis->toUserAccCmd(), timeout);
#endif

    if (fb_move_vel.isEnabled() == mcFALSE &&
        fb_power.getPowerStatus() == mcTRUE)
    {
      fb_move_vel.setExecute(mcTRUE);
      // printf("Axis powered on %d\n", fb_power.getPowerStatus() == mcTRUE);
    }

    // printf("Run time: %f, pos: %lf, vel: %lf\n", timeout, axis->toUserPos(),
    //         axis->toUserVel());
  }
#ifdef PLOT
  axis_profile_.plot("DemoVelocity.png");
#endif
  ASSERT_TRUE(fb_move_vel.isInVelocity() == mcTRUE);
  ASSERT_LT(fabs(axis->toUserVel() - 1.57), 0.01);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_Stop
TEST_F(FunctionBlockTest, MC_Stop)
{
#ifdef PLOT
  fb_profile_.reset();
  axis_profile_.reset();
#endif

  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbMoveVelocity move_vel;
  move_vel.setAxis(axis);
  move_vel.setVelocity(50);
  move_vel.setAcceleration(10);
  move_vel.setDeceleration(10);
  move_vel.setJerk(5000);
  move_vel.setBufferMode(mcAborting);

  FbStop stop;
  stop.setAxis(axis);
  stop.setAcceleration(20);
  stop.setDeceleration(20);
  stop.setJerk(5000);
#ifdef PLOT
  fb_profile_.addFB("mov_vel");
  fb_profile_.addFB("stop");
  fb_profile_.addItemName("mov_vel.execute");
  fb_profile_.addItemName("mov_vel.inVel");
  fb_profile_.addItemName("mov_vel.abort");
  fb_profile_.addItemName("mov_vel.error");
  fb_profile_.addItemName("stop.execute");
  fb_profile_.addItemName("stop.done");
#endif
  double time_out = 25;
  double t        = 0;
  while (t < time_out)
  {
    axis->runCycle();
    fb_power.runCycle();
    move_vel.runCycle();
    stop.runCycle();

    if (move_vel.isEnabled() == mcFALSE && t < 7.5)
    {  //使能成功后move1开始移动
      std::cout << "axis poweron, mov_vel start" << std::endl;
      move_vel.setExecute(mcTRUE);
    }

    if (6 < t && t < 12.5 && stop.isEnabled() == mcFALSE)
      stop.setExecute(mcTRUE);

    if (12.5 < t && stop.isEnabled() == mcTRUE)
      stop.setExecute(mcFALSE);

    if (7.5 < t && t < 10 && move_vel.isEnabled() == mcTRUE)
      move_vel.setExecute(mcFALSE);

    if (10 < t && t < 15 && move_vel.isEnabled() == mcFALSE)
      move_vel.setExecute(mcTRUE);

    if (15 < t && t < 20 && move_vel.isEnabled() == mcTRUE)
      move_vel.setExecute(mcFALSE);

    if (17.5 < t && move_vel.isEnabled() == mcFALSE)
      move_vel.setExecute(mcTRUE);
#ifdef PLOT
    axis_profile_.addState(axis->toUserPos(), axis->toUserVel(),
                           axis->toUserAccCmd(), t);
    fb_profile_.addState("mov_vel.execute", move_vel.isEnabled() == mcTRUE);
    fb_profile_.addState("mov_vel.inVel", move_vel.isInVelocity() == mcTRUE);
    fb_profile_.addState("mov_vel.abort", move_vel.isAborted() == mcTRUE);
    fb_profile_.addState("mov_vel.error", move_vel.isError() == mcTRUE);
    fb_profile_.addState("stop.execute", stop.isEnabled() == mcTRUE);
    fb_profile_.addState("stop.done", stop.isDone() == mcTRUE);
    fb_profile_.addTime(t);
#endif
    // printf("Run time: %f, pos: %f, vel: %f\n", t, axis->toUserPos(),
    // axis->toUserVel());
    t += 0.001;
  }
#ifdef PLOT
  axis_profile_.plot("mc_stop_axis.png");
  fb_profile_.plot("mc_stop_fb.png");
#endif
  ASSERT_TRUE(move_vel.isInVelocity() == mcTRUE);
  ASSERT_LT(fabs(axis->toUserVel() - 50), 0.01);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_Halt
TEST_F(FunctionBlockTest, MC_Halt)
{
#ifdef PLOT
  fb_profile_.reset();
  axis_profile_.reset();
#endif
  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbMoveVelocity move_vel;
  move_vel.setAxis(axis);
  move_vel.setVelocity(50);
  move_vel.setAcceleration(10);
  move_vel.setDeceleration(10);
  move_vel.setJerk(50);
  move_vel.setBufferMode(mcAborting);

  FbHalt halt;
  halt.setAxis(axis);
  halt.setAcceleration(5);
  halt.setJerk(50);
  halt.setBufferMode(mcAborting);
#ifdef PLOT
  fb_profile_.addFB("mov_vel");
  fb_profile_.addFB("halt");
  fb_profile_.addItemName("mov_vel.execute");
  fb_profile_.addItemName("mov_vel.inVel");
  fb_profile_.addItemName("mov_vel.abort");
  fb_profile_.addItemName("halt.execute");
  fb_profile_.addItemName("halt.done");
  fb_profile_.addItemName("halt.abort");
#endif
  double time_out = 40;
  double t        = 0;
  while (t < time_out)
  {
    axis->runCycle();
    fb_power.runCycle();
    move_vel.runCycle();
    halt.runCycle();

    if (move_vel.isEnabled() == mcFALSE && t < 7.5)
    {  //使能成功后move1开始移动
      std::cout << "axis poweron, mov_vel start" << std::endl;
      move_vel.setExecute(mcTRUE);
    }

    if (8.5 < t && t < 19 && move_vel.isEnabled() == mcTRUE)
      move_vel.setExecute(mcFALSE);

    if (19 < t && t < 21.5 && move_vel.isEnabled() == mcFALSE)
      move_vel.setExecute(mcTRUE);

    if (21.5 < t && t < 32.5 && move_vel.isEnabled() == mcTRUE)
      move_vel.setExecute(mcFALSE);

    if (32.5 < t && move_vel.isEnabled() == mcFALSE)
      move_vel.setExecute(mcTRUE);

    if (7 < t && t < 17.5 && halt.isEnabled() == mcFALSE)
      halt.setExecute(mcTRUE);

    if (17.5 < t && t < 27.5 && halt.isEnabled() == mcTRUE)
      halt.setExecute(mcFALSE);

    if (27.5 < t && t < 37.5 && halt.isEnabled() == mcFALSE)
      halt.setExecute(mcTRUE);

    if (37.5 < t && halt.isEnabled() == mcTRUE)
      halt.setExecute(mcFALSE);
#ifdef PLOT
    axis_profile_.addState(axis->toUserPos(), axis->toUserVel(),
                           axis->toUserAccCmd(), t);
    fb_profile_.addState("mov_vel.execute", move_vel.isEnabled() == mcTRUE);
    fb_profile_.addState("mov_vel.inVel", move_vel.isInVelocity() == mcTRUE);
    fb_profile_.addState("mov_vel.abort", move_vel.isAborted() == mcTRUE);
    fb_profile_.addState("halt.execute", halt.isEnabled() == mcTRUE);
    fb_profile_.addState("halt.done", halt.isDone() == mcTRUE);
    fb_profile_.addState("halt.abort", halt.isAborted() == mcTRUE);
    fb_profile_.addTime(t);
#endif
    // printf("Run time: %f, pos: %f, vel: %f\n", t, axis->toUserPos(),
    // axis->toUserVel());
    t += 0.001;
  }
#ifdef PLOT
  axis_profile_.plot("mc_halt_axis.png");
  fb_profile_.plot("mc_halt_fb.png");
#endif
  ASSERT_TRUE(move_vel.isInVelocity() == mcTRUE);
  ASSERT_LT(fabs(axis->toUserVel() - 50), 0.01);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_MoveAbsolute
TEST_F(FunctionBlockTest, MC_MoveAbsolute)
{
#ifdef PLOT
  fb_profile_.reset();
  axis_profile_.reset();
#endif
  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbMoveAbsolute move_abs1;
  move_abs1.setAxis(axis);
  move_abs1.setPosition(600);
  move_abs1.setVelocity(300);
  move_abs1.setAcceleration(500);
  move_abs1.setDeceleration(500);
  move_abs1.setJerk(5000);

  FbMoveAbsolute move_abs2;
  move_abs2.setAxis(axis);
  move_abs2.setPosition(1000);
  move_abs2.setVelocity(200);
  move_abs2.setAcceleration(500);
  move_abs2.setDeceleration(500);
  move_abs2.setJerk(5000);
  move_abs2.setBufferMode(mcAborting);

  FbSetPosition set_position1;
  set_position1.setAxis(axis);
  set_position1.setMode(mcSetPositionModeRelative);
  set_position1.setPosition(0);

#ifdef PLOT
  fb_profile_.addFB("move_abs1");
  fb_profile_.addFB("move_abs2");
  fb_profile_.addItemName("move_abs1.go");
  fb_profile_.addItemName("move_abs1.done");
  fb_profile_.addItemName("move_abs1.aborted");
  fb_profile_.addItemName("move_abs2.test");
  fb_profile_.addItemName("move_abs2.finish");
#endif
  double time_out = 7;
  double t        = 0;
  while (t < time_out)
  {
    //功能块调用
    axis->runCycle();
    fb_power.runCycle();
    set_position1.runCycle();
    move_abs1.runCycle();
    move_abs2.runCycle();

    if (set_position1.isEnabled() == mcFALSE &&
        fb_power.getPowerStatus() == mcTRUE && t < 2)
    {
      std::cout << "axis poweron, set position" << std::endl;
      set_position1.setEnable(mcTRUE);
    }

    if (set_position1.isEnabled() == mcTRUE &&
        move_abs1.isEnabled() == mcFALSE && t < 2)
    {  //使能成功后move1开始移动
      std::cout << "axis poweron, move_abs1 start" << std::endl;
      move_abs1.setExecute(mcTRUE);
    }

    if (2 < t && move_abs1.isEnabled() == mcTRUE)
      move_abs1.setExecute(mcFALSE);

    if (1 < t && t < 6 && move_abs2.isEnabled() == mcFALSE)
      move_abs2.setExecute(mcTRUE);

    if (6 < t && move_abs2.isEnabled() == mcTRUE)
      move_abs2.setExecute(mcFALSE);
#ifdef PLOT
    axis_profile_.addState(axis->toUserPos(), axis->toUserVel(),
                           axis->toUserAccCmd(), t);
    fb_profile_.addState("move_abs1.go", move_abs1.isEnabled() == mcTRUE);
    fb_profile_.addState("move_abs1.done", move_abs1.isDone() == mcTRUE);
    fb_profile_.addState("move_abs1.aborted", move_abs1.isAborted() == mcTRUE);
    fb_profile_.addState("move_abs2.test", move_abs2.isEnabled() == mcTRUE);
    fb_profile_.addState("move_abs2.finish", move_abs2.isDone() == mcTRUE);
    fb_profile_.addTime(t);
#endif
    // printf("Run time: %f, pos: %f, vel: %f\n", t, axis->toUserPos(),
    // axis->toUserVel());
    t += 0.001;
  }
#ifdef PLOT
  axis_profile_.plot("mc_move_abs_axis.png");
  fb_profile_.plot("mc_move_abs_fb.png");
#endif
  ASSERT_LT(fabs(axis->toUserVel() - 0.0), 0.01);
  ASSERT_LT(fabs(axis->toUserPos() - 1000), 0.01);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_MoveRelative
TEST_F(FunctionBlockTest, MC_MoveRelative)
{
#ifdef PLOT
  fb_profile_.reset();
  axis_profile_.reset();
#endif
  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbMoveRelative fb_move_rel_1, fb_move_rel_2;
  fb_move_rel_1.setAxis(axis);
  fb_move_rel_1.setContinuousUpdate(mcFALSE);
  fb_move_rel_1.setDistance(600);
  fb_move_rel_1.setVelocity(300);
  fb_move_rel_1.setAcceleration(500);
  fb_move_rel_1.setDeceleration(500);
  fb_move_rel_1.setJerk(5000);

  fb_move_rel_2.setAxis(axis);
  fb_move_rel_2.setContinuousUpdate(mcFALSE);
  fb_move_rel_2.setDistance(400);
  fb_move_rel_2.setVelocity(200);
  fb_move_rel_2.setAcceleration(500);
  fb_move_rel_2.setDeceleration(500);
  fb_move_rel_2.setJerk(5000);
  fb_move_rel_2.setBufferMode(mcAborting);
#ifdef PLOT
  fb_profile_.addFB("fb_move_rel_1");
  fb_profile_.addFB("fb_move_rel_2");
  fb_profile_.addItemName("fb_move_rel_1.go");
  fb_profile_.addItemName("fb_move_rel_1.done");
  fb_profile_.addItemName("fb_move_rel_1.aborted");
  fb_profile_.addItemName("fb_move_rel_2.test");
  fb_profile_.addItemName("fb_move_rel_2.finish");
#endif
  double time_out = 4;
  double t        = 0;
  double pos_tmp  = 0;
  mcBOOL trigger  = mcFALSE;
  while (t < time_out)
  {
    axis->runCycle();
    fb_power.runCycle();
    fb_move_rel_1.runCycle();
    fb_move_rel_2.runCycle();
    if (trigger == mcTRUE)
    {
      pos_tmp = axis->toUserPos();
      trigger = mcFALSE;
    }

    if (fb_move_rel_1.isEnabled() == mcFALSE && t < 2)
    {
      // After enabled, move_relative_1 start to move
      fb_move_rel_1.setExecute(mcTRUE);
      std::cout << "axis poweron, fb_move_rel_1 start" << std::endl;
    }

    if (2 < t && fb_move_rel_1.isEnabled() == mcTRUE)
      fb_move_rel_1.setExecute(mcFALSE);

    if (1 < t && t < 3.8 && fb_move_rel_2.isEnabled() == mcFALSE)
    {
      fb_move_rel_2.setExecute(mcTRUE);
      trigger = mcTRUE;
    }

    if (3.8 < t && fb_move_rel_2.isEnabled() == mcTRUE)
      fb_move_rel_2.setExecute(mcFALSE);
#ifdef PLOT
    axis_profile_.addState(axis->toUserPos(), axis->toUserVel(),
                           axis->toUserAccCmd(), t);
    fb_profile_.addState("fb_move_rel_1.go",
                         fb_move_rel_1.isEnabled() == mcTRUE);
    fb_profile_.addState("fb_move_rel_1.done",
                         fb_move_rel_1.isDone() == mcTRUE);
    fb_profile_.addState("fb_move_rel_1.aborted",
                         fb_move_rel_1.isAborted() == mcTRUE);
    fb_profile_.addState("fb_move_rel_2.test",
                         fb_move_rel_2.isEnabled() == mcTRUE);
    fb_profile_.addState("fb_move_rel_2.finish",
                         fb_move_rel_2.isDone() == mcTRUE);
    fb_profile_.addTime(t);
#endif
    t += 0.001;
    // printf("Run time: %f, pos: %f, vel: %f\n", t, axis->toUserPos(),
    // axis->toUserVel());
  }
#ifdef PLOT
  axis_profile_.plot("mc_mov_rel_axis.png");
  fb_profile_.plot("mc_mov_rel_fb.png");
#endif
  ASSERT_LT(fabs(axis->toUserVel() - 0.0), 0.01);
  ASSERT_LT(fabs(axis->toUserPos() - (pos_tmp + 400)), 0.01);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_MoveAdditive
TEST_F(FunctionBlockTest, MC_MoveAdditive)
{
#ifdef PLOT
  fb_profile_.reset();
  axis_profile_.reset();
#endif
  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbMoveAbsolute move_abs1;
  move_abs1.setAxis(axis);
  move_abs1.setPosition(600);
  move_abs1.setVelocity(300);
  move_abs1.setAcceleration(500);
  move_abs1.setDeceleration(500);
  move_abs1.setJerk(5000);
  move_abs1.setDirection(mcPositiveDirection);

  FbMoveAdditive move_add2;
  move_add2.setAxis(axis);
  move_add2.setDistance(400);
  move_add2.setVelocity(200);
  move_add2.setAcceleration(500);
  move_add2.setDeceleration(500);
  move_add2.setJerk(5000);
  move_add2.setBufferMode(mcAborting);

  FbSetPosition set_position1;
  set_position1.setAxis(axis);
  set_position1.setMode(mcSetPositionModeRelative);
  set_position1.setPosition(0);

#ifdef PLOT
  fb_profile_.addFB("move_abs1");
  fb_profile_.addFB("move_add2");
  fb_profile_.addItemName("move_abs1.go");
  fb_profile_.addItemName("move_abs1.done");
  fb_profile_.addItemName("move_abs1.aborted");
  fb_profile_.addItemName("move_add2.test");
  fb_profile_.addItemName("move_add2.finish");
#endif
  double time_out = 7;
  double t        = 0;
  while (t < time_out)
  {
    axis->runCycle();
    fb_power.runCycle();
    set_position1.runCycle();
    move_abs1.runCycle();
    move_add2.runCycle();

    if (set_position1.isEnabled() == mcFALSE &&
        fb_power.getPowerStatus() == mcTRUE)
    {
      std::cout << "axis poweron, set position" << std::endl;
      set_position1.setEnable(mcTRUE);
    }

    if (set_position1.isEnabled() == mcTRUE &&
        move_abs1.isEnabled() == mcFALSE && t < 2)
    {  //使能成功后move1开始移动
      std::cout << "axis poweron, move_abs1 start" << std::endl;
      move_abs1.setExecute(mcTRUE);
    }

    if (2 < t && move_abs1.isEnabled() == mcTRUE)
      move_abs1.setExecute(mcFALSE);

    if (1 < t && t < 6 && move_add2.isEnabled() == mcFALSE)
    {
      move_add2.setExecute(mcTRUE);
    }

    if (6 < t && move_add2.isEnabled() == mcTRUE)
      move_add2.setExecute(mcFALSE);
#ifdef PLOT
    axis_profile_.addState(axis->toUserPos(), axis->toUserVel(),
                           axis->toUserAccCmd(), t);
    fb_profile_.addState("move_abs1.go", move_abs1.isEnabled() == mcTRUE);
    fb_profile_.addState("move_abs1.done", move_abs1.isDone() == mcTRUE);
    fb_profile_.addState("move_abs1.aborted", move_abs1.isAborted() == mcTRUE);
    fb_profile_.addState("move_add2.test", move_add2.isEnabled() == mcTRUE);
    fb_profile_.addState("move_add2.finish", move_add2.isDone() == mcTRUE);
    fb_profile_.addTime(t);
#endif
    t += 0.001;
    // printf("Run time: %f, pos: %f, vel: %f\n", t, axis->toUserPos(),
    // axis->toUserVel());
  }
#ifdef PLOT
  axis_profile_.plot("mc_moveAdd_axis.png");
  fb_profile_.plot("mc_moveAdd_fb.png");
#endif
  ASSERT_LT(fabs(axis->toUserVel() - 0.0), 0.01);
  ASSERT_LT(fabs(axis->toUserPos() - (600 + 400)), 0.01);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_MoveVelocity
TEST_F(FunctionBlockTest, MC_MoveVelocity)
{
#ifdef PLOT
  fb_profile_.reset();
  axis_profile_.reset();
#endif
  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbMoveVelocity mov_vel1;
  mov_vel1.setAxis(axis);
  mov_vel1.setVelocity(500);
  mov_vel1.setAcceleration(500);
  mov_vel1.setDeceleration(500);
  mov_vel1.setJerk(5000);
  mov_vel1.setBufferMode(mcAborting);

  FbMoveVelocity mov_vel2;
  mov_vel2.setAxis(axis);
  mov_vel2.setVelocity(200);
  mov_vel2.setAcceleration(500);
  mov_vel2.setDeceleration(500);
  mov_vel2.setJerk(5000);
  mov_vel2.setBufferMode(mcAborting);
#ifdef PLOT
  fb_profile_.addFB("mov_vel1");
  fb_profile_.addFB("mov_vel2");
  fb_profile_.addItemName("mov_vel1.go");
  fb_profile_.addItemName("mov_vel1.inVel");
  fb_profile_.addItemName("mov_vel1.aborted");
  fb_profile_.addItemName("mov_vel1.next");
  fb_profile_.addItemName("mov_vel2.test");
  fb_profile_.addItemName("mov_vel2.finish");
#endif
  double time_out = 9;
  double t        = 0;
  mcBOOL next = mcFALSE, test = mcFALSE;
  while (t < time_out)
  {
    axis->runCycle();
    fb_power.runCycle();
    mov_vel1.runCycle();
    mov_vel2.runCycle();

    if (mov_vel1.isEnabled() == mcFALSE && t < 5)
    {  //使能成功后move1开始移动
      std::cout << "axis poweron, mov_vel1 start" << std::endl;
      mov_vel1.setExecute(mcTRUE);
    }

    if (5 < t && t < 6 && mov_vel1.isEnabled() == mcTRUE)
      mov_vel1.setExecute(mcFALSE);

    if (6 < t && t < 8 && mov_vel1.isEnabled() == mcFALSE)
      mov_vel1.setExecute(mcTRUE);

    if (8 < t && mov_vel1.isEnabled() == mcTRUE)
      mov_vel1.setExecute(mcFALSE);

    if (2 < t && t < 4 && next == mcFALSE)
    {
      next = mcTRUE;
      mov_vel2.setExecute(next);
    }

    if (4 < t && next == mcTRUE)
    {
      next = mcFALSE;
      mov_vel2.setExecute(mcFALSE);
    }

    if (6.5 < t && t < 8.5 && test == mcFALSE)
    {
      test = mcTRUE;
      mov_vel2.setExecute(test);
    }

    if (8.5 < t && test == mcTRUE)
    {
      test = mcFALSE;
      mov_vel2.setExecute(test);
    }
#ifdef PLOT
    axis_profile_.addState(axis->toUserPos(), axis->toUserVel(),
                           axis->toUserAccCmd(), t);
    fb_profile_.addState("mov_vel1.go", mov_vel1.isEnabled() == mcTRUE);
    fb_profile_.addState("mov_vel1.inVel", mov_vel1.isDone() == mcTRUE);
    fb_profile_.addState("mov_vel1.aborted", mov_vel1.isAborted() == mcTRUE);
    fb_profile_.addState("mov_vel1.next", next == mcTRUE);
    fb_profile_.addState("mov_vel2.test", test == mcTRUE);
    fb_profile_.addState("mov_vel2.finish", mov_vel2.isDone() == mcTRUE);
    fb_profile_.addTime(t);
#endif
    t += 0.001;
    // printf("Run time: %f, pos: %f, vel: %f\n", t, axis->toUserPos(),
    // axis->toUserVel());
  }
#ifdef PLOT
  axis_profile_.plot("mc_mov_vel_axis.png");
  fb_profile_.plot("mc_mov_vel_fb.png");
#endif
  ASSERT_LT(fabs(axis->toUserVel() - 200), 0.01);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_SetPosition
TEST_F(FunctionBlockTest, MC_SetPosition1)
{
  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbMoveAbsolute move_abs1;
  move_abs1.setAxis(axis);
  move_abs1.setPosition(600);
  move_abs1.setVelocity(300);
  move_abs1.setAcceleration(500);
  move_abs1.setDeceleration(500);
  move_abs1.setJerk(5000);

  FbMoveAbsolute move_abs2;
  move_abs2.setAxis(axis);
  move_abs2.setPosition(100);
  move_abs2.setVelocity(300);
  move_abs2.setAcceleration(500);
  move_abs2.setDeceleration(500);
  move_abs2.setJerk(5000);

  FbSetPosition set_position1;
  set_position1.setAxis(axis);
  set_position1.setMode(mcSetPositionModeAbsolute);
  set_position1.setPosition(0);

  FbReadActualPosition read_actual_pos1;
  read_actual_pos1.setAxis(axis);
  read_actual_pos1.setEnable(mcTRUE);

  double time_out = 5;
  double t        = 0;
  while (t < time_out)
  {
    //功能块调用
    axis->runCycle();
    fb_power.runCycle();
    set_position1.runCycle();
    move_abs1.runCycle();
    move_abs2.runCycle();
    read_actual_pos1.runCycle();

    if (set_position1.isEnabled() == mcFALSE &&
        fb_power.getPowerStatus() == mcTRUE && t < 0.5)
    {
      std::cout << "axis poweron, set position" << std::endl;
      set_position1.setEnable(mcTRUE);
    }

    if (move_abs1.isEnabled() == mcFALSE && t > 0.5)
    {  //使能成功后move1开始移动
      std::cout << "axis poweron, move_abs1 start" << std::endl;
      move_abs1.setExecute(mcTRUE);
      set_position1.setEnable(mcFALSE);
    }

    if (read_actual_pos1.getFloatValue() >= 100 &&
        set_position1.isEnabled() == mcFALSE)
    {  //当位置抵达100时，设置POS为300
      std::cout << "axis reach 100, setPosition1 start" << std::endl;
      set_position1.setPosition(300);
      set_position1.setEnable(mcTRUE);
    }

    if (move_abs1.isDone() == mcTRUE && move_abs2.isEnabled() == mcFALSE)
      move_abs2.setExecute(mcTRUE);  //当位置抵达600时，触发第二个功能块到100

    // printf("Run time: %ld, usr pos: %f, act pos: %f\n", t, axis->toUserPos(),
    // axis->getPos());
    t += 0.001;
  }

  ASSERT_LT(fabs(axis->toUserVel() - 0.0), 0.01);
  ASSERT_LT(fabs(axis->toUserPos() - 100), 0.5);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_SetPosition
TEST_F(FunctionBlockTest, MC_SetPosition2)
{
  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbMoveRelative move_rel1;
  move_rel1.setAxis(axis);
  move_rel1.setPosition(600);
  move_rel1.setVelocity(300);
  move_rel1.setAcceleration(500);
  move_rel1.setDeceleration(500);
  move_rel1.setJerk(5000);

  FbMoveRelative move_rel2;
  move_rel2.setAxis(axis);
  move_rel2.setPosition(100);
  move_rel2.setVelocity(300);
  move_rel2.setAcceleration(500);
  move_rel2.setDeceleration(500);
  move_rel2.setJerk(5000);

  FbSetPosition set_position1;
  set_position1.setAxis(axis);
  set_position1.setMode(mcSetPositionModeAbsolute);
  set_position1.setPosition(300);

  FbReadActualPosition read_actual_pos1;
  read_actual_pos1.setAxis(axis);
  read_actual_pos1.setEnable(mcTRUE);

  double time_out = 5;
  double t        = 0;
  while (t < time_out)
  {
    //功能块调用
    axis->runCycle();
    fb_power.runCycle();
    move_rel1.runCycle();
    move_rel2.runCycle();
    set_position1.runCycle();
    read_actual_pos1.runCycle();

    if (move_rel1.isEnabled() == mcFALSE)
    {  //使能成功后move1开始移动
      std::cout << "axis poweron, moveRel1 start" << std::endl;
      move_rel1.setExecute(mcTRUE);
    }

    if (read_actual_pos1.getFloatValue() >= 100 &&
        set_position1.isEnabled() == mcFALSE)
    {  //当位置抵达100时，设置POS为300
      std::cout << "axis reach 100, setPosition1 start" << std::endl;
      set_position1.setEnable(mcTRUE);
    }

    if (move_rel1.isDone() == mcTRUE && move_rel2.isEnabled() == mcFALSE)
      move_rel2.setExecute(mcTRUE);  //当位置抵达600时，触发第二个功能块到700

    // printf("Run time: %ld, usr pos: %f, act pos: %f\n", t, axis->toUserPos(),
    // axis->getPos());
    t += 0.001;
  }

  ASSERT_LT(fabs(axis->toUserVel() - 0.0), 0.01);
  ASSERT_LT(fabs(axis->toUserPos() - 700), 0.01);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_Homing
TEST_F(FunctionBlockTest, MC_Homing1)
{
  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);
  axis->setNodeQueueSize(3);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbHoming move_homing;
  move_homing.setAxis(axis);
  move_homing.setDirection(mcNegativeDirection);
  move_homing.setVelocity(300);
  move_homing.setAcceleration(500);
  move_homing.setDeceleration(500);
  move_homing.setJerk(5000);

  FbReadActualPosition read_actual_pos;
  read_actual_pos.setAxis(axis);
  read_actual_pos.setEnable(mcTRUE);
  double time_out = 3.5;
  double t        = 0;
  int64_t count   = 0;
  while (t < time_out)
  {
    //功能块调用
    axis->runCycle();
    fb_power.runCycle();
    move_homing.runCycle();
    read_actual_pos.runCycle();

    if (move_homing.isEnabled() == mcFALSE &&
        fb_power.getPowerStatus() == mcTRUE)
    {  //使能成功后moveRel开始移动
      std::cout << "axis poweron, moveHome start" << std::endl;
      move_homing.setExecute(mcTRUE);
      move_homing.setRefSignal(mcTRUE);  //触发home
    }

    if (count == 100)
    {
      move_homing.setRefSignal(mcFALSE);
    }

    if (move_homing.isDone() == mcTRUE)
    {
      std::cout << "moveHome done" << std::endl;
      break;
    }

    // printf("Run time: %ld, usr pos: %f, act vel: %f\n", t, axis->toUserPos(),
    // axis->toUserVel());
    count++;
    t += 0.001;
  }

  ASSERT_LT(fabs(axis->toUserVel() - 0.0), 0.01);
  ASSERT_LT(fabs(axis->toUserPos() - 0.0), 0.01);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_Homing
TEST_F(FunctionBlockTest, MC_Homing2)
{
  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);
  axis->setNodeQueueSize(3);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbMoveRelative move_rel;
  move_rel.setAxis(axis);
  move_rel.setPosition(100);
  move_rel.setVelocity(300);
  move_rel.setAcceleration(500);
  move_rel.setDeceleration(500);
  move_rel.setJerk(5000);

  FbHoming move_homing;
  move_homing.setAxis(axis);
  move_homing.setDirection(mcNegativeDirection);
  move_homing.setVelocity(300);
  move_homing.setAcceleration(500);
  move_homing.setDeceleration(500);
  move_homing.setJerk(5000);

  FbReadActualPosition read_actual_pos;
  read_actual_pos.setAxis(axis);
  read_actual_pos.setEnable(mcTRUE);
  double time_out = 3.5;
  double t        = 0;
  while (t < time_out)
  {
    //功能块调用
    axis->runCycle();
    fb_power.runCycle();
    move_rel.runCycle();
    move_homing.runCycle();
    read_actual_pos.runCycle();

    if (move_rel.isEnabled() == mcFALSE && fb_power.getPowerStatus() == mcTRUE)
    {  //使能成功后moveRel开始移动
      std::cout << "axis poweron, moveRel start" << std::endl;
      move_rel.setExecute(mcTRUE);
    }

    if (move_rel.isDone() == mcTRUE && move_homing.isEnabled() == mcFALSE)
    {
      std::cout << "moveRel done, moveHome start" << std::endl;
      move_homing.setExecute(mcTRUE);  //当位置到达100后，触发home
    }

    if (move_homing.isEnabled() == mcTRUE &&
        read_actual_pos.getFloatValue() <= 0.0)
      move_homing.setRefSignal(mcTRUE);

    if (move_homing.isDone() == mcTRUE)
    {
      std::cout << "moveHome done" << std::endl;
      break;
    }

    // printf("Run time: %ld, usr pos: %f, act vel: %f\n", t, axis->toUserPos(),
    // axis->toUserVel());
    t += 0.001;
  }

  ASSERT_LT(fabs(axis->toUserVel() - 0.0), 0.01);
  ASSERT_LT(fabs(axis->toUserPos() - 0.0), 0.01);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_Homing
TEST_F(FunctionBlockTest, MC_Homing3)
{
  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);
  axis->setNodeQueueSize(3);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbHoming move_homing;
  move_homing.setAxis(axis);
  move_homing.setDirection(mcNegativeDirection);
  move_homing.setVelocity(300);
  move_homing.setAcceleration(500);
  move_homing.setDeceleration(500);
  move_homing.setJerk(5000);

  FbReadActualPosition read_actual_pos;
  read_actual_pos.setAxis(axis);
  read_actual_pos.setEnable(mcTRUE);

  double time_out = 3.5;
  double t        = 0;
  int64_t count   = 0;
  while (t < time_out)
  {
    //功能块调用
    axis->runCycle();
    fb_power.runCycle();
    move_homing.runCycle();
    read_actual_pos.runCycle();

    if (move_homing.isEnabled() == mcFALSE &&
        fb_power.getPowerStatus() == mcTRUE)
    {  //使能成功后moveHome开始移动
      std::cout << "axis poweron, moveRel start" << std::endl;
      move_homing.setExecute(mcTRUE);
    }

    if (count == 500)
    {
      move_homing.setLimitNegSignal(mcTRUE);
    }

    if (count == 1500)
    {
      move_homing.setRefSignal(mcTRUE);
    }

    if (count == 1600)
    {
      move_homing.setRefSignal(mcFALSE);
    }

    if (move_homing.isDone() == mcTRUE)
    {
      std::cout << "moveHome done" << std::endl;
      break;
    }

    // printf("Run time: %ld, usr pos: %f, act vel: %f\n", t, axis->toUserPos(),
    // axis->toUserVel());
    count++;
    t += 0.001;
  }

  ASSERT_LT(fabs(axis->toUserVel() - 0.0), 0.0001);
  ASSERT_LT(fabs(axis->toUserPos() - 0.0), 0.01);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_MoveVelocity -> MC_Halt/MC_Stop -> MC_MoveRelative
TEST_F(FunctionBlockTest, MC_Sequence1)
{
  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbMoveVelocity fb_move_vel;
  fb_move_vel.setAxis(axis);
  fb_move_vel.setVelocity(50);
  fb_move_vel.setAcceleration(10);
  fb_move_vel.setDeceleration(10);
  fb_move_vel.setJerk(50);
  fb_move_vel.setBufferMode(mcAborting);

  FbHalt fb_halt;
  fb_halt.setAxis(axis);
  fb_halt.setAcceleration(5);
  fb_halt.setJerk(50);
  fb_halt.setBufferMode(mcAborting);

  FbMoveAbsolute fb_move_abs;
  fb_move_abs.setAxis(axis);
  fb_move_abs.setPosition(600);
  fb_move_abs.setVelocity(300);
  fb_move_abs.setAcceleration(500);
  fb_move_abs.setDeceleration(500);
  fb_move_abs.setJerk(5000);

  FbSetPosition set_position1;
  set_position1.setAxis(axis);
  set_position1.setMode(mcSetPositionModeRelative);
  set_position1.setPosition(0);

  double time_out = 17;
  double t        = 0;
  while (t < time_out)
  {
    axis->runCycle();
    fb_power.runCycle();
    set_position1.runCycle();
    fb_move_vel.runCycle();
    fb_halt.runCycle();
    fb_move_abs.runCycle();

    if (set_position1.isEnabled() == mcFALSE &&
        fb_power.getPowerStatus() == mcTRUE)
    {
      std::cout << "axis poweron, set position" << std::endl;
      set_position1.setEnable(mcTRUE);
    }

    if (fb_move_vel.isEnabled() == mcFALSE &&
        fb_power.getPowerStatus() == mcTRUE &&
        set_position1.isEnabled() == mcTRUE)
    {  //使能成功后move1开始移动
      std::cout << "axis poweron, fb_move_vel start" << std::endl;
      fb_move_vel.setExecute(mcTRUE);
    }

    if (fb_move_vel.isInVelocity() == mcTRUE && fb_halt.isEnabled() == mcFALSE)
    {  //使能成功后move1开始移动
      std::cout << "axis in velocity, halt start" << std::endl;
      fb_halt.setExecute(mcTRUE);
    }

    if (fb_halt.isDone() == mcTRUE && fb_move_abs.isEnabled() == mcFALSE)
    {  //使能成功后move1开始移动
      std::cout << "axis halt, fb_move_abs start" << std::endl;
      fb_move_abs.setExecute(mcTRUE);
    }

    // printf("Run time: %ld, pos: %f, vel: %f\n", t, axis->toUserPos(),
    //        axis->toUserVel());
    t += 0.001;
  }

  ASSERT_LT(fabs(axis->toUserPos() - 600), 0.01);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_Jog
TEST_F(FunctionBlockTest, MC_Jog)
{
#ifdef PLOT
  fb_profile_.reset();
  axis_profile_.reset();
#endif
  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbJog fb_jog;
  fb_jog.setAxis(axis);
  fb_jog.setExecute(mcFALSE);
  fb_jog.setContinuousUpdate(mcFALSE);
  fb_jog.setVelocity(1.57);
  fb_jog.setAcceleration(3.14);
  fb_jog.setJerk(50);
  printf("Function block initialized.\n");

  double timeout = 0.0;
  while (timeout < 5.0)
  {
    axis->runCycle();
    fb_power.runCycle();
    fb_jog.runCycle();
    timeout += 0.001;

#ifdef PLOT
    axis_profile_.addState(axis->toUserPos(), axis->toUserVel(),
                           axis->toUserAccCmd(), timeout);
#endif

    if (fb_jog.isEnabled() == mcFALSE && fb_power.getPowerStatus() == mcTRUE)
    {
      fb_jog.setExecute(mcTRUE);
      printf("Axis powered on %d\n", fb_power.getPowerStatus() == mcTRUE);
    }
    // Jog forward
    if (fabs(timeout - 1.0) < 0.0001)
    {
      fb_jog.setJogForwardSignal(mcTRUE);
    }
    // Jog halt
    if (fabs(timeout - 2.0) < 0.0001)
    {
      fb_jog.setJogForwardSignal(mcFALSE);
    }
    // Jog backward
    if (fabs(timeout - 3.0) < 0.0001)
    {
      fb_jog.setJogBackwardSignal(mcTRUE);
    }
    // Jog halt
    if (fabs(timeout - 4.0) < 0.0001)
    {
      fb_jog.setJogBackwardSignal(mcFALSE);
    }
  }
#ifdef PLOT
  axis_profile_.plot("mc_jog_axis.png");
#endif
  ASSERT_LT(fabs(axis->toUserVel()), 0.01);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_CamIn, MC_CamSelect
TEST_F(FunctionBlockTest, MC_Cam)
{
#ifdef PLOT
  fb_profile_.reset();
  axis_profile_.reset();
#endif
  RTmotion::AxisConfig config1;
  RTmotion::AxisConfig config2;
  RTmotion::AXIS_REF axis1;
  axis1 = new RTmotion::Axis();
  axis1->setAxisId(1);
  RTmotion::AXIS_REF axis2;
  axis2 = new RTmotion::Axis();
  axis2->setAxisId(2);

  axis1->setAxisConfig(&config1);
  printf("Axis1 initialized.\n");
  axis2->setAxisConfig(&config2);
  printf("Axis2 initialized.\n");

  RTmotion::Servo* servo1;
  servo1 = new RTmotion::Servo();
  axis1->setServo(servo1);

  RTmotion::Servo* servo2;
  servo2 = new RTmotion::Servo();
  axis2->setServo(servo2);

  RTmotion::FbPower fb_power1;
  fb_power1.setAxis(axis1);
  fb_power1.setEnable(mcTRUE);
  fb_power1.setEnablePositive(mcTRUE);
  fb_power1.setEnableNegative(mcTRUE);

  RTmotion::FbPower fb_power2;
  fb_power2.setAxis(axis2);
  fb_power2.setEnable(mcTRUE);
  fb_power2.setEnablePositive(mcTRUE);
  fb_power2.setEnableNegative(mcTRUE);

  RTmotion::FbMoveVelocity fb_move_vel;
  fb_move_vel.setAxis(axis1);
  fb_move_vel.setVelocity(1);
  fb_move_vel.setAcceleration(10);
  fb_move_vel.setDeceleration(10);
  fb_move_vel.setJerk(50);
  fb_move_vel.setBufferMode(RTmotion::mcAborting);

  RTmotion::McCamXYVA* cam_table = new RTmotion::McCamXYVA[21]{
    { 0, 0, NAN, NAN, RTmotion::polyFive },
    { 0.05, 0.18216653494266, NAN, NAN, RTmotion::polyFive },
    { 0.1, 0.87016810548376, NAN, NAN, RTmotion::polyFive },
    { 0.15, 2.05641722576408, NAN, NAN, RTmotion::polyFive },
    { 0.2, 3.13167438555392, NAN, NAN, RTmotion::polyFive },
    { 0.25, 3.73191015715167, NAN, NAN, RTmotion::polyFive },
    { 0.3, 3.96932297189104, NAN, NAN, RTmotion::polyFive },
    { 0.35, 3.98989548504385, NAN, NAN, RTmotion::polyFive },
    { 0.4, 3.87565752765028, NAN, NAN, RTmotion::polyFive },
    { 0.45, 3.66918595869634, NAN, NAN, RTmotion::polyFive },
    { 0.5, 3.39454683260162, NAN, NAN, RTmotion::polyFive },
    { 0.55, 3.06754062544119, NAN, NAN, RTmotion::polyFive },
    { 0.6, 2.70046667554222, NAN, NAN, RTmotion::polyFive },
    { 0.65, 2.30447191676131, NAN, NAN, RTmotion::polyFive },
    { 0.7, 1.89086353242174, NAN, NAN, RTmotion::polyFive },
    { 0.75, 1.47202253393456, NAN, NAN, RTmotion::polyFive },
    { 0.8, 1.06229448249912, NAN, NAN, RTmotion::polyFive },
    { 0.85, 0.67926960044916, NAN, NAN, RTmotion::polyFive },
    { 0.9, 0.34631157212864, NAN, NAN, RTmotion::polyFive },
    { 0.95, 0.09869066438798, NAN, NAN, RTmotion::polyFive },
    { 1.0, 0, NAN, NAN, RTmotion::noNextSegment }
  };

  RTmotion::FbCamRef fb_cam_ref;
  fb_cam_ref.setType(RTmotion::xyva);
  fb_cam_ref.setElementNum(21);
  fb_cam_ref.setMasterRangeStart(0);
  fb_cam_ref.setMasterRangeEnd(1.0);
  fb_cam_ref.setElements((unsigned char*)cam_table);

  RTmotion::FbCamTableSelect fb_cam_table_select;
  fb_cam_table_select.setMaster(axis1);
  fb_cam_table_select.setSlave(axis2);
  fb_cam_table_select.setCamTable(&fb_cam_ref);
  fb_cam_table_select.setMasterAbsolute(mcFALSE);
  fb_cam_table_select.setSlaveAbsolute(mcFALSE);
  fb_cam_table_select.setPeriodic(mcTRUE);
  fb_cam_table_select.setEnable(mcTRUE);

  RTmotion::FbCamIn fb_cam_in;
  fb_cam_in.setMaster(axis1);
  fb_cam_in.setSlave(axis2);
  fb_cam_in.setCamTableID(fb_cam_table_select.getCamTableID());
  fb_cam_in.setStartMode(RTmotion::mcRelative);
  fb_cam_in.setVelocity(50);
  fb_cam_in.setAcceleration(500);
  fb_cam_in.setDeceleration(500);
  fb_cam_in.setPosThreshold(1.0);
  fb_cam_in.setVelThreshold(10.0);
  fb_cam_in.setExecute(mcFALSE);

  RTmotion::FbCamOut fb_cam_out;
  fb_cam_out.setSlave(axis2);
  fb_cam_out.setExecute(mcFALSE);

#ifdef PLOT
  fb_profile_.addFB("fbCamIn");
  fb_profile_.addItemName("fbCamIn.isEnabled");
  fb_profile_.addItemName("fbCamIn.isDone");
#endif
  double time_out = 5;
  double t        = 0;
  while (t < time_out)
  {
    axis1->runCycle();
    axis2->runCycle();
    fb_power1.runCycle();
    fb_power2.runCycle();
    fb_move_vel.runCycle();
    fb_cam_table_select.runCycle();
    fb_cam_in.runCycle();
    fb_cam_out.runCycle();

    if (fb_power1.getPowerStatus() == mcTRUE &&
        fb_power2.getPowerStatus() == mcTRUE)
    {
      fb_move_vel.setExecute(mcTRUE);
      fb_cam_in.setExecute(mcTRUE);
    }

    if (t > 4.0)
    {
      fb_cam_out.setExecute(mcTRUE);
    }

#ifdef PLOT
    axis_profile_.addState(axis2->toUserPos(), axis2->toUserVel(),
                           axis2->toUserAccCmd(), t);
    fb_profile_.addState("fbCamIn.isEnabled", fb_cam_in.isEnabled() == mcTRUE);
    fb_profile_.addState("fbCamIn.isDone", fb_cam_in.isDone() == mcTRUE);
    fb_profile_.addTime(t);
#endif
    // printf("Axis 1: Run time: %f, pos: %f, vel: %f\n", t,
    // axis1->toUserPos(), axis1->toUserVel());
    // printf("Axis 2: Run time: %f, pos: %f, vel: %f, axis state: %d\n", t,
    // axis2->toUserPos(), axis2->toUserVel(), axis2->getAxisState());

    t += 0.001;
  }
#ifdef PLOT
  axis_profile_.plot("mc_cam_in_axis.png");
  fb_profile_.plot("mc_cam_fb.png");
#endif
  ASSERT_TRUE(fb_cam_out.isDone() == mcTRUE);
  delete servo1;
  delete servo2;
  delete axis1;
  delete axis2;
  delete[] cam_table;
  servo1    = nullptr;
  servo2    = nullptr;
  axis1     = nullptr;
  axis2     = nullptr;
  cam_table = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_GearIn, MC_GearOut
TEST_F(FunctionBlockTest, MC_Gear)
{
  RTmotion::AxisConfig config1;
  RTmotion::AxisConfig config2;
  RTmotion::AXIS_REF axis1;
  axis1 = new RTmotion::Axis();
  axis1->setAxisId(1);
  RTmotion::AXIS_REF axis2;
  axis2 = new RTmotion::Axis();
  axis2->setAxisId(2);

  axis1->setAxisConfig(&config1);
  printf("Axis1 initialized.\n");
  axis2->setAxisConfig(&config2);
  printf("Axis2 initialized.\n");

  RTmotion::Servo* servo1;
  servo1 = new RTmotion::Servo();
  axis1->setServo(servo1);

  RTmotion::Servo* servo2;
  servo2 = new RTmotion::Servo();
  axis2->setServo(servo2);

  RTmotion::FbPower fb_power1;
  fb_power1.setAxis(axis1);
  fb_power1.setEnable(mcTRUE);
  fb_power1.setEnablePositive(mcTRUE);
  fb_power1.setEnableNegative(mcTRUE);

  RTmotion::FbPower fb_power2;
  fb_power2.setAxis(axis2);
  fb_power2.setEnable(mcTRUE);
  fb_power2.setEnablePositive(mcTRUE);
  fb_power2.setEnableNegative(mcTRUE);

  RTmotion::FbMoveVelocity fb_move_vel;
  fb_move_vel.setAxis(axis1);
  fb_move_vel.setVelocity(1);
  fb_move_vel.setAcceleration(10);
  fb_move_vel.setDeceleration(10);
  fb_move_vel.setJerk(50);
  fb_move_vel.setBufferMode(RTmotion::mcAborting);

  /* initialize MC_GearIn */
  RTmotion::FbGearIn fb_gear_in;
  fb_gear_in.setMaster(axis1);
  fb_gear_in.setSlave(axis2);
  fb_gear_in.setRatioNumerator(2);
  fb_gear_in.setRatioDenominator(1);
  fb_gear_in.setAcceleration(10);
  fb_gear_in.setDeceleration(10);
  fb_gear_in.setJerk(50);
  fb_gear_in.setBufferMode(RTmotion::mcAborting);

  /* GearOut slave */
  RTmotion::FbGearOut fb_gear_out;
  fb_gear_out.setSlave(axis2);

  double time_out      = 2;
  double t             = 0;
  mcBOOL gear_in_flag  = mcTRUE;
  mcBOOL gear_out_flag = mcTRUE;

  while (t < time_out)
  {
    axis1->runCycle();
    axis2->runCycle();
    fb_power1.runCycle();
    fb_power2.runCycle();
    fb_move_vel.runCycle();
    fb_gear_in.runCycle();
    fb_gear_out.runCycle();

    if (fb_power1.getPowerStatus() == mcTRUE &&
        fb_power2.getPowerStatus() == mcTRUE)
    {
      fb_move_vel.setExecute(mcTRUE);
    }
    if (fb_move_vel.isInVelocity() == mcTRUE && gear_in_flag == mcTRUE)
    {
      // enablke GearIn
      fb_gear_in.setExecute(mcTRUE);
      gear_in_flag = mcFALSE;
      printf("Slave gear in.\n");
    }
    if (fb_gear_in.isError() == mcTRUE)
    {
      printf("Slave gear in failed! Error ID:%X\n", fb_gear_in.getErrorID());
      break;
    }
    if ((t > (time_out / 2)) && (gear_out_flag == mcTRUE))
    {
      printf("master vel:%f  slave vel:%f  slave state:%d\n",
             axis1->toUserVel(), axis2->toUserVel(), axis2->getAxisState());
      // enablke GearOut
      fb_gear_out.setExecute(mcTRUE);
      /* Change Master velocity */
      fb_move_vel.setVelocity(2);
      fb_move_vel.onRisingEdgeExecution();
      printf("Slave gear out and change master velocity to 2.\n");
      gear_out_flag = mcFALSE;
    }
    t += 0.001;
  }
  printf("master vel:%f  slave vel:%f  slave state:%d\n", axis1->toUserVel(),
         axis2->toUserVel(), axis2->getAxisState());

  /* Post Processing */
  delete servo1;
  delete servo2;
  delete axis1;
  delete axis2;
  servo1 = nullptr;
  servo2 = nullptr;
  axis1  = nullptr;
  axis2  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_GearInPos
TEST_F(FunctionBlockTest, MC_GearInPos)
{
#ifdef PLOT
  fb_profile_.reset();
  axis_profile_.reset();
#endif
  RTmotion::AxisConfig config1;
  RTmotion::AxisConfig config2;
  RTmotion::AXIS_REF axis1;
  axis1 = new RTmotion::Axis();
  axis1->setAxisId(1);
  RTmotion::AXIS_REF axis2;
  axis2 = new RTmotion::Axis();
  axis2->setAxisId(2);

  axis1->setAxisConfig(&config1);
  printf("Axis1 initialized.\n");
  axis2->setAxisConfig(&config2);
  printf("Axis2 initialized.\n");

  RTmotion::Servo* servo1;
  servo1 = new RTmotion::Servo();
  axis1->setServo(servo1);

  RTmotion::Servo* servo2;
  servo2 = new RTmotion::Servo();
  axis2->setServo(servo2);

  RTmotion::FbPower fb_power1;
  fb_power1.setAxis(axis1);
  fb_power1.setEnable(mcTRUE);
  fb_power1.setEnablePositive(mcTRUE);
  fb_power1.setEnableNegative(mcTRUE);

  RTmotion::FbPower fb_power2;
  fb_power2.setAxis(axis2);
  fb_power2.setEnable(mcTRUE);
  fb_power2.setEnablePositive(mcTRUE);
  fb_power2.setEnableNegative(mcTRUE);

  RTmotion::FbMoveVelocity fb_move_vel;
  fb_move_vel.setAxis(axis1);
  fb_move_vel.setVelocity(1);
  fb_move_vel.setAcceleration(10);
  fb_move_vel.setDeceleration(10);
  fb_move_vel.setJerk(50);
  fb_move_vel.setBufferMode(RTmotion::mcAborting);

  RTmotion::FbGearInPos fb_gear_in_pos;
  fb_gear_in_pos.setMaster(axis1);
  fb_gear_in_pos.setSlave(axis2);
  fb_gear_in_pos.setMasterStartDistance(1);
  fb_gear_in_pos.setMasterSyncPosition(3);
  fb_gear_in_pos.setRatioNumerator(1);
  fb_gear_in_pos.setRatioDenominator(2);
  fb_gear_in_pos.setSlaveSyncPosition(1);
  fb_gear_in_pos.setVelocity(50);
  fb_gear_in_pos.setAcceleration(500);
  fb_gear_in_pos.setDeceleration(500);
  fb_gear_in_pos.setPosSyncFactor(0.01);
  fb_gear_in_pos.setVelSyncFactor(0.05);
  fb_gear_in_pos.setBufferMode(mcAborting);

#ifdef PLOT
  fb_profile_.addFB("fbGearInPos");
  fb_profile_.addItemName("fbGearInPos.isEnabled");
  fb_profile_.addItemName("fbGearInPos.isDone");
#endif
  double time_out = 5;
  double t        = 0;
  while (t < time_out)
  {
    axis1->runCycle();
    axis2->runCycle();
    fb_power1.runCycle();
    fb_power2.runCycle();
    fb_move_vel.runCycle();
    fb_gear_in_pos.runCycle();

    if (fb_power1.getPowerStatus() == mcTRUE &&
        fb_power2.getPowerStatus() == mcTRUE)
    {
      fb_move_vel.setExecute(mcTRUE);
      fb_gear_in_pos.setExecute(mcTRUE);
    }

#ifdef PLOT
    axis_profile_.addState(axis2->toUserPos(), axis2->toUserVel(),
                           axis2->toUserAccCmd(), t);
    fb_profile_.addState("fbGearInPos.isEnabled",
                         fb_gear_in_pos.isEnabled() == mcTRUE);
    fb_profile_.addState("fbGearInPos.isDone",
                         fb_gear_in_pos.isDone() == mcTRUE);
    fb_profile_.addTime(t);
#endif
    // printf("Axis 1: Run time: %f, pos: %f, vel: %f\n", t,
    // axis1->toUserPos(), axis1->toUserVel());
    // printf("Axis 2: Run time: %f, pos: %f, vel: %f, axis state: %d\n", t,
    // axis2->toUserPos(), axis2->toUserVel(), axis2->getAxisState());

    t += 0.001;
  }
#ifdef PLOT
  axis_profile_.plot("mc_gear_in_pos_axis.png");
  fb_profile_.plot("mc_gear_in_pos_fb.png");
#endif
  ASSERT_LT(fabs(axis2->toUserVel() - 0.5), 0.1);
  delete servo1;
  delete servo2;
  delete axis1;
  delete axis2;
  servo1 = nullptr;
  servo2 = nullptr;
  axis1  = nullptr;
  axis2  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_ReadMotionState
TEST_F(FunctionBlockTest, DemoReadMotionState)
{
// plot
#ifdef PLOT
  fb_profile_.reset();
  axis_profile_.reset();
#endif
  // initialize the axes object
  AXIS_REF axis;
  axis = new Axis();
  AxisConfig config;
  axis->setAxisConfig(&config);
  axis->setAxisId(1);
  printf("Axis initialized.\n");

  // initialize the servo object
  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  // initialize the MC_Power FB
  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  // initialize the move FB
  FbMoveVelocity fb_move_vel;
  fb_move_vel.setAxis(axis);
  fb_move_vel.setExecute(mcFALSE);
  fb_move_vel.setContinuousUpdate(mcFALSE);
  fb_move_vel.setVelocity(20);
  fb_move_vel.setAcceleration(50);
  fb_move_vel.setDeceleration(50);
  fb_move_vel.setJerk(100);

  // initialize the test FB
  FbReadMotionState fb_read_motion_state;
  fb_read_motion_state.setAxis(axis);
  fb_read_motion_state.setEnable(mcTRUE);
  fb_read_motion_state.setSource(mcCommandedValue);
  printf("Function block initialized.\n");

#ifdef PLOT
  fb_profile_.addFB("fbReadMotionState");
  fb_profile_.addItemName("fbReadMotionState.constantVelocity");
  fb_profile_.addItemName("fbReadMotionState.accelerating");
  fb_profile_.addItemName("fbReadMotionState.directionPositive");
#endif
  // set test cycle
  double timeout      = 0;
  mcBOOL reverse_flag = mcFALSE;
  while (timeout < 4.0)
  {
    // cyclic execution
    axis->runCycle();
    fb_power.runCycle();
    fb_move_vel.runCycle();
    fb_read_motion_state.runCycle();
    timeout += 0.001;
    // check power state
    if (fb_power.getPowerStatus() == mcTRUE)
    {
      fb_move_vel.setExecute(mcTRUE);
      // printf("Axis powered on %d\n", fb_power.getPowerStatus() == mcTRUE);
    }
    // check the axis state and MC_ReadMotionState outputs
    if (timeout > 0.5)
    {
      if (fb_move_vel.isInVelocity() == mcTRUE && timeout > 2.5)
      {
        // printf("Axis in velocity.\n");
        ASSERT_TRUE(fb_read_motion_state.getConstantVelocity() == mcTRUE);
      }
      else if (reverse_flag == mcFALSE && timeout < 0.8)
      {
        // printf("Axis is accelerating.\n");
        ASSERT_TRUE(fb_read_motion_state.getConstantVelocity() == mcFALSE);
        ASSERT_TRUE(fb_read_motion_state.getAccelerating() == mcTRUE);
        ASSERT_TRUE(fb_read_motion_state.getDecelerating() == mcFALSE);
      }
      else if (reverse_flag == mcTRUE && timeout > 3.2)
      {
        // printf("Axis is decelerating.\n");
        ASSERT_TRUE(fb_read_motion_state.getConstantVelocity() == mcFALSE);
        ASSERT_TRUE(fb_read_motion_state.getAccelerating() == mcFALSE);
        ASSERT_TRUE(fb_read_motion_state.getDecelerating() == mcTRUE);
      }
      ASSERT_TRUE((fb_read_motion_state.getDirectionPositive() == mcTRUE &&
                   reverse_flag == mcFALSE) ||
                  (fb_read_motion_state.getDirectionPositive() == mcFALSE &&
                   reverse_flag == mcTRUE));
      ASSERT_TRUE((fb_read_motion_state.getDirectionNegative() == mcFALSE &&
                   reverse_flag == mcFALSE) ||
                  (fb_read_motion_state.getDirectionPositive() == mcTRUE &&
                   reverse_flag == mcTRUE));
    }

    // reverse velocity
    if (timeout == 3)
    {
      fb_move_vel.setVelocity(-20);
      fb_move_vel.setExecute(mcFALSE);
      reverse_flag = mcTRUE;
    }

    // printf("Run time: %f, pos: %lf, vel: %lf, acc: %lf, ConsVel:%d, Acc:%d,
    // Dirt:%d\n",
    //       timeout, axis->toUserPosCmd(), axis->toUserVelCmd(),
    //       axis->toUserAccCmd(), fb_read_motion_state.getConstantVelocity(),
    //       fb_read_motion_state.getAccelerating(),
    //       fb_read_motion_state.getDirectionPositive());

#ifdef PLOT
    axis_profile_.addState(axis->toUserPosCmd(), axis->toUserVelCmd(),
                           axis->toUserAccCmd(), timeout);
    fb_profile_.addState("fbReadMotionState.constantVelocity",
                         fb_read_motion_state.getConstantVelocity() == mcTRUE);
    fb_profile_.addState("fbReadMotionState.accelerating",
                         fb_read_motion_state.getAccelerating() == mcTRUE);
    fb_profile_.addState("fbReadMotionState.directionPositive",
                         fb_read_motion_state.getDirectionPositive() == mcTRUE);
    fb_profile_.addTime(timeout);
#endif
  }

#ifdef PLOT
  axis_profile_.plot("mc_read_motion_state_axis.png");
  fb_profile_.plot("mc_read_motion_state_fb.png");
#endif

  // posprocessing
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_SetOverride
TEST_F(FunctionBlockTest, MC_SetOverride)
{
  // plot
#ifdef PLOT
  fb_profile_.reset();
  axis_profile_.reset();
#endif

  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbMoveVelocity mov_vel;
  mov_vel.setAxis(axis);
  mov_vel.setVelocity(200);
  mov_vel.setAcceleration(500);
  mov_vel.setDeceleration(500);
  mov_vel.setJerk(5000);
  mov_vel.setBufferMode(mcAborting);

  FbSetOverride fb_set_override;
  fb_set_override.setAxis(axis);
  fb_set_override.setVelFactor(0.5);
  fb_set_override.setAccFactor(0.5);
  fb_set_override.setJerkFactor(0.5);

#ifdef PLOT
  fb_profile_.addFB("fbSetOverride");
  fb_profile_.addItemName("fbSetOverride.isEnabled");
#endif
  double time_out = 9;
  double t        = 0;
  while (t < time_out)
  {
    axis->runCycle();
    fb_power.runCycle();
    mov_vel.runCycle();
    fb_set_override.runCycle();

    if (mov_vel.isEnabled() == mcFALSE)
    {
      mov_vel.setExecute(mcTRUE);
      std::cout << "axis poweron, set start velocity to 500\n";
    }

    if (fabs(t - 1.0) < 0.0001)
    {
      fb_set_override.setEnable(mcTRUE);
      std::cout << "enable overriding, set vel, acc, and jerk factors all to "
                   "1/2\n";
    }

    if (fabs(t - 4.0) < 0.0001)
    {
      ASSERT_LT(fabs(axis->toUserVel() - 100), 1);
      fb_set_override.setEnable(mcFALSE);
      fb_set_override.setVelFactor(0);
      fb_set_override.setAccFactor(1);
      fb_set_override.setJerkFactor(1);
      std::cout << "disable overriding\n";
    }

    if (fabs(t - 6.0) < 0.0001)
    {
      ASSERT_LT(fabs(axis->toUserVel() - 100), 1);
    }

    t += 0.001;
    // printf("Axis: Run time: %f,\tvel: %f,\tacc:%f\n", t, axis->toUserVel(),
    // axis->toUserAcc());

#ifdef PLOT
    axis_profile_.addState(axis->toUserPosCmd(), axis->toUserVelCmd(),
                           axis->toUserAccCmd(), t);
    fb_profile_.addState("fbSetOverride.isEnabled",
                         fb_set_override.isEnabled() == mcTRUE);
    fb_profile_.addTime(t);
#endif
  }

#ifdef PLOT
  axis_profile_.plot("mc_set_override_axis.png");
  fb_profile_.plot("mc_set_override_fb.png");
#endif

  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

TEST_F(FunctionBlockTest, MC_DigitalCamSwitch)
{
#ifdef PLOT
  fb_profile_.reset();
  axis_profile_.reset();
#endif

  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbMoveVelocity fb_move_vel;
  fb_move_vel.setAxis(axis);
  fb_move_vel.setExecute(mcFALSE);
  fb_move_vel.setContinuousUpdate(mcFALSE);
  fb_move_vel.setVelocity(1);
  fb_move_vel.setAcceleration(50);
  fb_move_vel.setDeceleration(50);
  fb_move_vel.setJerk(500);
  printf("Function block initialized.\n");

  McCamSwitch cam_switch[4] = { { 1, 2.0, 3.0, 1, 0, NAN },
                                { 1, 2.5, 3.0, 2, 0, NAN },
                                { 1, 4.0, 1.0, 0, 0, NAN },
                                { 2, 3.0, NAN, 0, 1, 1350 } };

  McCamSwitchRef switches;
  switches.switch_number_      = 4;
  switches.cam_switch_pointer_ = cam_switch;

  McTrack tracks[2] = { { mcTRUE, 5, 0.5, 0.5, 0 },
                        { mcTRUE, 5, 0.5, 0.5, 0 } };

  mcDWORD output;
  FbDigitalCamSwitch fb_digital_cam_switch;
  fb_digital_cam_switch.setAxis(axis);
  fb_digital_cam_switch.setEnable(mcFALSE);
  fb_digital_cam_switch.setSwitches(switches);
  fb_digital_cam_switch.setOutputs(&output);
  fb_digital_cam_switch.setTrackOptions(tracks);
  fb_digital_cam_switch.setEnableMask(0x3);
  fb_digital_cam_switch.setValueSource(mcSetValue);

#ifdef PLOT
  fb_profile_.addFB("fbDigitalCamSwitch");
  fb_profile_.addItemName("fbDigitalCamSwitch.Track1");
  fb_profile_.addItemName("fbDigitalCamSwitch.Track2");
  fb_profile_.addItemName("fbDigitalCamSwitch.inOperation");
#endif

  double timeout = 0;
  while (timeout < 10.0)
  {
    axis->runCycle();
    fb_power.runCycle();
    fb_move_vel.runCycle();
    fb_digital_cam_switch.runCycle();
    timeout += 0.001;

#ifdef PLOT
    axis_profile_.addState(axis->toUserPos(), axis->toUserVel(),
                           axis->toUserAccCmd(), timeout);
    fb_profile_.addState("fbDigitalCamSwitch.Track1", output & 0x1);
    fb_profile_.addState("fbDigitalCamSwitch.Track2", output & 0x2);
    fb_profile_.addState("fbDigitalCamSwitch.inOperation",
                         fb_digital_cam_switch.isInOperation() == mcTRUE);
    fb_profile_.addTime(timeout);
#endif

    if (fb_move_vel.isEnabled() == mcFALSE &&
        fb_power.getPowerStatus() == mcTRUE)
    {
      fb_move_vel.setExecute(mcTRUE);
      fb_digital_cam_switch.setEnable(mcTRUE);
    }
  }
#ifdef PLOT
  axis_profile_.plot("mc_digital_cam_switch_axis.png");
  fb_profile_.plot("mc_digital_cam_switch_fb.png");
#endif
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test MC_MoveSuperimposed without underlying motion
TEST_F(FunctionBlockTest, MC_MoveSuperimposed1)
{
#ifdef PLOT
  fb_profile_.reset();
  axis_profile_.reset();
#endif
  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbMoveSuperimposed fb_move_sup;
  fb_move_sup.setAxis(axis);
  fb_move_sup.setContinuousUpdate(mcFALSE);
  fb_move_sup.setDistance(600);
  fb_move_sup.setVelocityDiff(300);
  fb_move_sup.setAcceleration(500);
  fb_move_sup.setDeceleration(500);
  fb_move_sup.setJerk(5000);
  fb_move_sup.setExecute(mcFALSE);
#ifdef PLOT
  fb_profile_.addFB("fb_move_sup");
  fb_profile_.addItemName("fb_move_sup.go");
  fb_profile_.addItemName("fb_move_sup.done");
#endif
  double time_out = 5;
  double t        = 0;
  while (t < time_out)
  {
    axis->runCycle();
    fb_power.runCycle();
    fb_move_sup.runCycle();

    if (1 < t && fb_power.isEnabled() == mcTRUE)
      fb_move_sup.setExecute(mcTRUE);

#ifdef PLOT
    axis_profile_.addState(axis->toUserPos(), axis->toUserVel(),
                           axis->toUserAccCmd(), t);
    fb_profile_.addState("fb_move_sup.go", fb_move_sup.isEnabled() == mcTRUE);
    fb_profile_.addState("fb_move_sup.done", fb_move_sup.isDone() == mcTRUE);
    fb_profile_.addTime(t);
#endif
    t += 0.001;
  }
#ifdef PLOT
  axis_profile_.plot("mc_mov_sup1_axis.png");
  fb_profile_.plot("mc_mov_sup1_fb.png");
#endif
  ASSERT_LT(fabs(axis->toUserVel() - 0.0), 0.01);
  ASSERT_LT(fabs(axis->toUserPos() - 600), 0.01);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test two MC_MoveSuperimposed with underlying motion
TEST_F(FunctionBlockTest, MC_MoveSuperimposed2)
{
#ifdef PLOT
  fb_profile_.reset();
  axis_profile_.reset();
#endif
  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbMoveRelative fb_move_rel;
  fb_move_rel.setAxis(axis);
  fb_move_rel.setContinuousUpdate(mcFALSE);
  fb_move_rel.setDistance(900);
  fb_move_rel.setVelocity(300);
  fb_move_rel.setAcceleration(500);
  fb_move_rel.setDeceleration(500);
  fb_move_rel.setJerk(5000);
  fb_move_rel.setBufferMode(mcAborting);

  FbMoveSuperimposed fb_move_sup1;
  fb_move_sup1.setAxis(axis);
  fb_move_sup1.setContinuousUpdate(mcFALSE);
  fb_move_sup1.setDistance(600);
  fb_move_sup1.setVelocityDiff(300);
  fb_move_sup1.setAcceleration(300);
  fb_move_sup1.setDeceleration(300);
  fb_move_sup1.setJerk(5000);
  fb_move_sup1.setExecute(mcFALSE);

  FbMoveSuperimposed fb_move_sup2;
  fb_move_sup2.setAxis(axis);
  fb_move_sup2.setContinuousUpdate(mcFALSE);
  fb_move_sup2.setDistance(100);
  fb_move_sup2.setVelocityDiff(200);
  fb_move_sup2.setAcceleration(100);
  fb_move_sup2.setDeceleration(100);
  fb_move_sup2.setJerk(5000);
  fb_move_sup2.setExecute(mcFALSE);

#ifdef PLOT
  fb_profile_.addFB("fb_move_rel");
  fb_profile_.addFB("fb_move_sup1");
  fb_profile_.addFB("fb_move_sup2");
  fb_profile_.addItemName("fb_move_rel.go");
  fb_profile_.addItemName("fb_move_rel.done");
  fb_profile_.addItemName("fb_move_rel.aborted");
  fb_profile_.addItemName("fb_move_sup1.go");
  fb_profile_.addItemName("fb_move_sup1.done");
  fb_profile_.addItemName("fb_move_sup1.aborted");
  fb_profile_.addItemName("fb_move_sup2.go");
  fb_profile_.addItemName("fb_move_sup2.done");
  fb_profile_.addItemName("fb_move_sup2.aborted");
#endif
  double time_out = 4;
  double t        = 0;
  while (t < time_out)
  {
    axis->runCycle();
    fb_power.runCycle();
    fb_move_rel.runCycle();
    fb_move_sup1.runCycle();
    fb_move_sup2.runCycle();

    // After enabled, move_relative_1 start to move
    if (fb_power.isEnabled() == mcTRUE && t < 1)
      fb_move_rel.setExecute(mcTRUE);

    if (0.5 < t && fb_move_rel.isEnabled() == mcTRUE)
      fb_move_sup1.setExecute(mcTRUE);

    if (1.0 < t && fb_move_rel.isEnabled() == mcTRUE)
      fb_move_sup2.setExecute(mcTRUE);

#ifdef PLOT
    axis_profile_.addState(axis->toUserPos(), axis->toUserVel(),
                           axis->toUserAccCmd(), t);
    fb_profile_.addState("fb_move_rel.go", fb_move_rel.isEnabled() == mcTRUE);
    fb_profile_.addState("fb_move_rel.done", fb_move_rel.isDone() == mcTRUE);
    fb_profile_.addState("fb_move_rel.aborted",
                         fb_move_rel.isAborted() == mcTRUE);
    fb_profile_.addState("fb_move_sup1.go", fb_move_sup1.isEnabled() == mcTRUE);
    fb_profile_.addState("fb_move_sup1.done", fb_move_sup1.isDone() == mcTRUE);
    fb_profile_.addState("fb_move_sup1.aborted",
                         fb_move_sup1.isAborted() == mcTRUE);
    fb_profile_.addState("fb_move_sup2.go", fb_move_sup2.isEnabled() == mcTRUE);
    fb_profile_.addState("fb_move_sup2.done", fb_move_sup2.isDone() == mcTRUE);
    fb_profile_.addState("fb_move_sup2.aborted",
                         fb_move_sup2.isAborted() == mcTRUE);
    fb_profile_.addTime(t);
#endif
    t += 0.001;
  }
#ifdef PLOT
  axis_profile_.plot("mc_mov_sup2_axis.png");
  fb_profile_.plot("mc_mov_sup2_fb.png");
#endif
  ASSERT_LT(fabs(axis->toUserVel() - 0.0), 0.01);
  ASSERT_GE(fabs(axis->toUserPos()), 1000);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

// Test one MC_MoveSuperimposed with underlying motion,
// align with the example in Part 1.
TEST_F(FunctionBlockTest, MC_MoveSuperimposed3)
{
#ifdef PLOT
  fb_profile_.reset();
  axis_profile_.reset();
#endif
  AxisConfig config;
  AXIS_REF axis;
  axis = new Axis();
  axis->setAxisId(1);

  axis->setAxisConfig(&config);
  printf("Axis initialized.\n");

  Servo* servo;
  servo = new Servo();
  axis->setServo(servo);

  FbPower fb_power;
  fb_power.setAxis(axis);
  fb_power.setEnable(mcTRUE);
  fb_power.setEnablePositive(mcTRUE);
  fb_power.setEnableNegative(mcTRUE);

  FbMoveRelative fb_move_rel;
  fb_move_rel.setAxis(axis);
  fb_move_rel.setContinuousUpdate(mcFALSE);
  fb_move_rel.setDistance(10000);
  fb_move_rel.setVelocity(300);
  fb_move_rel.setAcceleration(100);
  fb_move_rel.setDeceleration(100);
  fb_move_rel.setJerk(1000);
  fb_move_rel.setBufferMode(mcAborting);

  FbMoveSuperimposed fb_move_sup;
  fb_move_sup.setAxis(axis);
  fb_move_sup.setContinuousUpdate(mcFALSE);
  fb_move_sup.setDistance(1000);
  fb_move_sup.setVelocityDiff(200);
  fb_move_sup.setAcceleration(100);
  fb_move_sup.setDeceleration(100);
  fb_move_sup.setJerk(1000);
  fb_move_sup.setExecute(mcFALSE);
#ifdef PLOT
  fb_profile_.addFB("fb_move_rel");
  fb_profile_.addFB("fb_move_sup");
  fb_profile_.addItemName("fb_move_rel.go");
  fb_profile_.addItemName("fb_move_rel.done");
  fb_profile_.addItemName("fb_move_rel.aborted");
  fb_profile_.addItemName("fb_move_sup.go");
  fb_profile_.addItemName("fb_move_sup.done");
#endif
  double time_out = 40;
  double t        = 0;
  while (t < time_out)
  {
    axis->runCycle();
    fb_power.runCycle();
    fb_move_rel.runCycle();
    fb_move_sup.runCycle();

    // After enabled, move_relative_1 start to move
    if (fb_power.isEnabled() == mcTRUE && t < 1)
      fb_move_rel.setExecute(mcTRUE);

    if (fabs(t - 4) <= 0.001 && fb_move_rel.isEnabled() == mcTRUE)
      fb_move_sup.setExecute(mcTRUE);

    if (fabs(t - 11) <= 0.001 && fb_move_sup.isEnabled() == mcTRUE)
      fb_move_sup.setExecute(mcFALSE);

    if (fabs(t - 12) <= 0.001 && fb_move_sup.isEnabled() == mcFALSE)
      fb_move_sup.setExecute(mcTRUE);

    if (fabs(t - 14) <= 0.001 && fb_move_sup.isEnabled() == mcTRUE)
      fb_move_sup.setExecute(mcFALSE);

    if (fabs(t - 20) <= 0.001 && fb_move_sup.isEnabled() == mcFALSE)
      fb_move_sup.setExecute(mcTRUE);

    if (t > 30 && fb_move_sup.isDone() == mcTRUE)
      fb_move_sup.setExecute(mcFALSE);

#ifdef PLOT
    axis_profile_.addState(axis->toUserPos(), axis->toUserVel(),
                           axis->toUserAccCmd(), t);
    fb_profile_.addState("fb_move_rel.go", fb_move_rel.isEnabled() == mcTRUE);
    fb_profile_.addState("fb_move_rel.done", fb_move_rel.isDone() == mcTRUE);
    fb_profile_.addState("fb_move_rel.aborted",
                         fb_move_rel.isAborted() == mcTRUE);
    fb_profile_.addState("fb_move_sup.go", fb_move_sup.isEnabled() == mcTRUE);
    fb_profile_.addState("fb_move_sup.done", fb_move_sup.isDone() == mcTRUE);
    fb_profile_.addTime(t);
#endif
    t += 0.001;
  }
#ifdef PLOT
  axis_profile_.plot("mc_mov_sup3_axis.png");
  fb_profile_.plot("mc_mov_sup3_fb.png");
#endif
  ASSERT_LT(fabs(axis->toUserVel() - 0.0), 0.01);
  ASSERT_GE(fabs(axis->toUserPos()), 12000);
  delete servo;
  delete axis;
  servo = nullptr;
  axis  = nullptr;
  printf("FB test end. Delete axis and servo.\n");
}

int main(int argc, char** argv)
{
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
