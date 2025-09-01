// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file offline_scurve_planner.hpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#pragma once

#include <algo/common/include/scurve_planner.hpp>

using RTmotion::MC_ERROR_CODE;

namespace trajectory_processing
{
class ScurvePlannerOffLine : public ScurvePlanner
{
public:
  ScurvePlannerOffLine()
  {
  }
  ~ScurvePlannerOffLine() = default;

  /**
   * @brief Check whether trajectory is feasible. If not return MC_ERROR_CODE
   * @param condition  The input scurve condition, i.e. q0, q1, v0, v1, v_max,
   * a_max, j_max
   */

  MC_ERROR_CODE scurveCheckPosibility(const ScurveCondition& condition);

  /**
   * @brief For explanation look at page 79 of 'Trajectory planning for
   * automatic machines and robots(2008)'
   * @param condition  The input scurve condition, i.e. q0, q1, v0, v1, v_max,
   * a_max, j_max
   * @param profile The output scurve profile result, i.e. Tj1, Ta, Tj2, Td, Tv
   */
  MC_ERROR_CODE computeMaximumSpeedReached(const ScurveCondition& condition,
                                           ScurveProfile& profile);

  /**
   * @brief For explanation look at page 79 of 'Trajectory planning for
   * automatic machines and robots(2008)'
   * @param condition  The input scurve condition, i.e. q0, q1, v0, v1, v_max,
   * a_max, j_max
   * @param profile The output scurve profile result, i.e. Tj1, Ta, Tj2, Td, Tv
   */
  MC_ERROR_CODE computeMaximumSpeedNotReached(const ScurveCondition& condition,
                                              ScurveProfile& profile);

  /**
   * @brief Trying to achieve requirements with iteratively decreasing maximum
   * possible acceleration. Look at 'Trajectory planning for automatic machines
   * and robots(2008)'
   * @param condition  The input scurve condition, i.e. q0, q1, v0, v1, v_max,
   * a_max, j_max
   * @param profile The output scurve profile result, i.e. Tj1, Ta, Tj2, Td, Tv
   */
  MC_ERROR_CODE scurveSearchPlanning(const ScurveCondition& condition,
                                     ScurveProfile& profile, double T = 0,
                                     double scale     = 0.99,
                                     size_t max_iter  = 2000,
                                     double dt_thresh = 0.01,
                                     int timeout      = 500);

  /**
   * @brief Returns trajectory parameters for a given time, which contains
   * acceleration, velocity and position.
   * @param t The given timestamp
   * @param condition  The input scurve condition, i.e. q0, q1, v0, v1, v_max,
   * a_max, j_max
   * @param profile The input scurve profile, i.e. Tj1, Ta, Tj2, Td, Tv
   */
  double* getTrajectoryFunc(double t, const ScurveProfile& profile,
                            const ScurveCondition& condition);

  /**
   * @brief Returns trajectory parameters which wraps with sign transforms.
   * @param t The given timestamp
   * @param condition  The input scurve condition, i.e. q0, q1, v0, v1, v_max,
   * a_max, j_max
   * @param profile The input scurve profile, i.e. Tj1, Ta, Tj2, Td, Tv
   */
  double* getTrajectoryFunction(double t);

  /**
   * @brief Computes s-curve trajectory parameters which are:
   *        Tj1 --- non-zero constant jerk period while accelerating
   *        Ta  --- total acceleration period time
   *        Tj2 --- non-zero constant jerk period while decelerating
   *        Td  --- total deceleration time
   *        Tv  --- constant speed time
   * @param t The given timestamp
   * @param condition  The input scurve condition, i.e. q0, q1, v0, v1, v_max,
   * a_max, j_max
   * @param profile The output scurve profile result, i.e. Tj1, Ta, Tj2, Td, Tv
   */
  MC_ERROR_CODE scurveProfileNoOpt(const ScurveCondition& condition,
                                   ScurveProfile& profile);

  /**
   * @brief Computes optimal time scurve trajectory or trying to fit it in time
   * T.
   * @param T Trajectory execution time
   */
  MC_ERROR_CODE planTrajectory1D(double T = 0);

  /**
   * @brief Computes acceleration phase under conditions.
   * @param v  Initial velocity or end velocity
   * @param v_max Maximum velocity
   * @param a_max Maximum acceleration
   * @param j_max Maximum jerk
   * @param Tj Phase time with acceleration from 0 to a_max or a_max to 0
   * @param Tad Acceleration phase Tad = 2*Tj if a_max is not reached, Tad >
   * 2*Tj if a_max is reached
   */
  MC_ERROR_CODE computeAccelerationPhase(double v, double v_max, double a_max,
                                         double j_max, double& Tj, double& Tad);

  MC_ERROR_CODE plan() override
  {
    profile_.Tv  = 0;
    profile_.Tj2 = 0;
    profile_.Td  = 0;

    if (condition_.v1 > condition_.v0)
    {
      MC_ERROR_CODE res = computeAccelerationPhase(
          condition_.v0, condition_.v1, condition_.a_max, condition_.j_max,
          profile_.Tj1, profile_.Ta);
      return res;
    }
    else
    {
      MC_ERROR_CODE res = computeAccelerationPhase(
          condition_.v1, condition_.v0, condition_.a_max, condition_.j_max,
          profile_.Tj1, profile_.Ta);
      condition_.j_max = -condition_.j_max;
      return res;
    }
  }

  double* getWaypoint(double t) override
  {
    return getTrajectoryFunction(t);
  }
};

}  // namespace trajectory_processing