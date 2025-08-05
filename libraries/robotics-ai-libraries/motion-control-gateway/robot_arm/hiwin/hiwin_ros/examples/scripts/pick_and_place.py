# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
import rospy
import sys
import traceback
import time
import numpy as np

import moveit_commander
import moveit_msgs.msg
import geometry_msgs.msg
import tf.transformations
import tf
import trajectory_msgs.msg

FRAME_ID = "world"  # Reference frame used in all the code below
HOME_POSITION = [0, 0.7, -0.7, 0, -1.52, 0]
TOOL_LINK = "manipulator/tool0"


def set_gripper_posture(posture, set_close=False, set_open=False, effort=0):
    # type: (trajectory_msgs.msg.JointTrajectory, bool, bool) -> None
    """Set the gripper posture to 'open' or 'close' position

    :param posture: posture to set
    :param set_close: Set true to set it to close
    :param set_open: Set true to set it to open
    :param effort: [%] force used in gripping movement, set 0 if the movement
        is a simple move (no grip)
    """
    if set_close and not set_open:
        joint_position = 0.000
    elif set_open and not set_close:
        joint_position = 0.008
    else:  # Not clear what posture to set
        rospy.logwarn("Do not know how to set the gripper posture:"
                      "set_close={}, set_open={}".format(set_close, set_open))
        return
    posture.joint_names.append("eef_joint_finger_1")
    posture.joint_names.append("eef_joint_finger_2")
    posture.points = [trajectory_msgs.msg.JointTrajectoryPoint()]
    posture.points[0].positions.append(joint_position)
    posture.points[0].positions.append(joint_position)
    posture.points[0].time_from_start = rospy.Duration(secs=2, nsecs=0)
    posture.points[0].effort = [effort, effort]
    pass


def is_in_roi(pose):
    x = pose.position.x
    y = pose.position.y
    z = pose.position.z
    return x > -1 and x < 1 and y > 0.05 and y < 2 and z > -.01 and z < 0.5


def add_rnd_box(scene, name):
    # type: (moveit_commander.PlanningSceneInterface) -> None
    size = [0.02, 0.02, 0.02]
    # Set position
    pose = geometry_msgs.msg.PoseStamped()
    pose.header.frame_id = FRAME_ID
    pose.pose.position.x = 0.0 + 1.00 * (np.random.rand() - 0.5)
    pose.pose.position.y = 0.5 + 0.25 * (np.random.rand() - 0.5)
    pose.pose.position.z = 0.0 + 0.15 * np.random.rand()

    quaternion = \
        tf.transformations.quaternion_from_euler(0 + 0.0*(np.random.rand()-0.5),
                                                 0 + 0.0*(np.random.rand()-0.5),
                                                 0.0 + 0.0*(np.random.rand()-0.5))
    pose.pose.orientation.x = quaternion[0]
    pose.pose.orientation.y = quaternion[1]
    pose.pose.orientation.z = quaternion[2]
    pose.pose.orientation.w = quaternion[3]
    # Apply the objects to the scene
    #scene.add_mesh(name, filename=FILENAME, pose=pose, size=(0.001, 0.001, 0.001))
    scene.add_box(name, pose=pose, size=size)
    pass


