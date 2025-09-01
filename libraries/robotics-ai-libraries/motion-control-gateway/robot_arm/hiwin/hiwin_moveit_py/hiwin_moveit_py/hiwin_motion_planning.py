# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
"""
A basic example of planning and executing a pose goal with moveit_py.
"""

import time
import rclpy
import numpy as np
import PyKDL
from math import pi
from numpy import random
from rclpy.logging import get_logger
from geometry_msgs.msg import PoseStamped
from ament_index_python.packages import get_package_share_directory
from trajectory_msgs.msg import JointTrajectory

# moveit python library
from moveit.planning import MoveItPy
from moveit.core.robot_state import RobotState

# ik library
from urdf_parser_py.urdf import Robot
from pykdl_utils.kdl_parser import kdl_tree_from_urdf_model
from pykdl_utils.kdl_kinematics import KDLKinematics
from pykdl_utils.posemath import *


import socket
import logging
import time
import datetime as dt
import json

import pymodbus.client as ModbusClient
from pymodbus import (
    ExceptionResponse,
    Framer,
    ModbusException,
    pymodbus_apply_logging_config,
)

###############
from geometry_msgs.msg import TransformStamped
from tf2_ros.static_transform_broadcaster import StaticTransformBroadcaster
from rclpy.node import Node
import sys
###############

z_action_diff = 0.550 # 0.265 -> 0.465
pos_action_diff = 0.05

class StaticFramePublisher(Node):
    """
    Broadcast transforms that never change.

    This example publishes transforms from `world` to a static turtle frame.
    The transforms are only published once at startup, and are constant for all
    time.
    """

    def __init__(self, transformation):
        super().__init__('static_turtle_tf2_broadcaster')
        self.tf_static_broadcaster = StaticTransformBroadcaster(self)

    def make_transforms(self, pos_x, pos_y, pos_z, rot_x, rot_y, rot_z, rot_w):
        t = TransformStamped()

        t.header.stamp = self.get_clock().now().to_msg()
        t.header.frame_id = 'base'
        t.child_frame_id = 'pick_object'
        t.transform.translation.x = float(pos_x)
        t.transform.translation.y = float(pos_y)
        t.transform.translation.z = float(pos_z)
        t.transform.rotation.x = float(rot_x)
        t.transform.rotation.y = float(rot_y)
        t.transform.rotation.z = float(rot_z)
        t.transform.rotation.w = float(rot_w)

        self.tf_static_broadcaster.sendTransform(t)

class TrajectoryPublisherNode(Node):
    """
    : Publish the joint_trajectory msg of moveit2 to run_hiwim_plc
    """
    def __init__(self):
        super().__init__('trajectory_pub_node_py')
        self.pub = self.create_publisher(
            JointTrajectory,
            '/fake_joint_trajectory_controller/joint_trajectory',
            1)

    def pub_trajectory(self, trajectory):
        self.pub.publish(trajectory)

