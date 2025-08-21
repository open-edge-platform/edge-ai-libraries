# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
cmake_minimum_required(VERSION 3.10.2)
project(jaka_description)

find_package(ament_cmake REQUIRED)

install(DIRECTORY launch urdf meshes cfg ros2_control DESTINATION share/${PROJECT_NAME})

ament_package()