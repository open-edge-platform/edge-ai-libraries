// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file poly_five_planner.hpp
 *
 * Maintainer: Yichong Tang <yichong.tang@intel.com>
 *
 */

#pragma once

#include <algo/common/include/scurve_planner.hpp>

namespace trajectory_processing
{
struct PolyFiveCondition : ScurveCondition
{
};

struct PolyFiveProfile : ScurveProfile
{
  double a0 = 0.0;
  double a1 = 0.0;
  double a2 = 0.0;
  double a3 = 0.0;
  double a4 = 0.0;
  double a5 = 0.0;
};

class PolyFivePlanner : public ScurvePlanner
{
public:
  PolyFivePlanner()  = default;
  ~PolyFivePlanner() = default;

  RTmotion::MC_ERROR_CODE plan() override;
  double* getWaypoint(double t) override;

  PolyFiveCondition& getPolyFiveCondition();
  PolyFiveProfile& getPolyFiveProfile();

  PolyFiveProfile profile_;
  PolyFiveCondition condition_;
};

}  // namespace trajectory_processing