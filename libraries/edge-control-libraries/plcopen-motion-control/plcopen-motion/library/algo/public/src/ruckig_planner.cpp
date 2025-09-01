// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file ruckig_planner.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <algo/public/include/ruckig_planner.hpp>
#include <fb/common/include/logging.hpp>
#include <chrono>

using namespace RTmotion;

namespace trajectory_processing
{
RTmotion::MC_ERROR_CODE RuckigPlanner::plan()
{
  signTransforms(condition_);

  // Set input parameters
  input_.max_velocity     = { condition_.v_max };
  input_.max_acceleration = { condition_.a_max };
  input_.max_jerk         = { condition_.j_max };

  input_.current_position     = { condition_.q0 };
  input_.current_velocity     = { condition_.v0 };
  input_.current_acceleration = { condition_.a0 };

  input_.target_position     = { condition_.q1 };
  input_.target_velocity     = { condition_.v1 };
  input_.target_acceleration = { condition_.a1 };

  // printf("Debug condition_.a0 %f \n", condition_.a0);

  return otg_.validate_input(input_) ? RTmotion::mcErrorCodeGood :
                                       RTmotion::mcErrorCodeScurveInvalidInput;
}

double* RuckigPlanner::getWaypoint(double t)
{
  otg_.update(input_, output_);
  point_[mcPositionId]     = output_.new_position[0];
  point_[mcSpeedId]        = output_.new_velocity[0];
  point_[mcAccelerationId] = output_.new_acceleration[0];
  point_[mcJerkId] =
      (output_.new_acceleration[0] - input_.current_acceleration[0]) * t;

  input_.current_position     = output_.new_position;
  input_.current_velocity     = output_.new_velocity;
  input_.current_acceleration = output_.new_acceleration;

  // printf("Debug t %f, sk %f, vk %f, ak %f, jk %f.\n", output_.time,
  //         point_[mcPositionId], point_[mcSpeedId], point_[mcAccelerationId],
  //         point_[mcJerkId]);

  pointSignTransform(point_);

  return point_;
}

void RuckigPlanner::setFrequency(double f)
{
  otg_.delta_time = 1.0 / f;
}

}  // namespace trajectory_processing
