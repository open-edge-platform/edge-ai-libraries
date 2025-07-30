#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import gi
gi.require_version('Gst', '1.0')
# pylint: disable=wrong-import-position
from gi.repository import Gst
from src.server.common.utils import logging
from src.server.app_destination import AppDestination
# pylint: enable=wrong-import-position

class GStreamerRtspDestination(AppDestination):

    def __init__(self, request, pipeline):
        AppDestination.__init__(self, request, pipeline)
        self._pipeline = pipeline
        self._rtsp_path = pipeline.rtsp_path
        self._rtsp_server = pipeline.rtsp_server
        self._identifier = pipeline.identifier
        self._app_src = None
        self._is_audio_pipeline = False
        self._logger = logging.get_logger('GStreamerRtspDestination', is_static=True)
        self._need_data = False
        self._pts = 0
        self._last_timestamp = 0
        self._frame_size = 0
        self._clock = Gst.SystemClock()
        # caps = Gst.Caps.from_string("video/x-raw")
        # if self._pipeline.appsink_element.props.caps:
        #     caps = caps.intersect(self._pipeline.appsink_element.props.caps)
        # self._pipeline.appsink_element.props.caps = caps
        self._get_request_parameters(request)

    def _get_request_parameters(self, request):
        # destination_config = request.get("destination",
        #                                  {})
        # frame_config = destination_config.get("frame",
        #                                       {})
        self._cache_length = request.get("cache-length",30)
        self._sync_with_source = request.get("sync-with-source")
        self._sync_with_destination = request.get("sync-with-destination", True)
        self._encode_quality = request.get("encode-quality", 85)
        self.overlay = request.get("overlay", True)

    def _init_stream(self, sample):
        self._frame_size = sample.get_buffer().get_size()
        caps = sample.get_caps()
        self._pipeline.appsink_element.props.caps = caps
        self._need_data = False
        self._rtsp_server.add_stream(self._identifier, self._rtsp_path, caps, self,self.overlay)
        self._last_timestamp = self._clock.get_time()
        if self._sync_with_source is not None:
            self._pipeline.appsink_element.set_property("sync", self._sync_with_source)
            self._logger.info("Setting the appsink sync property to {}".format(self._sync_with_source))

    def on_need_data(self, _src, _):
        self._need_data = True

    def on_enough_data(self, _):
        self._need_data = False

    def set_app_src(self, app_src, is_audio_pipeline, rtsp_pipeline):
        self._app_src = app_src
        self._is_audio_pipeline = is_audio_pipeline
        self._pts = 0
        self._app_src.set_property("is-live", True)
        self._app_src.set_property("do-timestamp", True)
        self._app_src.set_property("blocksize", self._frame_size)
        if self._sync_with_destination:
            self._app_src.set_property("block", True)
            self._app_src.set_property("min-percent", 100)
        if self._cache_length:
            self._app_src.set_property("max-bytes",
                                       int(self._frame_size*self._cache_length))
        encoder = rtsp_pipeline.get_by_name("jpegencoder")
        if self._encode_quality and encoder:
            encoder.set_property("quality", self._encode_quality)

    def _push_buffer(self, buffer):
        buffer.make_writable()
        timestamp = self._clock.get_time()
        delta = timestamp - self._last_timestamp
        buffer.pts = buffer.dts = self._pts
        buffer.duration = delta
        self._pts += delta
        self._last_timestamp = timestamp
        retval = self._app_src.emit('push-buffer', buffer)
        if retval != Gst.FlowReturn.OK:
            self._logger.debug(
                "Push buffer failed for stream {} with {}".format(self._rtsp_path, retval))
            self._end_stream()

    def process_frame(self, frame):
        # pylint: disable=method-hidden
        self._init_stream(frame)
        self.process_frame = self._process_frame
        self.process_frame(frame)

    def _process_frame(self, frame):
        if self._need_data:
            self._push_buffer(frame.get_buffer())
        else:
            self._last_timestamp = self._clock.get_time()

    def _end_stream(self):
        self._need_data = False
        if self._app_src:
            self._app_src.end_of_stream()
            del self._app_src
            self._app_src = None

    def finish(self):
        self._end_stream()
        if self._rtsp_server:
            self._rtsp_server.remove_stream(self._rtsp_path)