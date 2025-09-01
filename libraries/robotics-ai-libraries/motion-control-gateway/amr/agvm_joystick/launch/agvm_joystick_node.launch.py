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

def generate_launch_description():
    return launch.LaunchDescription([
        launch_ros.actions.Node(
            package='agvm_joystick', 
            node_executable='agvm_joystick_node', 
            node_name='agvm_joystick_node', 
            output='screen',
            parameters=[
				{'agvm_joystick_devpath': '/dev/input/js0'},
				{'agvm_joystick_maxlinvel': 0.6},
				{'agvm_joystick_maxrotvel': 1.0},
				{'agvm_joystick_safevelrate': 0.5},
			]
         )
    ])
