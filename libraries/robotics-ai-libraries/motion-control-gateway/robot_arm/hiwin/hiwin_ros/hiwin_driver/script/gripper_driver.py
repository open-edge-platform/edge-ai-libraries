# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
import rospy
import time
import actionlib
import threading
import argparse

from control_msgs.msg import FollowJointTrajectoryAction
from trajectory_msgs.msg import JointTrajectory
from sensor_msgs.msg import JointState

from hiwin_gripper_interface import HiwinGripperInterface

JOINTS_NAMES = ['eef_joint_finger_1', 'eef_joint_finger_2']
last_joint_states_lock = threading.Lock()

DEBUG = True  # Set True to show debug log, False to hide it.


class HiwinGripperStatePublisher(object):
    """Reads robot joints' states and publish them on the joint_state topic."""
    def __init__(self, gripper_interface):
        # type: (HiwinGripperInterface) -> None
        """Initialize Robot's state publisher.
        :param
            robot_interface: HiwinRobotInterface used to connect to the robot
        """
        self.gripper_interface = gripper_interface
        self.gripper_name = self.gripper_interface.name
        self.pub_joint_states = rospy.Publisher('/joint_states',
                                                JointState,
                                                queue_size=10)
        self.ip = None
        self.robot_handler = None
        self.__keep_running = False
        self.__thread = None

    def start(self):
        """Begin the thread that runs the self.__run() function."""
        self.__keep_running = True
        self.__thread = threading.Thread(
            name="HiwinGripperJointStatePublisher",
            target=self.__run
        )
        self.__thread.daemon = True
        self.__thread.start()

    def __run(self):
        """Read the robot's axis, publish on the joint_states topic."""
        global last_joint_states_lock
        while self.__keep_running:
            rospy.sleep(0.1)
            # If the gripper is moving, we cannot get the current position
            if self.gripper_interface.is_moving():
                continue
            # Get the current gripper position
            position = self.gripper_interface.get_current_position()
            msg = JointState()
            msg.header.stamp = rospy.get_rostime()
            msg.header.frame_id = ""
            msg.name = JOINTS_NAMES
            msg.position = [position/2 for _ in range(len(JOINTS_NAMES))]
            msg.velocity = [0] * 2
            msg.effort = [0] * 2
            # Publish the current position to /joint_states topic
            self.pub_joint_states.publish(msg)
            with last_joint_states_lock:
                pass


