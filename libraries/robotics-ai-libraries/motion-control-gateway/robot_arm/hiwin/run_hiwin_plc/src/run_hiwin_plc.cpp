// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
// http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing,
// software distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions
// and limitations under the License.

#include <rclcpp/rclcpp.hpp>
#include <trajectory_msgs/msg/joint_trajectory.hpp>
#include <sensor_msgs/msg/joint_state.hpp>
#include <std_msgs/msg/bool.hpp>
#include <shmringbuf.h>
#include <moveit_msgs/msg/display_trajectory.hpp>
#include <moveit_msgs/msg/robot_trajectory.hpp>

using namespace std::chrono_literals;

static const rclcpp::Logger LOGGER = rclcpp::get_logger("run_hiwin_plc");

/* Hiwin robot joint name and initial joint values */
static const std::vector<std::string> joint_names = {"joint_1", "joint_2", 
                                                     "joint_3", "joint_4",
                                                     "joint_5", "joint_6"}; 
static const std::vector<double> joint_init_values = {0.0, 0.0, 0.0, 0.0, -1.57, 0.0};

/* Task flag */
typedef enum 
{
  WaitTrajectory     = 0,
  StartTrajectory    = 1,
  WaitTrajectoryDone = 2,
  DoneTrajectory     = 3
} TaskState;

#define NSEC_PER_SEC (1000000000L)

/* Shm related data types
 * s_buf, handle_s: data sent from RT domain
 * r_buf, handle_r: data sent to RT domain
 */
#define MSG_LEN 150000
#define JOINT_NUM 6
#define POINT_NUM 500
static char s_buf[MSG_LEN];
static char r_buf[MSG_LEN];
static shm_handle_t handle_s, handle_r;

struct TrajPoint
{
  double positions[JOINT_NUM] = {};
  double velocities[JOINT_NUM] = {};
  double accelerations[JOINT_NUM] = {};
  double effort[JOINT_NUM] = {};
  double time_from_start;
};

struct TrajCmd
{
  uint32_t point_num = 0;
  TrajPoint points[POINT_NUM]= {};
};

struct JointState
{
  double joint_pos[JOINT_NUM] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
  double joint_vel[JOINT_NUM] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
  bool traj_done = false;
};

static TrajCmd traj_cmd;
static JointState j_state;

/* PLC Shm node */
class ArmPLCShmNode
{
public:
  ArmPLCShmNode(const rclcpp::Node::SharedPtr& node)
  : node_(node)
  , task_(WaitTrajectory)
  {
    joint_msg_ = std::make_unique<sensor_msgs::msg::JointState>();
    joint_msg_->name = joint_names;
    joint_msg_->position = joint_init_values;

    traj_msg_ = std::make_shared<trajectory_msgs::msg::JointTrajectory>();

    timer_ = node_->create_wall_timer(2ms, std::bind(&ArmPLCShmNode::timerCB, this));

    joint_state_publisher_ = node_->create_publisher<sensor_msgs::msg::JointState>("/joint_states", 1);
    trajectory_subscriber_ = node_->create_subscription<trajectory_msgs::msg::JointTrajectory>(
        "/fake_joint_trajectory_controller/joint_trajectory", 1, std::bind(&ArmPLCShmNode::trajectoryCB, this, std::placeholders::_1));
    moveit2_trajectory_subscriber_ = node_->create_subscription<moveit_msgs::msg::DisplayTrajectory>(
        "/display_planned_path", 1, std::bind(&ArmPLCShmNode::moveitTrajectoryCB, this, std::placeholders::_1));
    action_publisher_ = node->create_publisher<std_msgs::msg::Bool>("/fake_joint_trajectory_controller/done", 1);
  }

  void trajectoryCB(const trajectory_msgs::msg::JointTrajectory::SharedPtr msg)
  {
#if 0
    RCLCPP_INFO(LOGGER, "Got trajectory msgs.");
    if (msg->joint_names.size() != joint_names.size() - 2)
    {
      RCLCPP_ERROR(LOGGER, "Received trajectory has wrong number of joint names.");
      return;
    }

    traj_msg_ = msg;
    task_ = StartTrajectory;
#endif
  }

  void moveitTrajectoryCB(const moveit_msgs::msg::DisplayTrajectory::SharedPtr msg)
  {
    RCLCPP_INFO(LOGGER, "Got moveit trajectory msgs. id: %s, size:%ld ", msg->model_id.c_str(), msg->trajectory.size());
    if (!msg->trajectory.size())
    {
      RCLCPP_ERROR(LOGGER, "Received trajectory has wrong number of joint names.");
      return;
    }
    moveit_msgs::msg::RobotTrajectory root_trajectory;
    root_trajectory = msg->trajectory[0];

    traj_msg_ = std::make_shared<trajectory_msgs::msg::JointTrajectory>(root_trajectory.joint_trajectory);
    task_ = StartTrajectory;
  }