class LLMTaskExecutor(Node):

    def __init__(self):
        self.logger = get_logger("hiwin_moveit_py")
        self.logger.info("MoveItPy setup Done")

        # instantiate MoveItPy instance and get planning component
        self.hiwin_py = MoveItPy(node_name="moveit_py")
        self.hiwin_arm = self.hiwin_py.get_planning_component("manipulator")
        self.logger.info("MoveItPy instance created")

        file_path=get_package_share_directory("hiwin_robot_moveit_config") + "/xacros/hiwin_robot_and_gripper.urdf"
        with open(file_path, encoding="utf-8") as f:
            self.robot = Robot.from_xml_string(f.read())
            f.close()
        self.kdl_kin = KDLKinematics("kdl_kinematics")

        base_link = "base_link"
        end_link = "tool0"
        self.logger.info("Root link: %s; end link: %s" % (base_link, end_link))
        self.kdl_kin.setup(self.robot, base_link, end_link)
        self.curr_pose = None

        # modbus TCP IO
        pymodbus_apply_logging_config("INFO")
        self.modbus_client = ModbusClient.ModbusTcpClient(
            "192.168.1.200",
            port="502",
            framer=Framer.SOCKET,
            # timeout=10,
            # retries=3,
            # retry_on_empty=False,y
            # source_address=("localhost", 0),
        )
        self.modbus_client.connect()
        self.logger.info("Modbus TCP create done.")

    def write_coils(self, addr, value):
        self.modbus_client.close()
        time.sleep(0.1)
        self.modbus_client.connect()
        try:
            ww = self.modbus_client.write_coil(addr, value, slave=1)
            self.logger.info("write addr: %d, value: %d" %(addr, value))
        except ModbusException as exc:
            self.logger.info("Received ModbusException(%s) from library" %(exc))
            self.modbus_client.close()
            return False
        if ww.isError():
            self.logger.error("Received Modbus library error (%s)" %(ww))
            self.modbus_client.close()
            return False
        if isinstance(ww, ExceptionResponse):
            self.logger.error("Received Modbus library exception (%s)" %(ww))
            self.modbus_client.close()
            # THIS IS NOT A PYTHON EXCEPTION, but a valid modbus message


    def prepare_state(self):
        global traj_pub_node
        ###################################################################
        # Resets the robot arm to its default position.
        ###################################################################

        # set goal state to the initialized robot state
        self.logger.info("set_start_state: ready")
    #    hiwin_arm.set_start_state(configuration_name="home")
        self.hiwin_arm.set_start_state_to_current_state()
        self.hiwin_arm.set_goal_state(configuration_name="ready")

        # plan to goal
        self.logger.info("Planning trajectory to: ready")
        plan_result = self.hiwin_arm.plan()

        # execute the plan
        if plan_result:
            self.logger.info("Executing plan")
            robot_trajectory = plan_result.trajectory
            msg = robot_trajectory.get_robot_trajectory_msg()
            traj_pub_node.pub_trajectory(msg.joint_trajectory)
            self.logger.info("Executing done")
        else:
            self.logger.error("Planning failed")
        self.logger.info("prepare_state done")
        time.sleep(3)

    def get_pick_pose(self, obj_name):
        ###################################################################
        # Determines the picking position for the object identified by `obj_name` and assigns it to `target_pose`.
        # Parameters:
        #   obj_name:
        ###################################################################
        # TBD
        self.logger.info("get_pick_name obj: "+obj_name)
        
        # f1 = PyKDL.Frame(PyKDL.Rotation.RPY(0, 0, 0), PyKDL.Vector(-0.2354, -0.1453, 0))
        f1 = PyKDL.Frame(PyKDL.Rotation.RPY(0, 0, 0), PyKDL.Vector(random.rand() * 0.2 - 0.4, random.rand() * 0.6 - 0.3, 0))
        f2 = PyKDL.Frame(PyKDL.Rotation.RPY(pi, 0, 0), PyKDL.Vector(0, 0, z_action_diff))
        f = f1 * f2

        pick_pose = PoseStamped()
        pick_pose.header.frame_id = "base_link"
        pick_pose.pose = toMsg(f)
        self.logger.info("pick position x:%f, y:%f, z:%f" %
                         (pick_pose.pose.position.x,
                          pick_pose.pose.position.y,
                          pick_pose.pose.position.z))
        self.logger.info("pick quaternion w:%f, x:%f, y:%f, z:%f" %
                         (pick_pose.pose.orientation.w,
                          pick_pose.pose.orientation.x,
                          pick_pose.pose.orientation.y,
                          pick_pose.pose.orientation.z))
        self.logger.info("get_pick_pose done")
        time.sleep(1)
        return pick_pose

    def get_place_pose(self, obj_name):
        ###################################################################
        # Determines the placement position for the object identified by `obj_name` and assigns it to `target_pose`.
        # Parameters:
        #   obj_name
        ###################################################################
        # TBD
        self.logger.info("get_place_pose obj: "+ obj_name)

        # f1 = PyKDL.Frame(PyKDL.Rotation.RPY(0, 0, 0), PyKDL.Vector(-0.1322, 0.23249, 0))
        f1 = PyKDL.Frame(PyKDL.Rotation.RPY(0, 0, 0), PyKDL.Vector(random.rand() * 0.2 - 0.4, random.rand() * 0.6 - 0.3, 0))
        f2 = PyKDL.Frame(PyKDL.Rotation.RPY(pi, 0, 0), PyKDL.Vector(0, 0, z_action_diff))
        f = f1 * f2

        place_pose = PoseStamped()
        place_pose.header.frame_id = "base_link"
        place_pose.pose = toMsg(f)
        self.logger.info("place position x:%f, y:%f, z:%f" % 
                         (place_pose.pose.position.x,
                          place_pose.pose.position.y,
                          place_pose.pose.position.z))
        self.logger.info("place quaternion w:%f, x:%f, y:%f, z:%f" %
                         (place_pose.pose.orientation.w,
                          place_pose.pose.orientation.x,
                          place_pose.pose.orientation.y,
                          place_pose.pose.orientation.z))
        self.logger.info("get_place_pose done")
        time.sleep(1)
        return place_pose

    def move(self, target_pose):
        global traj_pub_node
        if target_pose is None:
            return
        else:
            self.logger.info("move target position x:%f, y:%f, z:%f" %
                         (target_pose.pose.position.x,
                          target_pose.pose.position.y,
                          target_pose.pose.position.z))

        ###################################################################
        # Moves the robot arm to the position specified by `target_pose`.
        # Parameters:
        #   target_pose
        ###################################################################
        #q1 = np.array([0.0, 0.0, 0.0, 0.0, -1.571, 0.0])
        q1 = np.array([0.5591042132690773,-0.5041970990289314,-0.39331798054413175,0.0,-0.6677107642031672,0.559962075118857])
        homo_mat, quat, rot_euler = self.kdl_kin._extract_pose_msg(target_pose.pose)
        q_new = self.kdl_kin.inverse(homo_mat, q_guess=q1)
        self.logger.info("IK result q_new_1: {} {}".format(q_new,homo_mat))
        if q_new is None:
            self.logger.error("Error: IK failure q1 ")

            #q2 = np.array([1.1182, 0.62579, -1.50989, -0.565224, -1.572, -0.19405])
            q2 = np.array([-0.5500523367111487,-0.45985017957493285,-0.3990692119236363,0.0,-0.7123016825546168,-0.5503379430013053])
            homo_mat, quat, rot_euler = self.kdl_kin._extract_pose_msg(target_pose.pose)
            q_new = self.kdl_kin.inverse(homo_mat, q_guess=q2)
            self.logger.info("IK result q_new_2: {} {}".format(q_new,homo_mat))

            if q_new is None:
                self.logger.error("Error: IK failure q2 ")
                if target_pose.header.frame_id == "place_pos":
                    q_new = q2
                else:
                    return

        robot_model = self.hiwin_py.get_robot_model()
        robot_state = RobotState(robot_model)
        # set constraints message
        joint_values = {
            "joint_1": q_new[0],
            "joint_2": q_new[1],
            "joint_3": q_new[2],
            "joint_4": q_new[3],
            "joint_5": q_new[4],
            "joint_6": q_new[5],
        }
        robot_state.joint_positions = joint_values

        # set plan start state to current state
        self.hiwin_arm.set_start_state_to_current_state()
        # self.hiwin_arm.set_goal_state(pose_stamped_msg=target_pose, pose_link="tool0")
        self.hiwin_arm.set_goal_state(robot_state=robot_state)

        # plan to goal
        self.logger.info("Planning trajectory...")
        plan_result = self.hiwin_arm.plan()

        # execute the plan
        if plan_result:
            self.logger.info("Executing plan")
            robot_trajectory = plan_result.trajectory
            msg = robot_trajectory.get_robot_trajectory_msg()
            traj_pub_node.pub_trajectory(msg.joint_trajectory)
            self. logger.info("Executing done")
            self.curr_pose = target_pose
        else:
            self.logger.error("Planning failed")

        self.logger.info("move done")
        time.sleep(3)

    def suck(self):
        if self.curr_pose == None:
            return
        pick_pose_move = self.curr_pose
        ###################################################################
        # Activates the suction cup to pick up an object.
        ###################################################################
        self.logger.info("Enter suck")
        f1 = fromMsg(pick_pose_move.pose)
        f2 = PyKDL.Frame(PyKDL.Rotation.RPY(0, 0, 0), PyKDL.Vector(0, 0, pos_action_diff))
        f = f1 * f2
        pick_pose_move.pose = toMsg(f)
        self.logger.info("position x:%f, y:%f, z:%f" %
                         (pick_pose_move.pose.position.x,
                          pick_pose_move.pose.position.y,
                          pick_pose_move.pose.position.z))
        self.logger.info("quaternion w:%f, x:%f, y:%f, z:%f" %
                         (pick_pose_move.pose.orientation.w,
                          pick_pose_move.pose.orientation.x,
                          pick_pose_move.pose.orientation.y,
                          pick_pose_move.pose.orientation.z))
        self.logger.info("open pump!!!")
        self.write_coils(16, 1) # 17-1
        self.move(pick_pose_move)
        time.sleep(1)
        self.logger.info("Move end done")

        pick_pose_move.pose = toMsg(f1)
        self.logger.info("position x:%f, y:%f, z:%f" %(pick_pose_move.pose.position.x,
                                                pick_pose_move.pose.position.y,
                                                pick_pose_move.pose.position.z))
        self.logger.info("quaternion w:%f, x:%f, y:%f, z:%f" %(pick_pose_move.pose.orientation.w,
                                                        pick_pose_move.pose.orientation.x,
                                                        pick_pose_move.pose.orientation.y,
                                                        pick_pose_move.pose.orientation.z))
        self.move(pick_pose_move)
        self.logger.info("suck done")
        time.sleep(1)

    def release(self):
        if self.curr_pose == None:
            return
        place_pose_move = self.curr_pose
        ###################################################################
        # Deactivates the suction cup to release an object.
        ###################################################################
        f1 = fromMsg(place_pose_move.pose)
        f2 = PyKDL.Frame(PyKDL.Rotation.RPY(0, 0, 0), PyKDL.Vector(0, 0, pos_action_diff))
        f = f1 * f2
        place_pose_move.pose = toMsg(f)
        self.move(place_pose_move)
        self.logger.info("close pump!!!")
        self.write_coils(16, 0) # 17-1
        time.sleep(1) # TBD

        place_pose_move.pose = toMsg(f1)
        self.move(place_pose_move)
        self.logger.info("release done")
        time.sleep(1)

