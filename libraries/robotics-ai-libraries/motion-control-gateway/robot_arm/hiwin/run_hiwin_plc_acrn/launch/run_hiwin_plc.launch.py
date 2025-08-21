# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
import os
import yaml
from launch import LaunchDescription
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory

def load_file(package_name, file_path):
    package_path = get_package_share_directory(package_name)
    absolute_file_path = os.path.join(package_path, file_path)
    print(absolute_file_path)

    try:
        with open(absolute_file_path, 'r') as file:
            return file.read()
    except EnvironmentError: # parent of IOError, OSError *and* WindowsError where available
        return None

def load_yaml(package_name, file_path):
    package_path = get_package_share_directory(package_name)
    absolute_file_path = os.path.join(package_path, file_path)
    print(absolute_file_path)

    try:
        with open(absolute_file_path, 'r') as file:
            return yaml.safe_load(file)
    except EnvironmentError: # parent of IOError, OSError *and* WindowsError where available
        return None


def generate_launch_description():
    # # moveit_cpp.yaml is passed by filename for now since it's node specific
    moveit_cpp_yaml_file_name = get_package_share_directory('run_hiwin_moveit') + "/config/moveit_cpp.yaml"

    # Component yaml files are grouped in separate namespaces
    robot_description_config = load_file('hiwin_robot_moveit_config', 'xacros/hiwin_robot_and_gripper.urdf')
    robot_description = {'robot_description' : robot_description_config}

    robot_description_semantic_config = load_file('hiwin_robot_moveit_config', 'srdf/hiwin_robot.srdf')
    robot_description_semantic = {'robot_description_semantic' : robot_description_semantic_config}

    kinematics_yaml = load_yaml('hiwin_robot_moveit_config', 'config/kinematics.yaml')
    robot_description_kinematics = { 'robot_description_kinematics' : kinematics_yaml }

    controllers_yaml = load_yaml('run_hiwin_moveit', 'config/controllers.yaml')
    moveit_controllers = { 'moveit_simple_controller_manager' : controllers_yaml, 
                           'moveit_controller_manager': 'moveit_simple_controller_manager/MoveItSimpleControllerManager'}

    ompl_planning_pipeline_config = { 'ompl' : {
        'planning_plugin' : 'ompl_interface/OMPLPlanner',
        'request_adapters' : """default_planner_request_adapters/AddTimeOptimalParameterization default_planner_request_adapters/FixWorkspaceBounds default_planner_request_adapters/FixStartStateBounds default_planner_request_adapters/FixStartStateCollision default_planner_request_adapters/FixStartStatePathConstraints""" ,
        'start_state_max_bounds_error' : 0.1 } }
    ompl_planning_yaml = load_yaml('hiwin_robot_moveit_config', 'config/ompl_planning.yaml')
    ompl_planning_pipeline_config['ompl'].update(ompl_planning_yaml)

    # # MoveItCpp demo executable
    run_hiwin_moveit_node = Node(name='run_hiwin_moveit',
                                 package='run_hiwin_moveit',
                                 # TODO(henningkayser): add debug argument
                                 # prefix='xterm -e gdb --args',
                                 executable='run_hiwin_moveit',
                                 output='screen',
                                 parameters=[moveit_cpp_yaml_file_name,
                                             robot_description,
                                             robot_description_semantic,
                                             kinematics_yaml,
                                             ompl_planning_pipeline_config,
                                             moveit_controllers])

    # RViz
    rviz_config_file = get_package_share_directory('run_hiwin_moveit') + "/launch/run_hiwin_moveit.rviz"
    rviz_node = Node(package='rviz2',
                     executable='rviz2',
                     name='rviz2',
                     output='log',
                     arguments=['-d', rviz_config_file],
                     parameters=[robot_description])

    # Publish base link TF
    static_tf = Node(package='tf2_ros',
                     executable='static_transform_publisher',
                     name='static_transform_publisher',
                     output='log',
                     arguments=['0.0', '0.0', '0.0', '0.0', '0.0', '0.0', 'world', 'manipulator/base_link'])

    # Publish TF
    robot_state_publisher = Node(package='robot_state_publisher',
                                 executable='robot_state_publisher',
                                 name='robot_state_publisher',
                                 output='both',
                                 parameters=[robot_description])

    return LaunchDescription([ robot_state_publisher, static_tf, rviz_node, run_hiwin_moveit_node])
