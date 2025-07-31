#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

"""Influx Writer.
Publishes the metadata of frames to InfluxDB.
"""

# pylint: disable=wrong-import-position
import os
import time
import threading as th
from collections import deque

from src.common.log import get_logger
from utils.influx_client import InfluxClient


DEFAULT_APPDEST_INFLUX_QUEUE_SIZE = 1000


class InfluxdbWriter():
    """Influx Writer.
    """

    def __init__(self, config, qsize=DEFAULT_APPDEST_INFLUX_QUEUE_SIZE):
        """Constructor
        :param json config: Influx publisher config
        """
        self.queue = deque(maxlen=qsize)
        self.stop_ev = th.Event()
        self.host = os.getenv("INFLUXDB_HOST")
        self.port = os.getenv("INFLUXDB_PORT")
        self.username = os.getenv("INFLUXDB_USER")
        self.password = os.getenv("INFLUXDB_PASS")
        self.org = config.get("org")
        self.influx_bucket_name = config.get("bucket")
        self.influx_measurement = config.get("measurement", "dlsps")
        self.influxwrite_complete = th.Event()
        self.th = None
        self.log = get_logger(f'{__name__} ({self.influx_bucket_name})')
        if not self.influx_bucket_name:
            self.log.error(f'Empty value given for bucket name. It cannot be blank')
            self.initialized=False
        if not self.host:
            self.log.error(f'Empty value given for INFLUXDB_HOST. It cannot be blank')
            self.initialized=False
        if not self.port:
            self.log.error(f'Empty value given for INFLUXDB_PORT. It cannot be blank')
            self.initialized=False
        else:
            self.port = int(self.port)
        if not self.org:
            self.log.error(f'Empty value given for INFLUXDB_ORG. It cannot be blank')
            self.initialized=False
        if not self.username and not self.password:
            self.log.error(f'Empty value given for INFLUXDB_USER and INFLUXDB_PASS. It cannot be blank')
            self.initialized=False

        self.log.info(f'Initializing Influx Writer for bucket - {self.influx_bucket_name}')
        self.influx_client = InfluxClient(self.host, self.port, self.org, self.username, self.password)
        if not self.influx_client.bucket_exists(self.influx_bucket_name):
            self.log.error(f"Given bucket name - {self.influx_bucket_name} does NOT exist or server is inaccessible")
            self.initialized=False
        else:
            self.initialized=True
            self.log.info("InfluxDB Writer initialized")

    def start(self):
        """Start publisher.
        """
        self.log.info("Starting influx writer thread")
        self.th = th.Thread(target=self._run)
        self.th.start()

    def stop(self):
        """Stop publisher.
        """
        self.influxwrite_complete.set()
        if self.stop_ev.set():
            return
        self.stop_ev.set()
        if self.th:
            self.th.join()
            self.th = None
            self.log.info('Influx writer thread stopped')

    def error_handler(self, msg):
        self.log.error('Error in influx thread: {}'.format(msg))
        self.stop()

    def _run(self):
        """Run method for publisher.
        """
        self.log.info("Influx writer thread started")
        try:
            while not self.stop_ev.is_set():
                try:
                    _, metadata = self.queue.popleft()
                    self._publish(metadata)
                except IndexError:
                    self.log.debug("No data in client queue")
                    time.sleep(0.005)
                    
        except Exception as e:
            self.error_handler(e)
    
    def _publish(self, metadata):
        """Write object data to influx storage.
        :param metadata: Meta data
        :type: Dict
        """
        self.influx_client.publish(self.influx_bucket_name, self.influx_measurement, metadata)
        self.influxwrite_complete.set()