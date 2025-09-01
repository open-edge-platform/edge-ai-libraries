# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
include_directories(
  include
  # /opt/intel/oneapi/vtune/latest/sdk/include
)

# Create demo executables
add_executable(symg_servo_test symg_servo_test.cpp)
target_link_libraries(symg_servo_test 
  ${PROJECT_NAME}_symg
  ${RTMOTION_LIBRARIES}
  ${ETHERCAT_LIBRARIES}
  pthread
)

install(TARGETS symg_servo_test
  DESTINATION ${INSTALL_BINDIR}
)

add_executable(solo_mc_move_absolute solo_mc_move_absolute.cpp)
target_link_libraries(solo_mc_move_absolute
  ${PROJECT_NAME}
  ${RTMOTION_LIBRARIES}
  ${ENABLEKIT_LIBRARIES}
  ruckig::ruckig
  pthread
)

add_executable(solo_mc_move_relative solo_mc_move_relative.cpp)
target_link_libraries(solo_mc_move_relative
  ${PROJECT_NAME}
  ${RTMOTION_LIBRARIES}
  ${ENABLEKIT_LIBRARIES}
  ruckig::ruckig
  pthread
)

add_executable(solo_mc_move_additive solo_mc_move_additive.cpp)
target_link_libraries(solo_mc_move_additive
  ${PROJECT_NAME}
  ${RTMOTION_LIBRARIES}
  ${ENABLEKIT_LIBRARIES}
  ruckig::ruckig
  pthread
)

add_executable(solo_mc_move_velocity solo_mc_move_velocity.cpp)
target_link_libraries(solo_mc_move_velocity
  ${PROJECT_NAME}
  ${RTMOTION_LIBRARIES}
  ${ENABLEKIT_LIBRARIES}
  ruckig::ruckig
  pthread
)

add_executable(solo_mc_power_demo solo_mc_power_demo.cpp)
target_link_libraries(solo_mc_power_demo
  ${PROJECT_NAME}
  ${RTMOTION_LIBRARIES}
  ${ENABLEKIT_LIBRARIES}
  ruckig::ruckig
  pthread
)

add_executable(solo_mc_stop_demo solo_mc_stop_demo.cpp)
target_link_libraries(solo_mc_stop_demo
  ${PROJECT_NAME}
  ${RTMOTION_LIBRARIES}
  ${ENABLEKIT_LIBRARIES}
  ruckig::ruckig
  pthread
)

add_executable(solo_mc_torque_control solo_mc_torque_control.cpp)
target_link_libraries(solo_mc_torque_control
  ${PROJECT_NAME}
  ${RTMOTION_LIBRARIES}
  ${ENABLEKIT_LIBRARIES}
  ruckig::ruckig
  pthread
)

add_executable(solo_mc_home_demo solo_mc_home_demo.cpp)
target_link_libraries(solo_mc_home_demo
  ${PROJECT_NAME}
  ${RTMOTION_LIBRARIES}
  ${ENABLEKIT_LIBRARIES}
  ruckig::ruckig
  pthread
)

add_executable(solo_mc_homing_demo solo_mc_homing_demo.cpp)
target_link_libraries(solo_mc_homing_demo
  ${PROJECT_NAME}
  ${RTMOTION_LIBRARIES}
  ${ENABLEKIT_LIBRARIES}
  ruckig::ruckig
  pthread
)

add_executable(solo_mc_jog_demo solo_mc_jog_demo.cpp)
target_link_libraries(solo_mc_jog_demo
  ${PROJECT_NAME}
  ${RTMOTION_LIBRARIES}
  ${ENABLEKIT_LIBRARIES}
  ruckig::ruckig
  pthread
)

add_executable(solo_mc_override_demo solo_mc_override_demo.cpp)
target_link_libraries(solo_mc_override_demo
  ${PROJECT_NAME}
  ${RTMOTION_LIBRARIES}
  ${ENABLEKIT_LIBRARIES}
  ruckig::ruckig
  pthread
)

