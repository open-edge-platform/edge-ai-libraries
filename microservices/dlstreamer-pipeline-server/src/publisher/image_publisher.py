#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

"""Publisher to return pipeline outputs to a queue.
"""

import os
import queue
import time
from collections import deque
import threading as th
from distutils.util import strtobool

import numpy as np

from src.common.log import get_logger

DEFAULT_RESP_QUEUE_SIZE = 1    # if an old item is not picked, it is discarded as soon as new one comes synchronous

class ImagePublisher():
    """Image Publisher.
    """

    def __init__(self, qsize=DEFAULT_RESP_QUEUE_SIZE):
        """Constructor
        """
        self.queue = deque(maxlen=qsize)
        self.response_queue = queue.Queue(maxsize=1)  # hold item from input request
        self.stop_ev = th.Event()
        # self.topic = pub_topic

        self.log = get_logger(f'{__name__}')
        self.initialized=True

    def start(self):
        """Start publisher.
        """
        self.log.info("Starting publish thread for ImagePublisher")
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
        self.log.info('ImagePublisher thread stopped')

    def error_handler(self, msg):
        self.log.error('Error in RequestPubisher thread')
        self.stop()

    def _run(self):
        """Run method for publisher.
        """
        self.log.info("Publish thread started")
        try:
            while not self.stop_ev.is_set():
                try:
                    frame, meta_data = self.queue.popleft()
                    self.log.debug('Received data from gst queue')
                    self._publish(frame, meta_data)
                except IndexError:
                    self.log.debug("No data in request publisher queue")
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
        # meta_data['topic'] = self.topic
        msg = meta_data

        self.response_queue.put((frame, msg))
        self.log.debug('Message Sent to ImagePublisher: {}'.format(meta_data))


    def close(self):
        """Close publisher.
        """
        pass
        # with self.queue.mutex:
        #     self.queue.clear()
