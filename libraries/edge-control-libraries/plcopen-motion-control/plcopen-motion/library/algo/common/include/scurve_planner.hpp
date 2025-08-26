// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file scurve_planner.hpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#pragma once

#include <stdlib.h>
#include <math.h>
#include <algorithm>
#include <map>
#include <fb/common/include/global.hpp>
#include <algo/common/include/math_utils.hpp>

#define WAYPOINT_PROFILE_DIMENSION 4  // Position, velocity, acceleration, jerk

using RTmotion::MC_ERROR_CODE;

typedef enum
{
  mcPositionId     = 0,
  mcSpeedId        = 1,
  mcAccelerationId = 2,
  mcJerkId         = 3
} WaypointIndex;

namespace trajectory_processing
{
struct ScurveCondition
{
  // Condition inputs for planner
  double q0    = 0.0;
  double q1    = 0.0;
  double v0    = 0.0;
  double v1    = 0.0;
  double a0    = 0.0;
  double a1    = 0.0;
  double v_max = 0.0;
  double a_max = 0.0;
  double j_max = 0.0;
  double T     = 0.0;
};

struct ScurveProfile
{
  // Time domains for offline scurve planning results
  double Tj1 = 0.0;
  double Ta  = 0.0;
  double Tj2 = 0.0;
  double Tv  = 0.0;
  // Time domains for online scurve planning results
  double Tj2a = 0.0;
  double Tj2c = 0.0;
  double Tj2b = 0.0;
  double Td   = 0.0;
  double Th   = 0.0;
};

class ScurvePlanner
{
public:
  ScurvePlanner()  = default;
  ~ScurvePlanner() = default;

  /**
   * @brief Sign transforms for being able to calculate trajectory with q1 < q0.
   *        Look at 'Trajectory planning for automatic machines and
   * robots(2008)'
   * @param condition  The input scurve condition, i.e. q0, q1, v0, v1, v_max,
   * a_max, j_max
   */
  void signTransforms(ScurveCondition& condition);

  /**
   * @brief Transforms point back to the original sign.
   * @param p Reference to Point, i.e. acc, vel, pos
   */
  void pointSignTransform(double* p);

  virtual MC_ERROR_CODE plan();
  virtual double* getWaypoint(double t);
  virtual void setFrequency(double f);

  ScurveProfile profile_;
  ScurveCondition condition_;
  double point_[WAYPOINT_PROFILE_DIMENSION] = { 0 };
  double sign_     = 1.0;  // Sign transform flag parameter
  double freqency_ = 1000.0;
};

}  // namespace trajectory_processing