obj_info = {}
logger = get_logger("hiwin_moveit_py")

def set_obj_info(obj_info_str):
    global obj_info
    obj_info = json.loads(obj_info_str)


def prepare_state():
    return te.prepare_state()

def move(target_pose):
    return te.move(target_pose)

def suck():
    return te.suck()

def release():
    return te.release()


def get_pick_pose(obj_name):
    global obj_info
    global tf_node
    for obj in obj_info.values():
        if obj_name == obj['Name']:
            f_camera2base = PyKDL.Frame(
                    # x,y,z,w
                    PyKDL.Rotation.Quaternion(0.6904693334559218, 0.005276056519509131, -0.7231237096779546, 0.01778660412026753),
                    PyKDL.Vector(-0.4456467965265069, 0.24128339493150574, 0.5251393550585481))
                    # -0.3836467965265069, 0.23828339493150574, 0.5251393550585481
            f_optical2camera = PyKDL.Frame(
                    PyKDL.Rotation.Quaternion(-0.501311, 0.49979, -0.494814, 0.50404),
                    PyKDL.Vector(-0.000360718, 0.014533, 0.0))
            f_obj2optical = PyKDL.Frame(PyKDL.Rotation.RPY(0, 0, 0),
                             PyKDL.Vector(obj['centerX'], obj['centerY'], obj['centerZ']))
