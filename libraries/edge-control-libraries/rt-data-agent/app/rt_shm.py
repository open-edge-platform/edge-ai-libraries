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
import queue
import os

from ctypes import *
from .appbase import BaseTask
from .data_formatter import RawData

LOG = logging.getLogger(__name__)

class ShmTask(BaseTask):
    """
    EC data processing task by share memory
    """

    def __init__(self, dataq, libshm, name, maxblksize):
        BaseTask.__init__(self)
        self._dataq = dataq
        self._libshm = CDLL(libshm)
        self._buffer = bytearray(maxblksize)
        self._readbuf = c_char * len(self._buffer)
        self._name = name
        self._maxblksize = maxblksize

        # fill the APIs
        self._shm_init = self._libshm.shm_blkbuf_init
        self._shm_init.restype = c_void_p
        self._shm_open = self._libshm.shm_blkbuf_open
        self._shm_open.restype = c_void_p
        self._shm_dump = self._libshm.shm_dump
        self._shm_close = self._libshm.shm_blkbuf_close
        self._shm_write = self._libshm.shm_blkbuf_write
        self._shm_read = self._libshm.shm_blkbuf_read
        self._shm_full = self._libshm.shm_blkbuf_full
        self._shm_empty = self._libshm.shm_blkbuf_empty

    def _shm_process(self):
        buffer = bytearray(self._maxblksize)

        while self._shm_empty(c_void_p(self._handle)):
            time.sleep(0.01)
        numBytes = self._shm_read(c_void_p(self._handle), self._readbuf.from_buffer(buffer), self._maxblksize)
        #LOG.debug("Read %d bytes, %d...%d", numBytes, int(buffer[0]), int(buffer[numBytes-1]))
        rawdata = RawData(self._name, buffer, numBytes)
        self._dataq.put_nowait(rawdata)

    def execute(self):
        """
        Task Entry
        """
        # init shm
        self._handle = self._shm_open(self._name)
        if self._handle is None:
            LOG.info("Share memory buffer %s needs created before in sender by shm_blkbuf_init", self._name)
            raise Exception("No valid share memory buffer")

        while not self.is_task_stopping:
            if self._dataq.full():
                LOG.debug("Data queue is full")
                time.sleep(0.01)
                continue
            self._shm_process()

    def stop(self):
        BaseTask.stop(self)
        self._shm_close
