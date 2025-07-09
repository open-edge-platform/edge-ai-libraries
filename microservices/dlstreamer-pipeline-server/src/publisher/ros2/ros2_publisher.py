#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

"""ROS2 Publisher.
Publishes data from a pipeline with gstreamer app destination.
"""

# pylint: disable=wrong-import-position
import json
import os
import base64
import time
import threading as th
from collections import deque

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from src.common.log import get_logger

DEFAULT_APPDEST_ROS2_QUEUE_SIZE = 1000


class ROS2Publisher():
    """ROS2 Publisher.
    """

    def __init__(self, config, qsize=DEFAULT_APPDEST_ROS2_QUEUE_SIZE):
        """Constructor
        :param json app_cfg: Application config
            the meta-data for the frame (df: True)
        """
        self.queue = deque(maxlen=qsize)
        self.stop_ev = th.Event()
        self.topic = config.get('topic', "/dlstreamer_pipeline_results")
        assert len(self.topic) > 0, f'No specified topic'

        self.log = get_logger(f'{__name__} ({self.topic})')

        self.log.info(f'Initializing ROS2 publisher for topic {self.topic}')

        self.publish_frame = config.get("publish_frame", False)
        
        # Ensure ROS2 client library is initialized only once across threads and not yet shut down
        if not rclpy.ok():
            self.log.info("ROS2 client library not initialized, initializing now...")
            rclpy.init()

        self.node = Node(f'ros2_publisher_{th.get_ident()}')
        self.publisher = self.node.create_publisher(String, self.topic, 10)
        self.initialized=True
        self.log.info("ROS2 publisher initialized")

    def start(self):
        """Start publisher.
        """
        self.log.info("Starting publish thread for ROS2...")
        self.th = th.Thread(target=self._run)
        self.th.start()

    def stop(self):
        """Stop publisher.
        """
        if self.stop_ev.set():
            return
        self.stop_ev.set()
        self.th.join()
        self.th = None
        self.node.destroy_node()
        self.log.info('ROS2 publisher thread stopped')

    def error_handler(self, msg):
        self.log.error('Error in ROS2 publisher thread: {}'.format(msg))
        self.stop()

    def _run(self):
        """Run method for publisher.
        """
        self.log.info("ROS2 Publish thread started. Enable debug logs for seeing the messages being published")
        try:
            while not self.stop_ev.is_set():
                try:
                    frame, meta_data = self.queue.popleft()
                    self._publish(frame, meta_data)
                except IndexError:
                    self.log.debug("No data in publisher queue for ROS2 publish thread")
                    time.sleep(0.005)
                    
        except Exception as e:
            self.error_handler(e)
    
    def _publish(self, frame, meta_data):
        """Publish frame/metadata over ROS2

        :param frame: video frame
        :type: bytes
        :param meta_data: Meta data
        :type: Dict
        """
        if not self.publisher is not None:
            self.log.error(f"ROS2 publisher doesn't exist. Message not published. {meta_data}")
            return

        msg = dict()
        msg["metadata"]=meta_data
        if self.publish_frame:
            # Encode frame and convert to utf-8 string
            msg["blob"]=base64.b64encode(frame).decode('utf-8') 
            self.log.debug(
                f"Publishing frame along with meta data: {meta_data}")
        else:
            msg["blob"]=""
            self.log.debug(
                f"Publishing meta data: {meta_data}")

        ros2_msg = String()
        ros2_msg.data = json.dumps(msg)
        self.log.debug(f'Publishing ROS2 message to topic: {self.topic}')
        self.publisher.publish(ros2_msg)

        # Discarding publish message
        del msg
        del ros2_msg
