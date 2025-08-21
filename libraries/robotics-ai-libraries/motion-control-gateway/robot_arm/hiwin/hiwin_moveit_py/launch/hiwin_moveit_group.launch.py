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
from launch_ros.actions import Node
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.actions import ExecuteProcess
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
#        .moveit_cpp(file_path=get_package_share_directory("jaka_moveit_py")
#            + "/config/moveit_py.yaml")
#        .pilz_cartesian_limits(file_path=get_package_share_directory("jaka_moveit_config")
#            + "/config/pilz_cartesian_limits.yaml")
        .to_moveit_configs()
    )

    # Start the actual move_group node/action server
    move_group_node = Node(
        package="moveit_ros_move_group",
        executable="move_group",
        output="screen",
        parameters=[moveit_config.to_dict()],
    )

    # RViz
    rviz_config_file = os.path.join(
        get_package_share_directory('hiwin_moveit_py'), 'launch', 'run_move_group.rviz')
    rviz_node = Node(package='rviz2',
                     executable='rviz2',
                     name='rviz2',
                     output='log',
                     arguments=['-d', rviz_config_file],
                     parameters=[moveit_config.robot_description,
                                 moveit_config.robot_description_semantic,
                                 moveit_config.robot_description_kinematics,
                                 moveit_config.planning_pipelines,
                                 moveit_config.joint_limits,
                                 ])

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
            move_group_node,
            run_hiwin_plc_node,
        ]
    )
