// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file planner_test.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <fb/common/include/planner.hpp>
#include <thread>
#include <fb/common/include/logging.hpp>
#include "gtest/gtest.h"

#ifdef PLOT
#include <plot/matplotlibcpp.h>
namespace plt = matplotlibcpp;
#endif

namespace traj_pro = trajectory_processing;

// The fixture for testing class Foo.
class PlannerTest : public ::testing::Test
{
protected:
  // You can remove any or all of the following functions if their bodies would
  // be empty.

  PlannerTest()
  {
    // You can do set-up work for each test here.
  }

  ~PlannerTest() override
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
  void trajectoryPlot(double delta_time, double T = 10,
                      const std::string& file_name = "scurve.png")
  {
    double iter_t = 0;
    std::vector<double> pos, vel, acc, jerk, t;
    while (iter_t < T)
    {
      double* point = planner_.getTrajectoryPoint(iter_t);
      pos.push_back(point[mcPositionId]);
      vel.push_back(point[mcSpeedId]);
      acc.push_back(point[mcAccelerationId]);
      jerk.push_back(point[mcJerkId]);
      t.push_back(iter_t);
      iter_t += delta_time;
    }

    // Set the size of output image to 1280x720 pixels
    plt::figure_size(1280, 720);
    // Plot line from given t and pos.
    plt::subplot(4, 1, 1);
    plt::title("Scurve Figure");
    plt::named_plot("Position", t, pos, "tab:blue");
    plt::ylabel("Position");
    // Plot line from given t and pos.
    plt::subplot(4, 1, 2);
    plt::named_plot("Velocity", t, vel, "tab:orange");
    plt::ylabel("Velocity");
    // Plot line from given t and pos.
    plt::subplot(4, 1, 3);
    plt::named_plot("Acceleration", t, acc, "tab:green");
    plt::ylabel("Acceleration");
    // Plot line from given t and pos.
    plt::subplot(4, 1, 4);
    plt::named_plot("Jerk", t, jerk, "tab:red");
    plt::xlabel("time");
    plt::ylabel("Jerk");
    // Save the image (file format is determined by the extension)
    plt::save(file_name);
  }
#endif
  traj_pro::AxisPlanner planner_ = {};
};

// Tests velocity profile
TEST_F(PlannerTest, VelocityUp)
{
  planner_.setCondition(5, NAN, -1, 10, 0, 0, NAN, 5, 10, 30,
                        RTmotion::mcOffLine);
  RTmotion::MC_ERROR_CODE res = planner_.planTrajectory();

  if (res != RTmotion::mcErrorCodeGood)
    printf("Failed to find scurve profile \n");

  INFO_PRINT("Scurve profile: Ta = %f, Tv = %f, Td = %f, Tj1 = %f, Tj2 = %f \n",
             planner_.getScurveProfile().Ta, planner_.getScurveProfile().Tv,
             planner_.getScurveProfile().Td, planner_.getScurveProfile().Tj1,
             planner_.getScurveProfile().Tj2);
  ASSERT_LT(abs(planner_.getScurveProfile().Ta - 1.4333), 0.0001);
  ASSERT_LT(abs(planner_.getScurveProfile().Tv - 0), 0.0001);
  ASSERT_LT(abs(planner_.getScurveProfile().Td - 0), 0.0001);
  ASSERT_LT(abs(planner_.getScurveProfile().Tj1 - 0.3333), 0.0001);
  ASSERT_LT(abs(planner_.getScurveProfile().Tj2 - 0), 0.0001);
#ifdef PLOT
  trajectoryPlot(0.001, 2, "VelocityUp.png");
#endif
}

// Tests velocity profile
TEST_F(PlannerTest, VelocityDown)
{
  planner_.setCondition(5, NAN, 10, -5, 0, 0, NAN, 5, 10, 30,
                        RTmotion::mcOffLine);
  RTmotion::MC_ERROR_CODE res = planner_.planTrajectory();

  if (res != RTmotion::mcErrorCodeGood)
    printf("Failed to find scurve profile \n");

  INFO_PRINT("Scurve profile: Ta = %f, Tv = %f, Td = %f, Tj1 = %f, Tj2 = %f \n",
             planner_.getScurveProfile().Ta, planner_.getScurveProfile().Tv,
             planner_.getScurveProfile().Td, planner_.getScurveProfile().Tj1,
             planner_.getScurveProfile().Tj2);
  ASSERT_LT(abs(planner_.getScurveProfile().Ta - 1.8333), 0.0001);
  ASSERT_LT(abs(planner_.getScurveProfile().Tv - 0), 0.0001);
  ASSERT_LT(abs(planner_.getScurveProfile().Td - 0), 0.0001);
  ASSERT_LT(abs(planner_.getScurveProfile().Tj1 - 0.3333), 0.0001);
  ASSERT_LT(abs(planner_.getScurveProfile().Tj2 - 0), 0.0001);
#ifdef PLOT
  trajectoryPlot(0.001, 2, "VelocityDown.png");
#endif
}

// Tests example 3.9 at page 82 in 'Trajectory planning for automatic machines
// and robots(2008)' Maximum speed reached
TEST_F(PlannerTest, Example_3_9)
{
  planner_.setCondition(0, 10, 1, 0, 0, 0, NAN, 5, 10, 30, RTmotion::mcRuckig);
  RTmotion::MC_ERROR_CODE res = planner_.planTrajectory();

  if (res != RTmotion::mcErrorCodeGood)
    printf("Failed to find scurve profile \n");

#ifdef PLOT
  trajectoryPlot(0.001, 3, "Example_3_9.png");
#else
  double iter_t = 0, t = 3;
  double* point;
  while (iter_t < t)
  {
    point = planner_.getTrajectoryPoint(iter_t);
    iter_t += 0.001;
  }
  ASSERT_LT(abs(point[mcPositionId] - 10), 0.001);
  ASSERT_LT(abs(point[mcSpeedId] - 0), 0.001);
  ASSERT_LT(abs(point[mcAccelerationId] - 0), 0.001);
#endif
}

