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

   Follow the [Setup ECI APT Repository](../../plcopen-motion-control/docs/rt-motion/installation_setup/prerequisites/Apt-Repositories.rst) instructions  to configure the APT package manager.

   After setting up the repository, update the system APT repository lists:

   ```shell
   sudo apt-get update
   ```

3. Install plcopen-motion library:

```shell
sudo apt-get install plcopen-motion-dev plcopen-servo-dev plcopen-ruckig-dev plcopen-databus-dev plcopen-benchmark-dev
```

4. Install EtherCAT stack and ECAT-Enablekit. Note: You also can follow [Userspace EtherCAT Master Stack](../ethercat-masterstack/docs/igh_userspace.md) and [EtherCAT Enable Kit](../ecat-enablekit/README.md) to build/deploy these packages.

```shell
sudo apt-get install ighethercat-dpdk ecat-enablekit-dpdk
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

For RVIZ, please go to Motion Control Gateway to run ros2 node `robot_rviz`.

```shell
ros2 launch robot_rviz robot_rviz.launch.py
```

# LICENSE

The source code is licensed under the Apache. See [LICENSE](LICENSE) file for details.

