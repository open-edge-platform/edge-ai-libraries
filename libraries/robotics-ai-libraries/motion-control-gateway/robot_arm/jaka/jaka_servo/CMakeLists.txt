# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
cmake_minimum_required(VERSION 3.10.2)
project(jaka_servo)

# Common cmake code applied to all moveit packages
find_package(moveit_common REQUIRED)
moveit_package()

find_package(Eigen3 REQUIRED)
find_package(Boost REQUIRED system filesystem date_time thread)
find_package(ament_cmake REQUIRED)
find_package(control_msgs REQUIRED)
find_package(moveit_core REQUIRED)
find_package(moveit_ros_planning REQUIRED)
find_package(moveit_ros_planning_interface REQUIRED)
find_package(moveit_ros_perception REQUIRED)
find_package(moveit_servo REQUIRED)
find_package(geometric_shapes REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(pluginlib REQUIRED)
find_package(tf2_ros REQUIRED)
find_package(tf2_eigen REQUIRED)
find_package(tf2_geometry_msgs REQUIRED)
find_package(rviz_visual_tools REQUIRED)

set(THIS_PACKAGE_INCLUDE_DEPENDS
  ament_cmake
  rclcpp
  rclcpp_action
  tf2_geometry_msgs
  tf2_ros
  moveit_core
  moveit_ros_planning_interface
  tf2_geometry_msgs
  moveit_ros_planning
  pluginlib
  Eigen3
  Boost
  control_msgs
  moveit_servo
  rviz_visual_tools
)

add_executable(servo_keyboard_input src/servo_keyboard_input.cpp)
target_include_directories(servo_keyboard_input PUBLIC include)
ament_target_dependencies(servo_keyboard_input  ${THIS_PACKAGE_INCLUDE_DEPENDS})

add_executable(pose_tracking_demo src/pose_tracking_demo.cpp)
target_link_libraries(pose_tracking_demo ${POSE_TRACKING})
ament_target_dependencies(pose_tracking_demo ${THIS_PACKAGE_INCLUDE_DEPENDS})

add_executable(virtual_object_pub src/virtual_object_pub.cpp)
target_link_libraries(virtual_object_pub ${POSE_TRACKING})
ament_target_dependencies(virtual_object_pub ${THIS_PACKAGE_INCLUDE_DEPENDS})

add_executable(vision_object_pub src/vision_object_pub.cpp)
target_link_libraries(vision_object_pub ${POSE_TRACKING})
ament_target_dependencies(vision_object_pub ${THIS_PACKAGE_INCLUDE_DEPENDS})

add_executable(servo_server_node src/servo_server_node.cpp)
target_link_libraries(servo_server_node ${POSE_TRACKING})
ament_target_dependencies(servo_server_node ${THIS_PACKAGE_INCLUDE_DEPENDS})

install(
  TARGETS
    servo_keyboard_input pose_tracking_demo virtual_object_pub vision_object_pub servo_server_node
  DESTINATION
    lib/${PROJECT_NAME}
)

install(DIRECTORY config
  DESTINATION share/${PROJECT_NAME}
)

ament_export_dependencies(
  ${THIS_PACKAGE_INCLUDE_DEPENDS}
)

ament_export_include_directories(include)

ament_package()