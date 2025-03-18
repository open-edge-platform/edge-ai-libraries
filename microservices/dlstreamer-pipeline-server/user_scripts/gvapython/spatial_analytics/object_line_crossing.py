#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import os
from collections import namedtuple
from enum import Enum
from gvapython.gva_event_meta import gva_event_meta
from src.server.common.utils import logging

Point = namedtuple('Point', ['x', 'y'])
BoundingBox = namedtuple('BoundingBox', ['left', 'top', 'width', 'height'])
Direction = Enum('Direction', 'CLOCKWISE COUNTERCLOCKWISE PARALLEL', start=0)

'''
Object Line Crossing
Reference for line segment intersection calculation:
https://www.geeksforgeeks.org/check-if-two-given-line-segments-intersect/
'''

logger = logging.get_logger('object_line_crossing', is_static=True)

class ObjectLineCrossing: # pylint: disable=too-few-public-methods

    def __init__(self, lines=None, enable_watermark=False, log_level="INFO"):
        self._detected_objects = {}
        self._lines = []
        self._enable_watermark = enable_watermark
        logger.log_level = log_level
        if self._enable_watermark and os.getenv("ENABLE_RTSP") != "true":
            logger.warning("RTSP output is not enabled by environment variable.")
        if not lines:
            logger.warning("No line configuration was supplied to ObjectLineCrossing.")
            return
        for line in lines:
            try:
                self._lines.append(SpatialAnalysisCrossingLine(line))
            except Exception as error:
                logger.error(error)
                logger.error("Exception creating SpatialAnalysisCrossingLine: {}".format(line))
        if not self._lines:
            raise Exception('Empty line configuration. No lines to check against.')

    def process_frame(self, frame):
        try:
            for line in self._lines:
                related_objects = []
                crossed_directions = []
                for object_index, detected_object in enumerate(frame.regions()):
                    track_id = detected_object.object_id()
                    if track_id in self._detected_objects:
                        current_position = BoundingBox(*detected_object.normalized_rect())
                        direction = line.detect_line_crossing(previous_position=self._detected_objects[track_id],
                                                              current_position=current_position)
                        if direction:
                            direction = direction.lower()
                            logger.debug('ID {} {} {}'.format(track_id, direction, line.name))
                            related_objects.append(object_index)
                            crossed_directions.append(direction)
                if crossed_directions:
                    attributes = {'line-name':line.name,
                                  'related-objects':related_objects,
                                  'directions':crossed_directions,
                                  'clockwise-total': line.cross_totals[Direction.CLOCKWISE.value],
                                  'counterclockwise-total': line.cross_totals[Direction.COUNTERCLOCKWISE.value],
                                  'total': sum(line.cross_totals)}
                    gva_event_meta.add_event(frame,
                                                       event_type=line.event_type,
                                                       attributes=attributes)
            self._update_object_positions(frame)

            if self._enable_watermark:
                self._add_watermark(frame)

        except Exception as error:
            logger.error(error)
        return True

    def _update_object_positions(self, frame):
        for detected_object in frame.regions():
            track_id = detected_object.object_id()
            bounding_box = BoundingBox(*detected_object.normalized_rect())
            self._detected_objects[track_id] = bounding_box

    def _add_point(self, frame, point, label):
        region = frame.add_region(point.x, point.y, 0, 0, label=label, normalized=True)
        for tensor in region.tensors():
            tensor.set_name("watermark_region")

    def _add_watermark(self, frame):
        for index, _ in enumerate(self._lines):
            self._add_point(frame, self._lines[index].line_segment.start_point, "{}_Start".format(index))
            self._add_point(frame, self._lines[index].line_segment.end_point, "{}_End".format(index))
            self._add_point(frame, self._lines[index].get_segment_midpoint(),
                            "{}_Count".format(sum(self._lines[index].cross_totals)))

