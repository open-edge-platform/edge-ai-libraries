# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
import rospy
import time
import actionlib
import threading
import argparse

from control_msgs.msg import FollowJointTrajectoryAction
from control_msgs.msg import FollowJointTrajectoryFeedback
from sensor_msgs.msg import JointState
from std_msgs.msg import String

from hiwin_robot_interface import HiwinRobotInterface

JOINTS_NAMES = ['joint_1', 'joint_2', 'joint_3',
                'joint_4', 'joint_5', 'joint_6']
last_joint_states_lock = threading.Lock()

DEBUG = True  # Set True to show debug log, False to hide it.


class HiwinRobotStatesPublisher(object):
    """Reads robot joints' states and publish them on the joint_state topic."""
    def __init__(self, robot_interface):
        # type: (HiwinRobotInterface) -> None
        """Initialize Robot's state publisher.
        :param
            robot_interface: HiwinRobotInterface used to connect to the robot
        """
        self.robot_interface = robot_interface
        self.robot_name = self.robot_interface.name
        self.pub_joint_states = rospy.Publisher('/joint_states',
                                                JointState,
                                                queue_size=100)
        self.ip = None
        self.robot_handler = None
        self.__keep_running = False
        self.__thread = None

    def start(self):
        """Begin the thread that runs the self.__run() function."""
        self.__keep_running = True
        self.__thread = threading.Thread(name="HiwinRobotJointStatePublisher",
                                         target=self.__run)
        self.__thread.daemon = True
        self.__thread.start()

    def __run(self):
        """Read the robot's axis, publish on the joint_states topic."""
        global last_joint_states_lock
        while self.__keep_running:
            result, joints = self.robot_interface.get_current_joints()
            msg = JointState()
            msg.header.stamp = rospy.get_rostime()
            msg.name = [self.robot_name+"/".join(["", joint_name]) for joint_name in JOINTS_NAMES]
            msg.position = joints
            self.pub_joint_states.publish(msg)
            rospy.sleep(0.01)
            with last_joint_states_lock:
                pass


class HiwinDIOPublisher(object):
    def __init__(self, robot_interface):
        # type: (HiwinRobotInterface) -> None
        """Initialize Robot's state publisher.
        :param
            robot_interface: HiwinRobotInterface used to connect to the robot
        """
        self.robot_interface = robot_interface
        self.robot_name = self.robot_interface.name
        self.pub_dig_in = rospy.Publisher(self.robot_name + '/digital_input',
                                          String, queue_size=10)
        self.pub_dig_out = rospy.Publisher(self.robot_name + '/digital_output',
                                           String, queue_size=10)
        self.ip = None
        self.robot_handler = None
        self.__keep_running = False
        self.__thread_i = None
        self.__thread_o = None

    def start(self):
        """Begin the thread that runs the self.__run() function."""
        self.__keep_running = True
        self.__thread_i = threading.Thread(name="HiwinDIPublisher",
                                           target=self.__run_i)
        self.__thread_i.daemon = True
        self.__thread_i.start()

        self.__thread_o = threading.Thread(name="HiwinDOPublisher",
                                           target=self.__run_o)
        self.__thread_o.daemon = True
        self.__thread_o.start()

    def __run_i(self):
        """Read the robot's axis, publish on the joint_states topic."""
        global last_joint_states_lock
        while self.__keep_running:
            inputs = self.robot_interface.get_current_digital_inputs()
            msg = String()
            msg.data = "".join([str(i)+" " for i in inputs])
            self.pub_dig_in.publish(msg)
            rospy.sleep(0.1)
            with last_joint_states_lock:
                pass

    def __run_o(self):
        """Read the robot's axis, publish on the joint_states topic."""
        global last_joint_states_lock
        while self.__keep_running:
            outputs = self.robot_interface.get_current_digital_outputs()
            msg = String()
            msg.data = "".join([str(o)+" " for o in outputs])
            self.pub_dig_out.publish(msg)
            rospy.sleep(0.1)
            with last_joint_states_lock:
                pass


class HiwinDOSetter(object):
    def __init__(self, robot_interface):
        # type: (HiwinRobotInterface) -> None
        """Initialize Robot's state publisher.
        :param
            robot_interface: HiwinRobotInterface used to connect to the robot
        """
        self.robot_interface = robot_interface
        self.robot_name = self.robot_interface.name
        self.set_dig_out = rospy.Subscriber(self.robot_name +
                                            '/set_digital_output',
                                            String, callback=self.__set_do,
                                            queue_size=10)
        self.ip = None
        self.robot_handler = None
        self.__keep_running = False
        self.__thread_i = None
        self.__thread_o = None

    def __set_do(self, msg):  # type: (String) -> None
        if not self.robot_interface.is_connected():
            self.robot_interface.reconnect()
        try:
            do_index, do_value = msg.data.split(" ")
            self.robot_interface.set_io_value(int(do_index), bool(int(do_value)==1))
        except:
            rospy.logwarn_once("Set DO Message format is wrong, expected 'DO_INDEX DO_VALUE' (e.g. '12 1') but got {}".format(msg.data))
        

