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

#include <geometry_msgs/msg/pose_stamped.hpp>
#include <rclcpp/rclcpp.hpp>
#include <cmath>

static geometry_msgs::msg::Quaternion orientationAroundZAxis(double angle)
{
    auto orientation = geometry_msgs::msg::Quaternion();
    orientation.x = 0.0;
    orientation.y = 0.0;
    orientation.z = sin(angle) / (2 * cos(angle / 2));
    orientation.w = cos(angle / 2);
    return orientation;
}

int main(int argc, char ** argv)
{
    rclcpp::init(argc, argv);
    auto node = std::make_shared<rclcpp::Node>("nav2_pose_setter");
    auto posePublisher = node->create_publisher<geometry_msgs::msg::PoseStamped>(
        "/move_base_simple/goal", rclcpp::SystemDefaultsQoS());
        
    double pose[2][3];
    scanf("%lf %lf %lf", &pose[0][0], &pose[0][1], &pose[0][2]);
    scanf("%lf %lf %lf", &pose[1][0], &pose[1][1], &pose[1][2]);
    
    int i = 0;
    while(rclcpp::ok()) {
		getchar();
		geometry_msgs::msg::PoseStamped goal;
		goal.header.stamp = rclcpp::Clock().now();
		goal.header.frame_id = "map";

		goal.pose.position.x = pose[i][0];
		goal.pose.position.y = pose[i][1];
		goal.pose.position.z = 0.0;
		goal.pose.orientation = orientationAroundZAxis(pose[i][2]);
		
		posePublisher->publish(goal);
		i = !i;
	}
	
    rclcpp::shutdown();
	return 0;
}
