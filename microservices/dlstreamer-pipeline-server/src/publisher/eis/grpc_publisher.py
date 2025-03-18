#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

"""EII Message Bus publisher.
"""
# pylint: disable=wrong-import-position
import asyncio
import os
import time
from collections import deque
import threading as th
from distutils.util import strtobool

import numpy as np
from edge_grpc_client import Client

from src.common.log import get_logger


DEFAULT_APPDEST_EGRPC_QUEUE_SIZE = 1000


class EdgeGrpcPublisher():
    """EIS edge gRPC Publisher.
    """

    def __init__(self, pub_cfg, pub_topic, dev_mode="True", qsize=DEFAULT_APPDEST_EGRPC_QUEUE_SIZE):
        """Constructor
        :param cfg.Publisher pub_config: ConfigManager publisher configuration
        """
        self.queue = deque(maxlen=qsize)
        self.stop_ev = th.Event()
        self.topic = pub_topic

        self.log = get_logger(f'{__name__} ({self.topic})')


        self.log.info(f'Initializing grpc client for topic {self.topic}')

        client_ctx = pub_cfg
        self.endpoint = client_ctx.get_endpoint()
        self.host, port = self.endpoint.split(":")
        # Connect to Server
        self.publisher = Client(host=self.host, port=port, dev_mode=dev_mode, log=None)
        try:
            self.overlay_annotation = strtobool(pub_cfg.get_interface_value("overlay_annotation"))
        except Exception as e:
            self.overlay_annotation = False
            self.log.info("`overlay_annotation` key either not present in config interface or could not be fetched(enable debug if needed). Defaulting to False. ")
            self.log.debug("Exception while parsing config".format(e))
        self.log.info('overlay annotation enabled: {}'.format(bool(self.overlay_annotation)))
        self.log.warning('tensor blob export is NOT supported for gRPC publishers')
        self.initialized=True

    def start(self):
        """Start publisher.
        """
        self.log.info("Starting publish thread for grpc endpoint {}".format(self.endpoint))
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
        self.log.info('Client thread stopped for {} '.format(self.host))

    def error_handler(self, msg):
        self.log.error('Error in client thread {}: {}'.format(self.host, msg))
        self.stop()

    def _run(self):
        """Run method for publisher.
        """
        self.log.info("Publish thread started")
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
        """Publish frame/metadata

        :param frame: video frame
        :type: bytes
        :param meta_data: Meta data
        :type: Dict
        """
        meta_data['topic'] = self.topic
        # keys that should appear as columns. for DataStore-DCaaS compatibiltiy
        if "all_classes_keys" not in meta_data:
            meta_data["all_classes_keys"]=[]
        
        msg = meta_data

        asyncio.run(self.publisher.send(msg, frame))
        self.log.info('Published message: {} to topic: {} for client {}'.format(meta_data, self.topic, self.host))

        # Discarding publish message
        del msg
        del frame

    def close(self):
        """Close publisher.
        """
        del self.publisher
