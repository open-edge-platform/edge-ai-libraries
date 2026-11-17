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
#include "test_plot.hpp"
#include <plot/matplotlibcpp.h>
namespace plt = matplotlibcpp;
#endif

namespace traj_pro = trajectory_processing;

class PlannerClockTest : public ::testing::TestWithParam<double>
{
};

TEST_P(PlannerClockTest, FrequencySurvivesBackendSwitchingAndCopying)
{
  using namespace RTmotion;
#ifdef PLOT
  test_plot::TestPlot plot("planner_test");
#endif
  for (const auto type : { mcRuckig, mcOffLine, mcPoly5, mcLine })
  {
    SCOPED_TRACE(type);
    traj_pro::AxisPlanner original;
    original.setCondition(0, 2, 0, 0, 0, 0, 1, 1, 4, 40, type);
    original.setFrequency(GetParam());
    traj_pro::AxisPlanner copied(original);
    traj_pro::AxisPlanner assigned;
    assigned.setFrequency(GetParam() / 2);
    assigned = original;
    for (auto* planner : { &original, &copied, &assigned })
    {
#ifdef PLOT
      const std::string label =
          std::to_string(type) + (planner == &original ? " original" :
                                  planner == &copied   ? " copied" :
                                                         " assigned");
#endif
      planner->setCondition(0, 2, 0, 0, 0, 0, NAN, 1, 4, 40, mcRuckig);
      ASSERT_EQ(planner->onReplan(), mcErrorCodeGood);
      double position = 0, velocity = 0, acceleration = 0;
      for (int cycle = 1; cycle <= GetParam(); ++cycle)
      {
        ASSERT_EQ(planner->onExecution(cycle / GetParam(), &position, &velocity,
                                       &acceleration),
                  mcErrorCodeGood);
#ifdef PLOT
        plot.add("Position", label, cycle / GetParam(), position);
        plot.add("Velocity", label, cycle / GetParam(), velocity);
#endif
      }
#ifdef PLOT
      plot.add("Position", label + " expected at 1 s", 1, 0.825);
      plot.add("Velocity", label + " expected at 1 s", 1, 1);
#endif
      EXPECT_NEAR(position, 0.825, 1e-9);
      EXPECT_NEAR(velocity, 1, 1e-9);
    }
  }
#ifdef PLOT
  plot.save();
#endif
}

INSTANTIATE_TEST_SUITE_P(CycleFrequencies, PlannerClockTest,
                         ::testing::Values(250.0, 500.0, 1000.0, 2000.0));

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
    const std::string filename = "planner_test_" + file_name;
    plt::save(filename);
    plt::close();
    test_plot::TestPlot::recordFile(filename);
  }
#endif
  traj_pro::AxisPlanner planner_ = {};
};

TEST_F(PlannerTest, VelocityTrackingUsesCycleTime)
{
#ifdef PLOT
  test_plot::TestPlot plot("planner_test");
#endif
  for (const double delta_time : { 0.001, 0.002 })
  {
    SCOPED_TRACE(::testing::Message() << "delta_time=" << delta_time);
    planner_.setCondition(0, NAN, 0, 1, 0, 0, NAN, 1, 1, 10,
                          RTmotion::mcRuckig);
    double position = 0, velocity = 0, acceleration = 0;
    ASSERT_EQ(planner_.onVelocityTracking(delta_time, &position, &velocity,
                                          &acceleration),
              RTmotion::mcErrorCodeGood);
    EXPECT_NEAR(acceleration, 10 * delta_time, 1e-12);
    EXPECT_NEAR(velocity, 5 * delta_time * delta_time, 1e-12);
#ifdef PLOT
    plot.add("Acceleration", "Actual", delta_time, acceleration);
    plot.add("Acceleration", "Expected", delta_time, 10 * delta_time);
    plot.add("Velocity", "Actual", delta_time, velocity);
    plot.add("Velocity", "Expected", delta_time, 5 * delta_time * delta_time);
#endif
  }
#ifdef PLOT
  plot.save();
#endif
}

TEST_F(PlannerTest, VelocityTrackingReportsInvalidLimits)
{
  planner_.setCondition(0, NAN, 0, 1, 0, 0, NAN, 1, 1, 0, RTmotion::mcRuckig);
  double position = 2, velocity = 3, acceleration = 4;
#ifdef PLOT
  test_plot::TestPlot plot("planner_test");
  plot.add("Output values", "Position", 0, position);
  plot.add("Output values", "Velocity", 0, velocity);
  plot.add("Output values", "Acceleration", 0, acceleration);
#endif
  const auto result =
      planner_.onVelocityTracking(0.001, &position, &velocity, &acceleration);
  EXPECT_EQ(result, RTmotion::mcErrorCodeScurveInvalidInput);
  EXPECT_DOUBLE_EQ(position, 2);
  EXPECT_DOUBLE_EQ(velocity, 3);
  EXPECT_DOUBLE_EQ(acceleration, 4);
#ifdef PLOT
  plot.add("Output values", "Position", 1, position);
  plot.add("Output values", "Velocity", 1, velocity);
  plot.add("Output values", "Acceleration", 1, acceleration);
  plot.add("Error code", "Actual", 1, result);
  plot.add("Error code", "Expected", 1,
           RTmotion::mcErrorCodeScurveInvalidInput);
  plot.save();
#endif
}

