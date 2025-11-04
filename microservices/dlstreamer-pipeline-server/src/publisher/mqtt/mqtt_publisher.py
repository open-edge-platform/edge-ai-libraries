#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

"""MQTT Publisher.
Publishes data from a pipeline with gstreamer app destination.
"""

# pylint: disable=wrong-import-position
import json
import os
import base64
import time
import threading as th
from collections import deque

from src.common.log import get_logger
from src.publisher.common.filter import Filter
from utils.mqtt_client import MQTTClient


DEFAULT_APPDEST_MQTT_QUEUE_SIZE = 1000


class MQTTPublisher():
    """MQTT Publisher.
    """

    def __init__(self, config, qsize=DEFAULT_APPDEST_MQTT_QUEUE_SIZE):
        """Constructor
        :param json app_cfg: Application config
            the meta-data for the frame (df: True)
        """
        self.queue = deque(maxlen=qsize)
        self.stop_ev = th.Event()
        self.topic = config.get('topic', "dlstreamer_pipeline_results")
        assert len(self.topic) > 0, f'No specified topic'

        self.log = get_logger(f'{__name__} ({self.topic})')

        self.log.info(f'Initializing publisher for topic {self.topic}')
        self.host = os.getenv("MQTT_HOST")
        self.port = os.getenv("MQTT_PORT")
        if not self.host:
            self.log.error(f'Empty value given for MQTT_HOST. It cannot be blank')
        if not self.port:
            self.log.error(f'Empty value given for MQTT_PORT. It cannot be blank')
        else:
            self.port = int(self.port)

        self.publish_frame = config.get("publish_frame", False)

        self.qos = config.get('qos', 0)
        self.protocol = config.get('protocol', 4)

        filter_config = config.get('filter', None)
        if filter_config:
            self.filter = Filter(filter_config)
        else:
            self.filter = None

        self.tls_config = config.get('tls', None)

        self.client = MQTTClient(self.host, self.port, self.topic, self.qos, self.protocol, self.tls_config)
        self.initialized=True
        self.log.info("MQTT publisher initialized")

    def start(self):
        """Start publisher.
        """
        self.log.info("Starting publish thread for MQTT")
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
        self.log.info('MQTT publisher thread stopped')

    def error_handler(self, msg):
        self.log.error('Error in MQTT thread: {}'.format(msg))
        self.stop()

    def _run(self):
        """Run method for publisher.
        """
        self.log.info("MQTT Publish thread started")
        try:
            while not self.stop_ev.is_set():
                try:
                    frame, meta_data = self.queue.popleft()
                    self._publish(frame, meta_data)
                except IndexError:
                    self.log.debug("No data in client queue")
                    time.sleep(0.005)
                    
        except Exception as e:
            self.error_handler(e)
    
    def _publish(self, frame, meta_data):
        """Publish frame/metadata to mqtt broker

        :param frame: video frame
        :type: bytes
        :param meta_data: Meta data
        :type: Dict
        """
        if not self.client.is_connected():
            self.log.error(f"Client is not connected to MQTT broker. Message not published. {meta_data}")
            return

        if self.filter:
            if not self.filter.check_filter_criteria(meta_data):
                self.log.debug("Filter criteria not met, skipping...")
                return

        
        msg = dict()
        msg["metadata"]=meta_data
        if self.publish_frame:
            # Encode frame and convert to utf-8 string
            msg["blob"]=base64.b64encode(frame).decode('utf-8') 
            self.log.debug(
                f"Publishing frames along with meta data: {meta_data}")
        else:
            msg["blob"]=""
            self.log.debug(
                f"Publishing meta data: {meta_data}")
         
        msg = json.dumps(msg)

        self.log.debug(f'Publishing message to topic: {self.topic}')
        self.client.publish(self.topic, payload=msg)

        # Discarding publish message
        del msg
