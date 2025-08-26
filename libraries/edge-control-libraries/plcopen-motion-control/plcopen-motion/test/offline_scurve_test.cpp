// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file offline_scurve_test.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <algo/public/include/offline_scurve_planner.hpp>
#include <thread>
#include <fb/common/include/logging.hpp>
#include "gtest/gtest.h"

#ifdef PLOT
#include <plot/matplotlibcpp.h>
namespace plt = matplotlibcpp;
#endif

namespace traj_pro = trajectory_processing;

// The fixture for testing class Foo.
class ScurveTest : public ::testing::Test
{
protected:
  // You can remove any or all of the following functions if their bodies would
  // be empty.

  ScurveTest()
  {
    // You can do set-up work for each test here.
  }

  ~ScurveTest() override
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
  void trajectoryPlot(double delta_time,
                      const std::string& file_name = "scurve.png")
  {
    double T =
        planner_.profile_.Ta + planner_.profile_.Tv + planner_.profile_.Td;
    double iter_t = 0;
    std::vector<double> pos, vel, acc, jerk, t;
    while (iter_t < T)
    {
      double* point = planner_.getTrajectoryFunction(iter_t);
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

  traj_pro::ScurvePlannerOffLine planner_;
};

// Tests example 3.9 at page 82 in 'Trajectory planning for automatic machines
// and robots(2008)' Maximum speed reached
TEST_F(ScurveTest, Example_3_9)
{
  planner_.condition_.q0    = 0;
  planner_.condition_.q1    = 10;
  planner_.condition_.v0    = 1;
  planner_.condition_.v1    = 0;
  planner_.condition_.v_max = 5;
  planner_.condition_.a_max = 10;
  planner_.condition_.j_max = 30;

  RTmotion::MC_ERROR_CODE res = planner_.planTrajectory1D();

  if (res != RTmotion::mcErrorCodeGood)
    printf("Failed to find scurve profile \n");

  INFO_PRINT("Scurve profile: Ta = %f, Tv = %f, Td = %f, Tj1 = %f, Tj2 = %f \n",
             planner_.profile_.Ta, planner_.profile_.Tv, planner_.profile_.Td,
             planner_.profile_.Tj1, planner_.profile_.Tj2);
  ASSERT_LT(abs(planner_.profile_.Ta - 0.7333), 0.0001);
  ASSERT_LT(abs(planner_.profile_.Tv - 1.1433), 0.0001);
  ASSERT_LT(abs(planner_.profile_.Td - 0.8333), 0.0001);
  ASSERT_LT(abs(planner_.profile_.Tj1 - 0.3333), 0.0001);
  ASSERT_LT(abs(planner_.profile_.Tj2 - 0.3333), 0.0001);
#ifdef PLOT
  trajectoryPlot(0.001, "Example_3_9.png");
#endif
}

// Tests example 3.10 at page 83 of 'Trajectory planning for automatic machines
// and robots(2008)' Maximum speed not reached
TEST_F(ScurveTest, Example_3_10)
{
  planner_.condition_.q0    = 0;
  planner_.condition_.q1    = 10;
  planner_.condition_.v0    = 1;
  planner_.condition_.v1    = 0;
  planner_.condition_.v_max = 10;
  planner_.condition_.a_max = 10;
  planner_.condition_.j_max = 30;

  RTmotion::MC_ERROR_CODE res = planner_.planTrajectory1D();

  if (res != RTmotion::mcErrorCodeGood)
    printf("Failed to find scurve profile \n");

  INFO_PRINT("Scurve profile: Ta = %f, Tv = %f, Td = %f, Tj1 = %f, Tj2 = %f \n",
             planner_.profile_.Ta, planner_.profile_.Tv, planner_.profile_.Td,
             planner_.profile_.Tj1, planner_.profile_.Tj2);
  ASSERT_LT(abs(planner_.profile_.Ta - 1.0747), 0.0001);
  ASSERT_LT(abs(planner_.profile_.Tv - 0.0), 0.0001);
  ASSERT_LT(abs(planner_.profile_.Td - 1.1747), 0.0001);
  ASSERT_LT(abs(planner_.profile_.Tj1 - 0.3333), 0.0001);
  ASSERT_LT(abs(planner_.profile_.Tj2 - 0.3333), 0.0001);

  double* point = planner_.getTrajectoryFunction(planner_.profile_.Ta);
  INFO_PRINT("Scurve profile: Vlim = %f \n", point[mcSpeedId]);
  ASSERT_LT(abs(point[mcSpeedId] - 8.4136), 0.0001);
#ifdef PLOT
  trajectoryPlot(0.001, "Example_3_10.png");
#endif
}

// Tests example 3.11 at page 83 of 'Trajectory planning for automatic machines
// and robots(2008)' Maximum speed not reached and maximum acceleration not
// reached
TEST_F(ScurveTest, Example_3_11)
{
  planner_.condition_.q0    = 0;
  planner_.condition_.q1    = 10;
  planner_.condition_.v0    = 7;
  planner_.condition_.v1    = 0;
  planner_.condition_.v_max = 10;
  planner_.condition_.a_max = 10;
  planner_.condition_.j_max = 30;

  RTmotion::MC_ERROR_CODE res = planner_.planTrajectory1D();

  if (res != RTmotion::mcErrorCodeGood)
    printf("Failed to find scurve profile \n");

  INFO_PRINT("Scurve profile: Ta = %f, Tv = %f, Td = %f, Tj1 = %f, Tj2 = %f \n",
             planner_.profile_.Ta, planner_.profile_.Tv, planner_.profile_.Td,
             planner_.profile_.Tj1, planner_.profile_.Tj2);
  ASSERT_LT(abs(planner_.profile_.Ta - 0.4666), 0.0001);
  ASSERT_LT(abs(planner_.profile_.Tv - 0.0), 0.0001);
  ASSERT_LT(abs(planner_.profile_.Td - 1.4718), 0.0001);
  ASSERT_LT(abs(planner_.profile_.Tj1 - 0.2321), 0.0001);
  ASSERT_LT(abs(planner_.profile_.Tj2 - 0.2321), 0.0001);

  double* point = planner_.getTrajectoryFunction(planner_.profile_.Ta);
  INFO_PRINT("Scurve profile: Vlim = %f \n", point[mcSpeedId]);
  ASSERT_LT(abs(point[mcSpeedId] - 8.6329), 0.0001);

  point = planner_.getTrajectoryFunction(planner_.profile_.Tj1);
  INFO_PRINT("Scurve profile: Alim_a = %f \n", point[mcAccelerationId]);
  ASSERT_LT(abs(point[mcAccelerationId] - 6.9641), 0.0001);

  point = planner_.getTrajectoryFunction(
      planner_.profile_.Ta + planner_.profile_.Tv + planner_.profile_.Tj2);
  INFO_PRINT("Scurve profile: Alim_d = %f \n", point[mcAccelerationId]);
  ASSERT_LT(abs(point[mcAccelerationId] - (-6.9641)), 0.0001);
#ifdef PLOT
  trajectoryPlot(0.001, "Example_3_11.png");
#endif
}

// Tests example 3.12 at page 85 of 'Trajectory planning for automatic machines
// and robots(2008)' Maximum speed not reached and maximum acceleration not
// reached
TEST_F(ScurveTest, Example_3_12)
{
  planner_.condition_.q0    = 0;
  planner_.condition_.q1    = 10;
  planner_.condition_.v0    = 7.5;
  planner_.condition_.v1    = 0;
  planner_.condition_.v_max = 10;
  planner_.condition_.a_max = 10;
  planner_.condition_.j_max = 30;

  RTmotion::MC_ERROR_CODE res = planner_.planTrajectory1D();

  if (res != RTmotion::mcErrorCodeGood)
    printf("Failed to find scurve profile \n");

  INFO_PRINT("Scurve profile: Ta = %f, Tv = %f, Td = %f, Tj1 = %f, Tj2 = %f \n",
             planner_.profile_.Ta, planner_.profile_.Tv, planner_.profile_.Td,
             planner_.profile_.Tj1, planner_.profile_.Tj2);
  ASSERT_LT(abs(planner_.profile_.Ta - 0.0), 0.0001);
  ASSERT_LT(abs(planner_.profile_.Tv - 0.0), 0.0001);
  ASSERT_LT(abs(planner_.profile_.Td - 2.6667), 0.0001);
  ASSERT_LT(abs(planner_.profile_.Tj1 - 0.0), 0.0001);
  ASSERT_LT(abs(planner_.profile_.Tj2 - 0.0973), 0.0001);

  double* point = planner_.getTrajectoryFunction(planner_.profile_.Ta);
  INFO_PRINT("Scurve profile: Vlim = %f \n", point[mcSpeedId]);
  ASSERT_LT(abs(point[mcSpeedId] - 7.5), 0.0001);

  point = planner_.getTrajectoryFunction(planner_.profile_.Tj1);
  INFO_PRINT("Scurve profile: Alim_a = %f \n", point[mcAccelerationId]);
  ASSERT_LT(abs(point[mcAccelerationId] - 0.0), 0.0001);

  point = planner_.getTrajectoryFunction(
      planner_.profile_.Ta + planner_.profile_.Tv + planner_.profile_.Tj2);
  INFO_PRINT("Scurve profile: Alim_d = %f \n", point[mcAccelerationId]);
  ASSERT_LT(abs(point[mcAccelerationId] - (-2.9190)), 0.0001);
#ifdef PLOT
  trajectoryPlot(0.001, "Example_3_12.png");
#endif
}

// Tests example 3.13 at page 93 of 'Trajectory planning for automatic machines
// and robots(2008)' Maximum speed not reached and maximum acceleration not
// reached
TEST_F(ScurveTest, Example_3_13)
{
  planner_.condition_.q0    = 0;
  planner_.condition_.q1    = 10;
  planner_.condition_.v0    = 0;
  planner_.condition_.v1    = 0;
  planner_.condition_.v_max = 10;
  planner_.condition_.a_max = 20;
  planner_.condition_.j_max = 30;

  RTmotion::MC_ERROR_CODE res = planner_.planTrajectory1D();

  if (res != RTmotion::mcErrorCodeGood)
    printf("Failed to find scurve profile \n");

  INFO_PRINT("Scurve profile: Ta = %f, Tv = %f, Td = %f, Tj1 = %f, Tj2 = %f \n",
             planner_.profile_.Ta, planner_.profile_.Tv, planner_.profile_.Td,
             planner_.profile_.Tj1, planner_.profile_.Tj2);
  ASSERT_LT(abs(planner_.profile_.Ta - 1.1006), 0.0001);
  ASSERT_LT(abs(planner_.profile_.Tv - 0.0), 0.0001);
  ASSERT_LT(abs(planner_.profile_.Td - 1.1006), 0.0001);
  ASSERT_LE(planner_.profile_.Tj1 * 2, planner_.profile_.Ta);
  ASSERT_LT(planner_.profile_.Tj2 * 2, planner_.profile_.Td);

  double* point = planner_.getTrajectoryFunction(planner_.profile_.Ta);
  INFO_PRINT("Scurve profile: Vlim = %f \n", point[mcSpeedId]);
  ASSERT_LT(point[mcSpeedId], planner_.condition_.v_max);

  point = planner_.getTrajectoryFunction(planner_.profile_.Tj1);
  INFO_PRINT("Scurve profile: Alim_a = %f \n", point[mcAccelerationId]);
  ASSERT_LT(point[mcAccelerationId], planner_.condition_.a_max);

  point = planner_.getTrajectoryFunction(
      planner_.profile_.Ta + planner_.profile_.Tv + planner_.profile_.Tj2);
  INFO_PRINT("Scurve profile: Alim_d = %f \n", point[mcAccelerationId]);
  ASSERT_GT(point[mcAccelerationId], -planner_.condition_.a_max);
#ifdef PLOT
  trajectoryPlot(0.001, "Example_3_13.png");
#endif
}

int main(int argc, char** argv)
{
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}