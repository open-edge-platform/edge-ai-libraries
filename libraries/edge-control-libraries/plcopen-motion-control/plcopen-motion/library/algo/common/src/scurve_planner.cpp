// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file scurve_planner.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <algo/common/include/scurve_planner.hpp>

using namespace RTmotion;

namespace trajectory_processing
{
/**
 * @brief Get the sign of the number
 * @param num The input number
 * @return Return 1 if num >= 0, -1 if num < 0
 */
double sign(double num)
{
  double s = 1.0;
  s        = (num) < 0 ? -1.0 : s;
  return s;
}

void ScurvePlanner::signTransforms(ScurveCondition& condition)
{
  // Init condition variables for concise code
  double q0    = condition.q0;
  double q1    = condition.q1;
  double v0    = condition.v0;
  double v1    = condition.v1;
  double a0    = condition.a0;
  double a1    = condition.a1;
  double v_max = condition.v_max;
  double a_max = condition.a_max;
  double j_max = condition.j_max;

  double v_min = -v_max;
  double a_min = -a_max;
  double j_min = -j_max;

  sign_      = isnan(q1 - q0) ? 1.0 : sign(q1 - q0);
  double vs1 = (sign_ + 1) / 2;
  double vs2 = (sign_ - 1) / 2;

  condition.q0    = sign_ * q0;
  condition.q1    = sign_ * q1;
  condition.v0    = sign_ * v0;
  condition.v1    = sign_ * v1;
  condition.a0    = sign_ * a0;
  condition.a1    = sign_ * a1;
  condition.v_max = vs1 * v_max + vs2 * v_min;
  condition.a_max = vs1 * a_max + vs2 * a_min;
  condition.j_max = vs1 * j_max + vs2 * j_min;
}

void ScurvePlanner::pointSignTransform(double* p)
{
  std::for_each(p, p + WAYPOINT_PROFILE_DIMENSION,
                [this](double& c) { c *= sign_; });  // p = sign_ * p;
}

MC_ERROR_CODE ScurvePlanner::plan()
{
  return mcErrorCodeGood;
}

double* ScurvePlanner::getWaypoint(double /*t*/)
{
  return point_;
}

void ScurvePlanner::setFrequency(double f)
{
  freqency_ = f;
}
}  // namespace trajectory_processing
