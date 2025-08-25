// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file planner.hpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#pragma once

#include <fb/common/include/global.hpp>
#include <algo/public/include/offline_scurve_planner.hpp>
#include <algo/public/include/online_scurve_planner.hpp>
#include <algo/public/include/ruckig_planner.hpp>
#include <algo/private/include/poly_five_planner.hpp>
#include <algo/private/include/line_planner.hpp>
#include <chrono>

using RTmotion::MC_ERROR_CODE;

namespace trajectory_processing
{
class AxisPlanner
{
public:
  AxisPlanner();

  AxisPlanner(const AxisPlanner& planner);

  AxisPlanner& operator=(const AxisPlanner& planner);

  virtual ~AxisPlanner();

  void setCondition(const ScurveCondition& condition,
                    const RTmotion::PLANNER_TYPE type);
  void setCondition(double start_pos, double end_pos, double start_vel,
                    double end_vel, double start_acc, double end_acc,
                    double duration, double vel_max, double acc_max,
                    double jerk_max, RTmotion::PLANNER_TYPE type);

  MC_ERROR_CODE planTrajectory();

  double* getTrajectoryPoint(double t);

  MC_ERROR_CODE onReplan();

  MC_ERROR_CODE onExecution(double t, double* pos_cmd, double* vel_cmd,
                            double* acc_cmd);

  const ScurveCondition& getScurveCondition() const;

  ScurveProfile& getScurveProfile();

  void setStartTime(double t);

  void setFrequency(double f);

  RTmotion::PLANNER_TYPE getType() const;

private:
  ScurvePlanner* scurve_planner_;
  ScurvePlannerOnLine online_planner_;
  ScurvePlannerOffLine offline_planner_;
  RuckigPlanner ruckig_planner_;
  PolyFivePlanner poly_five_planner_;
  LinePlanner line_planner_;
  double start_time_;
  RTmotion::PLANNER_TYPE type_;
};

}  // namespace trajectory_processing
