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
import logging
import json

from .appbase import BaseTask
from .mqtt_service import MqttMessage

LOG = logging.getLogger(__name__)

class RawData:
    def __init__(self, name, data, size):
        self._name = name
        self._data = data
        self._size = size

    @property
    def name(self):
        return self._name
    
    @property
    def size(self):
        return self._size

    @property
    def data(self):
        return self._data


class DataFmtTask(BaseTask):
    """
    Data Formatter task
    """

    def __init__(self, in_queue, out_queue, json_cfg):
        BaseTask.__init__(self)
        self._inq = in_queue
        self._outq = out_queue
        self._cfg = open(json_cfg)
    
    def _get_data_u8(self, data, offset):
        return data[offset]
    
    def _get_data_u16(self, data, offset):
        return data[offset+1]*0x100 + data[offset]
    
    def _get_data_u32(self, data, offset):
        return data[offset+3]*0x1000000 \
            + data[offset+2]*0x10000 \
            + data[offset+1]*0x100 + data[offset]
    
    def _get_data_value(self, data, offset, type):
        if type == 8:
            value = int(self._get_data_u8(data, offset))
        elif type == 16:
            value = int(self._get_data_u16(data, offset))
        elif type == 32:
            value = int(self._get_data_u32(data, offset))
        else:
            value = int(0)
            LOG.error("Usupported type %s", type)
        
        return value
    
    def _data_parse(self, rawdata, cfg):
        LOG.debug("Raw data name %s, size: %d", rawdata.name, rawdata.size)
        #LOG.debug("\t %d...%d", int(rawdata.data[0]), int(rawdata.data[rawdata.size-1]))

        msg = {}
        topic = "Servo"
        for obj in cfg['entities']['objects']:
            for var in obj['variables']:
                tag = obj['name'] + '_' + var['name']
                value = self._get_data_value(rawdata.data, var['offset'], var['type'])
                LOG.debug("\t %s: %x", tag, value)
                msg[tag] = value
   
        message = MqttMessage(topic, msg)
        self._outq.put_nowait(message)


    def execute(self):
        """
        Task Entry
        """
        cfg = json.load(self._cfg)
        while not self.is_task_stopping:
            if self._inq.empty():
                time.sleep(0.01)
                continue
            rawdata = self._inq.get_nowait()
            if rawdata is None:
                continue

            self._data_parse(rawdata, cfg)

    def stop(self):
        BaseTask.stop(self)
        self._cfg.close()
