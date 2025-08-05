/*********************************************************************
 * Software License Agreement (BSD License)
 *
 *  Copyright (c) 2020, PickNik LLC
 *  All rights reserved.
 *
 *  Redistribution and use in source and binary forms, with or without
 *  modification, are permitted provided that the following conditions
 *  are met:
 *
 *   * Redistributions of source code must retain the above copyright
 *     notice, this list of conditions and the following disclaimer.
 *   * Redistributions in binary form must reproduce the above
 *     copyright notice, this list of conditions and the following
 *     disclaimer in the documentation and/or other materials provided
 *     with the distribution.
 *   * Neither the name of PickNik LLC nor the names of its
 *     contributors may be used to endorse or promote products derived
 *     from this software without specific prior written permission.
 *
 *  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 *  "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 *  LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
 *  FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
 *  COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
 *  INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
 *  BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
 *  LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
 *  CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
 *  LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
 *  ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 *  POSSIBILITY OF SUCH DAMAGE.
 *********************************************************************/

/* Author: Henning Kayser
   Desc: A simple demo node running MoveItCpp for planning and execution
*/

#include <thread>
#include <rclcpp/rclcpp.hpp>
#include <moveit/moveit_cpp/moveit_cpp.h>
#include <moveit/moveit_cpp/planning_component.h>
#include <moveit/robot_state/conversions.h>
#include <moveit_msgs/msg/display_robot_state.hpp>
#include <moveit/planning_scene_monitor/planning_scene_monitor.h>
#include <trajectory_msgs/msg/joint_trajectory.hpp>
#include <std_msgs/msg/bool.hpp>

static const rclcpp::Logger LOGGER = rclcpp::get_logger("run_jaka_moveit");

static const std::vector<std::string> j_names = {"joint_1", "joint_2", 
                                                 "joint_3", "joint_4",
                                                 "joint_5", "joint_6"}; 
static const std::vector<double> goal_1 = {-0.844, -0.164, -1.172, 0.5618, -1.570, -0.23};
static const std::vector<double> goal_2 = {0.708, -0.290, -1.639, 0.378, -1.785, 0.615};


class MoveItCppDemo
{
public:
  MoveItCppDemo(const rclcpp::Node::SharedPtr& node)
    : node_(node)
    , goal_index_(1)
  {
  }

  void run()
  {
    RCLCPP_INFO(LOGGER, "Initialize MoveItCpp: run_moveit_cpp");
    moveit_cpp_ = std::make_shared<moveit_cpp::MoveItCpp>(node_);
#if 1
    moveit_cpp_->getPlanningSceneMonitorNonConst()->providePlanningSceneService();
    moveit_cpp_->getPlanningSceneMonitorNonConst()->setPlanningScenePublishingFrequency(100);
#else
    moveit_cpp_->getPlanningSceneMonitor()->providePlanningSceneService();
    moveit_cpp_->getPlanningSceneMonitor()->setPlanningScenePublishingFrequency(100);
#endif
    RCLCPP_INFO(LOGGER, "Initialize PlanningComponent");
    moveit_cpp::PlanningComponent arm("jaka_arm", moveit_cpp_);

    while( rclcpp::ok())
    {
      // A little delay before running the plan
      rclcpp::sleep_for(std::chrono::seconds(5));

      // Set joint state goal
      auto target_state = *(moveit_cpp_->getCurrentState());
      if (goal_index_ == 1)
      {
        target_state.setVariablePositions(j_names, goal_1);
        goal_index_ = 2;
        RCLCPP_INFO(LOGGER, "Set goal 1");
      }
      else if (goal_index_ == 2)
      {
        target_state.setVariablePositions(j_names, goal_2);
        goal_index_ = 1;
        RCLCPP_INFO(LOGGER, "Set goal 2");
      }        
      // arm.setGoal("all_zeros");
      arm.setGoal(target_state);

      // Run actual plan
      RCLCPP_INFO(LOGGER, "Plan to goal");
      auto plan_solution = arm.plan();
      if (plan_solution)
      {
        RCLCPP_INFO(LOGGER, "arm.execute()");
        arm.execute(true);
      }

    }
  }

private:
  rclcpp::Node::SharedPtr node_;
  moveit_cpp::MoveItCppPtr moveit_cpp_;
  int goal_index_;
};

int main(int argc, char** argv)
{
  RCLCPP_INFO(LOGGER, "Initialize node");
  rclcpp::init(argc, argv);
  rclcpp::NodeOptions node_options;
  node_options.automatically_declare_parameters_from_overrides(true);
  rclcpp::Node::SharedPtr node = rclcpp::Node::make_shared("run_jaka_moveit", "", node_options);

  MoveItCppDemo demo(node);
  std::thread run_demo([&demo]() {
    // Let RViz initialize before running demo
    // TODO(henningkayser): use lifecycle events to launch node
    rclcpp::sleep_for(std::chrono::seconds(5));
    demo.run();
  });

  rclcpp::spin(node);
  run_demo.join();

  return 0;
}
