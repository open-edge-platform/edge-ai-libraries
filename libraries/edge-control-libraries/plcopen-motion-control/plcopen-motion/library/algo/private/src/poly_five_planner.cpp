// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file poly_five_planner.cpp
 *
 * Maintainer: Yichong Tang <yichong.tang@intel.com>
 *
 */

#include <algo/private/include/poly_five_planner.hpp>
#include <fb/common/include/logging.hpp>
#include <chrono>
#include <algo/common/include/math_utils.hpp>

using namespace RTmotion;

namespace trajectory_processing
{
RTmotion::MC_ERROR_CODE PolyFivePlanner::plan()
{
  condition_.q0 = ScurvePlanner::condition_.q0;
  condition_.q1 = ScurvePlanner::condition_.q1;
  condition_.v0 = ScurvePlanner::condition_.v0;
  condition_.v1 = ScurvePlanner::condition_.v1;
  condition_.a0 = ScurvePlanner::condition_.a0;
  condition_.a1 = ScurvePlanner::condition_.a1;

  double h = condition_.q1 - condition_.q0;

  profile_.a0 = condition_.q0;
  profile_.a1 = condition_.v0;
  profile_.a2 = condition_.a0 * 0.5;
  profile_.a3 =
      1 / (2 * __cube(condition_.T)) *
      (20 * h - (8 * condition_.v1 + 12 * condition_.v0) * condition_.T -
       (3 * condition_.a0 - condition_.a1) * __square(condition_.T));
  profile_.a4 =
      1 / (2 * __square(condition_.T) * __square(condition_.T)) *
      (-30 * h + (14 * condition_.v1 + 16 * condition_.v0) * condition_.T +
       (3 * condition_.a0 - 2 * condition_.a1) * __square(condition_.T));
  profile_.a5 =
      1 / (2 * __cube(condition_.T) * __square(condition_.T)) *
      (12 * h - (6 * condition_.v1 + 6 * condition_.v0) * condition_.T +
       (condition_.a1 - condition_.a0) * __square(condition_.T));

  DEBUG_PRINT(
      "PolyFivePlanner::plan: a0 %f, a1 %f, a2 %f, a3 %f, a4 %f, a5 %f\n",
      profile_.a0, profile_.a1, profile_.a2, profile_.a3, profile_.a4,
      profile_.a5);

  return mcErrorCodeGood;
}

double* PolyFivePlanner::getWaypoint(double t)
{
  point_[mcPositionId] = profile_.a0 + profile_.a1 * t +
                         profile_.a2 * __square(t) + profile_.a3 * __cube(t) +
                         profile_.a4 * __square(t) * __square(t) +
                         profile_.a5 * __cube(t) * __square(t);
  point_[mcSpeedId] =
      profile_.a1 + 2 * profile_.a2 * t + 3 * profile_.a3 * __square(t) +
      4 * profile_.a4 * __cube(t) + 5 * profile_.a5 * __square(t) * __square(t);
  point_[mcAccelerationId] = 2 * profile_.a2 + 6 * profile_.a3 * t +
                             12 * profile_.a4 * __square(t) +
                             20 * profile_.a5 * __cube(t);
  point_[mcJerkId] =
      6 * profile_.a3 + 24 * profile_.a4 * t + 60 * profile_.a5 * __square(t);

  return point_;
}

PolyFiveCondition& PolyFivePlanner::getPolyFiveCondition()
{
  return condition_;
}

PolyFiveProfile& PolyFivePlanner::getPolyFiveProfile()
{
  return profile_;
}

}  // namespace trajectory_processing