class HiwinGripperTrajectoryFollower(object):
    """Class used to control the gripper"""
    RATE = 0.02

    def __init__(self, gripper_interface):
        # type: (HiwinGripperInterface) -> None
        self.gripper_interface = gripper_interface
        self.gripper_name = self.gripper_interface.name
        self.server = actionlib.ActionServer(self.gripper_name +
                                             "/follow_joint_trajectory",
                                             FollowJointTrajectoryAction,
                                             self.on_goal, self.on_cancel,
                                             auto_start=False)
        self.goal_handle = None
        self.received_trajectory = None
        self.goal_position = None
        self.__keep_running = False
        self.__thread = None

        # For fake controller
        self.pub_joint_states = rospy.Publisher('/joint_states', JointState,
                                                queue_size=1)
        self.update_timer = rospy.Timer(rospy.Duration(self.RATE),
                                        self._update)

    def start(self):
        """Begin the thread that runs the self.server.start function."""
        self.__keep_running = True
        self.__thread = threading.Thread(name="HiwinGripperControlNode",
                                         target=self.server.start)
        self.__thread.daemon = True
        self.__thread.start()
        self.__keep_running = False

    def on_goal(self, goal_handle):
        """When a trajectory has been received from move_group, execute it."""
        # Communicate that the goal has been accepted
        if self.goal_handle:
            self.goal_handle.set_canceled()
            self.goal_handle = None
        self.goal_handle = goal_handle
        self.goal_handle.set_accepted()

        rospy.loginfo("Trajectory received and accepted")
        # Read the received trajectory
        self.received_trajectory = goal_handle.get_goal().trajectory
        # type: JointTrajectory

        target = self.received_trajectory.points[-1].positions
        # Read the goal effort: this will tell the gripper if it has
        # to move or to grip with strenght
        effort = self.received_trajectory.points[-1].effort

        rospy.loginfo("The trajectory has a total of {} points."
                      .format(len(self.received_trajectory.points)))
        rospy.logdebug("Target's position is described below:\n {}"
                       .format(target))
        self.goal_position = target[0]  # The fingers joints are dependent

        if len(effort) == 0 or effort[0] == 0:
            self.gripping = False
            self.gripper_interface.run_move(self.goal_position)
        else:
            self.gripping = True
            self.gripper_interface.run_grip(self.goal_position,
                                            effort=effort[0])

    def on_cancel(self, _):
        """When a trajectory is canceled, stop the robot."""
        rospy.logwarn("Trajectory was canceled before reaching goal.")
        # Stop the Robot in the current position
        self.gripper_interface.stop_motion()
        self.goal_handle.set_canceled()
        self.goal_handle = None
        self.received_trajectory = None
        self.goal_position = None
        self.gripping = False

    def _update(self, event):
        """ Check if the goal has been reached.

        Logic: The goal is reached if one of the two conditions are true:
            1. The position of the gripper is equal to the goal and the gripper
               is not moving. (condition for simple movements)
            2. The gripper is holding an object. (condition for gripping
               movements)
        """
        # If there is no goal, the goal is reached
        if self.goal_position is None or self.goal_handle is None:
            return

        # Condition #1
        if not self.gripping:  # Simple movement, no gripping
            goal_reached = \
                self.gripper_interface.is_in_position(self.goal_position) and \
                not self.gripper_interface.is_moving()
        # Condition #2
        elif self.gripping:  # The task is a grip movement
            goal_reached = self.gripper_interface.is_holding_object()

        if goal_reached:
            self.goal_handle.set_succeeded()
            self.goal_handle = None
            self.received_trajectory = None
            self.goal_position = None
            self.gripping = False
            return


if __name__ == '__main__':
    # Get the arguments
    arg_parser = argparse.ArgumentParser("Driver Node")
    arg_parser.add_argument("--gripper_com_port", help="COM port of gripper",
                            type=int)
    arg_parser.add_argument("--gripper_model", help="Model of the gripper (e.g."
                                                    " 32, 64)",
                            type=str, default="none", required=True)
    arg_parser.add_argument("--gripper_name", help="Name of the gripper",
                            type=str, default="none", required=False)
    arg_parser.add_argument("--log_level", help="Logging level: INFO, DEBUG",
                            type=str, default="INFO", required=False)
    arg_parser.add_argument("__name")
    arg_parser.add_argument("__log")
    args = arg_parser.parse_args()

    # Extract the necessary arguments
    gripper_com_port = args.gripper_com_port
    gripper_model = args.gripper_model
    gripper_name = args.gripper_name
    if args.log_level == "DEBUG" or args.log_level == "debug":
        log_level = rospy.DEBUG
    else:
        log_level = rospy.INFO

    # Start the ROS node
    rospy.init_node('hiwin_gripper_driver',
                    log_level=log_level,
                    disable_signals=True)
    if rospy.get_param("use_sim_time", False):
        rospy.logwarn("use_sim_time is set!!!")

    gripper = HiwinGripperInterface(comport=gripper_com_port,
                                    model=gripper_model,
                                    name=gripper_name)

    # Highest priority: start the controllers for the gripper.
    # (If the controller don't start in time, MoveIt! won't work.)
    # Start gripper controller
    gripper_action_server = HiwinGripperTrajectoryFollower(gripper)
    gripper_action_server.start()

    # Connect to the robot
    gripper.connect()

    # Start joint states publisher for the robot
    gripper_joints_publisher = HiwinGripperStatePublisher(gripper)
    gripper_joints_publisher.start()

    try:
        while not rospy.is_shutdown():
            time.sleep(1)
    except KeyboardInterrupt:
        pass
