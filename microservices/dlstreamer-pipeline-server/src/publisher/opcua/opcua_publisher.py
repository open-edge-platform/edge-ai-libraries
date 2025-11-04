#
# Apache v2 license
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

"""OPCUA Publisher.
Publishes data from a pipeline with gstreamer app destination.
"""

# pylint: disable=wrong-import-position
import json
import os
import base64
import time
import threading as th
from collections import deque
from asyncua.sync import Client, ua

from src.common.log import get_logger
from src.publisher.common.filter import Filter

DEFAULT_APPDEST_OPCUA_QUEUE_SIZE = 1000


class OPCUAPublisher():
    """OPCUA Publisher.
    """
    def __init__(self, opcua_cfg, qsize=DEFAULT_APPDEST_OPCUA_QUEUE_SIZE):
        """Constructor
        :param json opcua_cfg: OPCUA config
            the meta-data for the frame (df: True)
        """
        self.client = None
        self.publish_frame = False
        self.initialized=False
        self.stop_ev = th.Event()
        self.queue = deque(maxlen=qsize)
        self.log = get_logger(f'{__name__} (OPCUA)')

        opcua_server_ip = os.getenv("OPCUA_SERVER_IP", "").strip()
        opcua_server_port = os.getenv("OPCUA_SERVER_PORT", "").strip()
        server_username = os.getenv("OPCUA_SERVER_USERNAME", "").strip()
        server_password = os.getenv("OPCUA_SERVER_PASSWORD", "").strip()
        if not opcua_server_ip:
            self.log.error("OPC UA server IP address cannot be empty. Please provide a valid IP address.")
            return
        if not opcua_server_port:
            self.log.error("OPC UA server port cannot be empty. Please provide a valid port number.")
            return
        # Check if only one of the username or password is provided
        if bool(server_username) != bool(server_password):
            if not server_username:
                self.log.error("OPC UA username is required when a password is set. \
                                Please provide a valid username or remove the password for an anonymous connection, if supported by the server.")
            if not server_password:
                self.log.error("OPC UA password is required when a username is set. \
                                Please provide a valid password or remove the username for an anonymous connection, if supported by the server.")
            return

        opcua_url = f"opc.tcp://{opcua_server_ip}:{opcua_server_port}"
        self.log.info('Initializing publisher for OPCUA')
        self.client = Client(url=opcua_url)
        self.opcua_variable = opcua_cfg.get("variable", "").strip()
        if not self.opcua_variable:
            self.log.error(f"No variable configured for the OPCUA server {opcua_url}")
            return
        if server_username and server_password:
            self.client.set_user(server_username)
            self.client.set_password(server_password)
        self.publish_frame = opcua_cfg.get("publish_frame", False)
        try:
            self.client.connect()
            self.initialized=True
            self.log.info("OPCUA publisher initialized")
        except:
            self.client = None
            self.log.error(f"OPCUA: Failed to connect to the server {opcua_url}")

    def start(self):
        """Start publisher.
        """
        self.log.info("Starting publish thread for OPCUA")
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
        self.log.info('OPCUA publisher thread stopped')

    def error_handler(self, msg):
        self.log.error('Error in OPCUA thread: {}'.format(msg))
        self.stop()

    def _run(self):
        """Run method for publisher.
        """
        self.log.info("OPCUA Publish thread started")
        try:
            while not self.stop_ev.is_set():
                try:
                    frame, meta_data = self.queue.popleft()
                    self._publish(frame, meta_data)
                except IndexError:
                    self.log.debug("No data in client queue for OPCUA")
                    time.sleep(0.005)
        except Exception as e:
            self.error_handler(e)
    
    def _publish(self, frame, meta_data):
        """Publish frame/metadata to opcua broker

        :param frame: video frame
        :type: bytes
        :param meta_data: Meta data
        :type: Dict
        """
        if self.client == None:
            self.log.error(f"Client is not connected to OPCUA broker. Message not published. {meta_data}")
            return

        # Encode frame and convert to utf-8 string
        msg = dict()
        msg["metadata"]=meta_data
        if self.publish_frame:
            msg["blob"]=base64.b64encode(frame).decode('utf-8') 
        else:
            msg["blob"]=""
            
        msg = json.dumps(msg)
        try:
            if self.publish_frame:
                self.log.debug(f'Publishing frames along with meta data to OPCUA variable {self.opcua_variable}')
            else:
                self.log.debug(f'Publishing meta data to OPCUA variable {self.opcua_variable}')
            opcua_publisher_node = self.client.get_node(self.opcua_variable)
            data_value = ua.DataValue(ua.Variant(msg, VariantType=ua.VariantType.String, is_array=False), SourceTimestamp=None)
            opcua_publisher_node.write_value(data_value)
        except Exception as e:
            self.log.error(f"Failed to publish to OPCUA: {e}")
        # Discarding publish message
        del msg
