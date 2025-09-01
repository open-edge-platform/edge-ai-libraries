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
import time
import logging
import re
import subprocess
import queue

from .appbase import BaseTask
from .mqtt_service import MqttMessage

LOG = logging.getLogger(__name__)

class LatencyTask(BaseTask):
    """
    Latency monitor task
    """

    def __init__(self, commands, outq):
        BaseTask.__init__(self)
        self._commands = commands
        self._outq = outq
        self._topic = "xenomai"
        self._fields = [
            "latency/min",
            "latency/avg",
            "latency/max",
            "latency/best",
            "latency/worst"
        ]

    def _latency_process(self, line):
        if ('RTD|' in line):
            msg = {}
            res = re.split('[ |]+', line.splitlines()[0])
            #[RTH lat_min lat_avg lat_max overrun msw lat_best lat_worst]
            lats = [
                    float(res[1]), float(res[2]),
                    float(res[3]), float(res[6]), float(res[7])]
            for i in range(0, len(self._fields)):
                msg[self._fields[i]] = lats[i]

            message = MqttMessage(self._topic, msg)
            self._outq.put_nowait(message)

    def execute(self):
        """
        Task Entry
        """

        popen = subprocess.Popen(self._commands, 
            stdout = subprocess.PIPE, encoding='utf8')

        while not self.is_task_stopping:
            line = popen.stdout.readline()
            if not line:
                continue
            
            self._latency_process(line)
        
        popen.terminate()

    def stop(self):
        BaseTask.stop(self)
