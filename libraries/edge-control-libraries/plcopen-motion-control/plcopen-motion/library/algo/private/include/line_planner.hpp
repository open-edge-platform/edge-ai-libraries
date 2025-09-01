// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file line_planner.hpp
 *
 * Maintainer: Yichong Tang <yichong.tang@intel.com>
 *
 */

#pragma once

#include <algo/common/include/scurve_planner.hpp>

namespace trajectory_processing
{
struct LineCondition : ScurveCondition
{
};

struct LineProfile : ScurveProfile
{
  double k = 0.0;
  double b = 0.0;
};

class LinePlanner : public ScurvePlanner
{
public:
  LinePlanner()  = default;
  ~LinePlanner() = default;

  RTmotion::MC_ERROR_CODE plan() override;
  double* getWaypoint(double t) override;

  LineCondition& getLineCondition();
  LineProfile& getLineProfile();

  LineProfile profile_;
  LineCondition condition_;
};

}  // namespace trajectory_processing