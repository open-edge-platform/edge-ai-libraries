# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
import os
from launch import LaunchDescription
from launch_ros.actions import Node, SetParameter
from launch.actions import ExecuteProcess
from ament_index_python.packages import get_package_share_directory
from moveit_configs_utils import MoveItConfigsBuilder

def generate_launch_description():
    moveit_config = (
        MoveItConfigsBuilder(
            robot_name="hiwin_robot", package_name="hiwin_robot_moveit_config"
        )
        .robot_description(file_path=get_package_share_directory("hiwin_robot_moveit_config")
            + "/xacros/hiwin_robot_and_gripper.urdf")
        .robot_description_semantic(file_path=get_package_share_directory("hiwin_robot_moveit_config")
            + "/srdf/hiwin_robot.srdf")
        .robot_description_kinematics(file_path=get_package_share_directory("hiwin_robot_moveit_config")
            + "/config/kinematics.yaml")
        .planning_pipelines(pipelines=["ompl"], default_planning_pipeline="ompl")
        .trajectory_execution(file_path=get_package_share_directory("hiwin_moveit_py")
            + "/config/moveit_controllers.yaml")
        .joint_limits(file_path=get_package_share_directory("hiwin_robot_moveit_config")
            + "/config/joint_limits.yaml")
        .moveit_cpp(file_path=get_package_share_directory("hiwin_moveit_py")
            + "/config/moveit_py.yaml")
        .to_moveit_configs()
    )

    # moveit_py
    moveit_py_node = Node(
        name="moveit_py",
        package="hiwin_moveit_py",
        executable="hiwin_motion_planning",
        output="screen",
        parameters=[moveit_config.to_dict()],
    )

    #rviz
    rviz_config_file = (
        get_package_share_directory("hiwin_moveit_py") + "/launch/run_hiwin_moveit.rviz"
    )
    rviz_node = Node(
        package="rviz2",
        executable="rviz2",
        name="rviz2",
        output="log",
        arguments=["-d", rviz_config_file],
        parameters=[
            moveit_config.robot_description,
            moveit_config.robot_description_semantic,
        ],
    )

    # Publish base link TF
    static_tf = Node(
        package="tf2_ros",
        executable="static_transform_publisher",
        name="static_transform_publisher",
        output="log",
        arguments=["0.0", "0.0", "0.0", "0.0", "0.0", "0.0", "world", "base_link"],
    )

    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        name="robot_state_publisher",
        output="both",
        parameters=[moveit_config.robot_description],
    )

    # run_hiwin_plc node
    run_hiwin_plc_node = Node(name='run_hiwin_plc',
                              package='run_hiwin_plc',
                              executable='run_hiwin_plc',
                              output='log')

    return LaunchDescription(
        [
            robot_state_publisher,
            rviz_node,
            static_tf,
            moveit_py_node,
            run_hiwin_plc_node,
        ]
    )
