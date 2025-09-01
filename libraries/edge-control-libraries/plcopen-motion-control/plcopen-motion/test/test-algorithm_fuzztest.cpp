// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

#include <inttypes.h>
#include "fuzztest/fuzztest.h"
#include "gtest/gtest.h"

#include <algo/public/include/offline_scurve_planner.hpp>
#include <algo/public/include/online_scurve_planner.hpp>
#include <fb/common/include/planner.hpp>
#include <algo/public/include/ruckig_planner.hpp>
//#include <RTmotion/algorithm/time_optimal_trajectory_generation.hpp>

// offline_scurve_planner.cpp functions
void TestScurvePlannerOffLineGetTrajectoryFunction(double t)
{
  trajectory_processing::ScurvePlannerOffLine S;
  S.getTrajectoryFunction(t);
}

void TestScurvePlannerOffLineplanTrajectory1D(double T)
{
  trajectory_processing::ScurvePlannerOffLine S;
  S.planTrajectory1D(T);
}

// online_scurve_planner.cpp functions
void TestScurvePlannerOnLineGetWaypoint(double t)
{
  trajectory_processing::ScurvePlannerOnLine S;
  S.getWaypoint(t);
}

// planner.cpp functions
void TestAxisPlannerSetCondition(double start_pos, double end_pos,
                                 double start_vel, double end_vel,
                                 double start_acc, double end_acc,
                                 double vel_max, double acc_max,
                                 double jerk_max)
{
  trajectory_processing::AxisPlanner A;
  A.setCondition(start_pos, end_pos, start_vel, end_vel, start_acc, end_acc,
                 NAN, vel_max, acc_max, jerk_max, RTmotion::mcOffLine);
}

void TestAxisPlannerGetTrajectoryPoint(double t)
{
  trajectory_processing::AxisPlanner A;
  A.getTrajectoryPoint(t);
}

void TestAxisPlannerSetStartTime(double t)
{
  trajectory_processing::AxisPlanner A;
  A.setStartTime(t);
}

void TestAxisPlannerSetFrequency(double f)
{
  trajectory_processing::AxisPlanner A;
  A.setFrequency(f);
}

// ruckig_planner.cpp functions
void TestRuckigPlannerGetWaypoint(double t)
{
  trajectory_processing::RuckigPlanner R;
  R.getWaypoint(t);
}

void TestRuckigPlannerSetFrequency(double f)
{
  trajectory_processing::RuckigPlanner R;
  R.setFrequency(f);
}

// time_optimal_trajectory_generation.cpp functions

/* Todo: resolve Eigen/Core include issue

void TestPathGetConfig(double s)
{
    trajectory_processing::Path P;
    P.getConfig(s);
}

void TestPathGetTangent(double s)
{
    trajectory_processing::Path P;
    P.getTangent(s);
}

void TestPathGetCurvature(double s)
{
    trajectory_processing::Path P;
    P.getCurvature(s);
}

void TestTrajectoryGetMinMaxPathAcceleration(double path_pos, double path_vel,
bool max)
{
    trajectory_processing::Tragectory T;
    T.getMinMaxPathAcceleration(path_pos, path_vel, max);
}

void TestTrajectoryGetMinMaxPhaseSlope(double path_pos, double path_vel, bool
max)
{
    trajectory_processing::Tragectory T;
    T.getMinMaxPhaseSlope(path_pos, path_vel, max);
}

void TestTrajectoryGetAccelerationMaxPathVelocity(double path_pos)
{
    trajectory_processing::Tragectory T;
    T.getAccelerationMaxPathVelocity(path_pos);
}

void TestTrajectoryGetVelocityMaxPathVelocity(double path_pos)
{
    trajectory_processing::Tragectory T;
    T.getVelocityMaxPathVelocity(path_pos);
}

void TestTrajectoryGetAccelerationMaxPathVelocityDeriv(double path_pos)
{
    trajectory_processing::Tragectory T;
    T.getAccelerationMaxPathVelocityDeriv(path_pos);
}

void TestTrajectoryGetVelocityMaxPathVelocityDeriv(double path_pos)
{
    trajectory_processing::Tragectory T;
    T.getVelocityMaxPathVelocityDeriv(path_pos);
}

void TestTrajectoryGetTrajectorySegment(double time)
{
    trajectory_processing::Tragectory T;
    T.getTrajectorySegment(time);
}

void TestTrajectoryGetPosition(double time)
{
    trajectory_processing::Tragectory T;
    T.getPosition(time);
}

void TestTrajectoryGetVelocity(double time)
{
    trajectory_processing::Tragectory T;
    T.getVelocity(time);
}

void TestTrajectoryGetAcceleration(double time)
{
    trajectory_processing::Tragectory T;
    T.getAcceleration(time);
}

*/

FUZZ_TEST(FuzzSuite, TestScurvePlannerOffLineGetTrajectoryFunction);

FUZZ_TEST(FuzzSuite, TestScurvePlannerOffLineplanTrajectory1D);

// Commented so it is not run with every github runner, ignore output ex:
// Polynomial coeffs: a0 0.000000, a0 0.000000, a0 0.000000, a0 -nan, a0 -nan,
// a0 -nan
// FUZZ_TEST(FuzzSuite, TestScurvePlannerOnLineGetWaypoint);

FUZZ_TEST(FuzzSuite, TestAxisPlannerSetCondition);
FUZZ_TEST(FuzzSuite, TestAxisPlannerGetTrajectoryPoint);
FUZZ_TEST(FuzzSuite, TestAxisPlannerSetStartTime);
FUZZ_TEST(FuzzSuite, TestAxisPlannerSetFrequency);

FUZZ_TEST(FuzzSuite, TestRuckigPlannerGetWaypoint);
FUZZ_TEST(FuzzSuite, TestRuckigPlannerSetFrequency);

// FUZZ_TEST(FuzzSuite, TestPathGetConfig);
// FUZZ_TEST(FuzzSuite, TestPathGetTangent);
// FUZZ_TEST(FuzzSuite, TestPathGetCurvature);
// FUZZ_TEST(FuzzSuite, TestTrajectoryGetMinMaxPathAcceleration);
// FUZZ_TEST(FuzzSuite, TestTrajectoryGetMinMaxPhaseSlope);
// FUZZ_TEST(FuzzSuite, TestTrajectoryGetAccelerationMaxPathVelocity);
// FUZZ_TEST(FuzzSuite, TestTrajectoryGetVelocityMaxPathVelocity);
// FUZZ_TEST(FuzzSuite, TestTrajectoryGetAccelerationMaxPathVelocityDeriv);
// FUZZ_TEST(FuzzSuite, TestTrajectoryGetVelocityMaxPathVelocityDeriv);
// FUZZ_TEST(FuzzSuite, TestTrajectoryGetTrajectorySegment);
// FUZZ_TEST(FuzzSuite, TestTrajectoryGetPosition);
// FUZZ_TEST(FuzzSuite, TestTrajectoryGetVelocity);
// FUZZ_TEST(FuzzSuite, TestTrajectoryGetAcceleration);