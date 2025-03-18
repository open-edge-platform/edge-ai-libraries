#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import json
from collections import namedtuple
from enum import Enum, auto
from threading import Event, Thread

import gi

gi.require_version('Gst', '1.0')
gi.require_version('GstApp', '1.0')
# pylint: disable=wrong-import-position
from gi.repository import Gst
from gstgva.util import GVAJSONMeta
from src.server.app_source import AppSource
from src.server.gstreamer_app_destination import GvaSample
from src.server.gstreamer_pipeline import GStreamerPipeline
# pylint: enable=wrong-import-position

fields = ['data',
          'caps',
          'pts',
          'info',
          'message',
          'segment',
          'duration']

GvaFrameData = namedtuple('GvaFrameData', fields)
GvaFrameData.__new__.__defaults__ = (None,) * len(fields)

class GStreamerAppSource(AppSource, Thread):

    class Mode(Enum):
        PUSH = auto()
        PULL = auto()
        @classmethod
        def _missing_(cls, name):
            return cls[name.upper()]

    def __init__(self, request, pipeline, *args, **kwargs):
        AppSource.__init__(self, request, pipeline)
        self._mode = GStreamerAppSource.Mode.PULL
        self._input_queue = None
        self._src = None
        self._src = pipeline.appsrc_element

        request_config = request.get("source", {})
        self._input_queue = request_config.get("input", None)
        if (not self._src) or (not self._input_queue) or (not isinstance(pipeline,
                                                                         GStreamerPipeline)):
            raise Exception("GStreamerAppSource requires GStreamerPipeline "\
                            "appsrc element and input queue")
        self._mode = GStreamerAppSource.Mode(request_config.get("mode", "pull"))

        if (self._mode == GStreamerAppSource.Mode.PUSH):
            Thread.__init__(self, daemon=True, *args, **kwargs)
            self._stop = False
            self._push_frames = Event()
            self.start()

    def _create_input_frame(self, item):
        if (isinstance(item, GvaFrameData)):
            gst_buffer = None
            if (item.data):
                if (not isinstance(item.data, bytes)):
                    raise Exception("GvaFrameData must contain bytes")
                gst_buffer = Gst.Buffer.new_allocate(None, len(item.data))
                gst_buffer.fill(0, item.data)
                if (item.pts):
                    gst_buffer.pts = item.pts
                    gst_buffer.dts = item.pts
                if (item.duration):
                    gst_buffer.duration = item.duration
                if (item.message) and (isinstance(item.message, str)):
                    try:
                        item.message = json.loads(item.message)
                    except Exception:
                        pass
                if (item.message):
                    GVAJSONMeta.add_json_meta(gst_buffer, json.dumps(item.message))
            gst_caps = item.caps
            if (item.caps) and (isinstance(item.caps, str)):
                gst_caps = Gst.caps_from_string(item.caps)
            sample = Gst.Sample.new(gst_buffer, gst_caps, item.segment, item.info)
            return sample
        if isinstance(item, Gst.Sample):
            return item
        if isinstance(item, Gst.Buffer):
            return item
        if isinstance(item, GvaSample):
            return item.sample
        return None

    def _get_and_push(self):
        item = self._input_queue.get()
        if (not item):
            self._src.end_of_stream()
            return
        frame = self._create_input_frame(item)
        if isinstance(frame, Gst.Buffer):
            self._src.push_buffer(frame)
        elif isinstance(frame, Gst.Sample):
            self._src.push_sample(frame)


    def start_frames(self):
        if (self._mode == GStreamerAppSource.Mode.PUSH):
            self._push_frames.set()
            return
        self._get_and_push()

    def pause_frames(self):
        if (self._mode == GStreamerAppSource.Mode.PUSH):
            self._push_frames.clear()


    def finish(self):
        self._stop = True
        if (self._mode == GStreamerAppSource.Mode.PUSH):
            self._push_frames.set()

    def run(self):
        while (not self._stop):
            self._push_frames.wait()
            if (not self._stop):
                self._get_and_push()
