# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
add_executable(plcopen_benchmark plcopen_benchmark.cpp)
target_link_libraries(plcopen_benchmark
  ${PROJECT_NAME}_tool
  ${RTMOTION_LIBRARIES}
  ${SERVO_LIBRARIES}
  ${ENABLEKIT_LIBRARIES}
  pthread
)

install(TARGETS 
  plcopen_benchmark
  DESTINATION ${INSTALL_BINDIR}
)
