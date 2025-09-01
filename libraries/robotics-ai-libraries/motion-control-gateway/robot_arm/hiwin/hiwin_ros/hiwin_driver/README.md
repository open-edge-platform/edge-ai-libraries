# HIWIN Driver Package

This package contains driver's nodes for HIWIN's Robots and Gripper

## Overview
You can use this package to control certain HIWIN Robots and Grippers through ROS. 

## Remarks
Unlike others ROS-I driver packages, each HIWIN Robot's driver node does not communicate with a ROS Controller Node inside 
the robot's controller. Instead, the control is done by the driver node itself through HIWIN's HRSDK dll library which 
connects via IP to the HIWIN Robot Software System (HRSS) running on board of the Robotic arm.

Although the current version has been structured as described above, it is possible that future versions will support a more 
traditional ROS-Industrial protocol, connecting to a ROS Controller node on the Robot's controller through Simple Message.

## Requirements
- ROS on Windows
- A HIWIN robot which controller's HRSS software has been updated to version 3.2.16

## Get started
Currently supported robots:
- [RA605 710 GB Robotic arm](https://www.hiwin.tw/products/mar/articulated/ra605/ra605_710_gb.aspx)
- [RA610 1355 Robotic arm](https://www.hiwin.tw/products/mar/articulated/ra610/ra610_1355_gb.aspx)
- [RA620 1621 Robotic arm](https://www.hiwin.tw/products/mar/articulated/ra620/ra620_1621.aspx)
- [XEG16 electric gripper](https://www.hiwin.tw/products/ee/xeg/xeg_16.aspx)
- [XEG32 electric gripper](https://www.hiwin.tw/products/ee/xeg/xeg_32.aspx)
- [XEG64 electric gripper](https://www.hiwin.tw/products/ee/xeg/xeg_64.aspx)

### Run driver for Robotic Arm RT605 710GB 
- Turn on the robot and connect it to your computer with an ethernet cable (see arm's manual for more info).
- Get the IP of the robot on your network.
- Run the driver by launching the node as shown below:
  `roslaunch hiwin_driver hiwin_robot_interface.launch robot_ip:=<ip> robot_name:=<name>`
  
  Where:
  - `<ip>` is the IP of the robot
  - `<name>` is the name of the robot (default is "manipulator").
  
### Run driver for HIWIN's Grippers (XEG Series)
- Turn on the gripper as shown in the user manual.
- Connect the robot via USB to your computer and get the USB COM port.
- Run the driver by launching the node as shown below:
  `roslaunch hiwin_driver hiwin_gripper_interface.launch gripper_model:=<model> gripper_com_port:=<port> gripper_name:=<name>`
  
  Where:
  - `<model>` is the model of the gripper to control (16 for XEG16, 32 for XEG32, etc.)
  - `<port>` is the COM port to which the gripper is connected.
  - `<name>` is the name of the gripper (default is "gripper").
  
- If correctly connected, the gripper should execute a reset procedure.