#            f_obj2optical = PyKDL.Frame(PyKDL.Rotation.RPY(0, 0, 0),
#                             PyKDL.Vector(0.12512, 0.19938, 1.0547))
            f_cal = f_camera2base * f_optical2camera * f_obj2optical

            f1 = PyKDL.Frame(PyKDL.Rotation.RPY(0, 0, 0),
                             PyKDL.Vector(f_cal.p[0], f_cal.p[1], f_cal.p[2]))
            f2 = PyKDL.Frame(PyKDL.Rotation.RPY(pi, 0, 0), PyKDL.Vector(0, 0, z_action_diff))
            f = f1 * f2

            tf_node.make_transforms(f.p[0], f.p[1], f.p[2],
                    f.M.GetQuaternion()[0],
                    f.M.GetQuaternion()[1],
                    f.M.GetQuaternion()[2],
                    f.M.GetQuaternion()[3])

            pick_pose = PoseStamped()
            pick_pose.header.frame_id = "base_link"
            pick_pose.pose = toMsg(f)
            logger.info("pick position x:%f, y:%f, z:%f" %
                        (obj['centerX'],
                         obj['centerY'],
                         obj['centerZ']))
            return pick_pose
    return None


def get_place_pose(obj_name):
    global obj_info
    for obj in obj_info.values():
        if obj_name == obj['Name']:
            f1 = PyKDL.Frame(PyKDL.Rotation.RPY(0, 0, 0),
                             PyKDL.Vector(0.22587, 0.3713, 0.26089))
                                         # X, Y, Z
            f2 = PyKDL.Frame(PyKDL.Rotation.RPY(pi, 0, 0), PyKDL.Vector(0, 0, 0))
            f = f1 * f2

            place_pose = PoseStamped()
            place_pose.header.frame_id = "place_pos"
            place_pose.pose = toMsg(f)
            place_pose.pose.orientation.w = 0.0
            place_pose.pose.orientation.x = 0.991656
            place_pose.pose.orientation.y = 0.128914
            place_pose.pose.orientation.z = 0.0
            # if not obj_name == 'Default':
            #     logger.info("place position x:%f, y:%f, z:%f" %
            #                 (obj['centerX'],
            #                  obj['centerY'],
            #                  0))
            return place_pose
    return None