class HiwinRobotTrajectoryFollower(object):
    """Class used to make the robot follow the trajectory given by MoveIt!"""
    RATE = 0.02

    def __init__(self, robot_interface):
        # type: (HiwinRobotInterface) -> None
        self.robot_interface = robot_interface
        self.robot_name = self.robot_interface.name
        self.server = actionlib.ActionServer(self.robot_name +
                                             "/follow_joint_trajectory",
                                             FollowJointTrajectoryAction,
                                             self.on_goal, self.on_cancel,
                                             auto_start=False)
        rospy.Subscriber("manipulator/taskstart", String,
                         callback=self.taskstart_topic_callback, queue_size=10)
        self.pub_feedback_states = rospy.Publisher(
            '/feedback_states',
            FollowJointTrajectoryFeedback,
            queue_size=10 )
        self.goal_handle = None
        self.start_time = 0
        self.received_trajectory = None  # Store last received trajectory
        self.trajectory_to_execute = None  # Once executed, it will be deleted
        self.target = None
        self.update_timer = rospy.Timer(rospy.Duration(self.RATE),
                                        self._update)
        self.__keep_running = False
        self.__thread = None

    def start(self):
        """Begin the thread that runs the self.server.start function."""
        self.__keep_running = True
        self.__thread = threading.Thread(name="HiwinRobotControlNode",
                                         target=self.server.start)
        self.__thread.daemon = True
        self.__thread.start()
        self.__keep_running = False

    def on_goal(self, goal_handle):
        """When a trajectory has been received from move_group, execute it.

        Main idea: the trajectory is composed by many points. We move point to
            point (PTP) from each point to the next one. Note: as today, we
            do not take care of the time execution of the trajectory. For
            example, we do not care about the velocity of the trajectory that
            has been received. In future it is needed to add this possibility.
        """
        # Check if there is another goal on the go
        if self.goal_handle:
            self.on_cancel(None)
        # Communicate that the goal has been accepted
        self.goal_handle = goal_handle
        self.goal_handle.set_accepted()

        rospy.loginfo("Trajectory received and accepted")
        # Read the trajectory
        self.start_time = rospy.Time.now()
        self.received_trajectory = goal_handle.get_goal().trajectory
        self.trajectory_to_execute = goal_handle.get_goal().trajectory

        # Print out the target final point
        self.target = self.received_trajectory.points[-1].positions
        rospy.loginfo("The trajectory has a total of {} points."
                      .format(len(self.received_trajectory.points)))

    def on_cancel(self, _):
        """When a trajectory is canceled, stop the robot."""
        rospy.logwarn("Trajectory was canceled before reaching goal.")
        # Stop the Robot in the current position
        self.robot_interface.stop_motion()
        self.trajectory_to_execute = None
        self.target = None
        self.goal_handle.set_canceled()
        self.goal_handle = None

    def _update(self, event):
        """Manage trajectory goal_handle and publish the feedback"""
        # Publish the current feedback states of the robot
        self.publish_feedback()

        # If there is no goal pending, do nothing.
        if not self.goal_handle:
            return

        # If the goal has been reached, set goal successfully reached.
        if self.target is not None:
            if self.goal_reached(self.target):
                rospy.loginfo("Trajectory completed. Goal reached!")
                self.goal_handle.set_succeeded()
                self.goal_handle = None
                self.trajectory_to_execute = None
                self.target = None
                return

        # If there's no position trajectory to be executed, do nothing.
        if self.trajectory_to_execute is None:
            return

        # If a position trajectory need to be executed, execute it:
        #   for each point in the trajectory execute Point-To-Point movement
        #   (note that the first point is always the starting point)
        for point in self.trajectory_to_execute.points[1:]:
            # Read the target values of the joints
            target_joints = [joint for joint in point.positions]
            # Make sure the goal has not been canceled meanwhile
            if not self.goal_handle:
                break
            # Move to the target joints
            self.robot_interface.move_ptp(target_axis_values=target_joints)

        # The trajectory has been executed, forget it.
        self.trajectory_to_execute = None

    def goal_reached(self, target_joint_states):
        # type: (list[float]) -> bool
        """Returns True if the robot has achieved the goal, False otherwise.

        To reach the goal means:
          1. Be near the goal
          2. Not moving (being in IDLE state)

        :param
            target_joint_states: The goal states (in radians)
        """
        state_reached = self.robot_interface.is_in_state(target_joint_states)
        not_moving = self.robot_interface.is_in_idle()
        return state_reached and not_moving

    def publish_feedback(self):
        """Publishes the position feedback of the robot.

        The feedback is the difference between the desired states and the
        current ones.
        """
        # If there is no trajectory, there is nothing to do
        if self.received_trajectory is None:
            return

        # Get the current states of the joints
        success, current_joints_states = \
            self.robot_interface.get_current_joints()

        if not success:  # Couldn't get the current joints' state
            rospy.logwarn("Could not publish on feedback_states:"
                          "current states are unknown. Assuming all to 0.")
            current_joints_states = [0 for _ in range(6)]

        # Get the desired position. What should the robot joints be right now?
        time_from_start = rospy.Time.now() - self.start_time
        # Find which point represents the current desired position
        for point in self.received_trajectory.points:
            if time_from_start > point.time_from_start:
                continue
            break
        desired_point = point

        # Make sure the length of the current states and the target states
        # is exactly the length of the joints
        assert len(JOINTS_NAMES) == len(current_joints_states) and \
            len(JOINTS_NAMES) == len(desired_point.positions), \
            "Target and current states have different length. " \
            "Expected {} joints, got {} (target) and {} (current)".format(
                len(JOINTS_NAMES), len(desired_point.positions),
                len(current_joints_states)
            )

        # Create the message to be published
        msg = FollowJointTrajectoryFeedback()
        msg.header.frame_id = ""
        msg.header.stamp = rospy.get_rostime()
        msg.joint_names = JOINTS_NAMES

        # Set the goal states4
        msg.desired.positions = desired_point.positions
        msg.desired.velocities = []
        msg.desired.accelerations = []
        msg.desired.effort = []
        msg.desired.time_from_start = desired_point.time_from_start

        # Set the actual states
        msg.actual.positions = current_joints_states
        msg.actual.velocities = []
        msg.actual.accelerations = []
        msg.actual.effort = []
        msg.actual.time_from_start = desired_point.time_from_start

        # Calculate the error
        position_error = [goal - current for goal, current in zip(
            msg.desired.positions, msg.actual.positions
        )]
        velocity_error = [goal - current for goal, current in zip(
            msg.desired.velocities, msg.actual.velocities
        )]
        acceleration_error = [goal - current for goal, current in zip(
            msg.desired.accelerations,
            msg.actual.accelerations
        )]
        effort_error = [goal - current for goal, current in zip(
            msg.desired.effort, msg.actual.effort
        )]

        # Set the errors
        msg.error.positions = position_error
        msg.error.velocities = velocity_error
        msg.error.accelerations = acceleration_error
        msg.error.effort = effort_error
        msg.error.time_from_start = desired_point.time_from_start

        # Publish the message on /feedback_states topic
        self.pub_feedback_states.publish(msg)

    def taskstart_topic_callback(self, msg): # type: (String) -> None
        if not self.robot_interface.is_connected():
            self.robot_interface.reconnect(trials=1, sec_between_trials=1)
        self.robot_interface.stop_task()
        if not self.robot_interface.is_connected():
            self.robot_interface.reconnect(trials=1, sec_between_trials=1)
        self.robot_interface.start_task(msg.data) == 0
        return


