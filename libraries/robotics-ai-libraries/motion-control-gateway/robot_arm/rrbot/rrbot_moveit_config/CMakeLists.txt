# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
cmake_minimum_required(VERSION 3.10.2)
project(rrbot_moveit_config)
find_package(ament_cmake REQUIRED)

ament_package()

install(DIRECTORY config DESTINATION share/${PROJECT_NAME})
