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

#include <std_msgs/msg/int8.hpp>
#include <geometry_msgs/msg/transform_stamped.hpp>
#include <tf2_ros/transform_broadcaster.h>
#include <geometry_msgs/msg/pose_stamped.hpp>
#include <rviz_visual_tools/rviz_visual_tools.hpp>
#include <rclcpp/rclcpp.hpp>
#include <thread>
#include <mutex>

static const rclcpp::Logger LOGGER = rclcpp::get_logger("ur_realtime_servo.vision_object_pub");

using std::placeholders::_1;
namespace rvt = rviz_visual_tools;
using namespace std::literals;

class VisionOject : public rclcpp::Node
{
public:
  VisionOject(/* args */)
    : Node("vision_object_pub")
  {
    this->declare_parameter("workspace", workspace_);
    if (!this->get_parameter("workspace", workspace_))
    {
      RCLCPP_ERROR(LOGGER, "Failed to get workspace parameter.");
      return;
    }

    this->declare_parameter("x", x_default_);
    if (!this->get_parameter("x", x_default_))
    {
      RCLCPP_ERROR(LOGGER, "Failed to get x_default_ parameter.");
      return;
    }

    this->declare_parameter("z", z_default_);
    if (!this->get_parameter("z", z_default_))
    {
      RCLCPP_ERROR(LOGGER, "Failed to get z_default parameter.");
      return;
    }
    this->declare_parameter("debug", open_debug_print_);
    if (!this->get_parameter("debug", open_debug_print_))
    {
      RCLCPP_ERROR(LOGGER, "Failed to get open_debug_print_ parameter.");
      return;
    }

    RCLCPP_INFO(LOGGER,"workspace: [%f, %f, %f, %f, %f, %f]", workspace_[0], workspace_[1], workspace_[2], 
                                                              workspace_[3], workspace_[4], workspace_[5]);
    RCLCPP_INFO(LOGGER,"x_default: %f", x_default_);
    RCLCPP_INFO(LOGGER,"z_default: %f", z_default_);
    RCLCPP_INFO(LOGGER,"Enable debug print: %d", open_debug_print_);

    vision_pose_sub_ = this->create_subscription<geometry_msgs::msg::PoseStamped>(
      "/pose_estimator/pose_stamped", rclcpp::SystemDefaultsQoS(), 
      std::bind(&VisionOject::visionPoseCB, this, std::placeholders::_1));
    
    // Init target pose publisher
    target_pose_pub_ = this->create_publisher<geometry_msgs::msg::PoseStamped>("target_pose", 1 /* queue */);

    // Init object tf broadcaster
    tf_broadcaster_ = std::make_unique<tf2_ros::TransformBroadcaster>(this);

    // Init object tf transform
    obj_tf_.header.frame_id = "base_link";
    obj_tf_.child_frame_id = "object";
    obj_tf_.transform.translation.x = 0.35;
    obj_tf_.transform.translation.y = 0.35;
    obj_tf_.transform.translation.z = 0.21;
    obj_tf_.transform.rotation.x = 0;
    obj_tf_.transform.rotation.y = 0;
    obj_tf_.transform.rotation.z = 0;
    obj_tf_.transform.rotation.w = 1;

    // Init target pose transform
    target_pose_.header.frame_id = "base_link";
    target_pose_.pose.position.x = obj_tf_.transform.translation.x;
    target_pose_.pose.position.y = obj_tf_.transform.translation.y;
    target_pose_.pose.position.z = obj_tf_.transform.translation.z + 0.1;
    target_pose_.pose.orientation.x = 1;
    target_pose_.pose.orientation.y = 0;
    target_pose_.pose.orientation.z = 0;
    target_pose_.pose.orientation.w = 0;

    visual_tools_.reset(new rvt::RvizVisualTools("base_link", "/rviz_visual_tools", this));
    visual_tools_->loadMarkerPub();
    bool has_sub = visual_tools_->waitForMarkerSub(5.0);
    if (has_sub)
      RCLCPP_INFO(LOGGER, "/rviz_visual_tools does not have a subscriber after 5s. ");

    visual_tools_->deleteAllMarkers();
    visual_tools_->enableBatchPublishing();

    auto pose1 = Eigen::Isometry3d::Identity();
    auto pose2 = Eigen::Isometry3d::Identity();

    pose1.translation().x() = workspace_[0];
    pose1.translation().y() = workspace_[2];
    pose1.translation().z() = workspace_[4];

    pose2.translation().x() = workspace_[1];
    pose2.translation().y() = workspace_[3];
    pose2.translation().z() = workspace_[4];

    visual_tools_->publishCuboid(pose2.translation(), pose1.translation(), rvt::BLUE);

    pose1.translation().z() = workspace_[5];
    pose2.translation().z() = workspace_[5];
    
    visual_tools_->publishCuboid(pose2.translation(), pose1.translation(), rvt::BLUE);
    visual_tools_->trigger();

    timer_ = this->create_wall_timer(
      200ms, std::bind(&VisionOject::timer_callback, this));
  }

private:
  void visionPoseCB(const geometry_msgs::msg::PoseStamped::ConstSharedPtr msg)
  {
    if (open_debug_print_)
      RCLCPP_INFO(LOGGER, "Detected pose received. ");

    std::lock_guard<std::mutex> guard(vision_object_mutex_);

    if (mode_ == RESUME)
      mode_ = TRACKING;

    if (msg->header.frame_id == "base")
    {
      obj_tf_.transform.translation.x = -msg->pose.position.x;
      obj_tf_.transform.translation.y = -msg->pose.position.y;
      obj_tf_.transform.translation.z = msg->pose.position.z;
    }

    if (msg->header.frame_id == "base_link")
    {
      obj_tf_.transform.translation.x = msg->pose.position.x;
      obj_tf_.transform.translation.y = msg->pose.position.y;
      obj_tf_.transform.translation.z = msg->pose.position.z;
    }

    if (obj_tf_.transform.translation.x > workspace_[0] && obj_tf_.transform.translation.x < workspace_[1]
          && obj_tf_.transform.translation.y > workspace_[2] && obj_tf_.transform.translation.y < workspace_[3]
            && obj_tf_.transform.translation.z > workspace_[4] && obj_tf_.transform.translation.z < workspace_[5])
    {
      target_pose_.pose.position.x = x_default_;
      target_pose_.pose.position.y = obj_tf_.transform.translation.y;
      //target_pose_.pose.position.z = obj_tf_.transform.translation.z + 0.1;
      target_pose_.pose.position.z = z_default_;

      obj_tf_.header.stamp = this->now();
      tf_broadcaster_->sendTransform(obj_tf_);

      target_pose_.header.stamp = this->now();
      target_pose_pub_->publish(target_pose_);
    }

    if (open_debug_print_)
      RCLCPP_INFO(LOGGER, "Target pose published. ");
  }

