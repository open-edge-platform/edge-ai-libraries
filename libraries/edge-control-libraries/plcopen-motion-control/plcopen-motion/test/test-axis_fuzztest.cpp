// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

#include <inttypes.h>
#include "fuzztest/fuzztest.h"
#include "gtest/gtest.h"

#include <fb/common/include/axis.hpp>

void TestAxisSetBufferSize(RTmotion::mcUSINT size)
{
  RTmotion::AXIS_REF A;
  A = new RTmotion::Axis();
  A->setNodeQueueSize(size);

  A->deleteServo();
  A->deleteConfig();

  delete A;
}

void TestAxisToEncoderUnit(RTmotion::mcLREAL x)
{
  RTmotion::AXIS_REF A;
  A = new RTmotion::Axis();
  A->toEncoderUnit(x);

  A->deleteServo();
  A->deleteConfig();

  delete A;
}

void TestAxisCmdsProcessing()
{
  RTmotion::AXIS_REF A;
  A = new RTmotion::Axis();
  A->cmdsProcessing();

  A->deleteServo();
  A->deleteConfig();

  delete A;
}

void TestAxisSyncMotionKernelResultsToAxis()
{
  RTmotion::AXIS_REF A;
  A = new RTmotion::Axis();
  A->syncMotionKernelResultsToAxis();

  A->deleteServo();
  A->deleteConfig();

  delete A;
}

void TestAxisFixOverFlow(RTmotion::mcLREAL x)
{
  RTmotion::AXIS_REF A;
  A = new RTmotion::Axis();
  A->fixOverFlow(x);

  A->deleteServo();
  A->deleteConfig();

  delete A;
}

void TestAxisResetError(RTmotion::mcBOOL r)
{
  RTmotion::AXIS_REF A;
  A = new RTmotion::Axis();
  A->resetError(r);

  A->deleteServo();
  A->deleteConfig();

  delete A;
}

FUZZ_TEST(FuzzSuite, TestAxisSetBufferSize)
    .WithDomains(/*x:*/ fuzztest::InRange(0, 10));
FUZZ_TEST(FuzzSuite, TestAxisToEncoderUnit);
FUZZ_TEST(FuzzSuite, TestAxisCmdsProcessing);
FUZZ_TEST(FuzzSuite, TestAxisSyncMotionKernelResultsToAxis);
// error: static_assert failed due to requirement
// 'always_false<RTmotion::mcBOOL>'
// "=> Type not supported yet. Consider filing an issue."
// FUZZ_TEST(FuzzSuite, TestAxisResetError);