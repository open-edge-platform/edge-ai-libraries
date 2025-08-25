# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
import os
import rospy

from ctypes import *

# Init the path to the Hiwin Robot's SDK .dll file
CURRENT_FILE_DIRECTORY = os.path.dirname(os.path.abspath(__file__))
PARENT_DIRECTORY = os.path.dirname(CURRENT_FILE_DIRECTORY)
# The .dll file is contained in include\hiwin_robot_sdk\
EG_DLL_PATH = os.path.join(PARENT_DIRECTORY, "include", "hiwin_gripper_sdk",
                           "EG_Control_API.dll")


# Percentage of the force given to the gripper (see XEG DLL manual)
#                     model: [ L,  M,   H]
GRIPPERS_FORCE_RANGES = {16: [50, 75, 100],
                         32: [40, 70, 100],
                         64: [40, 70, 100]}


class HiwinGripperInterface(object):
    def __init__(self, comport, model, name=""):  # type:(int, int, str)->None
        """Initialize an interface to control the gripper.

        :param comport: number of the Com Port to connect to.
        :param model: (e.g. xeg_16) model of the gripper to connect to 
        :param name: name of the gripper (up to the user)
        """
        self.comport = comport
        self.model = int(model.split('_')[-1])
        self.name = name
        self.id = -1
        assert os.path.exists(EG_DLL_PATH), \
            "EG SDK not found. Given path: {path}".format(path=EG_DLL_PATH)
        self.EGLib = cdll.LoadLibrary(EG_DLL_PATH)
        self.EGLib.CurrentPosMulti.restype = c_double
        self.EGLib.WorkStateMulti.restype = c_bool
        self.EGLib.HoldStateMulti.restype = c_bool

    def connect(self):  # type: () -> bool
        """Connect to the gripper"""
        result = self.EGLib.StartConnectMulti(c_int(self.comport),
                                              c_int(self.model))
        # StartConnect's errors are bigger than 1000
        success = result < 1000
        if success:
            self.id = result
            rospy.logdebug("Successfully connected with gripper,"
                           " id: {}".format(self.id))
            self.EGLib.ResetMotionMulti(self.id)
        else:
            rospy.logdebug("Not possible to connect to gripper."
                           "Error n. {}".format(result))
        return success

    def is_connected(self):  # type: () -> bool
        """Returns True if the gripper is connected, False otherwise"""
        return self.id == -1 or \
               self.EGLib.DetectConnectMulti(c_int(self.id)) == 0

    def disconnect(self):  # type: () -> bool
        """Disconnect from the gripper. Returns True if successful."""
        # If it is already disconnected, do nothing
        if not self.is_connected():
            return True
        self.EGLib.CloseConnectMulti(self.id)

    def reconnect(self, trials=3):  # type: (int) -> bool
        """Try reconnecting to the gripper for <trials> number of times"""
        for trial in range(trials):
            if not self.is_connected():
                rospy.logdebug("Trying reconnecting with gripper."
                               " Trial #{}".format(trial))
                success = self.connect()
                if success:
                    rospy.logdebug("Successfully reconnected to the gripper")
                    return True
            else:
                return True
        rospy.logdebug("Not possible to reconnect with the gripper.")
        return False

    def is_in_position(self, position, threshold=0.0001):
        # type: (float, float) -> bool
        """Tells whether the gripper is in the given position.

        :param position: the position to check
        :param threshold: the threshold to consider two positions as equal.
            (the smaller the more precise the comparison)
        """
        current_position = self.get_current_position() / 2
        return abs(current_position - position) <= threshold

    def is_moving(self):  # type: () -> bool
        """Check the state of the gripper to see if it is busy moving.

        :return True if the gripper is busy moving, False if in idle.
        """
        if not self.is_connected():
            if not self.reconnect():  # Try reconnecting
                return False
        error_code = (c_int*1)()
        return self.EGLib.WorkStateMulti(c_int(self.id), error_code)

    def is_holding_object(self):
        error_code = (c_int*1)()
        return self.EGLib.HoldStateMulti(c_int(self.id), error_code)

    def movement_error(self):  # type: () -> bool
        """Tells if the gripper encountered obstacles during movement."""
        error_code = self.EGLib.AlarmStateMulti(c_int(self.id))
        # Error code will be equal to 3001 if obstacles are detected
        return error_code == 3001

    def get_current_position(self):  # type: () -> float
        """Return the current gripper position in meters [m]"""
        if not self.is_connected():
            if not self.reconnect():
                rospy.logdebug("Not possible to get gripper position.")
                return 0.000
        error_code = (c_int*1)()
        current_position = self.EGLib.CurrentPosMulti(c_int(self.id),
                                                      error_code)
        # Current position is expressed in millimeters: change to meters
        return float(current_position/1000.)

    def run_move(self, position, speed=60):
        # type: (float, [float, int]) -> None
        """Set gripper to a certain position (move to the position)

        :param position: position of the gripper to be set (in meters)
        :param speed: min 1 max 60, 80 or 100 depend on model XEG16, 32 or 64
            (the speed is expressed in mm/s)
        """
        # position must be given to the gripper in millimeters
        position *= 1000
        error_code = int(self.EGLib.RunMoveMulti(c_int(self.id),
                                                 c_double(2*position),
                                                 c_int(speed)))
        if error_code == 0:
            return
        else:
            rospy.logdebug("Unexpected error setting gripper position."
                           " Error n. {}".format(error_code))

    def run_grip(self, position, effort=None):
        """Run gripping movement on the gripper

        :param position: [m] position of one joint only
        :param effort: [%] effort of grip movement
        """
        # If you are here, the movement is actually a gripping action
        self.stop_motion()
        # Set grip speed and force
        grip_speed = 'H'  # for now, the default speed is the maximum speed
        grip_force = 'M'  # the default value for the force is the medium
        if effort is not None:
            # Compare the input effort with the gripper spec to set grasping
            # fuzzy force level (see gripper's SDK)
            gripper_force_range = GRIPPERS_FORCE_RANGES[self.model]
            nearest_force_levels = [f for f in gripper_force_range
                                    if f >= effort]
            if len(nearest_force_levels) > 0:
                nearest_force_level = nearest_force_levels[0]
            else:  # Effort exceed the gripper capacity, use the maximum level
                nearest_force_level = gripper_force_range[2]
            # Determine which level is it
            grip_force_level = gripper_force_range.index(nearest_force_level)
            grip_force = ['L', 'M', 'H'][grip_force_level]

        # Find the gripping direction
        current_position = self.get_current_position()
        in_direction = 2*position < current_position
        out_direction = 2*position > current_position
        if out_direction:
            direction_char = 'o'
        else:  # inside direction
            direction_char = 'c'

        # Find the grip stroke (SDK requires mesurements in millimiters)
        stroke = int(abs(2*position-current_position)*1000)

        # Do the gripping movement
        rospy.loginfo("Gripping with force {}, speed {}, direction {}".format(
            grip_force, grip_speed, 'in' if in_direction else "out"))
        self.EGLib.RunGripMulti(c_int(self.id), c_char(direction_char),
                                c_int(stroke), c_char(grip_speed),
                                c_char(grip_force))

    def stop_motion(self):
        self.EGLib.StopMotionMulti(c_int(self.id))
