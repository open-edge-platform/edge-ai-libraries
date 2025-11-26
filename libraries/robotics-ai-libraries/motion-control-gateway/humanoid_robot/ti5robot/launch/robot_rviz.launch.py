#!/usr/bin/env python3

import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch.conditions import IfCondition, UnlessCondition

def generate_launch_description():
    # Package name
    package_name = 'robot_rviz'
    
    # Paths
    pkg_share = FindPackageShare(package=package_name).find(package_name)
    urdf_file = os.path.join(pkg_share, 'urdf', 'ti5.urdf')
    rviz_config_file = os.path.join(pkg_share, 'rviz', 'urdf.rviz')
    
    # Read URDF file
    with open(urdf_file, 'r') as infp:
        robot_description_content = infp.read()
    
    # Robot State Publisher
    robot_state_publisher_node = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{
            'robot_description': robot_description_content
        }]
    )
    
    # Robot joint state aggregator node
    robot_joint_state_aggregator_node = Node(
        package=package_name,
        executable='robot_joint_state_aggregator_node',
        name='robot_joint_state_aggregator_node',
        output='screen',
        parameters=[{'publish_rate': 100}]
    )

    # Robot arm shm node
    robot_arm_shm_node = Node(
        package=package_name,
        executable='robot_arm_shm_node',
        name='robot_arm_shm_node',
        output='screen',
        parameters=[{'publish_rate': 100}]
    )

    # Robot leg shm node
    robot_leg_shm_node = Node(
        package=package_name,
        executable='robot_leg_shm_node',
        name='robot_leg_shm_node',
        output='screen',
        parameters=[{'publish_rate': 100}]
    )

    # RViz
    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        arguments=['-d', rviz_config_file] if os.path.exists(rviz_config_file) else [],
    )
    
    # Create launch description
    ld = LaunchDescription()
    
    # Add nodes
    ld.add_action(robot_joint_state_aggregator_node)
    ld.add_action(robot_arm_shm_node)
    ld.add_action(robot_leg_shm_node)

    ld.add_action(robot_state_publisher_node)
    ld.add_action(rviz_node)
    
    return ld
