# Robot Motion Control Task

Robotmctask is a C++ library of motion control task development that provides library and API to support Robot developer to develop robot application with AI inference engine and EtherCAT protocol.

For detailed information, see the [Introduction](./docs/introduction.md).

# Prerequisites

This component was developed for Debian and Ubuntu OS distributions. Before continuing, it is recommended to install Ubuntu on your system. At the time of publishing, Ubuntu 24.04 was the preferred version.

# Install Dependencies

1. Install develop tool:

```shell
sudo apt-get install cmake git build-essential libyaml-cpp-dev libeigen3-dev
```

2. Setup the ECI APT package repository to access the plcopen-motion and EtherCAT packages:

   Follow the [Setup ECI APT Repository](../../plcopen-motion-control/docs/user-guide/rt-motion/installation_setup/prerequisites/Apt-Repositories.rst) instructions  to configure the APT package manager.

   After setting up the repository, update the system APT repository lists:

   ```shell
   sudo apt-get update
   ```

3. Install plcopen-motion library:

```shell
sudo apt-get install plcopen-motion-dev plcopen-servo-dev plcopen-ruckig-dev plcopen-databus-dev plcopen-benchmark-dev libshmringbuf-dev
```

4. Install EtherCAT stack and ECAT-Enablekit. Note: You also can follow [Userspace EtherCAT Master Stack](../ethercat-masterstack/docs/igh_userspace.md) and [EtherCAT Enable Kit](../ecat-enablekit/README.md) to build/deploy these packages.

```shell
sudo apt-get install ighethercat-dpdk ecat-enablekit-dpdk libethercatd-dev
```

5. Follow with below command to install ruckig:

```shell
git clone -b v0.9.2 https://github.com/pantor/ruckig.git
cd ruckig
mkdir -p build && cd build
cmake -DCMAKE_BUILD_TYPE=Release ..
make
make install
```

6. Install OpenVINO Toolkit using APT repository. For details, visit the [OpenVINO Toolkit Overview Website](https://www.intel.com/content/www/us/en/developer/tools/openvino-toolkit/overview.html)

```shell
sudo apt-get install openvino-2026.1.0
```

7. Install robot_rviz

```shell
sudo apt install ros-<ROS2 codename>-ti5-rviz
```

| ROS 2 Distribution | Package Name |
|--------------------|--------------|
| Humble | ros-humble-ti5-rviz |
| Jazzy | ros-jazzy-ti5-rviz |



# Build

Follow below command to build library and examples:

```shell
mkdir build && cd build
cmake ..
make
sudo make install

# Try **sudo ldconfig** after installation if meet any problem related to library file missing.
```

# Run Minimum Example

Running the evaluation program using the following commands(simulation):

```shell
cd <Robot Motion Control Task>/examples/
sudo ../build/examples/mc_rl_sample -c config/robot_rl_ov.yaml -m 0 -s
```

**Note:** The configuration file `robot_rl_ov.yaml` specifies `inference_device`, which selects the OpenVINO target device used to run AI inference. It supports various devices, such as `CPU` for Intel CPUs, `GPU` for Intel integrated/discrete GPUs, `NPU` for Intel Neural Processing Units. You can modify the `inference_device` value in the configuration file to test different devices. For example, set `inference_device: "CPU"` to run the inference on CPU.

**Note:** If you want to run the inference on NPU with high inference performance, please make sure to pinning the NPU IRQ to a specific CPU core using below method:
1. Identify the NPU interrupt number(e.g. Panterlake/ArrowLake platform):

```shell
cat /sys/module/intel_vpu/drivers/pci\:intel_vpu/0000\:00\:0b.0/irq
```
2. Affinity the NPU IRQ to a specific CPU core (e.g., CPU core 11, which corresponds to the hexadecimal value `800` for CPU affinity):

```shell
echo 800 | sudo tee /proc/irq/<NPU_interrupt_number>/smp_affinity
```

For RVIZ, please go to Motion Control Gateway to run ros2 node `robot_rviz`.

```shell
ros2 launch robot_rviz robot_rviz.launch.py
```


Below ros2 topic publishers are available to control the left/right arm robot in RVIZ:

```shell
# For left arm joint trajectory controller (initial position is 0.0 for all joints)
ros2 topic pub --once /fake_joint_trajectory_controller/left_arm_joint_trajectory trajectory_msgs/msg/JointTrajectory '{
  header: {
    stamp: "now",
    frame_id: ""
  },
  joint_names: [
    "joint1",
    "joint2",
    "joint3",
    "joint4",
    "joint5",
    "joint6",
    "joint7"
  ],
  points: [{
    positions: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    velocities: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    accelerations: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    effort: [],
    time_from_start: {sec: 1, nanosec: 0}
  }]
}'

# For left arm joint trajectory controller (target position is 1.57 for joint2/joint4, 1.57 for radian of joint)
ros2 topic pub --once /fake_joint_trajectory_controller/left_arm_joint_trajectory trajectory_msgs/msg/JointTrajectory '{
  header: {
    stamp: "now",
    frame_id: ""
  },
  joint_names: [
    "joint1",
    "joint2",
    "joint3",
    "joint4",
    "joint5",
    "joint6",
    "joint7"
  ],
  points: [{
    positions: [0.0, 1.57, 0.0, -1.57, 0.0, 0.0, 0.0],
    velocities: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    accelerations: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    effort: [],
    time_from_start: {sec: 1, nanosec: 0}
  }]
}'
```

```shell
# For right arm joint trajectory controller (initial position is 0.0 for all joints)
ros2 topic pub --once /fake_joint_trajectory_controller/right_arm_joint_trajectory trajectory_msgs/msg/JointTrajectory '{
  header: {
    stamp: "now",
    frame_id: ""
  },
  joint_names: [
    "joint1",
    "joint2",
    "joint3",
    "joint4",
    "joint5",
    "joint6",
    "joint7"
  ],
  points: [{
    positions: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    velocities: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    accelerations: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    effort: [],
    time_from_start: {sec: 1, nanosec: 0}
  }]

}'

# For right arm joint trajectory controller (target position is 1.57 for joint2/joint4, 1.57 for radian of joint)
ros2 topic pub --once /fake_joint_trajectory_controller/right_arm_joint_trajectory trajectory_msgs/msg/JointTrajectory '{
  header: {
    stamp: "now",
    frame_id: ""
  },
  joint_names: [
    "joint1",
    "joint2",
    "joint3",
    "joint4",
    "joint5",
    "joint6",
    "joint7"
  ],
  points: [{
    positions: [0.0, -1.57, 0.0, 1.57, 0.0, 0.0, 0.0],
    velocities: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    accelerations: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    effort: [],
    time_from_start: {sec: 1, nanosec: 0}
  }]
}'
```

![robot_rviz](docs/images/robot_rviz.gif)

# LICENSE

The source code is licensed under the Apache. See [LICENSE](LICENSE) file for details.

