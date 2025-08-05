# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
add_executable(plc_rt_robot_arm plc_rt_robot_arm.cpp)
target_link_libraries(plc_rt_robot_arm ${LIBSHM_LIBRARIES} -lpthread)

add_executable(plc_rt_pos_rtmotion plc_rt_pos_rtmotion.cpp)
target_link_libraries(plc_rt_pos_rtmotion ${RTMOTION_LIBRARIES} ${LIBSHM_LIBRARIES} ruckig::ruckig -lpthread)

add_executable(plc_rt_amr plc_rt_amr.cpp)
target_link_libraries(plc_rt_amr ${LIBSHM_LIBRARIES} -lpthread)

install(TARGETS plc_rt_robot_arm plc_rt_amr plc_rt_pos_rtmotion
  RUNTIME DESTINATION ${INSTALL_BINDIR}
)

# Create samples with RTmotion library
add_executable(plc_rt_robot_arm_rtmotion plc_rt_robot_arm_rtmotion.cpp)
target_link_libraries(plc_rt_robot_arm_rtmotion ${RTMOTION_LIBRARIES} ${SERVO_LIBRARIES} ${ENABLEKIT_LIBRARIES}  ${LIBSHM_LIBRARIES} ruckig::ruckig -lpthread)

add_executable(plc_rt_amr_rtmotion plc_rt_amr_rtmotion.cpp)
target_link_libraries(plc_rt_amr_rtmotion ${RTMOTION_LIBRARIES} ${LIBSHM_LIBRARIES} ruckig::ruckig -lpthread)

add_executable(plc_rt_rrbot plc_rt_rrbot.cpp)
target_link_libraries(plc_rt_rrbot ${RTMOTION_LIBRARIES} ${LIBSHM_LIBRARIES} ${PYTHON_LIBRARIES} ruckig::ruckig -lpthread)

add_executable(plc_rt_rrbot_igh plc_rt_rrbot_igh.cpp)
target_link_libraries(plc_rt_rrbot_igh ${RTMOTION_LIBRARIES} ${SERVO_LIBRARIES} ${ENABLEKIT_LIBRARIES} ${LIBSHM_LIBRARIES} ruckig::ruckig -lpthread)

install(TARGETS plc_rt_robot_arm_rtmotion plc_rt_amr_rtmotion plc_rt_rrbot plc_rt_rrbot_igh
  RUNTIME DESTINATION ${INSTALL_BINDIR}
)

# Create PLC programs for SYMG AMR
add_executable(plc_rt_amr_rtmotion_symg plc_rt_amr_rtmotion_symg.cpp)
target_compile_options(plc_rt_amr_rtmotion_symg PRIVATE -Wno-unused-but-set-variable)
target_link_libraries(plc_rt_amr_rtmotion_symg
  ${RTMOTION_LIBRARIES}
  ${LIBSHM_LIBRARIES}
  ${SYMG_SERVO_LIBRARIES}
  ${ETHERCAT_LIBRARIES}
  ruckig::ruckig
  -lpthread
)
install(TARGETS plc_rt_amr_rtmotion_symg
  RUNTIME DESTINATION ${INSTALL_BINDIR}
)