// Tests example 3.10 at page 83 of 'Trajectory planning for automatic machines
// and robots(2008)' Maximum speed not reached
TEST_F(PlannerTest, Example_3_10)
{
  planner_.setCondition(0, 10, 1, 0, 0, 0, NAN, 10, 10, 30, RTmotion::mcRuckig);
  RTmotion::MC_ERROR_CODE res = planner_.planTrajectory();

  if (res != RTmotion::mcErrorCodeGood)
    printf("Failed to find scurve profile \n");

#ifdef PLOT
  trajectoryPlot(0.001, 3, "Example_3_10.png");
#else
  double iter_t = 0, t = 3;
  double* point;
  while (iter_t < t)
  {
    point = planner_.getTrajectoryPoint(iter_t);
    iter_t += 0.001;
  }
  ASSERT_LT(abs(point[mcPositionId] - 10), 0.001);
  ASSERT_LT(abs(point[mcSpeedId] - 0), 0.001);
  ASSERT_LT(abs(point[mcAccelerationId] - 0), 0.001);
#endif
}

// Tests example 3.11 at page 83 of 'Trajectory planning for automatic machines
// and robots(2008)' Maximum speed not reached and maximum acceleration not
// reached
TEST_F(PlannerTest, Example_3_11)
{
  planner_.setCondition(0, 10, 7, 0, 0, 0, NAN, 10, 10, 30, RTmotion::mcRuckig);
  RTmotion::MC_ERROR_CODE res = planner_.planTrajectory();

  if (res != RTmotion::mcErrorCodeGood)
    printf("Failed to find scurve profile \n");

#ifdef PLOT
  trajectoryPlot(0.001, 2, "Example_3_11.png");
#else
  double iter_t = 0, t = 2;
  double* point;
  while (iter_t < t)
  {
    point = planner_.getTrajectoryPoint(iter_t);
    iter_t += 0.001;
  }
  ASSERT_LT(abs(point[mcPositionId] - 10), 0.001);
  ASSERT_LT(abs(point[mcSpeedId] - 0), 0.001);
  ASSERT_LT(abs(point[mcAccelerationId] - 0), 0.001);
#endif
}

// Tests example 3.12 at page 85 of 'Trajectory planning for automatic machines
// and robots(2008)' Maximum speed not reached and maximum acceleration not
// reached
TEST_F(PlannerTest, Example_3_12)
{
  planner_.setCondition(0, 10, 7.5, 0, 0, 0, NAN, 10, 10, 30,
                        RTmotion::mcRuckig);
  RTmotion::MC_ERROR_CODE res = planner_.planTrajectory();

  if (res != RTmotion::mcErrorCodeGood)
    printf("Failed to find scurve profile \n");

#ifdef PLOT
  trajectoryPlot(0.001, 2, "Example_3_12.png");
#else
  double iter_t = 0, t = 2;
  double* point;
  while (iter_t < t)
  {
    point = planner_.getTrajectoryPoint(iter_t);
    iter_t += 0.001;
  }
  ASSERT_LT(abs(point[mcPositionId] - 10), 0.001);
  ASSERT_LT(abs(point[mcSpeedId] - 0), 0.001);
  ASSERT_LT(abs(point[mcAccelerationId] - 0), 0.001);
#endif
}

// Tests example 3.13 at page 93 of 'Trajectory planning for automatic machines
// and robots(2008)' Maximum speed not reached and maximum acceleration not
// reached
TEST_F(PlannerTest, Example_3_13)
{
  planner_.setCondition(0, 10, 0, 0, 0, 0, NAN, 10, 20, 30, RTmotion::mcRuckig);
  RTmotion::MC_ERROR_CODE res = planner_.planTrajectory();

  if (res != RTmotion::mcErrorCodeGood)
    printf("Failed to find scurve profile \n");

#ifdef PLOT
  trajectoryPlot(0.001, 2.5, "Example_3_13.png");
#else
  double iter_t = 0, t = 2.5;
  double* point;
  while (iter_t < t)
  {
    point = planner_.getTrajectoryPoint(iter_t);
    iter_t += 0.001;
  }
  ASSERT_LT(abs(point[mcPositionId] - 10), 0.001);
  ASSERT_LT(abs(point[mcSpeedId] - 0), 0.001);
  ASSERT_LT(abs(point[mcAccelerationId] - 0), 0.001);
#endif
}

TEST_F(PlannerTest, Test_Negative)
{
  planner_.setCondition(10, 0, 1, 0, 0, 0, NAN, 5, 10, 30, RTmotion::mcRuckig);
  RTmotion::MC_ERROR_CODE res = planner_.planTrajectory();

  if (res != RTmotion::mcErrorCodeGood)
    printf("Failed to find scurve profile \n");

#ifdef PLOT
  trajectoryPlot(0.001, 3, "Test_Negative.png");
#else
  double iter_t = 0, t = 3;
  double* point;
  while (iter_t < t)
  {
    point = planner_.getTrajectoryPoint(iter_t);
    iter_t += 0.001;
  }
  ASSERT_LT(abs(point[mcPositionId] - 0), 0.001);
  ASSERT_LT(abs(point[mcSpeedId] - 0), 0.001);
  ASSERT_LT(abs(point[mcAccelerationId] - 0), 0.001);
#endif
}

int main(int argc, char** argv)
{
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}