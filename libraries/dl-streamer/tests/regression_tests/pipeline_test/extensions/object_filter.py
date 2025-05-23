# ==============================================================================
# Copyright (C) 2025 Intel Corporation
#
# SPDX-License-Identifier: MIT
# ==============================================================================

class ObjectFilter:
    def __init__(self,
                 enable=False,
                 max_objects=None,
                 min_objects=None,
                 fake_object_width=1,
                 fake_object_height=1):
        self.enable = enable
        self._min_objects = min_objects
        self._max_objects = max_objects
        self._fake_object_width = fake_object_width
        self._fake_object_height = fake_object_height

    def process_frame(self, frame):
        if not self.enable:
            return True
        regions = list(frame.regions())
        if self._min_objects and len(regions) < self._min_objects:
            for _ in range(len(regions), self._min_objects):
                regions.append(frame.add_region(0, 0, self._fake_object_width, self._fake_object_height, "fake", 1.0, True))

        if self._max_objects and len(regions) > self._max_objects:
            regions = regions[0:self._max_objects]

        return True
