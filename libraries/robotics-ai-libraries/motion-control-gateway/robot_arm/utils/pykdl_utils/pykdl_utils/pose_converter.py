#!/usr/bin/env python
#
# Provides scripts for automatically converting from different pose types 
# to others.
#
# Copyright (c) 2012, Georgia Tech Research Corporation
# All rights reserved.
# 
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#     * Neither the name of the Georgia Tech Research Corporation nor the
#       names of its contributors may be used to endorse or promote products
#       derived from this software without specific prior written permission.
# 
# THIS SOFTWARE IS PROVIDED BY GEORGIA TECH RESEARCH CORPORATION ''AS IS'' AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL GEORGIA TECH BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA,
# OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
# OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
# ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# Author: Kelsey Hawkins

import numpy as np
import copy

import rclpy
from rclpy.node import Node
from std_msgs.msg import Header
from geometry_msgs.msg import PoseStamped, Pose, Point, Quaternion, PointStamped
from geometry_msgs.msg import Transform, TransformStamped, Vector3
from geometry_msgs.msg import Twist, TwistStamped
import pykdl_utils.transformations as trans

def rot_mat_to_axis_angle(R):
    ang = np.arccos((np.trace(R) - 1.0)/2.0)
    axis = np.array([R[2,1]-R[1,2], R[0,2]-R[2,0], R[1,0]-R[0,1]])
    axis = axis / np.linalg.norm(axis)
    return (axis, ang)

def axis_angle_to_rot_mat(axis, ang):
    axis = axis / np.linalg.norm(axis)
    K = np.mat([[0.0, -axis[2], axis[1]],
                [axis[2], 0.0, -axis[0]],
                [-axis[1], axis[0], 0.0]])
    I = np.mat(np.eye(3))
    return I + np.sin(ang)*K + (1.0 - np.cos(ang))*K*K

