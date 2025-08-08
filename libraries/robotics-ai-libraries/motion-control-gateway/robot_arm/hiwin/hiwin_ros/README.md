# HIWIN ROS-I Package

This package allows you to monitor and control HIWIN industrial robots within the ROS framework. HIWIN currently support the following supports packages.
- [RA605 710 GB Robotic arm](https://www.hiwin.tw/products/mar/articulated/ra605/ra605_710_gb.aspx) - 5kg payload industrial robot.
- [RA610 1355 Robotic arm](https://www.hiwin.tw/products/mar/articulated/ra610/ra610_1355_gb.aspx) - 10kg playload industrial robot.
- [RA620 1621 Robotic arm](https://www.hiwin.tw/products/mar/articulated/ra620/ra620_1621.aspx) - 20kg playload industrial robot.
- [XEG16 electric gripper](https://www.hiwin.tw/products/ee/xeg/xeg_16.aspx) - High presision electric gripper.
- [XEG32 electric gripper](https://www.hiwin.tw/products/ee/xeg/xeg_32.aspx) - High presision electric gripper.
- [XEG64 electric gripper](https://www.hiwin.tw/products/ee/xeg/xeg_64.aspx) - High presision electric gripper.

## Prerequisites:
- A 64bit Windows OS (x64 architecture is needed for .dll libraries)
- Install [ROS on Windows](http://wiki.ros.org/Installation/Windows)

##  Run simulated MoveIt! environment without real robot
- Run the demo launch file with the command:

  `roslaunch hiwin_robot_moveit_config demo.launch manipulator_model:=<manipulator_model> gripper_model:=<gripper_model>`

  Note: 
     - substitute `<manipulator_model>` with the robot model (e.g. _ra605_710_gb_).
     - substitute `<gripper_model>` with the gripper model (e.g. _xeg_16_).

## Run package to control a real Robot and Gripper
If you already purchased a robotic arm and an electric gripper you can follow the following steps:

1. Connect the robotic arm to your network through an ethernet cable, make sure your computer and your robot are on the same domain (e.g. robot's ip is 192.168.0.1, computer's ip is 192.168.0.100).

1. Connect your gripper via USB to your computer and check in which COM port is the USB insert. (You can use [XEG-W1](https://www.hiwin.tw/support/ee/eg_software.aspx) software to check gripper's COM Port)

1. Load the control nodes for robot and gripper:

    `roslaunch hiwin_driver hiwin_robot_interface.launch manipulator_ip:=<manipulator_ip>`

    `roslaunch hiwin_driver hiwin_gripper_interface.launch gripper_model:=<gripper_model> gripper_com_port:=<gripper_com_port>`

    Note: 
     - substitute `<manipulator_ip>` with the IP address of the robotic arm.
     - substitute `<gripper_model>` with the gripper model (e.g. _xeg_16_).
     - substitute `<gripper_com_port>` with the gripper p (16 or 32).
     

1. Load the model, run MoveIt! and (optional) run the RVIZ simulated environment

    `roslaunch hiwin_robot_moveit_config start_planning.launch manipulator_model:=<manipulator_model> gripper_model:=<gripper_model>`

    Note: 
     - substitute `<manipulator_model>` with the robot model (default is _ra605_710_gb_)
     - substitute `<gripper_model>` with the gripper model (e.g. _xeg_16_).
    
### Control the interface for HIWIN's electric gripper XEG series

If you want to use HIWIN's gripper independently, you need to run the gripper interface to control the gripper via ROS.

1. Connect the gripper controller as illustrated in the gripper manual.
2. Before running your planner, run the gripper interface node.
    
    `roslaunch hiwin_driver hiwin_gripper_interface.launch gripper_com_port:=<port> gripper_model:=<model> gripper_name:=<name>`
 
    Note:
    - substitute`<port>` with the COM port the gripper is connected to.
    - substitute `<model>` with the gripper model (e.g. _xeg_16_).
    - The driver node will be listening for target positions on the action server `<name>/follow_joint_trajectory`.
      Choose `<name>` accordingly to your planning groups and controllers definitions.
    - If successfully run, this node will launch a test movement of the gripper. The test is necessary for the correct 
      operation of the gripper.
3. Run your planner or other commander nodes.
    
    `roslaunch <some_package> <some_planning_execution_launch_file>`

### Licence

All the files included in this directory are under the BSD 3 Clause Licence. A copy of the licence is included in this folder.