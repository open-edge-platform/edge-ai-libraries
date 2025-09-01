// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file planner.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <fb/common/include/planner.hpp>
#include <fb/common/include/logging.hpp>
#include <chrono>

namespace trajectory_processing
{
AxisPlanner::AxisPlanner()
  : online_planner_()
  , offline_planner_()
  , ruckig_planner_()
  , poly_five_planner_()
  , line_planner_()
{
  start_time_     = 0.0;
  type_           = RTmotion::mcRuckig;
  scurve_planner_ = &ruckig_planner_;
}

AxisPlanner::AxisPlanner(const AxisPlanner& planner)
{
  *this = planner;
}

AxisPlanner& AxisPlanner::operator=(const AxisPlanner& planner)
{
  if (this != &planner)
  {
    type_       = planner.type_;
    start_time_ = planner.start_time_;
    this->setCondition(planner.getScurveCondition(), planner.getType());
  }
  return *this;
}

AxisPlanner::~AxisPlanner()
{
  scurve_planner_ = nullptr;
}

void AxisPlanner::setCondition(const ScurveCondition& condition,
                               const RTmotion::PLANNER_TYPE type)
{
  this->setCondition(condition.q0, condition.q1, condition.v0, condition.v1,
                     condition.a0, condition.a1, condition.T, condition.v_max,
                     condition.a_max, condition.j_max, type);
}

void AxisPlanner::setCondition(double start_pos, double end_pos,
                               double start_vel, double end_vel,
                               double start_acc, double end_acc,
                               double duration, double vel_max, double acc_max,
                               double jerk_max, RTmotion::PLANNER_TYPE type)
{
  switch (type)
  {
    case RTmotion::mcOffLine: {
      type_           = RTmotion::mcOffLine;
      scurve_planner_ = &offline_planner_;
      break;
    }
    case RTmotion::mcRuckig: {
      type_           = RTmotion::mcRuckig;
      scurve_planner_ = &ruckig_planner_;
      break;
    }
    case RTmotion::mcPoly5: {
      type_                                             = RTmotion::mcPoly5;
      scurve_planner_                                   = &poly_five_planner_;
      ((PolyFivePlanner*)scurve_planner_)->condition_.T = duration;
      break;
    }
    case RTmotion::mcLine: {
      type_                                         = RTmotion::mcLine;
      scurve_planner_                               = &line_planner_;
      ((LinePlanner*)scurve_planner_)->condition_.T = duration;
      break;
    }
    case RTmotion::mcOnLine:
    default:
      break;
  }

  scurve_planner_->condition_.q0    = start_pos;
  scurve_planner_->condition_.q1    = end_pos;
  scurve_planner_->condition_.v0    = start_vel;
  scurve_planner_->condition_.v1    = end_vel;
  scurve_planner_->condition_.a0    = start_acc;
  scurve_planner_->condition_.a1    = end_acc;
  scurve_planner_->condition_.v_max = vel_max;
  scurve_planner_->condition_.a_max = acc_max;
  scurve_planner_->condition_.j_max = jerk_max;
  DEBUG_PRINT("AxisPlanner::setCondition:Scurve condition: q0 = %f, q1 = %f, "
              "v0 = %f, v1 = %f \n",
              scurve_planner_->condition_.q0, scurve_planner_->condition_.q1,
              scurve_planner_->condition_.v0, scurve_planner_->condition_.v1);

  // printf("setCondition: online_planner_: %p, offline_planner_: %p\n",
  // (void*)&online_planner_, (void*)&offline_planner_); printf("setCondition:
  // scurve_planner_: %p, ruckig_planner_: %p\n", (void*)scurve_planner_,
  // (void*)&ruckig_planner_);
}

MC_ERROR_CODE AxisPlanner::planTrajectory()
{
  // printf("planTrajectory: scurve_planner_: %p, ruckig_planner_: %p\n",
  // (void*)scurve_planner_, (void*)&ruckig_planner_);
  return scurve_planner_->plan();
}

double* AxisPlanner::getTrajectoryPoint(double t)
{
  return scurve_planner_->getWaypoint(t);
}

MC_ERROR_CODE AxisPlanner::onReplan()
{
  MC_ERROR_CODE res = planTrajectory();

  DEBUG_PRINT("AxisPlanner::onReplan:Scurve profile: Ta = %f, Tv = %f, Td = "
              "%f, Tj1 = %f, Tj2 = %f \n",
              scurve_planner_->profile_.Ta, scurve_planner_->profile_.Tv,
              scurve_planner_->profile_.Td, scurve_planner_->profile_.Tj1,
              scurve_planner_->profile_.Tj2);
  return res;
}

MC_ERROR_CODE AxisPlanner::onExecution(double t, double* pos_cmd,
                                       double* vel_cmd, double* acc_cmd)
{
  double d;
  if (type_ == RTmotion::mcPoly5 || type_ == RTmotion::mcLine)
    d = t;
  else
    d = t - start_time_;

  double* point = getTrajectoryPoint(d);
  *pos_cmd      = point[mcPositionId];
  *vel_cmd      = point[mcSpeedId];
  *acc_cmd      = point[mcAccelerationId];

  DEBUG_PRINT("AxisPlanner::onExecution:time: %f, pos_cmd: %f, vel_cmd: %f, "
              "acc_cmd: %f\n",
              d, point[mcPositionId], point[mcSpeedId],
              point[mcAccelerationId]);

  return RTmotion::mcErrorCodeGood;
}

const ScurveCondition& AxisPlanner::getScurveCondition() const
{
  if (type_ == RTmotion::mcPoly5)
  {
    return ((PolyFivePlanner*)scurve_planner_)->condition_;
  }
  else if (type_ == RTmotion::mcLine)
  {
    return ((LinePlanner*)scurve_planner_)->condition_;
  }
  else
  {
    return scurve_planner_->condition_;
  }
}

ScurveProfile& AxisPlanner::getScurveProfile()
{
  if (type_ == RTmotion::mcPoly5)
  {
    return ((PolyFivePlanner*)scurve_planner_)->profile_;
  }
  else if (type_ == RTmotion::mcLine)
  {
    return ((LinePlanner*)scurve_planner_)->profile_;
  }
  else
  {
    return scurve_planner_->profile_;
  }
}

void AxisPlanner::setStartTime(double t)
{
  start_time_ = t;
}

void AxisPlanner::setFrequency(double f)
{
  scurve_planner_->setFrequency(f);
}

RTmotion::PLANNER_TYPE AxisPlanner::getType() const
{
  return type_;
}

}  // namespace trajectory_processing