  void timerCB(void)
  {
    // Send the trajectory to RT domain
    if (task_ == StartTrajectory)
    {
      task_ = WaitTrajectoryDone;
      traj_done_flag_ = false;
      sendJointCmdsToRT(traj_msg_);
      RCLCPP_INFO(LOGGER, "Trajectory start.");
    }
    
    // If trajectory is done, publish "done" message to MoveIt pipeline
    if (task_ == WaitTrajectoryDone && traj_done_flag_)
    {
      std_msgs::msg::Bool action_msgs;
      action_msgs.data = true;
      task_ = WaitTrajectory;
      action_publisher_->publish(action_msgs);
      RCLCPP_INFO(LOGGER, "Trajectory done.");
    }

    // Receive joint state message from RT domain
    receiveJointStateFromRT(joint_msg_->position);
    joint_msg_->header.stamp = node_->now();
    joint_state_publisher_->publish(*joint_msg_);
  }

  void sendJointCmdsToRT(const trajectory_msgs::msg::JointTrajectory::SharedPtr msg)
  {
    traj_cmd.point_num = msg->points.size();
    for (size_t i = 0; i < msg->points.size(); i++)
    {
      traj_cmd.points[i].time_from_start = msg->points[i].time_from_start.sec * NSEC_PER_SEC + msg->points[i].time_from_start.nanosec;

      for (size_t j = 0; j < JOINT_NUM; j++)
      {
        traj_cmd.points[i].positions[j] = msg->points[i].positions[j];
        traj_cmd.points[i].velocities[j] = msg->points[i].velocities[j];
        traj_cmd.points[i].accelerations[j] = msg->points[i].accelerations[j];
        // traj_cmd.points[i].effort[j] = msg->points[i].effort[j];
      }
    }

    // Send the joint commands to RT domain
    memcpy(r_buf, &traj_cmd, sizeof(traj_cmd));
    if (!shm_blkbuf_full(handle_r))
    {
      // RCLCPP_ERROR(LOGGER, "debug.");
      int ret = shm_blkbuf_write(handle_r, r_buf, sizeof(r_buf));
      RCLCPP_DEBUG(LOGGER, "%s: sent %d bytes\n", __FUNCTION__, ret);
    }
  }

  void receiveJointStateFromRT(std::vector<double>& joint_state)
  {
    /* get the joint states */
    if (!shm_blkbuf_empty(handle_s))
    {
      int ret = shm_blkbuf_read(handle_s, s_buf, sizeof(s_buf));
      if (ret)
      {
        memcpy(&j_state, s_buf, sizeof(j_state));
        
        if (!traj_done_tmp_ && j_state.traj_done) // Only done at the rising edge
          traj_done_flag_ = true;

        for (size_t i = 0; i < JOINT_NUM; i++)
        {
          joint_state[i] = j_state.joint_pos[i];
          RCLCPP_DEBUG(LOGGER, "\t %ldth joint: %f\n", i, j_state.joint_pos[i]);
        }

        traj_done_tmp_ = j_state.traj_done;
      }
    }
  }

private:
  rclcpp::Node::SharedPtr node_;
  std::unique_ptr<sensor_msgs::msg::JointState> joint_msg_;
  std::shared_ptr<trajectory_msgs::msg::JointTrajectory> traj_msg_;
  rclcpp::Publisher<sensor_msgs::msg::JointState>::SharedPtr joint_state_publisher_;
  rclcpp::Subscription<trajectory_msgs::msg::JointTrajectory>::SharedPtr trajectory_subscriber_;
  rclcpp::Subscription<moveit_msgs::msg::DisplayTrajectory>::SharedPtr moveit2_trajectory_subscriber_;
  rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr action_publisher_;
  rclcpp::TimerBase::SharedPtr timer_;
  TaskState task_;
  bool traj_done_tmp_ = false;
  bool traj_done_flag_ = false;
};

/* Main program */
int main(int argc, char** argv)
{
  RCLCPP_INFO(LOGGER, "Initialize node");
  rclcpp::init(argc, argv);
  rclcpp::NodeOptions node_options;
  node_options.automatically_declare_parameters_from_overrides(true);
  rclcpp::Node::SharedPtr node = rclcpp::Node::make_shared("run_hiwin_plc", "", node_options);

  handle_s = shm_blkbuf_open((char*)"rtsend");
  handle_r = shm_blkbuf_open((char*)"rtread");

  ArmPLCShmNode demo(node);

  rclcpp::spin(node);

  return 0;
}

