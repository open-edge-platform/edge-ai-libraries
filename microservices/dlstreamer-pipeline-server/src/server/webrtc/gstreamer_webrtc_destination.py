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

class GStreamerWebRTCDestination(AppDestination):

    def __init__(self, request, pipeline):
        AppDestination.__init__(self, request, pipeline)
        self._pipeline = pipeline
        self._webrtc_manager = pipeline.webrtc_manager
        self._app_src = None
        self._logger = logging.get_logger('GStreamerWebRTCDestination', is_static=True)
        self._need_data = False
        self._pts = 0
        self._last_timestamp = 0
        self._frame_size = 0
        self._frame_count = 0
        self._clock = Gst.SystemClock()
        # caps = Gst.Caps.from_string("video/x-raw")
        # if self._pipeline.appsink_element.props.caps:
        #     caps = caps.intersect(self._pipeline.appsink_element.props.caps)
        # self._pipeline.appsink_element.props.caps = caps
        self._get_request_parameters(request)

    def _get_request_parameters(self, request):
        # destination_config = request.get("destination", {})
        # frame_config = destination_config.get("frame", {})
        self._webrtc_peerid = request["peer-id"]
        self._cache_length = request.get("cache-length", 30)
        self._sync_with_source = request.get("sync-with-source")
        self._sync_with_destination = request.get("sync-with-destination", True)
        self.overlay = request.get("overlay",True)
        self.bitrate = request.get("bitrate", 2048)

    def _init_stream(self, sample):
        self._frame_size = sample.get_buffer().get_size()
        caps = sample.get_caps()
        self._pipeline.appsink_element.props.caps = caps
        self._need_data = False
        self._last_timestamp = self._clock.get_time()
        if self._sync_with_source is not None:
            self._pipeline.appsink_element.set_property("sync", self._sync_with_source)
            self._logger.info("Setting the appsink sync property to {}".format(self._sync_with_source))
        self._logger.info("Adding WebRTC frame destination stream for peer_id {}.".format(self._webrtc_peerid))
        self._logger.debug("WebRTC Stream frame caps == {}".format(caps))
        self._webrtc_manager.add_stream(self._webrtc_peerid, caps, self,self.overlay)

    def _on_need_data(self, _unused_src, _):
        self._need_data = True

    def _on_enough_data(self, _):
        self._need_data = False

    def set_app_src(self, app_src, webrtc_pipeline):
        self._app_src = app_src
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
        encoder = webrtc_pipeline.get_by_name("h264enc")
        if self.bitrate and encoder:
            # if encoder has the bitrate property, set it
            if encoder.find_property("bitrate") is not None:
                self._logger.debug("Setting bitrate to {} for WebRTC stream".format(self.bitrate))
                encoder.set_property("bitrate", self.bitrate)
        self._app_src.connect('need-data', self._on_need_data)
        self._app_src.connect('enough-data', self._on_enough_data)

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
                "Push buffer failed for stream {} with {}".format(self._webrtc_peerid, retval))
            self._end_stream()

    def process_frame(self, frame):
        self._logger.info("process_frame negotiating caps")
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
            self._logger.debug("WebRTC Stream - EOS received")
            del self._app_src
            self._app_src = None

    def finish(self):
        self._end_stream()
        if self._webrtc_manager:
            self._webrtc_manager.remove_stream(self._webrtc_peerid)