add_executable(solo_mc_digital_cam_switch solo_mc_digital_cam_switch.cpp)
target_link_libraries(solo_mc_digital_cam_switch
${PROJECT_NAME}
${RTMOTION_LIBRARIES}
${ENABLEKIT_LIBRARIES}
ruckig::ruckig
pthread
)

add_executable(solo_mc_move_superimposed_demo solo_mc_move_superimposed_demo.cpp)
target_link_libraries(solo_mc_move_superimposed_demo
  ${PROJECT_NAME}
  ${RTMOTION_LIBRARIES}
  ${ENABLEKIT_LIBRARIES}
  ruckig::ruckig
  pthread
)

add_executable(duo_rtmotion_demo duo_rtmotion_demo.cpp)
target_link_libraries(duo_rtmotion_demo
  ${PROJECT_NAME}
  ${RTMOTION_LIBRARIES}
  ${ENABLEKIT_LIBRARIES}
  ruckig::ruckig
  pthread
)

add_executable(duo_rtmotion_cam_demo duo_rtmotion_cam_demo.cpp)
target_link_libraries(duo_rtmotion_cam_demo
  ${PROJECT_NAME}
  ${RTMOTION_LIBRARIES}
  ${ENABLEKIT_LIBRARIES}
  ruckig::ruckig
  pthread
)

add_executable(duo_rtmotion_gear_demo duo_rtmotion_gear_demo.cpp)
target_link_libraries(duo_rtmotion_gear_demo
  ${PROJECT_NAME}
  ${RTMOTION_LIBRARIES}
  ${ENABLEKIT_LIBRARIES}
  ruckig::ruckig
  pthread
)

add_executable(duo_rtmotion_gear_in_pos_demo duo_rtmotion_gear_in_pos_demo.cpp)
target_link_libraries(duo_rtmotion_gear_in_pos_demo
  ${PROJECT_NAME}
  ${RTMOTION_LIBRARIES}
  ${ENABLEKIT_LIBRARIES}
  ruckig::ruckig
  pthread
)

add_executable(six_rtmotion_demo six_rtmotion_demo.cpp)
target_link_libraries(six_rtmotion_demo
  ${PROJECT_NAME}
  ${RTMOTION_LIBRARIES}
  ${ENABLEKIT_LIBRARIES}
  ruckig::ruckig
  pthread
  #-lpthread
  #-ldl /opt/intel/oneapi/vtune/latest/sdk/lib64/libittnotify.a
)

# add_executable(symg_servo_rtmotion_test symg_servo_rtmotion_test.cpp)
# target_link_libraries(symg_servo_rtmotion_test
#   ${PROJECT_NAME}_symg
#   ${RTMOTION_LIBRARIES}
#   ${ETHERCAT_LIBRARIES}
#   pthread
# )

# EtherCAT IO test
add_executable(ethercat_io_demo ethercat_io_demo.cpp)
target_link_libraries(ethercat_io_demo
  ${PROJECT_NAME}_io
  ${RTMOTION_LIBRARIES}
  ${ETHERCAT_LIBRARIES}
  ${ENABLEKIT_LIBRARIES}
  pthread
)

install(TARGETS 
  solo_mc_move_absolute
  solo_mc_move_relative
  solo_mc_move_additive
  solo_mc_move_velocity
  solo_mc_power_demo
  solo_mc_stop_demo
  solo_mc_torque_control
  solo_mc_home_demo
  solo_mc_homing_demo
  solo_mc_jog_demo
  solo_mc_digital_cam_switch
  solo_mc_move_superimposed_demo
  solo_mc_override_demo
  duo_rtmotion_demo
  duo_rtmotion_gear_demo
  duo_rtmotion_cam_demo
  duo_rtmotion_gear_in_pos_demo
  six_rtmotion_demo
  ethercat_io_demo
  DESTINATION ${INSTALL_BINDIR}
)

install(
  DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/ENI/
  DESTINATION ${INSTALL_BINDIR}
  FILES_MATCHING PATTERN "*.xml"
  PATTERN "*.cpp" EXCLUDE
  PATTERN "*.txt" EXCLUDE
)
