# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
include_directories(
    ${CMAKE_CURRENT_SOURCE_DIR}/../mc
    ${CMAKE_CURRENT_SOURCE_DIR}/../mc/ectask
    ${CMAKE_CURRENT_SOURCE_DIR}/../mc/inference
)

add_executable(mc_rl_sample mc_rl_sample.cpp)
target_link_libraries(mc_rl_sample
  ${RTMOTION_LIBRARIES}
  ${SERVO_LIBRARIES}
  ${ENABLEKIT_LIBRARIES}
  ectask
  mc_inference
  -lpthread
)

