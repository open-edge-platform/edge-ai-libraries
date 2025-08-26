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
#ifdef ENABLE_SHM_RINGBUF
#include <shmringbuf.h>
#endif
#ifdef ENABLE_SHM_ACRN
#include "run_hiwin_plc_acrn/acrn_shm.hpp"
#endif

using namespace std::chrono_literals;

static const rclcpp::Logger LOGGER = rclcpp::get_logger("run_hiwin_plc");

/* Hiwin robot joint name and initial joint values */
static const std::vector<std::string> joint_names = {"manipulator/joint_1", "manipulator/joint_2", 
                                                     "manipulator/joint_3", "manipulator/joint_4",
                                                     "manipulator/joint_5", "manipulator/joint_6"}; 
static const std::vector<double> joint_init_values = {0.0, 0.0, 0.0, 0.0, -1.57, 0.0};

/* Task flag */
typedef enum 
{
  WaitTrajectory =   0,
  StartTrajectory =  1,
  DoneTrajectory =   2
} TaskState;

/* Shm related data types
 * s_buf, handle_s: data sent from RT domain
 * r_buf, handle_r: data sent to RT domain
 */
#define MSG_LEN 512
#define JOINT_NUM 6
static char s_buf[MSG_LEN];
static char r_buf[MSG_LEN];

#ifdef ENABLE_SHM_RINGBUF
static shm_handle_t handle_s, handle_r;
#endif // ENABLE_SHM_RINGBUF

struct JointCmd
{
  uint8_t mode = 0; // "0" position control, "1" velocity control 
  double joint_values[JOINT_NUM] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
};

struct JointState
{
  double joint_pos[JOINT_NUM] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
  double joint_vel[JOINT_NUM] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
};

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
    action_publisher_ = node->create_publisher<std_msgs::msg::Bool>("/fake_joint_trajectory_controller/done", 1);

#ifdef ENABLE_SHM_ACRN
    node->declare_parameter("enable_acrn_shm", true);
    node->get_parameter("enable_acrn_shm", mEnableAcrnShm);
    if (mEnableAcrnShm) {
      acrn_shm_ = std::make_shared<cross_vm_messenger::AcrnSharedMemory>(0, 8192);
      acrn_shm_->assign("rtsend", MSG_LEN);
      acrn_shm_->assign("rtread", MSG_LEN);
    }
