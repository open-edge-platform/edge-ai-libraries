# ==============================================================================
# Copyright (C) 2025 Intel Corporation
#
# SPDX-License-Identifier: MIT
# ==============================================================================

class ObjectRemovalByLabel:
    def __init__(self,
                 object_filter=["person", "vase"]):
        self._object_filter = object_filter

    def process_frame(self, frame):
        if not self._object_filter:
            return True
        regions = list(frame.regions())
        removable_regions = [region for region in regions if region.label() in self._object_filter]

        orig_regions=list(frame.regions())
        removable_region_ids = [region.region_id() for region in removable_regions]
        for region in orig_regions:
            if region.region_id() in removable_region_ids:
                frame.remove_region(region)

        return True