##
# Static class with a set of conversion functions for converting any of the supported
# pose types into any of the others without having to provide the type explicity.
class PoseConv(Node):
    POSE_TYPES = [
        'pose_msg', 
        'pose_stamped_msg', 
        'point_msg', 
        'point_stamped_msg',
        'tf_msg',
        'tf_stamped_msg',
        'twist_msg',
        'twist_stamped_msg',
        'homo_mat',
        'pos_rot',
        'pos_quat',
        'pos_euler',
        'pos_axis_angle']
    
    def __init__(self, name):
        super().__init__(name)        

    ##
    # Returns a string describing the type of the given pose as
    # listed in PoseConv.POSE_TYPES. Returns None if unrecognized.
    @staticmethod
    def get_type(*args):
        try:
            if type(args[0]) is str:
                return PoseConv.get_type(*args[1:])
            if len(args) == 1:
                if type(args[0]) is Pose:
                    return 'pose_msg'
                elif type(args[0]) is PoseStamped:
                    return 'pose_stamped_msg'
                elif type(args[0]) is Transform:
                    return 'tf_msg'
                elif type(args[0]) is TransformStamped:
                    return 'tf_stamped_msg'
                elif type(args[0]) is Twist:
                    return 'twist_msg'
                elif type(args[0]) is TwistStamped:
                    return 'twist_stamped_msg'
                elif type(args[0]) is Point:
                    return 'point_msg'
                elif type(args[0]) is PointStamped:
                    return 'point_stamped_msg'
                elif isinstance(args[0], (np.matrix, np.ndarray)) and np.shape(args[0]) == (4, 4):
                    return 'homo_mat'
                elif isinstance(args[0], (tuple, list)) and len(args[0]) == 2:
                    pos_arg = np.mat(args[0][0])
                    if pos_arg.shape != (1, 3) and pos_arg.shape != (3, 1):
                        return None
                    if isinstance(args[0][1], (tuple, list)) and len(args[0][1]) == 2:
                        if len(args[0][1][0]) == 3 and np.array(args[0][1][1]).size == 1:
                            return 'pos_axis_angle'
                        else:
                            return None
                    rot_arg = np.mat(args[0][1])
                    if rot_arg.shape == (3, 3):
                        return 'pos_rot'
                    if 1 not in rot_arg.shape:
                        return None
                    rot_arg = rot_arg.tolist()[0]
                    if len(rot_arg) == 3:
                        return 'pos_euler'
                    elif len(rot_arg) == 4:
                        return 'pos_quat'
                    else:
                        return None
            elif len(args) == 2:
                return PoseConv.get_type(((args[0], args[1]),))
        except:
            pass
        return None

    ##
    # @return geometry_msgs.Pose
    # @staticmethod
    def to_pose_msg(self, *args):
        header, homo_mat, quat_rot, _ = self._make_generic(args)
        if homo_mat is None:
            self.get_logger().info("[pose_converter] Unknown pose type.")
            return None
        else:
            p = Pose()
            p.position.x = homo_mat[:3,3].T.A[0][0]
            p.position.y = homo_mat[:3,3].T.A[0][1]
            p.position.z = homo_mat[:3,3].T.A[0][2]
            p.orientation.x = quat_rot[0]
            p.orientation.y = quat_rot[1]
            p.orientation.z = quat_rot[2]
            p.orientation.w = quat_rot[3]
            return p
    ##
    # @return geometry_msgs.PoseStamped
    # @staticmethod
    def to_pose_stamped_msg(self, *args):
        header, homo_mat, quat_rot, _ = self._make_generic(args)
        if homo_mat is None:
            self.get_logger().info("[pose_converter] Unknown pose type.")
            return None
        ps = PoseStamped()
        if header is None:
            ps.header.stamp = self.get_clock().now()
        else:
            ps.header.stamp = header[1]
            ps.header.frame_id = header[2]
            ps.pose.position.x = homo_mat[:3,3].T.A[0][0]
            ps.pose.position.y = homo_mat[:3,3].T.A[0][1]
            ps.pose.position.z = homo_mat[:3,3].T.A[0][2]
            ps.pose.orientation.x = quat_rot[0]
            ps.pose.orientation.y = quat_rot[1]
            ps.pose.orientation.z = quat_rot[2]
            ps.pose.orientation.w = quat_rot[3]
        return ps

    ##
    # @return geometry_msgs.Point
    # @staticmethod
    def to_point_msg(self, *args):
        header, homo_mat, quat_rot, _ = self._make_generic(args)
        if homo_mat is None:
            self.get_logger().info("[pose_converter] Unknown pose type.")
            return None
        p = Point()
        p.x = homo_mat[:3,3].T.A[0][0]
        p.y = homo_mat[:3,3].T.A[0][1]
        p.z = homo_mat[:3,3].T.A[0][2]
        return p

    ##
    # @return geometry_msgs.PointStamped
    # @staticmethod
    def to_point_stamped_msg(self, *args):
        header, homo_mat, quat_rot, _ = self._make_generic(args)
        if homo_mat is None:
            self.get_logger().info("[pose_converter] Unknown pose type.")
            return None
        ps = PointStamped()
        if header is None:
            ps.header.stamp = self.get_clock().now()
        else:
            ps.header.stamp = header[1]
            ps.header.frame_id = header[2]
        ps.point.x = homo_mat[:3,3].T.A[0][0]
        ps.point.y = homo_mat[:3,3].T.A[0][1]
        ps.point.z = homo_mat[:3,3].T.A[0][2]
        return ps

    ##
    # @return geometry_msgs.Transform
    # @staticmethod
    def to_tf_msg(self, *args):
        header, homo_mat, quat_rot, _ = self._make_generic(args)
        if homo_mat is None:
            self.get_logger().info("[pose_converter] Unknown pose type.")
            return None
        else:
            t = Transform()
            t.translation.x = homo_mat[:3,3].T.A[0][0]
            t.translation.y = homo_mat[:3,3].T.A[0][1]
            t.translation.z = homo_mat[:3,3].T.A[0][2]
            t.rotation.x = quat_rot[0]
            t.rotation.y = quat_rot[1]
            t.rotation.z = quat_rot[2]
            t.rotation.w = quat_rot[3]
            return t

    ##
    # @return geometry_msgs.TransformStamped
    # @staticmethod
    def to_tf_stamped_msg(self, *args):
        header, homo_mat, quat_rot, _ = self._make_generic(args)
        if homo_mat is None:
            self.get_logger().info("[pose_converter] Unknown pose type.")
            return None
        tf_stamped = TransformStamped()
        if header is None:
            tf_stamped.header.stamp = self.get_clock().now()
        else:
            tf_stamped.header.stamp = header[1]
            tf_stamped.header.frame_id = header[2]
        tf_stamped.transform.translation.x = homo_mat[:3,3].T.A[0][0]
        tf_stamped.transform.translation.y = homo_mat[:3,3].T.A[0][1]
        tf_stamped.transform.translation.z = homo_mat[:3,3].T.A[0][2]
        tf_stamped.transform.rotation.x = quat_rot[0]
        tf_stamped.transform.rotation.y = quat_rot[1]
        tf_stamped.transform.rotation.z = quat_rot[2]
        tf_stamped.transform.rotation.w = quat_rot[3]
        return tf_stamped

    ##
    # @return geometry_msgs.Twist
    # @staticmethod
    def to_twist_msg(self, *args):
        _, homo_mat, _, euler_rot = self._make_generic(args)
        if homo_mat is None:
            self.get_logger().info("[pose_converter] Unknown pose type.")
            return None
        else:
            t = Twist()
            t.linear.x = homo_mat[:3,3].T.A[0][0]
            t.linear.y = homo_mat[:3,3].T.A[0][1]
            t.linear.z = homo_mat[:3,3].T.A[0][2]
            t.angular.x = euler_rot[0]
            t.angular.y = euler_rot[1]
            t.angular.z = euler_rot[2]
            return t

    ##
    # @return geometry_msgs.TwistStamped
    # @staticmethod
    def to_twist_stamped_msg(self, *args):
        header, homo_mat, _, euler_rot = self._make_generic(args)
        if homo_mat is None:
            self.get_logger().info("[pose_converter] Unknown pose type.")
            return None
        twist_stamped = TwistStamped()
        header_msg = Header()
        if header is None:
            header_msg.stamp = self.get_clock().now()
        else:
            header_msg.stamp = header[1]
            header_msg.frame_id = header[2]
        twist_stamped.twist.linear.x = homo_mat[:3,3].T.A[0][0]
        twist_stamped.twist.linear.y = homo_mat[:3,3].T.A[0][1]
        twist_stamped.twist.linear.z = homo_mat[:3,3].T.A[0][2]
        twist_stamped.twist.angular.x = euler_rot[0]
        twist_stamped.twist.angular.y = euler_rot[1]
        twist_stamped.twist.angular.z = euler_rot[2]
        return twist_stamped

    ##
    # @return 4x4 numpy mat
    # @staticmethod
    def to_homo_mat(self, *args):
        header, homo_mat, quat_rot, _ = self._make_generic(args)
        if homo_mat is None:
            self.get_logger().info("[pose_converter] Unknown pose type.")
            return None
        else:
            return homo_mat.copy()

    ##
    # @return (3x1 numpy mat, 3x3 numpy mat)
    # @staticmethod
    def to_pos_rot(self, *args):
        header, homo_mat, quat_rot, _ = self._make_generic(args)
        if homo_mat is None:
            self.get_logger().info("[pose_converter] Unknown pose type.")
            return None, None
        else:
            return homo_mat[:3,3].copy(), homo_mat[:3,:3].copy()

    ##
    # @return (3 list, 4 list)
    # @staticmethod
    def to_pos_quat(self, *args):
        header, homo_mat, quat_rot, _ = self._make_generic(args)
        if homo_mat is None:
            self.get_logger().info("[pose_converter] Unknown pose type.")
            return None, None
        else:
            return copy.copy(list(homo_mat[:3,3].T.A[0])), copy.copy(quat_rot)

    ##
    # @return (3 list, 3 list)
    # @staticmethod
    def to_pos_euler(self, *args):
        header, homo_mat, quat_rot, euler_rot = self._make_generic(args)
        if homo_mat is None:
            self.get_logger().info("[pose_converter] Unknown pose type.")
            return None, None
        else:
            return copy.copy(list(homo_mat[:3,3].T.A[0])), copy.copy(euler_rot)

    ##
    # @return (3 list, (3 list, float))
    # @staticmethod
    def to_pos_axis_angle(self, *args):
        header, homo_mat, quat_rot, _ = self._make_generic(args)
        if homo_mat is None:
            self.get_logger().info("[pose_converter] Unknown pose type.")
            return None, None
        else:
            return copy.copy(list(homo_mat[:3,3].T.A[0])), rot_mat_to_axis_angle(homo_mat[:3,:3])

    # @staticmethod
    def _make_generic(self, args):
        try:
            if type(args[0]) == str:
                frame_id = args[0]
                header, homo_mat, rot_quat, rot_euler = self._make_generic(args[1:])
                if homo_mat is None:
                    return None, None, None, None
                if header is None:
                    header = [0, self.get_clock().now(), '']
                header[2] = frame_id
                return header, homo_mat, rot_quat, rot_euler

            if len(args) == 2:
                return self._make_generic(((args[0], args[1]),))
            elif len(args) == 1:
                pose_type = PoseConv.get_type(*args)
                if pose_type is None:
                    return None, None, None, None
                if pose_type == 'pose_msg':
                    homo_mat, rot_quat, rot_euler = PoseConv._extract_pose_msg(args[0])
                    return None, homo_mat, rot_quat, rot_euler
                elif pose_type == 'pose_stamped_msg':
                    homo_mat, rot_quat, rot_euler = PoseConv._extract_pose_msg(args[0].pose)
                    seq = args[0].header.seq
                    stamp = args[0].header.stamp
                    frame_id = args[0].header.frame_id
                    return [seq, stamp, frame_id], homo_mat, rot_quat, rot_euler
                elif pose_type == 'tf_msg':
                    homo_mat, rot_quat, rot_euler = PoseConv._extract_tf_msg(args[0])
                    return None, homo_mat, rot_quat, rot_euler
                elif pose_type == 'tf_stamped_msg':
                    homo_mat, rot_quat, rot_euler = PoseConv._extract_tf_msg(args[0].transform)
                    seq = args[0].header.seq
                    stamp = args[0].header.stamp
                    frame_id = args[0].header.frame_id
                    return [seq, stamp, frame_id], homo_mat, rot_quat, rot_euler
                elif pose_type == 'point_msg':
                    homo_mat, rot_quat, rot_euler = PoseConv._extract_point_msg(args[0])
                    return None, homo_mat, rot_quat, rot_euler
                elif pose_type == 'point_stamped_msg':
                    homo_mat, rot_quat, rot_euler = PoseConv._extract_point_msg(args[0].point)
                    seq = args[0].header.seq
                    stamp = args[0].header.stamp
                    frame_id = args[0].header.frame_id
                    return [seq, stamp, frame_id], homo_mat, rot_quat, rot_euler
                elif pose_type == 'twist_msg':
                    homo_mat, rot_quat, rot_euler = PoseConv._extract_twist_msg(args[0])
                    return None, homo_mat, rot_quat, rot_euler
                elif pose_type == 'twist_stamped_msg':
                    homo_mat, rot_quat, rot_euler = PoseConv._extract_twist_msg(args[0].twist)
                    seq = args[0].header.seq
                    stamp = args[0].header.stamp
                    frame_id = args[0].header.frame_id
                    return [seq, stamp, frame_id], homo_mat, rot_quat, rot_euler
                elif pose_type == 'homo_mat':
                    return (None, np.mat(args[0]), trans.quaternion_from_matrix(args[0]).tolist(),
                            trans.euler_from_matrix(args[0]))
                elif pose_type in ['pos_rot', 'pos_euler', 'pos_quat', 'pos_axis_angle']:
                    pos_arg = np.mat(args[0][0])
                    if pos_arg.shape == (1, 3):
                        # matrix is row, convert to column
                        pos = pos_arg.T
                    elif pos_arg.shape == (3, 1):
                        pos = pos_arg

                    if pose_type == 'pos_axis_angle':
                        homo_mat = np.mat(np.eye(4))
                        homo_mat[:3,:3] = axis_angle_to_rot_mat(args[0][1][0], args[0][1][1])
                        quat = trans.quaternion_from_matrix(homo_mat)
                        rot_euler = trans.euler_from_matrix(homo_mat)
                    elif pose_type == 'pos_rot':
                        # rotation matrix
                        homo_mat = np.mat(np.eye(4))
                        homo_mat[:3,:3] = np.mat(args[0][1])
                        quat = trans.quaternion_from_matrix(homo_mat)
                        rot_euler = trans.euler_from_matrix(homo_mat)
                    else:
                        rot_arg = np.mat(args[0][1])
                        if rot_arg.shape[1] == 1:
                            rot_arg = rot_arg.T
                        rot_list = rot_arg.tolist()[0]
                        if pose_type == 'pos_euler':
                            # Euler angles rotation
                            homo_mat = np.mat(trans.euler_matrix(*rot_list))
                            quat = trans.quaternion_from_euler(*rot_list)
                            rot_euler = rot_list
                        elif pose_type == 'pos_quat':
                            # quaternion rotation
                            homo_mat = np.mat(trans.quaternion_matrix(rot_list))
                            quat = rot_list
                            rot_euler = trans.euler_from_quaternion(quat)

                    homo_mat[:3, 3] = pos
                    return None, homo_mat, np.array(quat), rot_euler
        except:
            pass

        return None, None, None, None

    @staticmethod
    def _extract_pose_msg(pose):
        px = pose.position.x; py = pose.position.y; pz = pose.position.z
        ox = pose.orientation.x; oy = pose.orientation.y
        oz = pose.orientation.z; ow = pose.orientation.w
        quat = [ox, oy, oz, ow]
        rot_euler = trans.euler_from_quaternion(quat)
        homo_mat = np.mat(trans.quaternion_matrix(quat))
        homo_mat[:3,3] = np.mat([[px, py, pz]]).T
        return homo_mat, quat, rot_euler

    @staticmethod
    def _extract_tf_msg(tf_msg):
        px = tf_msg.translation.x; py = tf_msg.translation.y; pz = tf_msg.translation.z 
        ox = tf_msg.rotation.x; oy = tf_msg.rotation.y
        oz = tf_msg.rotation.z; ow = tf_msg.rotation.w
        quat = [ox, oy, oz, ow]
        rot_euler = trans.euler_from_quaternion(quat)
        homo_mat = np.mat(trans.quaternion_matrix(quat))
        homo_mat[:3,3] = np.mat([[px, py, pz]]).T
        return homo_mat, quat, rot_euler

    @staticmethod
    def _extract_twist_msg(twist_msg):
        pos = [twist_msg.linear.x, twist_msg.linear.y, twist_msg.linear.z]
        rot_euler = [twist_msg.angular.x, twist_msg.angular.y, twist_msg.angular.z]
        quat = trans.quaternion_from_euler(*rot_euler, axes='sxyz')
        homo_mat = np.mat(trans.euler_matrix(*rot_euler))
        homo_mat[:3,3] = np.mat([pos]).T
        return homo_mat, quat, rot_euler

    @staticmethod
    def _extract_point_msg(point_msg):
        pos = [point_msg.x, point_msg.y, point_msg.z]
        homo_mat = np.mat(np.eye(4))
        homo_mat[:3,3] = np.mat([pos]).T
        return homo_mat, [0., 0., 0., 1.], [0., 0., 0.]


