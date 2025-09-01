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
#include <thread>

static const rclcpp::Logger LOGGER = rclcpp::get_logger("jaka_servo.virtual_object_pub");

int main(int argc, char** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::Node::SharedPtr node = rclcpp::Node::make_shared("virtual_object_pub");

  node->declare_parameter("pub_mode", 0);
  int pub_mode =
      node->get_parameter("pub_mode").get_parameter_value().get<int>();

  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(node);
  std::thread executor_thread([&executor]() { executor.spin(); });

  // Initialize the transform broadcaster
  std::unique_ptr<tf2_ros::TransformBroadcaster> tf_broadcaster =
    std::make_unique<tf2_ros::TransformBroadcaster>(node);

  // Make a publisher for sending pose commands
  auto target_pose_pub = node->create_publisher<geometry_msgs::msg::PoseStamped>("target_pose", 1 /* queue */);

  // Get the current EE transform
  geometry_msgs::msg::TransformStamped obj_tf;
  obj_tf.header.frame_id = "base_link";
  obj_tf.child_frame_id = "object";
  obj_tf.transform.translation.x = -0.35;
  if (pub_mode == 0)
    obj_tf.transform.translation.y = -0.15;
  if (pub_mode == 1)
    obj_tf.transform.translation.y = 0.25;
  obj_tf.transform.translation.z = 0.21;
  obj_tf.transform.rotation.x = 0;
  obj_tf.transform.rotation.y = 0;
  obj_tf.transform.rotation.z = 0;
  obj_tf.transform.rotation.w = 1;

  // Convert it to a Pose
  geometry_msgs::msg::PoseStamped target_pose;
  target_pose.header.frame_id = "base_link";
  target_pose.pose.position.x = obj_tf.transform.translation.x;
  target_pose.pose.position.y = obj_tf.transform.translation.y;
  target_pose.pose.position.z = obj_tf.transform.translation.z;
  target_pose.pose.orientation.x = 0.46;
  target_pose.pose.orientation.y = 0.89;
  target_pose.pose.orientation.z = 0;
  target_pose.pose.orientation.w = 0;

  // Publish target pose
  target_pose.header.stamp = node->now();
  target_pose_pub->publish(target_pose);
  obj_tf.header.stamp = node->now();
  tf_broadcaster->sendTransform(obj_tf);

  rclcpp::Rate loop_rate(100);
  for (size_t i = 0; i < 5000 && obj_tf.transform.translation.y >= -0.15 && obj_tf.transform.translation.y <= 0.25; ++i)
  {
    // Modify the pose target a little bit each cycle
    // This is a dynamic pose target
    double vel_scale = 0.0005;
    if (pub_mode == 0)
    {
      obj_tf.transform.translation.y += vel_scale;
      obj_tf.header.stamp = node->now();
      tf_broadcaster->sendTransform(obj_tf);

      target_pose.pose.position.y += vel_scale;
      target_pose.header.stamp = node->now();
      target_pose_pub->publish(target_pose);
    }

    if (pub_mode == 1)
    {
      obj_tf.transform.translation.y -= vel_scale;
      obj_tf.header.stamp = node->now();
      tf_broadcaster->sendTransform(obj_tf);

      target_pose.pose.position.y -= vel_scale;
      target_pose.header.stamp = node->now();
      target_pose_pub->publish(target_pose);
    }

    loop_rate.sleep();
  }

  // Kill executor thread before shutdown
  executor.cancel();
  executor_thread.join();

  rclcpp::shutdown();
  return EXIT_SUCCESS;
}
