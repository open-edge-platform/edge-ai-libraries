#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import os
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

# The RTSP server serves every client (and waits for every media to be prepared) on the threads of its thread pool,
# and GStreamer's default is ONE thread. A stream whose media never gets prepared (for example a pipeline that stopped
# feeding its appsrc) then blocks that thread for the whole prepare timeout (20 s) per request, and every other
# client, including the other cameras' streams, waits behind it; clients that retry (a relay re-pulling a stream) keep
# the thread blocked for good. More threads keep one bad stream from stopping the others.
DEFAULT_RTSP_MAX_THREADS = 8


def _max_threads():
    try:
        value = int(os.getenv("RTSP_SERVER_MAX_THREADS", str(DEFAULT_RTSP_MAX_THREADS)))
    except ValueError:
        value = DEFAULT_RTSP_MAX_THREADS
    return value if value == -1 or value >= 1 else DEFAULT_RTSP_MAX_THREADS     # -1 = unlimited


Stream = namedtuple('stream', ['source', 'caps', 'overlay', 'overlay_properties', 'encoding'])
Stream.__new__.__defaults__ = (None, None, True, None, 'mjpeg')

class GStreamerRtspServer():
    def __init__(self, port):
        self._logger = logging.get_logger('GSTRtspServer', is_static=True)
        Gst.init(None)
        self._stopped = False
        self._port = port
        self._server = GstRtspServer.RTSPServer()
        self._server.set_service(str(port))
        self._server.get_thread_pool().set_max_threads(_max_threads())
        self._context = None
        self._mainloop = None
        self._mount_points = self._server.get_mount_points()
        self._streams = {}
        self._factories = {}
        self._thread = None

    def check_if_path_exists(self, rtsp_path):
        if rtsp_path in self._streams:
            self._logger.error("RTSP Stream at {} already exists, use different path".format(rtsp_path))
            raise Exception("RTSP Stream at {} already exists, use different path".format(rtsp_path))

    def add_stream(self, identifier, rtsp_path, stream):
        """Register a stream for the given RTSP path.

        `stream` is a `Stream` namedtuple instance describing the source,
        caps, overlay settings and encoding to mount at `rtsp_path`.
        """
        self._streams[rtsp_path] = stream
        # One factory per stream. A shared factory caches its media by path, and a media outlives its pipeline until
        # its RTSP session times out (60 s by default), so a pipeline restarted on the same path was handed the old
        # media, which nothing feeds any more: DESCRIBE/PLAY succeed but no video arrives.
        factory = GStreamerRtspFactory(self)
        factory.set_shared(True)
        factory.set_eos_shutdown(True)      # drop the media as soon as its pipeline ends
        self._factories[rtsp_path] = factory
        self._mount_points.add_factory(rtsp_path, factory)
        url = "rtsp:://<host ip>:{}{}".format(self._port, rtsp_path)
        self._logger.info("Created RTSP Stream for instance {} at {}".format(identifier, url))

    def remove_stream(self, rtsp_path, owner=None):
        """Unregister `rtsp_path`. With `owner`, only if that destination still owns the stream: a pipeline that
        stopped can release its path before it has finished tearing down, and a new pipeline may already own it."""
        self._logger.debug(
            "Removing RTSP Stream: {}".format(rtsp_path))
        stream = self._streams.get(rtsp_path)
        if stream is not None and (owner is None or stream.source is owner):
            self._mount_points.remove_factory(rtsp_path)
            self._factories.pop(rtsp_path, None)
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
            self._factories = None
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