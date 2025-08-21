# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
import os
import math
import rospy
import time
import datetime

from ctypes import *

# Init the path to the Hiwin Robot's SDK .dll file
CURRENT_FILE_DIRECTORY = os.path.dirname(os.path.abspath(__file__))
PARENT_DIRECTORY = os.path.dirname(CURRENT_FILE_DIRECTORY)
# The .dll file is contained in include\hiwin_robot_sdk\
HRSDK_DLL_PATH = os.path.join(PARENT_DIRECTORY, "include", "hiwin_robot_sdk",
                              "HRSDK.dll")


def degrees_to_radians(angles_in_degrees):
    # type: (list[float]) -> list[float]
    """Get radians values of angles expressed in degrees

    :param
        angles_in_degrees: list of values in degrees
    :return
        angles_in_radians: list of the values in radiant
    """
    angles_in_radians = (c_double * len(angles_in_degrees))()
    for axis_n, angle_in_degrees in enumerate(angles_in_degrees):
        angles_in_radians[axis_n] = c_double(math.radians(angle_in_degrees))
    return angles_in_radians


def radians_to_degrees(angles_in_radians):
    # type: (list[float]) -> list[float]
    """Get degrees values of angles expressed in radians

    :param
        angles_in_radians: list of values in radians
    :return
        angles_in_degrees: list of the values in degrees
    """
    angles_in_degrees = (c_double * len(angles_in_radians))()
    for axis_n, angle_in_radians in enumerate(angles_in_radians):
        angles_in_degrees[axis_n] = c_double(math.degrees(angle_in_radians))
    return angles_in_degrees


def callback_function(cmd, rlt, msg, len):
    #print(cmd)
    pass


