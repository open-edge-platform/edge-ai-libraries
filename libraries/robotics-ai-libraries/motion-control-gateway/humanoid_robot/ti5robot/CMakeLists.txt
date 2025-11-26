cmake_minimum_required(VERSION 3.8)
project(robot_rviz)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# Find shmringbuf
find_path(
    PLCOPEN_CMAKE_MODULE_PATH
    NAMES find_libshm.cmake
    HINTS ${ROOTDIR}/usr/include ${ROOTDIR}/usr/local/include
)
message(STATUS "PLCOPEN_CMAKE_MODULE_PATH: ${PLCOPEN_CMAKE_MODULE_PATH}")
include(${PLCOPEN_CMAKE_MODULE_PATH}/find_libshm.cmake)

include_directories(
    ${LIBSHM_INCLUDE_DIRS}
)

# Find dependencies
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(urdf REQUIRED)

find_package(trajectory_msgs REQUIRED)

# Create executable
# add_executable(robot_rviz_node src/robot_rviz_node.cpp)
# ament_target_dependencies(robot_rviz_node rclcpp sensor_msgs urdf)

add_executable(robot_joint_state_aggregator_node src/robot_joint_state_aggregator_node.cpp)
ament_target_dependencies(robot_joint_state_aggregator_node rclcpp sensor_msgs trajectory_msgs)

add_executable(robot_arm_shm_node src/robot_arm_shm_node.cpp)
ament_target_dependencies(robot_arm_shm_node rclcpp sensor_msgs trajectory_msgs)
target_link_libraries(robot_arm_shm_node ${LIBSHM_LIBRARIES})

add_executable(robot_leg_shm_node src/robot_leg_shm_node.cpp)
ament_target_dependencies(robot_leg_shm_node rclcpp sensor_msgs trajectory_msgs)
target_link_libraries(robot_leg_shm_node ${LIBSHM_LIBRARIES})

# Install targets
install(TARGETS
   robot_joint_state_aggregator_node
   DESTINATION lib/${PROJECT_NAME})
 
install(TARGETS
   robot_arm_shm_node
   DESTINATION lib/${PROJECT_NAME})

install(TARGETS
   robot_leg_shm_node
   DESTINATION lib/${PROJECT_NAME})

# install(TARGETS
#  robot_rviz_node
#  DESTINATION lib/${PROJECT_NAME})

# Install directories
install(DIRECTORY
  launch
  urdf
  meshes
  rviz
  DESTINATION share/${PROJECT_NAME}/
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