class PickAndPlace:
    def __init__(self, group, scene):
        # type: (moveit_commander.MoveGroupCommander, moveit_commander.PlanningSceneInterface) -> None
        self.group = group
        self.scene = scene
        self.occupancy = np.zeros(shape=[4, 3, 8], dtype=int)

    def clear_scene(self):
        """Delete all the object from the scene and robot"""
        for object_name in self.scene.get_known_object_names():
            self.scene.remove_world_object(object_name)
        for object_name in self.scene.get_attached_objects():
            self.group.detach_object(object_name)
            self.scene.remove_world_object(object_name)

    def add_collision_objects(self):
        """Create collisions object in the scene"""
        # Add some .stl or objects in your scene here
        #scene.add_mesh(name, filename="C:\\Users\\...", pose=geometry_msgs.msg.PoseStamped(), size=(0.001, 0.001, 0.001))
        pass

    def get_free_place_pose(self):
        # type (None) -> geometrymsgs.msg.PoseStamped
        """Return the a pose to put an object (for pallet purposes)"""
        pose = geometry_msgs.msg.PoseStamped()
        pose.header.frame_id = FRAME_ID

        # Define the initial position of the pallet
        initial_point_x = 0.35
        initial_point_y = 0.00
        initial_point_z = 0.05

        # Find free place in the palletting matrix
        X, Y, Z = self.occupancy.shape
        found = False
        for z in range(Z):
            for y in range(Y):
                for x in range(X):
                    if self.occupancy[x, y, z] == 0:
                        self.occupancy[x, y, z] = 1
                        found = True
                        break
                    if found: break
                if found: break
            if found: break

        current_orientation = self.group.get_current_pose().pose.orientation
        q = [current_orientation.x,
             current_orientation.y,
             current_orientation.z,
             current_orientation.w]
        eul = tf.transformations.euler_from_quaternion(q)
        quaternion = tf.transformations.quaternion_from_euler(
            0,
            0,
            0
        )
        
        pose.pose.orientation.x = quaternion[0]
        pose.pose.orientation.y = quaternion[1]
        pose.pose.orientation.z = quaternion[2]
        pose.pose.orientation.w = quaternion[3]
        pose.pose.position.x = initial_point_x + 0.03*x
        pose.pose.position.y = initial_point_y - 0.03*y
        pose.pose.position.z = initial_point_z + 0.03*z

        return pose

    def pick(self, object_pose, object_id):
        """Pick up an object on the scene"""
        # Create a grasp position
        grasp = moveit_msgs.msg.Grasp()
        grasp.grasp_pose.header.frame_id = FRAME_ID

        # Create pre_grasp position
        set_gripper_posture(grasp.pre_grasp_posture, set_open=True, effort=0)

        # Set the pre_grasp_approach
        grasp.pre_grasp_approach.direction.header.frame_id = TOOL_LINK
        grasp.pre_grasp_approach.direction.vector.z = 1
        grasp.pre_grasp_approach.min_distance = 0.075
        grasp.pre_grasp_approach.desired_distance = 0.085
        rotation = tf.transformations.quaternion_from_euler(0, -3.14, 0)
        obj_quat = [
            object_pose.orientation.x,
            object_pose.orientation.y,
            object_pose.orientation.z,
            object_pose.orientation.w
        ]
        quaternion = tf.transformations.quaternion_multiply(obj_quat, rotation)
        grasp.grasp_pose.pose.orientation.x = quaternion[0]
        grasp.grasp_pose.pose.orientation.y = quaternion[1]
        grasp.grasp_pose.pose.orientation.z = quaternion[2]
        grasp.grasp_pose.pose.orientation.w = quaternion[3]

        # Set the position of the grasp
        grasp.grasp_pose.pose.position.x = object_pose.position.x
        grasp.grasp_pose.pose.position.y = object_pose.position.y
        grasp.grasp_pose.pose.position.z = object_pose.position.z

        # Set grasp posture
        set_gripper_posture(grasp.grasp_posture, set_close=True, effort=20)

        # Set the post_grasp_approach
        grasp.post_grasp_retreat.direction.header.frame_id = FRAME_ID
        grasp.post_grasp_retreat.direction.vector.z = 1
        grasp.post_grasp_retreat.min_distance = 0.075
        grasp.post_grasp_retreat.desired_distance = 0.085

        self.group.allow_replanning(2)
        self.group.set_max_velocity_scaling_factor(0.01)

        success = self.group.pick(object_name=object_id, grasp=grasp) == 1
        self.group.clear_path_constraints()
        return success

    def place(self, object_id):
        # type: (moveit_commander.MoveGroupCommander) -> None
        """Place a object down on the scene"""
        # Create a place_location position
        place_location = moveit_msgs.msg.PlaceLocation()
        place_location.place_pose.header.frame_id = FRAME_ID
        # Set the pose
        pose = self.get_free_place_pose()
        place_location.place_pose = pose

        # Set pre place approach
        place_location.pre_place_approach.direction.header.frame_id = FRAME_ID
        place_location.pre_place_approach.direction.vector.z = -1
        place_location.pre_place_approach.min_distance = 0.095
        place_location.pre_place_approach.desired_distance = 0.12
        # Post place
        place_location.post_place_retreat.direction.header.frame_id = FRAME_ID
        place_location.post_place_retreat.direction.vector.z = 1
        place_location.post_place_retreat.min_distance = 0.065
        place_location.post_place_retreat.desired_distance = 0.07

        set_gripper_posture(place_location.post_place_posture, set_open=True,
                            effort=0)
        self.group.set_support_surface_name("table")

        self.group.clear_path_constraints()
        success = self.group.place(object_id, place_location)
        return success


if __name__ == '__main__':
    try:
        i = 1
        # Initialize the ROS Node
        import os
        moveit_commander.roscpp_initialize(sys.argv)
        rospy.init_node("pick_and_place_example")
        # Initialize scene and move group commander
        scene = moveit_commander.PlanningSceneInterface()
        group = moveit_commander.MoveGroupCommander("manipulator")
        group.set_planner_id("RRTConnect")
        group.go(wait=True)

        group.set_max_velocity_scaling_factor(0.5)
        group.set_goal_orientation_tolerance(0.5)
        group.set_goal_position_tolerance(0.0001)

        pick_and_place = PickAndPlace(group, scene)
        # Clear the scene from objects of previous session
        pick_and_place.clear_scene()
        
        # Add scene collision objects (avoid robot to collide with other objects)
        pick_and_place.add_collision_objects()
        done = []
        # Main loop
        while True:
            group.go(HOME_POSITION)
            time.sleep(0.1)

            # Add a box for testing\
            rospy.loginfo("Adding box in a random position in front of the robot.")
            add_rnd_box(scene=scene, name="Box_"+str(i))
            import time
            time.sleep(2)
            # Get the objects in the scene
            objects_names = scene.get_known_object_names()

            for obj_name in objects_names:
                if "Box" not in obj_name:
                    continue
                poses = scene.get_object_poses(object_ids=objects_names)
                pose = poses[obj_name]
                obj = scene.get_objects([obj_name])[obj_name]

                # If the object is in the Region Of Interest, do stuff
                if obj_name not in done:
                    rospy.loginfo("Object '{}' is in ROI!".format(obj_name))
                    # Try to pick the object
                    if pick_and_place.pick(object_pose=pose,
                                           object_id=obj_name):
                        # Try to place the object
                        if not pick_and_place.place(object_id=obj_name):
                            rospy.logerr("Not possible to place the object")
                            raise Exception("Not possible to place the object")
                        i += 1
                        done.append(obj_name)

    except Exception:
        traceback.print_exc()

    moveit_commander.roscpp_shutdown()
