# Joint State Publisher

This contains a package for publishing `sensor_msgs/msg/JointState` messages for a robot described with URDF.
Given a URDF (either passed on the command-line or via the `/robot_description` topic), this node
will continually publish values for all of the movable joints in the URDF to the `/joint_states` topic.
In combination with `robot_state_publisher`, this ensures that there is a valid transform for all joints
even when the joint doesn't have encoder data.

Published Topics
----------------
* `/joint_states` (`sensor_msgs/msg/JointState`) - The state of all of the movable joints in the system.

Subscribed Topics
-----------------
* (optional) `/robot_description` (`std_msgs/msg/String`) - If no URDF is given on the command-line, then this node will listen on the `/robot_description` topic for the URDF to be published.  Once it has been received at least once, this node will start to publish joint values to `/joint_states`.
* (optional) `/any_topic` (`sensor_msgs/msg/JointState`) - If the `sources_list` parameter is not empty (see Parameters below), then every named topic in this parameter will be subscribed to for joint state updates.  Do *not* add the default `/joint_states` topic to this list, as it will end up in an endless loop!

Parameters
----------
* `rate` (int) - The rate at which to publish updates to the `/joint_states` topic.  Defaults to 10.
* `publish_default_positions` (bool) - Whether to publish a default position for each movable joint to the `/joint_states` topic.  Defaults to True.
* `publish_default_velocities` (bool) - Whether to publish a default velocity for each movable joint to the `/joint_states` topic.  Defaults to False.
* `publish_default_efforts` (bool) - Whether to publish a default effort for each movable joint to the `/joint_states` topic.  Defaults to False.
* `use_mimic_tags` (bool) - Whether to honor `<mimic>` tags in the URDF.  Defaults to True.
* `use_smallest_joint_limits` (bool) - Whether to honor `<safety_controller>` tags in the URDF.  Defaults to True.
* `source_list` (array of strings) - Each string in this array represents a topic name.  For each string, create a subscription to the named topic of type `sensor_msgs/msg/JointStates`.  Publication to that topic will update the joints named in the message.  Defaults to an empty array.
* `delta` (double) - How much to automatically move joints during each iteration.  Defaults to 0.0.
* `zeros` (dictionary of string -> float) - A dictionary of joint_names to initial starting values for the joint.  In Eloquent, pass on the command-line as '-p zeros.joint_name:=value'.  Defaults to an empty dictionary, in which case 0 is assumed as the zero for all joints.
* `dependent_joints` (dictionary of string -> dictionary of 'parent', 'factor', 'offset') - A dictionary of joint_names to the joints that they mimic; compare to the `<mimic>` tag in URDF.  A joint listed here will mimic the movements of the 'parent' joint, subject to the 'factor' and 'offset' provided.  The 'parent' name must be provided, while the 'factor' and 'offset' parameters are optional (they default to 1.0 and 0.0, respectively).  In Eloquent, pass on the command-line as '-p dependent_joints.left_leg.parent:=right_leg -p dependent_joints.left_leg.offset:=0.0 -p dependent_joints.left_leg.factor:=2.0'. Defaults to the empty dictionary, in which case only joints that are marked as `<mimic>` in the URDF are mimiced.
