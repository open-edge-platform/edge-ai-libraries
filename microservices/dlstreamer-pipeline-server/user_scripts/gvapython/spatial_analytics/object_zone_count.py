#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import traceback
from gvapython.gva_event_meta import gva_event_meta
from src.server.common.utils import logging

def print_message(message):
    print("", flush=True)
    print(message, flush=True)

logger = logging.get_logger('object_zone_count', is_static=True)

class ObjectZoneCount:
    DEFAULT_EVENT_TYPE = "object-zone-count"
    DEFAULT_TRIGGER_ON_INTERSECT = True
    DEFAULT_DETECTION_CONFIDENCE_THRESHOLD = 0.0

    # Caller supplies one or more zones via request parameter
    def __init__(self, zones=None, enable_watermark=False, log_level="INFO"):
        self._zones = []
        self._logger = logger
        self._logger.log_level = log_level
        self._enable_watermark = enable_watermark
        if not zones:
            logger.warning("No zone configuration was supplied to ObjectZoneCount.")
            return
        self._zones = self._assign_defaults(zones)
        if not self._zones:
            raise Exception('Empty zone configuration. No zones to check against.')

    # Note that the pipeline already applies a pipeline-specific threshold value, but
    # this method serves as an example for handling optional zone-specific parameters.
    # If a field (e.g., 'threshold') exists in extension configuration, it overrides default value.
    def _assign_defaults(self, zones):
        for zone in zones:
            if not "threshold" in zone:
                zone["threshold"] = ObjectZoneCount.DEFAULT_DETECTION_CONFIDENCE_THRESHOLD
        return zones

    def process_frame(self, frame):
        try:
            for zone in self._zones:
                statuses = []
                related_objects = []
                for object_index, detected_object in enumerate(frame.regions()):
                    if not self._is_watermark_region(detected_object):
                        zone_status = self._detect_zone_count(frame, detected_object, zone)
                        if zone_status:
                            statuses.append(zone_status)
                            related_objects.append(object_index)
                if related_objects:
                    gva_event_meta.add_event(frame,
                                             event_type=ObjectZoneCount.DEFAULT_EVENT_TYPE,
                                             attributes={'zone-name':zone['name'],
                                                         'related-objects':related_objects,
                                                         'status':statuses,
                                                         'zone-count': len(related_objects)})
            if self._enable_watermark:
                self._add_watermark_regions(frame)
        except Exception:
            print_message("Error processing frame: {}".format(traceback.format_exc()))
        return True

    def _is_watermark_region(self, region):
        for tensor in region.tensors():
            if tensor.name() == "watermark_region":
                return True
        return False

    def _add_watermark_regions(self, frame):
        for zone in self._zones:
            self._add_watermark_region(frame, zone, zone["name"], False)

    def _add_watermark_region(self, frame, zone, frame_label, draw_label):
        zone_poly = zone["polygon"]
        rv_x1, rv_y1 = None, None
        if self._enable_watermark:
            for zone_vertex in range(len(zone_poly)):
                draw_label_value = ""
                # We draw zone label on first vertex defined in configuration (zone index 0)
                if zone_vertex == 0:
                    draw_label_value = frame_label
                if rv_x1 is None and rv_x1 is None:
                    rv_x1, rv_y1 = zone_poly[0]
                else:
                    rv_x1, rv_y1 = zone_poly[zone_vertex % len(zone_poly)]
                dot_region = frame.add_region(rv_x1, rv_y1, 0.008, 0.008, label=draw_label_value, normalized=True)
                for tensor in dot_region.tensors():
                    # Rendering color is currently assigned using position of zone, within extension configuration
                    # list, for simplicity.
                    tensor['label_id'] = self._zones.index(zone)
                    tensor.set_name("watermark_region")
                if draw_label:
                    break

    def _get_detection_poly(self, detected_object):
        detection_poly = [0, 0, 0, 0]
        x_min = detected_object.normalized_rect().x
        x_max = detected_object.normalized_rect().x + detected_object.normalized_rect().w
        y_min = detected_object.normalized_rect().y
        y_max = detected_object.normalized_rect().y + detected_object.normalized_rect().h
        detection_poly[0] = (x_min, y_min)
        detection_poly[1] = (x_min, y_max)
        detection_poly[2] = (x_max, y_max)
        detection_poly[3] = (x_max, y_min)
        return detection_poly

    def _detect_zone_count(self, frame, detected_object, zone):
        object_poly = self._get_detection_poly(detected_object)
        intersects_zone = False
        within_zone = False
        if (detected_object.confidence() >= zone["threshold"]):  # applying optional confidence filter
            within_zone = self.detection_within_zone(zone["polygon"], object_poly)
            if (not within_zone) and (ObjectZoneCount.DEFAULT_TRIGGER_ON_INTERSECT):
                intersects_zone = self.detection_intersects_zone(zone["polygon"], object_poly)
                if intersects_zone:
                    self._add_status_watermark(frame, zone, "intersects")
                    return "intersects"
            if within_zone:
                self._add_status_watermark(frame, zone, "within")
                return "within"
        return None

    def _add_status_watermark(self, frame, zone, status):
        if self._enable_watermark:
            event_label = "{}-{}".format(zone["name"], status)
            self._add_watermark_region(frame, zone, event_label, True)

    def detection_intersects_zone(self, zone_poly, object_poly):
        intersects = not ((zone_poly[0][0] >= object_poly[2][0]) or (zone_poly[2][0] <= object_poly[0][0]) or \
                    (zone_poly[2][1] <= object_poly[3][1]) or (zone_poly[3][1] >= object_poly[2][1]))
        return intersects

    def detection_within_zone(self, zone_poly, object_poly):
        inside = (self.point_within_zone(object_poly[0], zone_poly) and \
            self.point_within_zone(object_poly[1], zone_poly) and \
            self.point_within_zone(object_poly[2], zone_poly) and \
            self.point_within_zone(object_poly[3], zone_poly))
        return inside

    def point_within_zone(self, vertex, zone_poly):
        within = False
        vert_x, vert_y = vertex
        rv_x1, rv_x2 = None, None
        for zone_vertex in range(len(zone_poly)):
            if rv_x1 is None and rv_x2 is None:
                rv_x1, rv_y1 = zone_poly[0]
            rv_x2, rv_y2 = zone_poly[zone_vertex % len(zone_poly)]
            if min(rv_y1, rv_y2) < vert_y <= max(rv_y1, rv_y2) and vert_x <= max(rv_x1, rv_x2):
                if rv_y1 != rv_y2:
                    intersection = (vert_y-rv_y1)*(rv_x2-rv_x1)/(rv_y2-rv_y1)+rv_x1
                if rv_x1 != rv_x2 or vert_x <= intersection:
                    within = not within
            rv_x1, rv_y1 = rv_x2, rv_y2
        return within
