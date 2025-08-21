// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

#include <inttypes.h>
#include "fuzztest/fuzztest.h"
#include "gtest/gtest.h"

#include <fb/common/include/execution_node.hpp>
#include <fb/common/include/fb_axis_motion.hpp>
#include <fb/common/include/fb_axis_read.hpp>
#include <fb/public/include/fb_homing.hpp>
#include <fb/public/include/fb_power.hpp>
#include <fb/public/include/fb_reset.hpp>
#include <fb/private/include/fb_set_position.hpp>

// execution_node.cpp functions
void TestExecutionNodeSetFrequency(RTmotion::mcLREAL f)
{
  RTmotion::ExecutionNode N;
  N.setFrequency(f);
}

void TestExecutionNodeSetStartPos(RTmotion::mcLREAL pos)
{
  RTmotion::ExecutionNode N;
  N.setStartPos(pos);
}

void TestExecutionNodeSetStartVel(RTmotion::mcLREAL v)
{
  RTmotion::ExecutionNode N;
  N.setStartVel(v);
}

void TestExecutionNodeSetStartAcc(RTmotion::mcLREAL a)
{
  RTmotion::ExecutionNode N;
  N.setStartAcc(a);
}

void TestExecutionNodeSetEndAcc(RTmotion::mcLREAL a)
{
  RTmotion::ExecutionNode N;
  N.setEndAcc(a);
}

void TestExecutionNodeSetTerminateCondition(RTmotion::mcLREAL rp)
{
  RTmotion::ExecutionNode N;
  N.setTerminateCondition(rp);
}

void TestExecutionNodeSetEndVel(RTmotion::mcLREAL v)
{
  RTmotion::ExecutionNode N;
  N.setEndVel(v);
}

void TestExecutionNodeSetEndPos(RTmotion::mcLREAL p)
{
  RTmotion::ExecutionNode N;
  N.setEndPos(p);
}

void TestExecutionNodeOffsetFB(RTmotion::mcLREAL hp)
{
  RTmotion::ExecutionNode N;
  N.offsetFB(hp);
}

void TestExecutionNodeSetPlannerStartTime(RTmotion::mcLREAL t)
{
  RTmotion::ExecutionNode N;
  N.setPlannerStartTime(t);
}

// fb_axis_motion.cpp functions
void TestFbAxisMotionSetExecute(RTmotion::mcBOOL e)
{
  RTmotion::FbAxisMotion F;
  F.setExecute(e);
}

void TestFbAxisMotionSetContinuousUpdate(RTmotion::mcBOOL cu)
{
  RTmotion::FbAxisMotion F;
  F.setContinuousUpdate(cu);
}

// fb_axis_read.cpp functions
void TestFbAxisReadSetExecute(RTmotion::mcBOOL e)
{
  RTmotion::FbAxisAdmin F;
  F.setEnable(e);
}

// fb_home.cpp functions
void TestFbHomeSetRefSignal(RTmotion::mcBOOL s)
{
  RTmotion::FbHoming F;
  F.setRefSignal(s);
}

void TestFbHomeSetLimitNegSignal(RTmotion::mcBOOL s)
{
  RTmotion::FbHoming F;
  F.setLimitNegSignal(s);
}

void TestFbHomeSetLimitPosSignal(RTmotion::mcBOOL s)
{
  RTmotion::FbHoming F;
  F.setLimitPosSignal(s);
}

// fb_power.cpp functions
void TestFbPowerSetExecute(RTmotion::mcBOOL e)
{
  RTmotion::FbPower F;
  F.setEnable(e);
}

void TestFbPowerSetEnablePositive(RTmotion::mcBOOL ep)
{
  RTmotion::FbPower F;
  F.setEnablePositive(ep);
}

void TestFbPowerSetEnableNegative(RTmotion::mcBOOL en)
{
  RTmotion::FbPower F;
  F.setEnableNegative(en);
}

// fb_reset.cpp functions
void TestFbResetSetExecute(RTmotion::mcBOOL e)
{
  RTmotion::FbReset F;
  F.setEnable(e);
}

// fb_set_position.cpp functions
void TestFbSetPositionSetExecute(RTmotion::mcBOOL e)
{
  RTmotion::FbSetPosition F;
  F.setEnable(e);
}

FUZZ_TEST(FuzzSuite, TestExecutionNodeSetFrequency);
FUZZ_TEST(FuzzSuite, TestExecutionNodeSetStartPos);
FUZZ_TEST(FuzzSuite, TestExecutionNodeSetStartVel);
FUZZ_TEST(FuzzSuite, TestExecutionNodeSetStartAcc);
FUZZ_TEST(FuzzSuite, TestExecutionNodeSetEndAcc);
FUZZ_TEST(FuzzSuite, TestExecutionNodeSetTerminateCondition);
FUZZ_TEST(FuzzSuite, TestExecutionNodeSetEndVel);
FUZZ_TEST(FuzzSuite, TestExecutionNodeSetEndPos);
FUZZ_TEST(FuzzSuite, TestExecutionNodeOffsetFB);
// FUZZ_TEST(FuzzSuite, TestExecutionNodeOnExecution);
FUZZ_TEST(FuzzSuite, TestExecutionNodeSetPlannerStartTime);

// FUZZ_TEST(FuzzSuite, TestFbAxisMotionSetExecute);
// FUZZ_TEST(FuzzSuite, TestFbAxisMotionSetContinuousUpdate);

// FUZZ_TEST(FuzzSuite, TestFbAxisReadSetExecute);

// FUZZ_TEST(FuzzSuite, TestFbHomeSetRefSignal);
// FUZZ_TEST(FuzzSuite, TestFbHomeSetLimitNegSignal);
// FUZZ_TEST(FuzzSuite, TestFbHomeSetLimitPosSignal);

// FUZZ_TEST(FuzzSuite, TestFbPowerSetExecute);
// FUZZ_TEST(FuzzSuite, TestFbPowerSetEnablePositive);
// FUZZ_TEST(FuzzSuite, TestFbPowerSetEnableNegative);

// FUZZ_TEST(FuzzSuite, TestFbResetSetExecute);

// FUZZ_TEST(FuzzSuite, TestFbSetPositionSetExecute);
