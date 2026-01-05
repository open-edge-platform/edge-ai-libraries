# This file was downloaded from https://github.com/intel-retail/automated-self-checkout
# This script is not part of the ViPPET tool. It was obtained from the above repository and is used here for the retail pipeline purposes.
'''
* Copyright (C) 2023 Intel Corporation.
*
* SPDX-License-Identifier: Apache-2.0
'''

import zxingcpp
import pyzbar.pyzbar as pyzbar
from pyzbar.pyzbar import ZBarSymbol
from collections import OrderedDict
from dataclasses import dataclass
from abc import ABC, abstractmethod


class LRUCache:
    def __init__(self, max_tracked_objects):
        self.data = OrderedDict()
        self.capacity = max_tracked_objects

    def get(self, key: int) -> int:
        if key not in self.data:
            return None
        else:
            self.data.move_to_end(key)
            return self.data[key]

    def put(self, key: int, value: int) -> None:
        self.data[key] = value
        self.data.move_to_end(key)
        if len(self.data) > self.capacity:
            self.data.popitem(last=False)


class ObjectFilter:

    def __init__(self, disable=False, reclassify_interval=5,
                 max_tracked_objects=100):
        self.disable = disable

        self.reclassify_interval = reclassify_interval
        self.frame_count = 0
        self.tracked_objects = LRUCache(max_tracked_objects)

    def process_frame(self, frame):

        if self.disable:
            return True
        self.frame_count += 1
        skip_frame_processing = False
        if self.reclassify_interval != -1 and (
                self.reclassify_interval == 0 or
                (self.frame_count % self.reclassify_interval != 0)):
            skip_frame_processing = True

        regions = list(frame.regions())
        for region in regions:
            object_id = region.object_id()
            if object_id:
                if (self.tracked_objects.get(object_id)
                        is not None) and skip_frame_processing:
                    frame.remove_region(region)
                self.tracked_objects.put(object_id, True)
        return True