TEST_F(PlannerTest, PositionPlanningAfterVelocityTracking)
{
#ifdef PLOT
  test_plot::TestPlot plot("planner_test");
#endif
  planner_.setCondition(0, NAN, 0, 1, 0, 0, NAN, 1, 1, 10, RTmotion::mcRuckig);
  double position = 0, velocity = 0, acceleration = 0;
  ASSERT_EQ(
      planner_.onVelocityTracking(0.001, &position, &velocity, &acceleration),
      RTmotion::mcErrorCodeGood);
  planner_.setCondition(0, 1, 0, 0, 0, 0, NAN, 2, 5, 20, RTmotion::mcRuckig);
  ASSERT_EQ(planner_.onReplan(), RTmotion::mcErrorCodeGood);
  for (int cycle = 0; cycle < 3000; ++cycle)
  {
    ASSERT_EQ(planner_.onExecution((cycle + 1) * 0.001, &position, &velocity,
                                   &acceleration),
              RTmotion::mcErrorCodeGood);
#ifdef PLOT
    plot.add("Position", "Actual", (cycle + 1) * 0.001, position);
    plot.add("Position", "Target", (cycle + 1) * 0.001, 1);
    plot.add("Velocity", "Actual", (cycle + 1) * 0.001, velocity);
    plot.add("Acceleration", "Actual", (cycle + 1) * 0.001, acceleration);
#endif
  }
  EXPECT_NEAR(position, 1, 1e-12);
  EXPECT_NEAR(velocity, 0, 1e-12);
  EXPECT_NEAR(acceleration, 0, 1e-12);
#ifdef PLOT
  plot.save();
#endif
}

// Tests velocity profile
TEST_P(PlannerClockTest, TrackingPreservesPositionClockOnSuccessAndError)
{
  using namespace RTmotion;
#ifdef PLOT
  test_plot::TestPlot plot("planner_test");
#endif
  for (const bool invalid : { false, true })
  {
    SCOPED_TRACE(invalid);
    traj_pro::AxisPlanner planner;
    planner.setFrequency(GetParam());
    planner.setCondition(0, NAN, 0, 1, 0, 0, NAN, 1, 4, invalid ? 0 : 40,
                         mcRuckig);
    double position = 0, velocity = 0, acceleration = 0;
    const auto result = planner.onVelocityTracking(
        2 / GetParam(), &position, &velocity, &acceleration, -1);
    EXPECT_EQ(result,
              invalid ? mcErrorCodeScurveInvalidInput : mcErrorCodeGood);
#ifdef PLOT
    const std::string label = invalid ? "After invalid tracking" :
                                        "After valid tracking";
    plot.add("Tracking error code", label, invalid ? 1 : 0, result);
#endif
    planner.setCondition(0, 2, 0, 0, 0, 0, NAN, 1, 4, 40, mcRuckig);
    ASSERT_EQ(planner.onReplan(), mcErrorCodeGood);
    for (int cycle = 1; cycle <= GetParam(); ++cycle)
    {
      ASSERT_EQ(planner.onExecution(cycle / GetParam(), &position, &velocity,
                                    &acceleration),
                mcErrorCodeGood);
#ifdef PLOT
      plot.add("Position", label, cycle / GetParam(), position);
      plot.add("Velocity", label, cycle / GetParam(), velocity);
      plot.add("Acceleration", label, cycle / GetParam(), acceleration);
#endif
    }
    EXPECT_NEAR(position, 0.825, 1e-9);
    for (int cycle = static_cast<int>(GetParam()) + 1;
         cycle <= static_cast<int>(std::ceil(2.35 * GetParam())); ++cycle)
    {
      ASSERT_EQ(planner.onExecution(cycle / GetParam(), &position, &velocity,
                                    &acceleration),
                mcErrorCodeGood);
#ifdef PLOT
      plot.add("Position", label, cycle / GetParam(), position);
      plot.add("Velocity", label, cycle / GetParam(), velocity);
      plot.add("Acceleration", label, cycle / GetParam(), acceleration);
#endif
    }
    EXPECT_NEAR(position, 2, 1e-9);
    EXPECT_NEAR(velocity, 0, 1e-9);
  }
#ifdef PLOT
  plot.add("Position", "Expected at 1 s", 1, 0.825);
  plot.add("Position", "Final target", 2.35, 2);
  plot.save();
#endif
}

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