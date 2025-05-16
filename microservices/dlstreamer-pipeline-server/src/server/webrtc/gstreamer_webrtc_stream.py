#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

from threading import Thread
from socket import gaierror
import gi
import requests

# pylint: disable=wrong-import-position
gi.require_version('Gst', '1.0')
from gi.repository import Gst
gi.require_version('GstWebRTC', '1.0')
from gi.repository import GstWebRTC
gi.require_version('GstSdp', '1.0')
from gi.repository import GstSdp
# pylint: enable=wrong-import-position
import src.server.gstreamer_pipeline as GstPipeline
from src.server.common.utils import logging

class GStreamerWebRTCStream:
    def __init__(self, peer_id, frame_caps, launch_string, destination_instance,
                 whip_endpoint):
        self._logger = logging.get_logger('GStreamerWebRTCStream', is_static=True)
        self._peer_id = peer_id
        self._frame_caps = frame_caps
        self._launch_string = launch_string
        self._destination_instance = destination_instance
        self._server = whip_endpoint
        self._logger.debug("GStreamerWebRTCStream __init__ with Whip endpoint  {}".format(self._server))
        self._stopped = False
        self._thread = None
        self._pipe = None
        self._state = None
        self._webrtc_pipeline = None
        self._webrtc_pipeline_type = "GStreamer WebRTC Stream"

    def prepare_destination_pads(self, pipeline):
        self._pipe = pipeline
        self._pipe.caps = self._frame_caps
        appsrc = self._pipe.get_by_name("webrtc_source")
        self._destination_instance.set_app_src(appsrc, self._pipe)

    def _finished_callback(self):
        self._logger.info("GStreamerPipeline finished for peer_id:{}".format(self._peer_id))

    def _start_pipeline(self):
        self._logger.info("Starting WebRTC pipeline for peer_id:{}".format(self._peer_id))
        config = {"type": self._webrtc_pipeline_type, "template": self._launch_string,
                  "prepare-pads": self.prepare_destination_pads}
        request = {"source": { "type": "webrtc_destination" }, "peer_id": self._peer_id}
        self._reset()
        self._webrtc_pipeline = GstPipeline.GStreamerPipeline(
            self._peer_id, config, None, request, self._finished_callback, None)
        self._webrtc_pipeline.start()
        self._logger.info("WebRTC pipeline started for peer_id:{}".format(self._peer_id))

    def _log_banner(self, heading):
        banner = "="*len(heading)
        self._logger.info(banner)
        self._logger.info(heading)
        self._logger.info(banner)

    def _check_plugins(self):
        self._log_banner("WebRTC Plugin Check")
        needed = ["opus", "vpx", "nice", "webrtc", "dtls", "srtp", "rtp",
                  "rtpmanager","rswebrtc"]
        missing = list(filter(lambda p: Gst.Registry.get().find_plugin(p) is None, needed))
        if missing:
            self._logger.info("Missing gstreamer plugins: {}".format(missing))
            return False
        self._logger.debug("Successfully found required gstreamer plugins")
        return True

    def _thread_launcher(self):
        try:
            self._start_pipeline()
        except (KeyboardInterrupt, SystemExit):
            pass

    def start(self):
        self._logger.info("Starting WebRTC Stream using Signaling Server at: {}".format(self._server))
        if not self._check_plugins():
            self._logger.error("WebRTC Stream error - dependent plugins are missing!")
        self._thread = Thread(target=self._thread_launcher)
        self._thread.start()

    def _reset(self):
        if self._webrtc_pipeline:
            self._webrtc_pipeline.stop()
        self._webrtc_pipeline = None
        self._pipe = None

    def stop(self):
        self._reset()
        self._stopped = True
        self._logger.info("Stopping GStreamer WebRTC Stream for peer_id {}".format(self._peer_id))
        if self._thread:
            self._thread.join()
        self._thread = None
        self._logger.debug("GStreamer WebRTC Stream completed pipeline for peer_id {}".format(self._peer_id))