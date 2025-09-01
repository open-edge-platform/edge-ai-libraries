#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions
# and limitations under the License.

import sys
import json
import time
import argparse
import os
import logging
import queue
import signal

# add current path into PYTHONPATH
APP_PATH = os.path.dirname(__file__)
sys.path.append(APP_PATH)

from app.appbase import AppBase
from app.mqtt_service import MqttMessage, MqttPubTask
from app.rt_shm import ShmTask
from app.data_formatter import DataFmtTask
from app.latency import LatencyTask

LOG = logging.getLogger(__name__)

LAT_CMD = ['taskset', '-c', '3', '/usr/xenomai/bin/latency', '-c', '3']

class monitor_app(AppBase):
    """
    Monitor application
    """

    def __init__(self, host, port, qos, lat, lib):
        AppBase.__init__(self)
        self._host = host
        self._port = port
        self._qos = qos
        self._lat = lat
        self._lib = lib

    def run(self):
        dataq = queue.Queue(100)
        msgq = queue.Queue(100)
        mqtt_task = MqttPubTask(msgq, self._host, self._port, self._qos)
        mqtt_task.start()
        if self._lat:
            latency_task = LatencyTask(LAT_CMD, msgq)
            latency_task.start()
        shm_task = ShmTask(dataq, bytes(self._lib, "utf8"), b'shm_test', 1024)
        shm_task.start()
        datafmt_task = DataFmtTask(dataq, msgq, b'./config.json')
        datafmt_task.start()


def parse_args():
    """
    Parse command line arguments.
    """
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default='localhost', help='MQTT broker host')
    ap.add_argument('--port', default=1883, type=int, help='MQTT broker port')
    ap.add_argument('--qos', default=1, type=int, help='MQTT publish qos')
    ap.add_argument('--lat', action='store_true', help='Enable xenomai latency publishing')
    ap.add_argument('--lib', default='/usr/lib/x86_64-linux-gnu/libshmringbuf.so', help='libshmringbuf.so path')
    return ap.parse_args()


def start_app():
    """
    App entry.
    """
    args = parse_args()
    app = monitor_app(args.host, args.port, args.qos, args.lat, args.lib)

    def signal_handler(num, _):
        logging.getLogger().error("signal %d", num)
        app.stop()
        sys.exit(1)

    # setup the signal handler
    signames = ['SIGINT', 'SIGHUP', 'SIGQUIT', 'SIGUSR1']
    for name in signames:
        signal.signal(getattr(signal, name), signal_handler)

    app.run_and_wait_task()

if __name__ == "__main__":
    start_app()
