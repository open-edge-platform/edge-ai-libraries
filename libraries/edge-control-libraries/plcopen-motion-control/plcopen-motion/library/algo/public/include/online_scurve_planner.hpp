// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file online_scurve_planner.hpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#pragma once

#include <algo/common/include/scurve_planner.hpp>

using RTmotion::MC_ERROR_CODE;

namespace trajectory_processing
{
typedef enum
{
  mcNotYetStarted = 0,
  mcDeceleration  = 1,
  mcAcceleration  = 2
} StopPhaseMode;

typedef enum
{
  mcNoJerk   = 0,
  mcJerkMin  = 1,
  mcJerkZero = 2,
  mcJerkMax  = 3
} StopPhase;
class ScurvePlannerOnLine : public ScurvePlanner
{
public:
  ScurvePlannerOnLine()  = default;
  ~ScurvePlannerOnLine() = default;

  void computeProfile(double jk, double tk, double& ak, double& vk,
                      double& sk);  // Equation (1)

  void computeStopPhaseDccProfile(double& jk, double& hk, double& Tj2a,
                                  double& Tj2b, double& Td);

  void computeStopPhaseAccProfile(double& jk, double& hk, double& Tj2a,
                                  double& Tj2b, double& Td);

  void computeStopPhaseDcc(double t, double& jk, double& ak, double& vk,
                           double& sk);

  void computeStopPhaseAcc(double t, double& jk, double& ak, double& vk,
                           double& sk);

  void computeFirstPhaseAcc(double t, double& jk, double& ak, double& vk,
                            double& sk);  // v0 <= Vmax

  void computeFirstPhaseDcc(double t, double& jk, double& ak, double& vk,
                            double& sk);  // v0 > Vmax

  MC_ERROR_CODE plan() override
  {
    signTransforms(condition_);
    return RTmotion::mcErrorCodeGood;
  }

  double* getWaypoint(double t) override;

  void reset();

  double sk_, vk_, ak_, jk_, tk_;
  double s_init_, v_init_, a_init_, t_init_;
  bool triggered_     = false;
  StopPhaseMode mode_ = mcNotYetStarted;
  StopPhase phase_    = mcNoJerk;
};

}  // namespace trajectory_processing