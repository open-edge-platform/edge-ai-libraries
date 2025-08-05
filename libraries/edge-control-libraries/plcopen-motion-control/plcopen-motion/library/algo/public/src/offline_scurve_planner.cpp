// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file offline_scurve_planner.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <algo/public/include/offline_scurve_planner.hpp>
#include <fb/common/include/logging.hpp>
#include <chrono>
#include <algo/common/include/math_utils.hpp>

using namespace RTmotion;

constexpr double EPSILON = 0.01;

namespace trajectory_processing
{
MC_ERROR_CODE
ScurvePlannerOffLine::scurveCheckPosibility(const ScurveCondition& condition)
{
  // Init condition variables for concise code
  const double q0    = condition.q0;
  const double q1    = condition.q1;
  const double v0    = condition.v0;
  const double v1    = condition.v1;
  const double a_max = condition.a_max;
  const double j_max = condition.j_max;

  double dv = abs(v1 - v0);
  double dq = abs(q1 - q0);

  double time_to_reach_max_a = a_max / j_max;

  double time_to_set_set_speeds = sqrt(dv / j_max);

  double tj = fmin(time_to_reach_max_a, time_to_set_set_speeds);

  if (tj == time_to_reach_max_a)
  {
    if (dq > 0.5 * (v0 + v1) * (tj + dv / a_max))
    {
      return mcErrorCodeGood;
    }
  }
  else if (tj < time_to_reach_max_a)
  {
    if (dq > tj * (v0 + v1))
    {
      return mcErrorCodeGood;
    }
  }

  return mcErrorCodeScurveNotFeasible;
}

MC_ERROR_CODE ScurvePlannerOffLine::computeAccelerationPhase(
    double v, double v_max, double a_max, double j_max, double& Tj, double& Tad)
{
  // Deceleration period
  if ((v_max - v) * j_max < __square(a_max))  // (3.19)(3.20)
  {
    // a_max is not reached
    Tj  = sqrt((v_max - v) / j_max);  // (3.21)(3.23)
    Tad = 2 * Tj;                     // (3.21)(3.23)
  }
  else
  {
    // a_max is reached
    Tj  = a_max / j_max;             // (3.22)(3.24)
    Tad = Tj + (v_max - v) / a_max;  // (3.22)(3.24)
  }
  return mcErrorCodeGood;
}

MC_ERROR_CODE ScurvePlannerOffLine::computeMaximumSpeedReached(
    const ScurveCondition& condition, ScurveProfile& profile)
{
  // Init condition variables for concise code
  double tj1 = profile.Tj1, ta = profile.Ta, tj2 = profile.Tj2, td = profile.Td,
         tv = profile.Tv;

  const double q0    = condition.q0;
  const double q1    = condition.q1;
  const double v0    = condition.v0;
  const double v1    = condition.v1;
  const double v_max = condition.v_max;
  const double a_max = condition.a_max;
  const double j_max = condition.j_max;

  // Acceleration period
  computeAccelerationPhase(v0, v_max, a_max, j_max, tj1, ta);

  // Deceleration period
  computeAccelerationPhase(v1, v_max, a_max, j_max, tj2, td);

  tv = (q1 - q0) / v_max - (ta / 2) * (1 + v0 / v_max) -
       (td / 2) * (1 + v1 / v_max);  // (3.25)

  profile.Tj1 = tj1;
  profile.Ta  = ta;
  profile.Tj2 = tj2;
  profile.Td  = td;
  profile.Tv  = tv;

  if (tv < 0)
    return mcErrorCodeScurveMaxVelNotReached;

  return mcErrorCodeGood;
}

MC_ERROR_CODE ScurvePlannerOffLine::computeMaximumSpeedNotReached(
    const ScurveCondition& condition, ScurveProfile& profile)
{
  // Init condition variables for concise code
  double tj1 = profile.Tj1, ta = profile.Ta, tj2 = profile.Tj2, td = profile.Td,
         tv = profile.Tv;

  const double q0    = condition.q0;
  const double q1    = condition.q1;
  const double v0    = condition.v0;
  const double v1    = condition.v1;
  const double a_max = condition.a_max;
  const double j_max = condition.j_max;

  // Assuming that a_max/a_min is reached
  double tj;
  tj1 = tj2 = tj = a_max / j_max;  // (3.26a)
  tv             = 0;

  double v = __square(a_max) / j_max;
  double delta =
      __square(a_max) * __square(a_max) / __square(j_max) +
      2 * (__square(v0) + __square(v1)) +
      a_max * (4 * (q1 - q0) - 2 * (a_max / j_max) * (v0 + v1));  // (3.27)

  ta = (v - 2 * v0 + sqrt(delta)) / (2 * a_max);  // (3.26b)
  td = (v - 2 * v1 + sqrt(delta)) / (2 * a_max);  // (3.26c)

  profile.Tj1 = tj1;
  profile.Ta  = ta;
  profile.Tj2 = tj2;
  profile.Td  = td;
  profile.Tv  = tv;

  if (ta < 0 || td < 0)
    return mcErrorCodeScurveMaxAccNotReached;

  return mcErrorCodeGood;
}

MC_ERROR_CODE ScurvePlannerOffLine::scurveSearchPlanning(
    const ScurveCondition& condition, ScurveProfile& profile, double T,
    double scale, size_t max_iter, double dt_thresh, int timeout)
{
  // Init condition variables for concise code
  ScurveCondition condition_copied = condition;

  size_t it = 0;

  auto start        = std::chrono::high_resolution_clock::now();
  int consume_time  = 0;
  MC_ERROR_CODE res = mcErrorCodeGood;
  while (it < max_iter && condition_copied.a_max > EPSILON &&
         consume_time <= timeout)
  {
    MC_ERROR_CODE res_step =
        computeMaximumSpeedNotReached(condition_copied, profile);

    double &tj1 = profile.Tj1, ta = profile.Ta, tj2 = profile.Tj2,
           td = profile.Td, tv = profile.Tv;

    if (res_step == mcErrorCodeGood)  // Ta > 0 && Td > 0
    {
      if (T == 0)
      {
        if (ta < 2 * tj1 ||
            td < 2 * tj2)  // Max acc cannot be reached, scale down max acc
        {
          it++;
          condition_copied.a_max *= scale;
          res = mcErrorCodeScurveMaxAccNotReached;
        }
        else  // Max acc can be reached
        {
          return mcErrorCodeGood;
        }
      }
      else
      {
        // Sync duration T
        if (abs(T - ta - td - tv) <= dt_thresh)  // Execution duration aligns to
                                                 // T
        {
          return mcErrorCodeGood;
        }
        else  // Too fast to complete before the end of duration T, scale down
              // max acc
        {
          it++;
          condition_copied.a_max *= scale;
          res = mcErrorCodeScurveFailToFindMaxAcc;
        }
      }
    }
    else  // Ta < 0 || Td < 0, invalid parameter
    {
      const double q0    = condition_copied.q0;
      const double q1    = condition_copied.q1;
      const double v0    = condition_copied.v0;
      const double v1    = condition_copied.v1;
      const double j_max = condition_copied.j_max;

      if (ta < 0)
      {
        ta  = 0;
        tj1 = 0;
        td  = 2 * (q1 - q0) / (v1 + v0);  // (3.28a)
        tj2 = (j_max * (q1 - q0) -
               sqrt(j_max * (j_max * __square(q1 - q0) +
                             __square(v1 + v0) * (v1 - v0)))) /
              (j_max * (v1 + v0));  // (3.28b)
      }

      if (td < 0)
      {
        td  = 0;
        tj2 = 0;
        ta  = 2 * (q1 - q0) / (v1 + v0);  // (3.29a)
        tj1 = (j_max * (q1 - q0) -
               sqrt(j_max * (j_max * __square(q1 - q0) -
                             __square(v1 + v0) * (v1 - v0)))) /
              (j_max * (v1 + v0));  // (3.29b)
      }
      profile.Tj1 = tj1;
      profile.Ta  = ta;
      profile.Tj2 = tj2;
      profile.Td  = td;
      profile.Tv  = tv;
      return mcErrorCodeGood;
    }
    auto end = std::chrono::high_resolution_clock::now();
    consume_time =
        std::chrono::duration_cast<std::chrono::microseconds>(end - start)
            .count();
  }

  return res;
}

double* ScurvePlannerOffLine::getTrajectoryFunc(
    double t, const ScurveProfile& profile, const ScurveCondition& condition)
{
  // Init condition variables for concise code
  const double tj1 = profile.Tj1, ta = profile.Ta, tj2 = profile.Tj2,
               td = profile.Td, tv = profile.Tv;

  const double q0    = condition.q0;
  const double q1    = condition.q1;
  const double v0    = condition.v0;
  const double v1    = condition.v1;
  const double j_max = condition.j_max;

  double tw = ta + td + tv;

  // maximum values of velocity and acceleration
  // actually reached during the trajectory
  double a_lim_a = j_max * tj1;
  double a_lim_d = -j_max * tj2;
  double v_lim   = v0 + (ta - tj1) * a_lim_a;

  // Returns trajectory parameters double[4] which contains
  // acceleration, speed and position for a given time t

  // NOLINTBEGIN(*-readability-identifier-naming)
  auto trajectory = [&](double t) -> double* {
    double q, v, a, j, tt, j_min = -j_max;
    // Acceleration phase
    if (0 <= t && t < tj1)
    {
      // (3.30a)
      q = q0 + v0 * t + j_max * __cube(t) / 6;
      v = v0 + j_max * __square(t) / 2;
      a = j_max * t;
      j = j_max;
    }
    else if (tj1 <= t && t < (ta - tj1))
    {
      // (3.30b)
      q = q0 + v0 * t +
          a_lim_a * (3 * __square(t) - 3 * tj1 * t + __square(tj1)) / 6;
      v = v0 + a_lim_a * (t - tj1 / 2);
      a = a_lim_a = j_max * tj1;
      j           = 0;
    }
    else if ((ta - tj1) <= t && t < ta)
    {
      tt = ta - t;
      // (3.30c)
      q = q0 + (v_lim + v0) * ta / 2 - v_lim * tt - j_min * __cube(tt) / 6;
      v = v_lim + j_min * __square(tt) / 2;
      a = -j_min * tt;
      j = j_min = -j_max;
    }
    // Constant velocity phase
    else if (ta <= t && t < (ta + tv))
    {
      // (3.30d)
      q = q0 + (v_lim + v0) * ta / 2 + v_lim * (t - ta);
      v = v_lim;
      a = 0;
      j = 0;
    }
    // Deceleration phase
    else if ((tw - td) <= t && t < (tw - td + tj2))
    {
      tt = t - tw + td;
      // (3.30e)
      q = q1 - (v_lim + v1) * td / 2 + v_lim * tt - j_max * __cube(tt) / 6;
      v = v_lim - j_max * __square(tt) / 2;
      a = -j_max * tt;
      j = j_min = -j_max;
    }
    else if ((tw - td + tj2) <= t && t < (tw - tj2))
    {
      tt = t - tw + td;
      // (3.30f)
      q = q1 - (v_lim + v1) * td / 2 + v_lim * tt +
          a_lim_d * (3 * __square(tt) - 3 * tj2 * tt + __square(tj2)) / 6;
      v = v_lim + a_lim_d * (tt - tj2 / 2);
      a = a_lim_d = -j_max * tj2;
      j           = 0;
    }
    else if ((tw - tj2) <= t && t < tw)
    {
      tt = tw - t;
      // (3.30g)
      q = q1 - v1 * tt - j_max * __cube(tt) / 6;
      v = v1 + j_max * __square(tt) / 2;
      a = -j_max * tt;
      j = j_max;
    }
    else
    {
      q = q1;
      v = v1;
      a = 0;
      j = 0;
    }

    point_[mcPositionId]     = q;
    point_[mcSpeedId]        = v;
    point_[mcAccelerationId] = a;
    point_[mcJerkId]         = j;

    return point_;
  };
  // NOLINTEND(*-readability-identifier-naming)

  return trajectory(t);
}

double* ScurvePlannerOffLine::getTrajectoryFunction(double t)
{
  double* point = getTrajectoryFunc(t, profile_, condition_);

  if (!isnan(condition_.q1))
    pointSignTransform(point);

  return point;
}

MC_ERROR_CODE ScurvePlannerOffLine::scurveProfileNoOpt(
    const ScurveCondition& condition, ScurveProfile& profile)
{
  MC_ERROR_CODE res = scurveCheckPosibility(condition);
  if (res != mcErrorCodeGood)
    return res;

  res = computeMaximumSpeedReached(condition, profile);
  if (res != mcErrorCodeGood)
  {
    res = scurveSearchPlanning(condition, profile);
    if (res != mcErrorCodeGood)
      return res;
  }

  return res;
}

MC_ERROR_CODE ScurvePlannerOffLine::planTrajectory1D(double T)
{
  signTransforms(condition_);

  MC_ERROR_CODE res;
  // Computing Optimal time profile
  if (T == 0)
    res = scurveProfileNoOpt(condition_, profile_);
  // Computing constant time profile
  else
    res = scurveSearchPlanning(condition_, profile_, T);

  return res;
}

}  // namespace trajectory_processing
