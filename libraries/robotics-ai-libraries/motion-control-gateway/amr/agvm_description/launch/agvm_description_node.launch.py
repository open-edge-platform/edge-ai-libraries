# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http:#www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions
# and limitations under the License.

import launch
import launch.actions
from launch.substitutions import LaunchConfiguration
import launch_ros.actions
from ament_index_python.packages import get_package_share_directory

def generate_launch_description():
    agvm_description_path = get_package_share_directory('agvm_description')
    urdf_path = agvm_description_path + '/urdf/agvm.urdf'
    return launch.LaunchDescription([
        launch_ros.actions.Node(
            package='robot_state_publisher', 
            node_executable='robot_state_publisher', 
            node_name='robot_state_publisher', 
            output='screen',
            arguments=[urdf_path],
         ),
         
        launch_ros.actions.Node(
            package='joint_state_publisher', 
            node_executable='joint_state_publisher', 
            node_name='joint_state_publisher', 
            output='screen',
            arguments=[urdf_path],
         ),
    ])
