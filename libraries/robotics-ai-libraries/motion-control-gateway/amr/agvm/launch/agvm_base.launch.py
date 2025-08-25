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
import launch_ros.actions
from ament_index_python.packages import get_package_share_directory

def generate_launch_description():
    return launch.LaunchDescription([
        launch.actions.IncludeLaunchDescription(
            launch.launch_description_sources.PythonLaunchDescriptionSource(
                get_package_share_directory('agvm_description') + '/launch/agvm_description_node.launch.py')),
                
        launch.actions.IncludeLaunchDescription(
            launch.launch_description_sources.PythonLaunchDescriptionSource(
                get_package_share_directory('agvm_plcshm') + '/launch/agvm_plcshm_node.launch.py')),
                
        launch.actions.IncludeLaunchDescription(
            launch.launch_description_sources.PythonLaunchDescriptionSource(
                get_package_share_directory('agvm_joystick') + '/launch/agvm_joystick_node.launch.py')),
                
        launch.actions.IncludeLaunchDescription(
            launch.launch_description_sources.PythonLaunchDescriptionSource(
                get_package_share_directory('ydlidar') + '/launch/ydlidar.py')),
    ])

'''
launch.actions.IncludeLaunchDescription(
	launch.launch_description_sources.PythonLaunchDescriptionSource(
		get_package_share_directory('ira_laser_tools') + '/launch/laserscan_multi_merger.launch.py')),
                
<launch>
  <include file="$(find agvm_description)/launch/agvm_description_node.launch"/>
  <include file="$(find agvm_plcshm)/launch/agvm_plcshm_node.launch"/>
  <include file="$(find agvm_joystick)/launch/agvm_joystick_node.launch"/>
  <include file="$(find ydlidar)/launch/lidar.launch"/>
</launch>
'''
