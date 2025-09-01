// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file line_planner.cpp
 *
 * Maintainer: Yichong Tang <yichong.tang@intel.com>
 *
 */

#include <algo/private/include/line_planner.hpp>
#include <fb/common/include/logging.hpp>
#include <chrono>
#include <algo/common/include/math_utils.hpp>

using namespace RTmotion;

namespace trajectory_processing
{
RTmotion::MC_ERROR_CODE LinePlanner::plan()
{
  condition_.q0 = ScurvePlanner::condition_.q0;
  condition_.q1 = ScurvePlanner::condition_.q1;

  double h = condition_.q1 - condition_.q0;

  profile_.b = condition_.q0;
  profile_.k = h / condition_.T;

  DEBUG_PRINT("LinePlanner::plan: k %f, b %f\n", profile_.k, profile_.b);

  return mcErrorCodeGood;
}

double* LinePlanner::getWaypoint(double t)
{
  point_[mcPositionId]     = profile_.k * t + profile_.b;
  point_[mcSpeedId]        = profile_.k;
  point_[mcAccelerationId] = 0;
  point_[mcJerkId]         = 0;

  return point_;
}

LineCondition& LinePlanner::getLineCondition()
{
  return condition_;
}

LineProfile& LinePlanner::getLineProfile()
{
  return profile_;
}

}  // namespace trajectory_processing