class SpatialAnalysisCrossingLine:

    FocusPoint = Enum('Focus_Point', 'bottom_center center')

    def __init__(self, line):
        self.event_type = 'object-line-crossing'
        self._focus_point = self.FocusPoint.bottom_center
        self.cross_totals = [0] * len(Direction)

        if 'name' not in line:
            raise ValueError('Crossing Line \'name\' not defined')
        self.name = line['name']

        if 'line' not in line:
            raise ValueError('Line segment not defined')
        if len(line['line']) != 2 or \
           len(line['line'][0]) != 2 or \
           len(line['line'][1]) != 2:
            raise ValueError('Line segment incorrectly defined')

        start_x = line['line'][0][0]
        start_y = line['line'][0][1]
        end_x = line['line'][1][0]
        end_y = line['line'][1][1]
        if start_x < 0 or start_x > 1 or start_y < 0 or start_y > 1:
            raise ValueError('Start point not normalized values [0,1]')
        if end_x < 0 or end_x > 1 or end_y < 0 or end_y > 1:
            raise ValueError('End point not normalized values [0,1]')
        self.line_segment = LineSegment(Point(start_x, start_y), Point(end_x, end_y))

        if 'focus' in line:
            try:
                self._focus_point = self.FocusPoint[line['focus']]
            except Exception as exception:
                raise ValueError('Got invalid focus point: {}'.format(line['focus'])) from exception

    def detect_line_crossing(self, previous_position, current_position):
        previous_position_point = self._get_focus_point(previous_position)
        current_position_point = self._get_focus_point(current_position)
        object_segment = LineSegment(previous_position_point, current_position_point)
        if (self.line_segment.intersect(object_segment)):
            orientation = self.line_segment.get_orientation(current_position_point)
            self.cross_totals[orientation.value] += 1
            return orientation.name
        return None

    def _get_focus_point(self, bounding_box):
        if self._focus_point == self.FocusPoint.bottom_center:
            return Point(x=bounding_box.left + (bounding_box.width/2.0),
                         y=bounding_box.top + bounding_box.height)
        if self._focus_point == self.FocusPoint.center:
            return Point(x=bounding_box.left + (bounding_box.width/2.0),
                         y=bounding_box.top + (bounding_box.height/2.0))
        return None

    def get_segment_midpoint(self):
        return self.line_segment.get_midpoint()

class LineSegment:

    def __init__(self, start_point, end_point):
        self.start_point = start_point
        self.end_point = end_point

    # Checks if point is on this segment. All points are assumed collinear.
    def point_on_segment(self, point):
        if ((point.x <= max(self.start_point.x, self.end_point.x)) and
                (point.x >= min(self.start_point.x, self.end_point.x)) and
                (point.y <= max(self.start_point.y, self.end_point.y)) and
                (point.y >= min(self.start_point.y, self.end_point.y))):
            return True
        return False

    def get_orientation(self, point):
        cross_product = (float(self.end_point.y - self.start_point.y) * (point.x - self.end_point.x)) - \
                        (float(point.y - self.end_point.y) * (self.end_point.x - self.start_point.x))
        if (cross_product > 0):
            return Direction.COUNTERCLOCKWISE
        if (cross_product < 0):
            return Direction.CLOCKWISE
        return Direction.PARALLEL

    def intersect(self, object_segment):

        orientation1 = self.get_orientation(object_segment.start_point)
        orientation2 = self.get_orientation(object_segment.end_point)
        orientation3 = object_segment.get_orientation(self.start_point)
        orientation4 = object_segment.get_orientation(self.end_point)
        # Basic Case
        # (self.start_point, self.end_point, object_segment.start_point) and
        # (self.start_point, self.end_point, object_segment.end_point) have diferent orientations and
        # (object_segment.start_point, object_segment.end_point, self.start_point) and
        # (object_segment.start_point, object_segment.end_point, self.end_point) have different orientations
        if ((orientation1 != orientation2) and (orientation3 != orientation4)):
            return True

        # Special Cases
        # Check if PARALLEL points are on the same segment
        if ((orientation1 == Direction.PARALLEL) and self.point_on_segment(object_segment.start_point)):
            return True
        if ((orientation2 == Direction.PARALLEL) and self.point_on_segment(object_segment.end_point)):
            return True
        if ((orientation3 == Direction.PARALLEL) and object_segment.point_on_segment(self.start_point)):
            return True
        if ((orientation4 == Direction.PARALLEL) and object_segment.point_on_segment(self.end_point)):
            return True

        return False

    def get_midpoint(self):
        return Point((self.start_point.x + self.end_point.x) / 2.0,
                     (self.start_point.y + self.end_point.y) / 2.0)
