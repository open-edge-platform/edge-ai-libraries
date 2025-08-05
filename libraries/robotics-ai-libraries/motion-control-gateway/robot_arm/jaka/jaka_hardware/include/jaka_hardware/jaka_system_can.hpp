// Copyright 2020 ros2_control Development Team
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#ifndef JAKA_HARDWARE__JAKA_SYSTEM_CAN_HPP_
#define JAKA_HARDWARE__JAKA_SYSTEM_CAN_HPP_

#include <memory>
#include <string>
#include <vector>

//#include "hardware_interface/base_interface.hpp"
#include "hardware_interface/handle.hpp"
#include "hardware_interface/hardware_info.hpp"
#include "hardware_interface/system_interface.hpp"
#include "hardware_interface/types/hardware_interface_return_values.hpp"
#include "hardware_interface/types/hardware_interface_type_values.hpp"
#include "rclcpp/macros.hpp"
#include "jaka_hardware/visibility_control.h"

#include <shmringbuf.h>

/* Shm related data types
 * s_buf, handle_s: data sent from RT domain
 * r_buf, handle_r: data sent to RT domain
 */
#define MSG_LEN 4000
#define JOINT_NUM 6

struct JointCommand
{
  double positions[JOINT_NUM] = {0};
  double velocities[JOINT_NUM] = {0};
  double accelerations[JOINT_NUM] = {0};
  double efforts[JOINT_NUM] = {0};
};

struct JointState
{
  double positions[JOINT_NUM] = {0};
  double velocities[JOINT_NUM] = {0};
  double accelerations[JOINT_NUM] = {0};
  double efforts[JOINT_NUM] = {0};
};

namespace jaka_hardware
{
class JAKASystemCANHardware
: public hardware_interface::SystemInterface
{
public:
  RCLCPP_SHARED_PTR_DEFINITIONS(JAKASystemCANHardware);

  ROS2_CONTROL_DEMO_HARDWARE_PUBLIC
  hardware_interface::CallbackReturn on_init(
    const hardware_interface::HardwareInfo & info) override;

  ROS2_CONTROL_DEMO_HARDWARE_PUBLIC
  hardware_interface::CallbackReturn on_configure(
    const rclcpp_lifecycle::State & previous_state) override;

  ROS2_CONTROL_DEMO_HARDWARE_PUBLIC
  std::vector<hardware_interface::StateInterface> export_state_interfaces() override;

  ROS2_CONTROL_DEMO_HARDWARE_PUBLIC
  std::vector<hardware_interface::CommandInterface> export_command_interfaces() override;

  ROS2_CONTROL_DEMO_HARDWARE_PUBLIC
  hardware_interface::CallbackReturn on_activate(
    const rclcpp_lifecycle::State & previous_state) override;

  ROS2_CONTROL_DEMO_HARDWARE_PUBLIC
  hardware_interface::CallbackReturn on_deactivate(
    const rclcpp_lifecycle::State & previous_state) override;

  ROS2_CONTROL_DEMO_HARDWARE_PUBLIC
  hardware_interface::return_type read(
    const rclcpp::Time & time, const rclcpp::Duration & period) override;

  ROS2_CONTROL_DEMO_HARDWARE_PUBLIC
  hardware_interface::return_type write(
    const rclcpp::Time & time, const rclcpp::Duration & period) override;

  bool shm_read();
  bool shm_write();

private:
  // Parameters for the JAKA simulation
  double hw_start_sec_;
  double hw_stop_sec_;
  double hw_slowdown_;

  // Store the command for the simulated robot
  std::vector<double> hw_commands_;
  std::vector<double> hw_states_;

  char s_buf_[MSG_LEN];
  char r_buf_[MSG_LEN];
  shm_handle_t handle_s_, handle_r_;
  JointCommand joint_cmd_;
  JointState joint_state_;
};

}  // namespace jaka_hardware

#endif  // JAKA_HARDWARE__JAKA_SYSTEM_CAN_HPP_