if __name__ == '__main__':
    # Get the arguments
    arg_parser = argparse.ArgumentParser("Driver Node")
    arg_parser.add_argument("--robot_ip", help="IP addr of the robot",
                            type=str)
    arg_parser.add_argument("--robot_name", help="Name of the robot", type=str)
    arg_parser.add_argument("--control_mode", help="Default is 1, set it to 0 if you do not want to control the robot, but only to monitor its state.",
                            type=bool, default=1, required=False)
    arg_parser.add_argument("--log_level", help="Logging level: INFO, DEBUG",
                            type=str, default="INFO", required=False)
    arg_parser.add_argument("__name")
    arg_parser.add_argument("__log")
    args = arg_parser.parse_args()

    # Extract the necessary arguments
    robot_ip = args.robot_ip
    robot_name = args.robot_name
    control_mode = int(args.control_mode)
    if args.log_level == "DEBUG":
        log_level = rospy.DEBUG
    elif args.log_level == "ERROR":
        log_level = rospy.ERROR
    else:
        log_level = rospy.INFO

    # Start the ROS node
    rospy.init_node('hiwin_robot_sdk_'+robot_name,
                    log_level=log_level,
                    disable_signals=True)
    if rospy.get_param("use_sim_time", False):
        rospy.logwarn("use_sim_time is set!!!")

    robot_ctr = HiwinRobotInterface(robot_ip=robot_ip, connection_level=control_mode,
                                    name=robot_name)
    robot_ctr.connect()

    # Highest priority: start the controllers for the robot.
    # (If the controllers don't start in time, MoveIt! won't work.)
    # Start arm controller
    arm_action_server = HiwinRobotTrajectoryFollower(robot_ctr)
    arm_action_server.start()

    set_do_thread = HiwinDOSetter(robot_ctr)

    robot_mtr = HiwinRobotInterface(robot_ip=robot_ip, connection_level=0,
                                    name=robot_name)

    # Start joint states publisher for the robot
    hiwin_states_publisher = HiwinRobotStatesPublisher(robot_mtr)
    hiwin_states_publisher.start()

    # Start Digital I/O publisher for the robot
    hiwin_dio_publisher = HiwinDIOPublisher(robot_mtr)
    hiwin_dio_publisher.start()

    try:
        rospy.spin()
    except KeyboardInterrupt:
        pass