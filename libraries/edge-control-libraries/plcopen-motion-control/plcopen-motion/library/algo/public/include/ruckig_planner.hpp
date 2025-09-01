// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file ruckig_planner.hpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#pragma once

#include <algo/common/include/scurve_planner.hpp>
#include <ruckig/ruckig.hpp>

#define RUCKIG_DEFAULT_FREQUENCY 0.001
#define RUCKIG_AXIS_NUM 1

namespace trajectory_processing
{
class RuckigPlanner : public ScurvePlanner
{
public:
  RuckigPlanner()  = default;
  ~RuckigPlanner() = default;

  RTmotion::MC_ERROR_CODE plan() override;
  double* getWaypoint(double t) override;
  void setFrequency(double f) override;

  ruckig::Ruckig<RUCKIG_AXIS_NUM> otg_ =
      ruckig::Ruckig<RUCKIG_AXIS_NUM>(RUCKIG_DEFAULT_FREQUENCY);
  ruckig::InputParameter<RUCKIG_AXIS_NUM> input_;
  ruckig::OutputParameter<RUCKIG_AXIS_NUM> output_;
};

}  // namespace trajectory_processing
