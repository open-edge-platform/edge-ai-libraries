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
            robot_name="jaka_zu3", package_name="jaka_moveit_config"
        )
        .robot_description(file_path=get_package_share_directory("jaka_description")
            + "/urdf/jaka_system_can.urdf.xacro")
        .robot_description_semantic(file_path=get_package_share_directory("jaka_moveit_config")
            + "/config/jaka_zu3.srdf")
        .robot_description_kinematics(file_path=get_package_share_directory("jaka_moveit_config")
            + "/config/kinematics.yaml")
        .planning_pipelines(pipelines=["ompl"], default_planning_pipeline="ompl")
        .trajectory_execution(file_path=get_package_share_directory("jaka_moveit_py")
            + "/config/moveit_controllers.yaml")
        .joint_limits(file_path=get_package_share_directory("jaka_moveit_config")
            + "/config/joint_limits.yaml")
        .moveit_cpp(file_path=get_package_share_directory("jaka_moveit_py")
            + "/config/moveit_py.yaml")
#        .pilz_cartesian_limits(file_path=get_package_share_directory("jaka_moveit_config")
#            + "/config/pilz_cartesian_limits.yaml")
        .to_moveit_configs()
    )

    # moveit_py
    moveit_py_node = Node(
        name="moveit_py",
        package="jaka_moveit_py",
        executable="jaka_motion_planning",
        output="screen",
        parameters=[moveit_config.to_dict()],
    )

    #rviz
    rviz_config_file = (
        get_package_share_directory("jaka_moveit_py") + "/launch/run_jaka_moveit.rviz"
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

    ros2_controllers_path = os.path.join(
        get_package_share_directory("jaka_moveit_py"),
        "config",
        "jaka_controllers.yaml",
    )
    ros2_control_node = Node(
        package="controller_manager",
        executable="ros2_control_node",
        parameters=[ros2_controllers_path],
        remappings=[
            ("/controller_manager/robot_description", "/robot_description"),
        ],
        output="both",
    )

    load_controllers = []
    for controller in [
        "joint_state_broadcaster",
        "joint_trajectory_controller",
    ]:
        load_controllers += [
            ExecuteProcess(
                cmd=["ros2 run controller_manager spawner {}".format(controller)],
                shell=True,
                output="screen",
            )
        ]

    return LaunchDescription(
        [
            robot_state_publisher,
            rviz_node,
            static_tf,
            moveit_py_node,
            ros2_control_node,
        ]
        + load_controllers
    )
