# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
import launch
import launch.actions
from launch.substitutions import LaunchConfiguration
import launch_ros.actions

def generate_launch_description():
    return launch.LaunchDescription([
        launch_ros.actions.Node(
            package='ydlidar', 
            node_executable='ydlidar_node', 
            node_name='ydlidar_node_front', 
            output='screen',
			parameters=[
				{'frame_id': 'base_scan'},
				{'port' : '/dev/ttyUSB0'}, 
				{'baudrate' : 230400},
				{'angle_fixed' : True},
				{'low_exposure' : False},
				{'heartbeat' : False},
				{'resolution_fixed' : True},
				{'angle_min' : -180.0},
				{'angle_max' : 180.0},
				{'ignore_array' : '-151, -143, -37, -24, 29, 37, 143, 151'},
				{'range_min' : 0.1},
				{'range_max' : 10.0},
				{'samp_rate' : 9},
				{'frequency' : 12.0},
			],
         ),
    ])
