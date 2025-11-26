# Robot Motion Control Task

Robotmctask is a C++ library of motion control task development that provides library and API to support Robot developer to develop robot application with AI inference engine and EtherCAT protocal.

For detailed information, see the [Introduction](./docs/introduction.md).

# Dependency(Ubuntu):

1. install develop tool

```shell
sudo apt-get install cmake git build-essential libyaml-cpp-dev libeigen3-dev
```

2. install plcopen-motion library

```shell
sudo apt install plcopen-motion-dev plcopen-servo-dev   plcopen-ruckig-dev plcopen-databus-dev plcopen-benchmark-dev
```

3. install ethercat stack and ecat-enablekit, you also can follow with  [Userspace EtherCAT Master Stack](../masterstack/docs/igh_userspace.md) and  [EtherCAT Enable Kit](../ecat-enablekit/README.md) to build/deploy them.

```shell
sudo apt install ighethercat-dpdk ecat-enablekit-dpdk
```

4. follow with below command to install ruckig:

```shell
git clone -b v0.9.2 https://github.com/pantor/ruckig.git
cd ruckig
mkdir -p build && cd build
cmake -DCMAKE_BUILD_TYPE=Release ..
make
make install
```

# Build

Follow below command to build library and examples

```shell
mkdir build && cd build
cmake ..
make
sudo make install

# Try **sudo ldconfig** after installation if meet any problem realted to library file missing.
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




