# Copyright 2021 Open Robotics (2021)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.actions import ExecuteProcess, DeclareLaunchArgument, RegisterEventHandler
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.substitutions import Command, FindExecutable, PathJoinSubstitution, LaunchConfiguration
from launch.launch_description_sources import PythonLaunchDescriptionSource

from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare

import xacro
import yaml


def load_file(package_name, file_path):
    package_path = get_package_share_directory(package_name)
    absolute_file_path = os.path.join(package_path, file_path)
    try:
        with open(absolute_file_path, 'r') as file:
            return file.read()
    except EnvironmentError:
        # parent of IOError, OSError *and* WindowsError where available
        return None


def load_yaml(package_name, file_path):
    package_path = get_package_share_directory(package_name)
    absolute_file_path = os.path.join(package_path, file_path)
    try:
        with open(absolute_file_path, 'r') as file:
            return yaml.safe_load(file)
    except EnvironmentError:
        # parent of IOError, OSError *and* WindowsError where available
        return None


def generate_launch_description():
    # moveit_cpp.yaml is passed by filename for now since it's node specific
    moveit_cpp_yaml_file_name = os.path.join(
        get_package_share_directory('run_jaka_moveit'),
        'config',
        'moveit_cpp.yaml')

    jaka_description_path = os.path.join(
        get_package_share_directory('jaka_description'))

    xacro_file = os.path.join(jaka_description_path,
                              'urdf',
                              'jaka_system_can.urdf.xacro')

    doc = xacro.parse(open(xacro_file))
    xacro.process_doc(doc)
    robot_description_config = doc.toxml()
    robot_description = {'robot_description': robot_description_config}

    robot_description_semantic_config = load_file('jaka_moveit_config',
                                                  os.path.join('config', 'jaka_zu3.srdf'))
    robot_description_semantic = {'robot_description_semantic': robot_description_semantic_config}

    kinematics_yaml = load_yaml('jaka_moveit_config',
                                os.path.join('config', 'kinematics.yaml'))

    controllers_yaml = load_yaml('run_jaka_moveit',
                                 os.path.join('config', 'moveit_controllers.yaml'))
    moveit_controllers = {'moveit_simple_controller_manager': controllers_yaml,
                          'moveit_controller_manager':
                          'moveit_simple_controller_manager/MoveItSimpleControllerManager'
                          }

    ompl_planning_pipeline_config = { 'ompl' : {
        'planning_plugin' : 'ompl_interface/OMPLPlanner',
        'request_adapters' : """default_planner_request_adapters/AddTimeOptimalParameterization default_planner_request_adapters/FixWorkspaceBounds default_planner_request_adapters/FixStartStateBounds default_planner_request_adapters/FixStartStateCollision default_planner_request_adapters/FixStartStatePathConstraints""" ,
        'start_state_max_bounds_error' : 0.1 } }
    ompl_planning_yaml = load_yaml('jaka_moveit_config', 'config/ompl_planning.yaml')
    ompl_planning_pipeline_config['ompl'].update(ompl_planning_yaml)

    joint_limits_yaml = {
    "robot_description_planning": load_yaml(
        "jaka_moveit_config", "config/joint_limits.yaml"
    )
    }

    # MoveItCpp demo executable
    run_moveit_cpp_node = Node(name='run_jaka_moveit',
                               package='run_jaka_moveit',
                               # TODO(henningkayser): add debug argument
                               # prefix='xterm -e gdb --args',
                               executable='run_moveit_cpp',
                               output='screen',
                               parameters=[moveit_cpp_yaml_file_name,
                                           robot_description,
                                           robot_description_semantic,
                                           kinematics_yaml,
                                           ompl_planning_pipeline_config,
                                           moveit_controllers,
                                           joint_limits_yaml])

    # RViz
    rviz_config_file = os.path.join(
        get_package_share_directory('run_jaka_moveit'), 'launch', 'run_jaka_moveit.rviz')
    rviz_node = Node(package='rviz2',
                     executable='rviz2',
                     name='rviz2',
                     output='log',
                     arguments=['-d', rviz_config_file],
                     parameters=[robot_description,
                                 robot_description_semantic])

    # Publish base link TF
    static_tf = Node(package='tf2_ros',
                     executable='static_transform_publisher',
                     name='static_transform_publisher',
                     output='log',
                     arguments=['0.0', '0.0', '0.0', '0.0', '0.0', '0.0', 'world', 'base_link'])
    
    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        name="robot_state_publisher",
        output="both",
        parameters=[robot_description],
    )

    # ros2_control using FakeSystem as hardware
    ros2_controllers_path = os.path.join(
        get_package_share_directory("jaka_bringup"),
        "config",
        "jaka_controllers.yaml",
    )

    ros2_control_node = Node(
        package="controller_manager",
        executable="ros2_control_node",
        parameters=[robot_description, ros2_controllers_path],
        output={
            "stdout": "screen",
            "stderr": "screen",
        },
    )

    joint_state_broadcaster_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["joint_state_broadcaster", "--controller-manager", "/controller_manager"],
    )

    robot_controller_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["joint_trajectory_controller", "--controller-manager", "/controller_manager"],
    )

    # Delay rviz start after `joint_state_broadcaster`
    delay_rviz_after_joint_state_broadcaster_spawner = RegisterEventHandler(
        event_handler=OnProcessExit(
            target_action=joint_state_broadcaster_spawner,
            on_exit=[rviz_node],
        )
    )

    # Delay start of robot_controller after `joint_state_broadcaster`
    delay_robot_controller_spawner_after_joint_state_broadcaster_spawner = RegisterEventHandler(
        event_handler=OnProcessExit(
            target_action=joint_state_broadcaster_spawner,
            on_exit=[robot_controller_spawner],
        )
    )

    nodes = [
        robot_state_publisher,
        rviz_node,
        static_tf,
        run_moveit_cpp_node,
        ros2_control_node,
        joint_state_broadcaster_spawner,
        delay_robot_controller_spawner_after_joint_state_broadcaster_spawner,
    ]

    return LaunchDescription(nodes)