class HiwinRobotInterface(object):
    """Class used as bridge python-CPP and SDK."""
    # The value of the robot state
    IDLE_MOTION_STATE = 1
    RUNNING_MOTION_STATE = 2

    def __init__(self, robot_ip, connection_level, name=""):
        # type: (str, int, str, str) -> None
        """Hiwin Robot SDK Initialization"""
        # Initialize the variables
        self.ip = robot_ip
        self.level = connection_level
        self.robot_id = -1
        self.name = name
        # Load the SDK
        # Make sure the SKL library absolute file contains the file
        assert os.path.exists(HRSDK_DLL_PATH), \
            "HRSDK not found. Given path: {path}".format(path=HRSDK_DLL_PATH)
        self.HRSDKLib = cdll.LoadLibrary(HRSDK_DLL_PATH)
        try:
            self.HRSDKLib.set_log_level(c_int(3))
        except AttributeError:
            pass
        # Get the callback function
        callback_type = CFUNCTYPE(None, c_uint16, c_uint16,
                                  POINTER(c_uint16), c_int)
        self.callback = callback_type(callback_function)
        self.reconnecting = False  # Used to know if we are trying to reconnect

    def connect(self):  # type: () -> bool
        """Connect to the Hiwin robot

        :param
            ip   : Computer connect to robot (str)
            level: Connection level (int)
        :return
            success: True if connection has succeeded, False otherwise (bool)
        """
        self.robot_id = self.HRSDKLib.open_connection(self.ip, c_int(self.level),
                                                      self.callback)
        if self.is_connected():
            success = True
            if self.level == 1:
                # Initialize some parametes
                #   set operation mode to "Auto"
                self.HRSDKLib.set_operation_mode(c_int(self.robot_id),
                                                 c_int(1))
                self.HRSDKLib.set_override_ratio(c_int(self.robot_id),
                                                 c_int(100))
            rospy.loginfo("HIWIN Robot '{}' successfully connected.".format(self.name))
        else:
            success = False
        return success

    def reconnect(self, trials=5, sec_between_trials=2.0):
        # type: (int, float) -> bool
        """Try to reconnect to the robot. The ip and connection level for the
        connection are taken from the ones given during __init__().

        :param trials: Number of time to try to reconnect (int)
        :param sec_between_trials: seconds to sleep between each trial (float)

        :return success: True if correctly connected, False otherwise
        """
        # Get the connection level
        connection_level = self.get_connection_level()
        # If robot is already connected with the correct level, nothing to do.
        if connection_level == self.level:
            success = True
            return success

        # If the robot is already reconnecting, do nothing
        if self.reconnecting:
            return False
        self.reconnecting = True

        # Try to reconnect to the robot
        for trial in xrange(trials):
            rospy.loginfo('Reconnecting to HIWIN robot "{robot_name}": '
                          'trial #{trial_num}.'.format(robot_name=self.name,
                                                       trial_num=trial+1))
            # Connect to the robot
            success = self.connect()
            if success:
                rospy.loginfo('Successfully reconnected with the robot!')
                self.reconnecting = False
                return success
            else:
                self.close()
                # Retry after a while
                time.sleep(sec_between_trials)
        rospy.logwarn('Could not reconnect to robot "{robot_name}"! '
                      'Total trials: {trials_num}'
                      .format(robot_name=self.name, trials_num=trials))
        self.reconnecting = False
        return False

    def close(self):
        # type: () -> bool
        """Disconnect to robot

        :return
            Success: True if successfully disconnected, False otherwise
        """
        error_id = self.HRSDKLib.close_connection(c_int(self.robot_id))

        # If correctly disconnected error_id is equal to 0
        if error_id == 0:
            return True
        else:
            return False

    def is_connected(self):
        # type: () -> bool
        """Function to know if the robot is currently connected.

        :return
            is_connected: True if the robot is connected, False otherwise
        """
        connection_level = self.get_connection_level()
        # If connection_level is -1 it means that the robot is disconnected
        is_connected = (connection_level == self.level)
        return is_connected

    def is_in_state(self, joints_states, angle_threshold=0.01):
        # type: (list[float], float) -> bool
        """Check if the robot is in the given state (or close enough).

        The robot is in the state if all the angles are the same as the given
        joints states (allowing a optional angle_threshold)

        :param joints_states: list of joints angles expressed in radians
        :param angle_threshold: value (in radians) over which two angles are
                                considered different one to the other.
        """
        success, current_joints_states = self.get_current_joints()

        # For each joint of the robot
        for current_joint_state, joint_state in zip(
                current_joints_states, joints_states):
            # Check if the current value is the same as the input one
            if abs(current_joint_state-joint_state) >\
                    angle_threshold:
                # One of the joints is not in the state input
                return False  # The robot is not in the given state

        # All the joints of the
        return True

    def is_in_idle(self):
        # type: () -> bool
        """Tells whether the robot is in IDLE or not."""
        robot_motion_state = self.get_robot_motion_state()
        is_in_idle_state = (robot_motion_state == self.IDLE_MOTION_STATE)
        return is_in_idle_state

    def is_running(self):
        # type: () -> bool
        """Tells whether the robot is running (moving) or not."""
        robot_motion_state = self.get_robot_motion_state()
        is_running = (robot_motion_state == self.RUNNING_MOTION_STATE)
        return is_running

    def get_hrsdk_version(self):
        # type: () -> (int, str)
        """Get HRSDK version

        :return
            error_id:
                Success :0
                Fail    :else
            version   : HRSDK version (string)
        """
        version = create_string_buffer(15)
        error_id = self.HRSDKLib.get_HRSDK_version(version)
        return error_id, version.value.decode("utf-8")

    def get_connection_level(self):
        # type: () -> int
        """Get user connect level to the robot

        :return
            Connection level:
                Operator :0
                Expert   :1
        """
        # TODO: Check if the robot is connected first
        connection_level = self.HRSDKLib.get_connection_level(
            c_int(self.robot_id))
        return connection_level

    def set_connection_level(self, level):
        # type: (int) -> bool
        """Get user connect level

        :parameter
            level:
                Operator :0
                Expert   :1
        :return
            bool:
                True: success
                False: failure
        """
        result = self.HRSDKLib.set_control_level(c_int(self.robot_id),
                                                 c_int(level))
        if result == level:
            return True
        elif result != level:
            return False

    def get_robot_motion_state(self):
        return self.HRSDKLib.get_motion_state(self.robot_id)

    def get_current_joints(self):
        # type: () -> (bool, list[float])
        """Get Robot current joints (in rad).

        :returns
            success: True or False whether or not it was possible to retrieve
                the current joints of the robot
            axis_values: include a1~a6 (in radians)
        """
        # If the robot is not connected, try reconnecting
        if not self.is_connected():
            successfully_reconnected = self.reconnect()
            if not successfully_reconnected:
                rospy.logwarn("Robot disconnected, it was not possible to get "
                              "the joints")
                return False, [0 for i in range(6)]
        # Create C double array
        axis_values = (c_double * 6)()
        # Get the current joint state
        result = self.HRSDKLib.get_current_joint(c_int(self.robot_id),
                                                 axis_values)
        return result == 0, [float(value) for value in
                             degrees_to_radians(axis_values)]

    def get_current_digital_inputs(self):
        # type: () -> (list[int])
        """Get Robot current digital inputs.

        :returns
            inputs: list of the value of the digital inputs
            (1 if on 0 if off)
        """
        # If the robot is not connected, try reconnecting
        if not self.is_connected():
            successfully_reconnected = self.reconnect()
            if not successfully_reconnected:
                rospy.logwarn("Robot disconnected, it was not possible to get "
                              "the digital inputs")
                return [-1 for _ in range(48)]
        inputs = []
        for i in range(1, 49):
            inputs.append(self.HRSDKLib.get_digital_input(c_int(self.robot_id),
                                                          c_int(i)))
        return inputs

    def get_current_digital_outputs(self):
        # type: () -> (list[int])
        """Get Robot current digital outputs.

        :returns
            outputs: list of the value of the digital outputs
            (1 if on 0 if off)
        """
        # If the robot is not connected, try reconnecting
        if not self.is_connected():
            successfully_reconnected = self.reconnect()
            if not successfully_reconnected:
                rospy.logwarn("Robot disconnected, it was not possible to get "
                              "the digital outputs")
                return [-1 for _ in range(48)]
        outputs = []
        for i in range(1, 49):
            outputs.append(self.HRSDKLib.get_digital_output(c_int(self.robot_id),
                                                           c_int(i)))
        return outputs

    def move_ptp(self, target_axis_values, mode=1):
        # type: (list[float], int) -> None
        """Move Point-To-Point (PTP) to a certain position

        :param target_axis_values: target position of each joint
                                (list of angles in radians)
        :param mode              : movement mode (int)
        """
        # If the robot is not connected, try reconnecting
        if not self.is_connected():
            successfully_reconnected = self.reconnect()
            if not successfully_reconnected:
                rospy.logwarn("Robot disconnected, not possible to move PTP.")
                return

        # Transform from rad to degrees
        target_axis_values = radians_to_degrees(target_axis_values)

        rospy.logdebug("Robot '{name}' moving PTP to: {target} [deg]"
                       .format(name=self.name,
                               target=[round(val, 3)
                                       for val in target_axis_values]))
        rospy.logdebug("Level of connection: {level}".format(
            level=self.get_connection_level()))
        # Use HRSDK library to move the robot to the desired position
        self.HRSDKLib.ptp_axis(c_int(self.robot_id), c_int(mode),
                               target_axis_values)

    def stop_motion(self):
        """Stop the motion of the robot."""
        self.HRSDKLib.motion_abort(self.robot_id)

    def set_io_value(self, io, value):
        # type: (int, bool) -> None
        self.HRSDKLib.set_digital_output(c_int(self.robot_id),
                                         c_int(io),
                                         c_bool(value))

    def stop_task(self):  # type: (str) -> bool
        #print self.get_connection_level(), " < connection level"
        return self.HRSDKLib.task_abort(c_int(self.robot_id))

    def pause_task(self):  # type: (str) -> bool
        #print self.get_connection_level(), " < connection level"
        return self.HRSDKLib.task_hold(c_int(self.robot_id))

    def continue_task(self):  # type: (str) -> bool
        #print self.get_connection_level(), " < connection level"
        return self.HRSDKLib.task_continue(c_int(self.robot_id))

    def start_task(self, string_msg):  # type: (str) -> bool
        #print self.get_connection_level(), " < connection level"
        return self.HRSDKLib.task_start(c_int(self.robot_id), string_msg)
