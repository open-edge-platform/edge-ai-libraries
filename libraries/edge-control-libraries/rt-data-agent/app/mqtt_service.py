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
import paho.mqtt.client as mqtt
import logging

from .appbase import BaseTask

LOG = logging.getLogger(__name__)

class MqttMessage:
    def __init__(self, topic, message):
        self._topic = topic
        self._message = message

    @property
    def topic(self):
        return self._topic

    @property
    def message(self):
        return self._message
    
    @message.setter
    def message(self, new):
        self._message = new

class MqttPubTask(BaseTask):
    """
    MQTT message publish task
    """

    def __init__(self, in_queue, host, port, qos):
        BaseTask.__init__(self)
        self._inq = in_queue
        self._host = host
        self._port = port
        self._qos = qos

        self._client = mqtt.Client()
#        self._client.username_pw_set(username="test", password="test")
        self._client.on_connect = self._on_connect
        self._client.connect(self._host, self._port, 60)
        self._client.loop_start()

    def _on_connect(self, client, userdata, flags, rc):
        if not rc == 0:
            LOG.error("MQTT connect %s:%s failed, %s",
                    self._host, str(self._port), mqtt.connack_string(rc))
        else:
            LOG.info("MQTT connect broker successfully.")

    def execute(self):
        """
        Task Entry
        """
        while not self.is_task_stopping:
            if self._inq.empty():
                time.sleep(0.01)
                continue
            msg = self._inq.get_nowait()
            if msg is None:
                continue
            
            LOG.info("MQTT send %s: %s", msg.topic, json.dumps(msg.message))
            msginfo = self._client.publish(msg.topic, json.dumps(msg.message), self._qos)
            if not msginfo.rc == mqtt.MQTT_ERR_SUCCESS:
                LOG.error("MQTT publish failed, %s", mqtt.error_string(msginfo.rc))

    def stop(self):
        BaseTask.stop(self)
        self._client.loop_stop()
