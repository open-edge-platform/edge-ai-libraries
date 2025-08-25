// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file trajectory.cpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#include <algo/public/include/trajectory.hpp>
#include <fb/common/include/logging.hpp>

namespace trajectory_processing
{
std::vector<double> interp_cubic(double t, double T, std::vector<double> p0_pos,
                                 std::vector<double> p1_pos,
                                 std::vector<double> p0_vel,
                                 std::vector<double> p1_vel)
{
  /*Returns positions of the joints at time 't' */
  std::vector<double> positions;
  for (unsigned int i = 0; i < p0_pos.size(); i++)
  {
    double a = p0_pos[i];
    double b = p0_vel[i];
    double c =
        (-3 * p0_pos[i] + 3 * p1_pos[i] - 2 * T * p0_vel[i] - T * p1_vel[i]) /
        pow(T, 2);
    double d = (2 * p0_pos[i] - 2 * p1_pos[i] + T * p0_vel[i] + T * p1_vel[i]) /
               pow(T, 3);
    positions.push_back(a + b * t + c * pow(t, 2) + d * pow(t, 3));
  }
  return positions;
}

bool doTraj(std::vector<double> inp_timestamps,
            std::vector<std::vector<double>> inp_positions,
            std::vector<std::vector<double>> inp_velocities,
            std::chrono::high_resolution_clock::time_point& t0, bool& done)
{
  std::vector<double> positions;

  auto t                = std::chrono::high_resolution_clock::now();
  static unsigned int j = 0;
  if (inp_timestamps[inp_timestamps.size() - 1] >=
      std::chrono::duration_cast<std::chrono::duration<double>>(t - t0).count())
  {
    if (inp_timestamps[j] <=
            std::chrono::duration_cast<std::chrono::duration<double>>(t - t0)
                .count() &&
        j < inp_timestamps.size() - 1)
    {
      j++;
    }
    positions = interp_cubic(
        std::chrono::duration_cast<std::chrono::duration<double>>(t - t0)
                .count() -
            inp_timestamps[j - 1],
        inp_timestamps[j] - inp_timestamps[j - 1], inp_positions[j - 1],
        inp_positions[j], inp_velocities[j - 1], inp_velocities[j]);
    printf(
        "Axis position command sent: %f, at time: %ld \n", positions[0],
        std::chrono::duration_cast<std::chrono::milliseconds>(t - t0).count());
    // axis_->execPos(positions);

    return true;
  }
  j = 0;

  done = true;
  return true;
}

}  // namespace trajectory_processing