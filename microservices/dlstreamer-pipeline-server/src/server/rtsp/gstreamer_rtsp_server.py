#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

from threading import Thread
from collections import namedtuple

import gi
gi.require_version('GstRtspServer', '1.0')
gi.require_version('Gst', '1.0')
# pylint: disable=wrong-import-position
from gi.repository import Gst, GstRtspServer, GLib
from src.server.common.utils import logging
from src.server.rtsp.gstreamer_rtsp_factory import GStreamerRtspFactory
# pylint: enable=wrong-import-position

Stream = namedtuple('stream', ['source', 'caps','overlay'])
Stream.__new__.__defaults__ = (None, None, True)

class GStreamerRtspServer():
    def __init__(self, port):
        self._logger = logging.get_logger('GSTRtspServer', is_static=True)
        Gst.init(None)
        self._stopped = False
        self._port = port
        self._server = GstRtspServer.RTSPServer()
        self._server.set_service(str(port))
        self._context = None
        self._mainloop = None
        self._mount_points = self._server.get_mount_points()
        self._streams = {}
        self._thread = None
        self._factory = GStreamerRtspFactory(self)
        self._factory.set_shared(True)

    def check_if_path_exists(self, rtsp_path):
        if rtsp_path in self._streams:
            self._logger.error("RTSP Stream at {} already exists, use different path".format(rtsp_path))
            raise Exception("RTSP Stream at {} already exists, use different path".format(rtsp_path))

    def add_stream(self, identifier, rtsp_path, caps, source, overlay):
        self._streams[rtsp_path] = Stream(source, caps, overlay)
        self._mount_points.add_factory(rtsp_path, self._factory)
        url = "rtsp:://<host ip>:{}{}".format(self._port, rtsp_path)
        self._logger.info("Created RTSP Stream for instance {} at {}".format(identifier, url))

    def remove_stream(self, rtsp_path):
        self._logger.debug(
            "Removing RTSP Stream: {}".format(rtsp_path))
        if rtsp_path in self._streams:
            self._mount_points.remove_factory(rtsp_path)
            del self._streams[rtsp_path]

    def get_source(self, rtsp_path):
        if rtsp_path in self._streams:
            return self._streams[rtsp_path]
        return None

    def _loop(self):
        try:
            self._mainloop.run()
        except (KeyboardInterrupt, SystemExit):
            pass
        self._logger.debug("Exiting RTSP Main loop")

    def start(self):
        self._context = GLib.MainContext()
        self._server.attach(self._context)
        self._mainloop = GLib.MainLoop.new(self._context, False)
        self._thread = Thread(target=self._loop, daemon=True)
        self._thread.start()
        self._logger.info("Gstreamer RTSP Server Started on port: {}".format(self._port))

    def stop(self):
        if not self._stopped:
            self._stopped = True
            self._logger.info("Stopping Gstreamer RTSP Server")
            for rtsp_path in list(self._streams):
                self.remove_stream(rtsp_path)
            self._factory = None
            self._streams = None
            if self._mainloop:
                self._mainloop.quit()
            if self._thread:
                self._thread.join()
            self._mainloop = None
            self._thread = None
            if self._context:
                self._context.unref()
            self._context = None
            self._server = None
            self._logger.debug("Gstreamer RTSP Server Stopped")