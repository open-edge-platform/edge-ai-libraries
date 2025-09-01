## Real-time domain (one of two options)
- RT
    ```shell
    # Terminal 1
    taskset -c 1 ./src/plc_rt_pos_rtmotion # Run simulated robot arm

    taskset -c 1 ./src/plc_rt_pos_rtmotion_jaka # Run jaka robot arm
    ```
## ROS2 domain (one of four options)
-  ROS2 Control interface
    ```shell
    # Terminal 2
    sudo su
    cp /home/intel/.Xauthority ~/
    ros2 launch jaka_bringup jaka_system_can.launch.py
    ```
-  ROS2 MoveIt demo
    ```shell
    # Terminal 2
    sudo su
    cp /home/intel/.Xauthority ~/
    ros2 launch jaka_bringup jaka_moveit_demo.launch.py
    ```
-  ROS2 MoveIt group
    ```shell
    # Terminal 2
    sudo su
    cp /home/intel/.Xauthority ~/
    ros2 launch jaka_bringup jaka_moveit_group.launch.py
    ```
- ROS2 MoveIt Servo Demo - teleop
    ```shell
    # Terminal 2
    sudo su
    cp /home/intel/.Xauthority ~/
    ros2 launch jaka_bringup jaka_moveit_teleop.launch.py
    
    # Terminal 3
    ros2 control switch_controllers --start forward_position_controller --stop joint_trajectory_controller

    # Terminal 3
    ros2 run jaka_servo servo_keyboard_input
    ```
- ROS2 MoveIt Servo Demo - pose tracking
    ```shell
    # Terminal 2
    sudo su
    cp /home/intel/.Xauthority ~/
    ros2 launch jaka_bringup jaka_moveit_servo.launch.py
    
    # Terminal 3
    ros2 control switch_controllers --start forward_position_controller --stop joint_trajectory_controller

    # Terminal 3
    ros2 run jaka_servo virtual_object_pub
    ros2 run jaka_servo virtual_object_pub --ros-args -p pub_mode:=1
    ```

    