  void timer_callback()
  {
    if (mode_ == TRACKING && (this->now() - target_pose_.header.stamp).seconds() > 1.0)
    {
      mode_ = RESUME;
      if (open_debug_print_)
        RCLCPP_INFO(LOGGER, "Change to resume mode.");
    }

    if (mode_ == RESUME)
    {
      obj_tf_.transform.translation.x = 0.46;
      // obj_tf_.transform.translation.y = 0.265;
      obj_tf_.transform.translation.z = 0.174;
      if (obj_tf_.transform.translation.y < 0.265)
        obj_tf_.transform.translation.y += 0.04;

      target_pose_.pose.position.x = obj_tf_.transform.translation.x;
      target_pose_.pose.position.y = obj_tf_.transform.translation.y;
      target_pose_.pose.position.z = obj_tf_.transform.translation.z + 0.1;

      obj_tf_.header.stamp = this->now();
      tf_broadcaster_->sendTransform(obj_tf_);

      target_pose_.header.stamp = this->now();
      target_pose_pub_->publish(target_pose_);

      if (open_debug_print_)
        RCLCPP_INFO(LOGGER, "Resume pose published.");
    }
  }

  rclcpp::Subscription<geometry_msgs::msg::PoseStamped>::SharedPtr vision_pose_sub_;
  rclcpp::Publisher<geometry_msgs::msg::PoseStamped>::SharedPtr target_pose_pub_;
  std::unique_ptr<tf2_ros::TransformBroadcaster> tf_broadcaster_;

  geometry_msgs::msg::TransformStamped obj_tf_;
  geometry_msgs::msg::PoseStamped target_pose_;
  
  rvt::RvizVisualToolsPtr visual_tools_;
  std::vector<double> workspace_ = {0.45, 0.65, -0.35, 0.35, 0.1, 0.3};
  double x_default_ = 0.46; // Default x coordinate
  double z_default_ = 0.275; // Default z coordinate
  bool open_debug_print_ = false;

  rclcpp::TimerBase::SharedPtr timer_;
  enum TRACK_MODE{
    TRACKING = 0,
    RESUME = 1
  };

  TRACK_MODE mode_ = RESUME;
  std::mutex vision_object_mutex_;
};

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  rclcpp::Node::SharedPtr node = std::make_shared<VisionOject>();
  rclcpp::executors::MultiThreadedExecutor executor;
  executor.add_node(node);
  executor.spin();
  executor.cancel();
  rclcpp::shutdown();
  return 0;
}