#endif
  }

  void trajectoryCB(const trajectory_msgs::msg::JointTrajectory::SharedPtr msg)
  {
    RCLCPP_INFO(LOGGER, "Got trajectory msgs.");
    if (msg->joint_names.size() != joint_names.size())
    {
      RCLCPP_ERROR(LOGGER, "Received trajectory has wrong number of joint names.");
      return;
    }

    traj_msg_ = msg;
    start_time_ = node_->now();
    prev_time_ = start_time_;
    index_ = 0;
    task_ = StartTrajectory;
  }

  void timerCB(void)
  {
    if (task_ == StartTrajectory)
    {
      const auto waypoint_time = start_time_ + rclcpp::Duration(traj_msg_->points[index_].time_from_start);
      const auto time_now = node_->now();
      if (waypoint_time == time_now || (prev_time_ <= waypoint_time && time_now >= waypoint_time))
      {
        // joint_msg_->position = traj_msg_->points[index_].positions;
        /* Copy the joint commands */
        sendJointCmdsToRT(traj_msg_->points[index_].positions);
        index_++;
      }

      prev_time_ = time_now;

      if (index_ == traj_msg_->points.size())
      {
        RCLCPP_INFO(LOGGER, "Trajectory done.");
        task_ = DoneTrajectory;
        std_msgs::msg::Bool action_msgs;
        action_msgs.data = true;
        action_publisher_->publish(action_msgs);
      }
    }
    
    receiveJointStateFromRT(joint_msg_->position);
    joint_msg_->header.stamp = node_->now();
    joint_state_publisher_->publish(*joint_msg_);
  }

  void sendJointCmdsToRT(const std::vector<double>& target)
  {
    JointCmd joint_cmd;
    if (target.size() !=  JOINT_NUM)
    {
      RCLCPP_ERROR(LOGGER, "Required joint number: %d, actual: %d", JOINT_NUM, target.size());
      return;
    }
    for (size_t i = 0; i < JOINT_NUM; i++)
      joint_cmd.joint_values[i] = target[i];

    // Send the joint commands to RT domain
    memcpy(r_buf, &joint_cmd, sizeof(joint_cmd));
    int ret = 0;
  #ifdef ENABLE_SHM_RINGBUF
    if (!shm_blkbuf_full(handle_r))
    {
      ret = shm_blkbuf_write(handle_r, r_buf, sizeof(r_buf));
      RCLCPP_DEBUG(LOGGER, "%s: sent %d bytes\n", __FUNCTION__, ret);
    }
  #endif // ENABLE_SHM_RINGBUF
  #ifdef ENABLE_SHM_ACRN
    if (mEnableAcrnShm) {
      ret = acrn_shm_->write("rtread", r_buf, sizeof(r_buf));
      RCLCPP_DEBUG(LOGGER, "%s: sent %d bytes crossing VMs\n", __FUNCTION__, ret);
    }
  #endif
  }

  void receiveJointStateFromRT(std::vector<double>& joint_state)
  {
    /* get the joint commands */
    int ret = 0;
  #ifdef ENABLE_SHM_RINGBUF
    if (!shm_blkbuf_empty(handle_s))
    {
      ret = shm_blkbuf_read(handle_s, s_buf, sizeof(s_buf));
    }
  #endif // ENABLE_SHM_RINGBUF
  #ifdef ENABLE_SHM_ACRN
    if (mEnableAcrnShm) {
      ret = acrn_shm_->read("rtsend", s_buf, sizeof(s_buf));
    }
  #endif // ENABLE_SHM_ACRN
    if (ret)
    {
      JointState j_state;
      memcpy(&j_state, s_buf, sizeof(j_state));
      
      for (size_t i = 0; i < JOINT_NUM; i++)
      {
        joint_state[i] = j_state.joint_pos[i];
        RCLCPP_DEBUG(LOGGER, "\t %dth joint: %f\n", i, j_state.joint_pos[i]);
      }
    }

  }

private:
  rclcpp::Node::SharedPtr node_;
  std::unique_ptr<sensor_msgs::msg::JointState> joint_msg_;
  std::shared_ptr<trajectory_msgs::msg::JointTrajectory> traj_msg_;
  rclcpp::Publisher<sensor_msgs::msg::JointState>::SharedPtr joint_state_publisher_;
  rclcpp::Subscription<trajectory_msgs::msg::JointTrajectory>::SharedPtr trajectory_subscriber_;
  rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr action_publisher_;
  rclcpp::TimerBase::SharedPtr timer_;
  TaskState task_;
  rclcpp::Time start_time_;
  rclcpp::Time prev_time_;
  size_t index_;

#ifdef ENABLE_SHM_ACRN
    std::shared_ptr<cross_vm_messenger::AcrnSharedMemory> acrn_shm_;
    bool mEnableAcrnShm = true;
#endif // ENABLE_SHM_ACRN
};

/* Main program */
int main(int argc, char** argv)
{
  RCLCPP_INFO(LOGGER, "Initialize node");
  rclcpp::init(argc, argv);
  rclcpp::NodeOptions node_options;
  node_options.automatically_declare_parameters_from_overrides(true);
  rclcpp::Node::SharedPtr node = rclcpp::Node::make_shared("run_hiwin_plc", "", node_options);
#ifdef ENABLE_SHM_RINGBUF
  handle_s = shm_blkbuf_open("rtsend");
  handle_r = shm_blkbuf_open("rtread");
#endif // ENABLE_SHM_RINGBUF

  ArmPLCShmNode demo(node);

  rclcpp::spin(node);

  return 0;
}