def main(args=None):
    rclpy.init(args=args)
    pose_converter = PoseConv("pose_converter")
    pose = ([0.1, -0.5, 1.0], [0.04842544,  0.01236504,  0.24709477,  0.96770153])
    errors = 0
    for type_from in PoseConv.POSE_TYPES:
        for type_to in PoseConv.POSE_TYPES:
            print 
            print("Types: FROM %s, TO %s" % (type_from, type_to))
            loc = {}
            exec("from_pose = pose_converter.to_%s(pose)" % type_from, {"pose_converter": pose_converter, "pose": pose}, loc)
            from_pose = loc["from_pose"]
            # print(from_pose)
            if from_pose is None or (type(from_pose) is tuple and from_pose[0] is None):
                print("from_pose ERROR\n" * 5)
                errors += 1
                continue
            exec("to_pose = pose_converter.to_%s('base_link', from_pose)" % type_to, {"pose_converter": pose_converter, "frome_pose": from_pose}, loc)
            to_pose = loc["to_pose"]
            if to_pose is None or (type(to_pose) is tuple and to_pose[0] is None):
                print("to_pose ERROR\n" * 5)
                errors += 1
                continue
            exec("back_pose = pose_converter.to_%s(to_pose)" % type_from, {"pose_converter": pose_converter, "to_pose": to_pose}, loc)
            back_pose = loc["back_pose"]
            if back_pose is None or (type(back_pose) is tuple and back_pose[0] is None):
                print("back_pose ERROR\n" * 5)
                errors += 1
                continue
            exec("orig_pose = pose_converter.to_pos_quat(back_pose)", {"pose_converter": pose_converter, "back_pose": back_pose}, loc)
            orig_pose = loc["orig_pose"]
            if orig_pose is None or (type(orig_pose) is tuple and orig_pose[0] is None):
                print("orig_pose ERROR\n" * 5)
                print(pose)
                print(orig_pose)
                errors += 1
                continue
            if not np.allclose(orig_pose[0], pose[0]):
                print("orig_pose pos ERROR\n" * 5)
                print(pose)
                print(orig_pose)
                errors += 1
                continue
            if 'point' not in type_to + type_from and not np.allclose(orig_pose[1], pose[1]):
                print("orig_pose rot ERROR\n" * 5)
                print(pose)
                print(orig_pose)
                errors += 1
                continue
            print("-" * 50)
            if type_from != pose_converter.get_type(from_pose) or type_to != pose_converter.get_type(to_pose):
                print("get_type ERROR\n" * 5)
                errors += 1
                continue
            print(from_pose)
            print("-" * 20)
            print(to_pose)
    pose_converter.destroy_node()
    rclpy.shutdown()
    print("\n\nErrors: %d" % errors)

if __name__ == "__main__":
    main()