class PrimitiveActionServer:
    def __init__(self, logger, host='localhost', port=8099):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.bind((host, port))
        self.msg = None
        self.logger = logger

    def read(self, conn: socket.socket = None):
        try:
            data = conn.recv(1024).decode()
        except Exception as e:
            self.logger.info(f"recv failed: {e}")
            return
        self.logger.info(f"{data}")
        return data


    def write(self, success, conn: socket.socket = None):
        msg = f"{dt.datetime.now()} [{success}] - {self.msg}"
        self.logger.info(f"{msg}")
        try:
            conn.send(msg.encode())
        except Exception as e:
            self.logger.info(f"send failed: {e}")
            return

    def execute(self, msg):
        code_statements = msg.split('\n')

        for statement in code_statements:
            try:
                self.logger.info(f"Executed: {statement}")
                exec(statement)
            except Exception as e:
                self.logger.info(f"Error executing statement: {statement}\nException: {e}")
                return False
        return True

    def serve(self):
        self._sock.listen()
        self.logger.info("Serving...")
        while True:
            self.logger.info("Waiting for connection...")
            conn, addr = self._sock.accept()
            self.logger.info(f"Recived new conn: {conn} from {addr}")
            self.msg = self.read(conn)
            result = self.execute(self.msg)
            self.write(result, conn)

def main():

    ###################################################################
    # MoveItPy Setup
    ###################################################################
    rclpy.init()
    logger.info("- MoveItPy Setup Done")

    global tf_node
    tf_node = StaticFramePublisher(sys.argv)

    global traj_pub_node
    traj_pub_node = TrajectoryPublisherNode()

    global te
    te = LLMTaskExecutor()

    ###################################################################
    # LLM API process begin

    # LLM API process end
    ###################################################################

    primServer = PrimitiveActionServer(logger)
    primServer.serve()
    print("1"*40, flush=True)

    while True:
        time.sleep(1)

    disconnect_device()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
