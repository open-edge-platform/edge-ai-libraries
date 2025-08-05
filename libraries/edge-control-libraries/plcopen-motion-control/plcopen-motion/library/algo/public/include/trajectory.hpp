// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

/**
 * @file trajectory.hpp
 *
 * Maintainer: Yu Yan <yu.yan@intel.com>
 *
 */

#pragma once

#include <stdio.h>
#include <string>
#include <map>
#include <vector>
#include <chrono>
#include <cmath>

namespace trajectory_processing
{
struct VariableBounds
{
  double max_velocity_;
  double min_velocity_;
  double max_acceleration_;
  double min_acceleration_;
  bool velocity_bounded_;
  bool acceleration_bounded_;
};

class WayPoint
{
public:
  WayPoint()
  {
  }
  ~WayPoint() = default;

  double getVariablePosition(int joint)
  {
    return position_[joint];
  }
  double getVariableVelocity(int joint)
  {
    return velocity_[joint];
  }
  double getVariableAcceleration(int joint)
  {
    return acceleration_[joint];
  }
  void setVariablePosition(int joint, double pos)
  {
    position_[joint] = pos;
  }
  void setVariableVelocity(int joint, double vel)
  {
    velocity_[joint] = vel;
  }
  void setVariableAcceleration(int joint, double acc)
  {
    acceleration_[joint] = acc;
  }

private:
  std::map<int, double> position_;
  std::map<int, double> velocity_;
  std::map<int, double> acceleration_;
};

class RobotTrajectory
{
public:
  RobotTrajectory()
  {
  }
  ~RobotTrajectory() = default;

  bool empty() const
  {
    return path_.empty();
  }
  int getWayPointCount()
  {
    return path_.size();
  }
  WayPoint getWayPoint(size_t index)
  {
    return path_[index];
  }
  double getWayPointTimeStamp(size_t index)
  {
    return time_stamp_list_[index];
  }
  const std::vector<std::string>& getVariableNames()
  {
    return joint_names_;
  }
  const std::vector<int>& getVariableIndexList()
  {
    return index_list_;
  }
  unsigned getVariableCount()
  {
    return joint_names_.size();
  }
  VariableBounds getVariableBounds(std::string joint)
  {
    return variable_bounds_[joint];
  }
  void clear()
  {
    path_.clear();
    time_stamp_list_.clear();
  }
  void addSuffixWayPoint(WayPoint waypoint, double time_stamp)
  {
    path_.push_back(waypoint);
    time_stamp_list_.push_back(time_stamp);
  }
  void addWayPoint(WayPoint waypoint)
  {
    path_.push_back(waypoint);
  }
  bool addressTimeStamps()
  {
    if (path_.size() != time_stamp_list_.size())
    {
      printf("Time stamps size don't match waypoints number.");
      return false;
    }

    for (size_t i = 1; i < time_stamp_list_.size(); i++)
    {
      time_stamp_list_[i] = time_stamp_list_[i - 1] + time_stamp_list_[i];
    }

    return true;
  }

  void setVariableNames(const std::vector<std::string>& names)
  {
    joint_names_ = names;
  }
  void getVariableIndexList(const std::vector<int>& indexes)
  {
    index_list_ = indexes;
  }
  void setVariableBounds(const std::map<std::string, VariableBounds>& bounds)
  {
    variable_bounds_ = bounds;
  }

private:
  std::vector<WayPoint> path_;
  std::vector<double> time_stamp_list_;
  std::vector<std::string> joint_names_;
  std::vector<int> index_list_;
  std::map<std::string, VariableBounds> variable_bounds_;
};

extern std::vector<double> interp_cubic(double t, double T,
                                        std::vector<double> p0_pos,
                                        std::vector<double> p1_pos,
                                        std::vector<double> p0_vel,
                                        std::vector<double> p1_vel);

extern bool doTraj(std::vector<double> inp_timestamps,
                   std::vector<std::vector<double>> inp_positions,
                   std::vector<std::vector<double>> inp_velocities,
                   std::chrono::high_resolution_clock::time_point& t0,
                   bool& done);

}  // namespace trajectory_processing
