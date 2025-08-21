# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
cmake_minimum_required(VERSION 3.10.2)
project(hiwin_ra605_710_gb_support)

find_package(ament_cmake REQUIRED)

install(DIRECTORY launch urdf meshes cfg DESTINATION share/${PROJECT_NAME})

ament_package()