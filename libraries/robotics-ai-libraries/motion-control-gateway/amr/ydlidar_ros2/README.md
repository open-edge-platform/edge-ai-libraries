# YDLIDAR ROS2 PACKAGE V1.3.6

---

ROS2 node and test application for YDLIDAR

Visit EAI Website for more details about YDLIDAR.

## Changes to 3rd party source

This work is based off of the open-source
[YDLIDAR SDK](https://github.com/YDLIDAR/sdk.git) repository.

The following patches are provided to enhance the YDLIDAR SDK source:

| Directory            | Enhancement                   |
| -------------------- | ----------------------------- |
| [patches](patches)   | Wrap angle beyond 180 degrees |

### How to build YDLIDAR ros2 package

1) Clone this project to your ament's workspace src folder
2) Running ament to build ydlidar_node and ydlidar_client
3) Create the name "/dev/ydlidar" for YDLIDAR

```bash
     cd workspace/ydlidar/startup
     sudo chmod 777 ./*
     sudo sh initenv.sh
```

### How to run YDLIDAR ros2 package

1. Run YDLIDAR node and view using test application

```bash
    ros2 run ydlidar ydlidar_node
    ros2 run ydlidar ydlidar_client
```

You should see YDLIDAR's scan result in the console

1. Run YDLIDAR node and view using test application by launch

```bash
    launch $(ros2 pkg prefix ydlidar)/share/ydlidar/launch/ydlidar.py
    ros2 run ydldiar ydlidar_client or ros2 topic echo /scan
```

***Configuration***
path: ~/.ros2/config.ini

***Parameters***

| Parameter           | Description                                                                 |
|---------------------|-----------------------------------------------------------------------------|
| `port` (string, default: `/dev/ydlidar`)           | Serial port name used in your system.                              |
| `baudrate` (int, default: `230400`)                | Serial port baud rate.                                              |
| `frame_id` (string, default: `laser_frame`)        | Frame ID for the device.                                            |
| `low_exposure` (singleChannel, default: `false`)   | Indicates whether the LIDAR is single communication (S2) LIDAR.     |
| `resolution_fixed` (bool, default: `true`)         | Indicates whether the LIDAR has a fixed angular resolution.         |
| `auto_reconnect` (bool, default: `true`)           | Indicates whether the LIDAR auto reconnects.                        |
| `reversion` (bool, default: `false`)               | Indicates whether the LIDAR data is rotated 180°.                   |
| `isToFLidar` (bool, default: `false`)              | Indicates whether the LIDAR is a TOF (TX8) LIDAR.                   |
| `angle_min` (double, default: `-180`)              | Minimum valid angle (°) for LIDAR data.                             |
| `angle_max` (double, default: `180`)               | Maximum valid angle (°) for LIDAR data.                             |
| `range_min` (double, default: `0.08`)              | Minimum valid range (m) for LIDAR data.                             |
| `range_max` (double, default: `32.0`)              | Maximum valid range (m) for LIDAR data.                             |
| `ignore_array` (string, default: `""`)             | Set the current angle range value to zero.                          |
| `samp_rate` (int, default: `9`)                    | The LIDAR sampling frequency.                                       |
| `frequency` (double, default: `10`)                | The LIDAR scanning frequency.                                       |

#### Upgrade Log

#### 2019-12-23 version:1.4.4

- support all standards lidar

#### 2018-07-16 version:1.3.6

- Update SDK version to 1.3.9

- remove imu sync.

#### 2018-07-16 version:1.3.5

- Update SDK version to 1.3.6

- add imu sync.

#### 2018-04-16 version:1.3.1

- Update SDK version to 1.3.1

- Increase sampling frequency,scan frequency setting.

- Unified coordinate system.

- Repair X4,S4 LIDAR cannot be opened.

- Increased G4 G4C F4Pro LIDAR power-off protection.

- Increased S4B LIDAR low optical power setting.

- Fix the wait time for closing ros node.

- Compensate for each laser point timestamp.

- Unified profile, automatic correction lidar model.
