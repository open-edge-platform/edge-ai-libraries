// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

#include <inttypes.h>
#include "fuzztest/fuzztest.h"
#include "gtest/gtest.h"

#include <fb/common/include/servo.hpp>

void TestServoRunCycle(RTmotion::mcLREAL f)
{
  RTmotion::Servo S;
  S.runCycle(f);
}

FUZZ_TEST(FuzzSuite, TestServoRunCycle);
