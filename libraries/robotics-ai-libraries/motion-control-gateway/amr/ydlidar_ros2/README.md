YDLIDAR ROS2 PACKAGE V1.3.6
=====================================================================

ROS2 node and test application for YDLIDAR

Visit EAI Website for more details about YDLIDAR.


Changes to 3rd party source
=====================================================================

This work is based off of the open-source
[YDLIDAR SDK](https://github.com/YDLIDAR/sdk.git) repository.

The following patches are provided to enhance the YDLIDAR SDK source:

| Directory            | Enhancement                   |
| -------------------- | ----------------------------- |
| [patches](patches)   | Wrap angle beyond 180 degrees |

How to build YDLIDAR ros2 package
=====================================================================
    1) Clone this project to your ament's workspace src folder
    2) Running ament to build ydlidar_node and ydlidar_client
    3) Create the name "/dev/ydlidar" for YDLIDAR
    --$ cd workspace/ydlidar/startup
    --$ sudo chmod 777 ./*
    --$ sudo sh initenv.sh

How to run YDLIDAR ros2 package
=====================================================================

1. Run YDLIDAR node and view using test application
------------------------------------------------------------
ros2 run ydlidar ydlidar_node

ros2 run ydlidar ydlidar_client

You should see YDLIDAR's scan result in the console

2.Run YDLIDAR node and view using test application by launch
------------------------------------------------------------
launch $(ros2 pkg prefix ydlidar)/share/ydlidar/launch/ydlidar.py

ros2 run ydldiar ydlidar_client or ros2 topic echo /scan

Configuration
=====================================================================
path: ~/.ros2/config.ini

Parameters
=====================================================================
port (string, default: /dev/ydlidar)

    serial port name used in your system. 

baudrate (int, default: 230400)

    serial port baud rate. 

frame_id (string, default: laser_frame)

    frame ID for the device. 

low_exposure (singleChannel, default: false)

    indicated whether the LIDAR is single communication(S2) lidar. 

resolution_fixed (bool, default: true)

    indicated whether the LIDAR has a fixed angular resolution. 

auto_reconnect (bool, default: true)

    indicated whether the LIDAR auto reconnection. 

reversion (bool, default: false)

    indicated whether the LIDAR data rotation 180°. 

isToFLidar (bool, default: false)

    indicated whether the LIDAR is TOF(TX8) lidar. 

angle_min (double, default: -180)

    Min valid angle (°) for LIDAR data. 

angle_max (double, default: 180)

    Max valid angle (°) for LIDAR data. 

range_min (double, default: 0.08)

    Min valid range (m) for LIDAR data. 

range_max (double, default: 32.0)

    Max valid range (m) for LIDAR data. 

ignore_array (string, default: "")

    Set the current angle range value to zero. 

samp_rate (int, default: 9)

    the LIDAR sampling frequency.

frequency (double, default: 10)

    the LIDAR scanning frequency.







Upgrade Log
=====================================================================

2019-12-23 version:1.4.4

   1.support all standards lidar


2018-07-16 version:1.3.6

   1.Update SDK verison to 1.3.9
 
   2.remove imu sync.

2018-07-16 version:1.3.5

   1.Update SDK verison to 1.3.6

   2.add imu sync.

2018-04-16 version:1.3.1

   1.Update SDK verison to 1.3.1

   2.Increase sampling frequency,scan frequency setting.

   3.Unified coordinate system.

   4.Repair X4,S4 LIDAR cannot be opened.

   5.Increased G4 G4C F4Pro LIDAR power-off protection.

   6.Increased S4B LIDAR low optical power setting.

   7.Fix the wait time for closing ros node.
   
   8.Compensate for each laser point timestamp.

   9.Unified profile, automatic correction lidar model.






