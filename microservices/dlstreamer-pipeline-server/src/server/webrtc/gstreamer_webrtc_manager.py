#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

from src.server.webrtc.gstreamer_webrtc_stream import GStreamerWebRTCStream
from src.server.common.utils import logging

class GStreamerWebRTCManager:
    _source = "appsrc name=webrtc_source format=GST_FORMAT_TIME "
    _WebRTCVideoPipeline = " ! videoconvert ! video/x-raw,format=I420 ! gvawatermark " \
				" ! vp8enc name=vp8encoder deadline=1 ! rtpvp8pay " \
				" ! queue ! application/x-rtp,media=video,encoding-name=VP8,payload=97 " \
				" ! webrtcbin name=webrtc_destination bundle-policy=max-bundle"

    def __init__(self, signaling_server):
        self._logger = logging.get_logger('GStreamerWebRTCManager', is_static=True)
        self._signaling_server = signaling_server
        self._streams = {}

    def _peerid_in_use(self, peer_id):
        if not peer_id:
            raise Exception("Empty peer_id was passed to WebRTCManager!")
        if peer_id in self._streams:
            return True
        return False

    def add_stream(self, peer_id, frame_caps, destination_instance):
        stream_caps = self._select_caps(frame_caps.to_string())
        if not self._peerid_in_use(peer_id):
            launch_string = self._get_launch_string(stream_caps)
            self._streams[peer_id] = GStreamerWebRTCStream(peer_id, stream_caps, launch_string, destination_instance,
                                                           self._signaling_server)
            self._logger.info("Starting WebRTC Stream for peer_id:{}".format(peer_id))
            self._streams[peer_id].start()

    def _select_caps(self, caps):
        split_caps = caps.split(',')
        new_caps = []
        selected_caps = ['video/x-raw', 'width', 'height', 'framerate',
                         'layout', 'format']
        for cap in split_caps:
            for selected in selected_caps:
                if selected in cap:
                    new_caps.append(cap)
        return new_caps

    def _get_launch_string(self, stream_caps):
        s_src = "{} caps=\"{}\"".format(self._source, ','.join(stream_caps))
        pipeline_launch = " {} {} ".format(s_src, self._WebRTCVideoPipeline)
        self._logger.info(pipeline_launch)
        return pipeline_launch

    def remove_stream(self, peer_id):
        if peer_id in self._streams:
            self._logger.info("Stopping WebRTC Stream for peer_id {id}".format(id=peer_id))
            self._streams[peer_id].stop()
            del self._streams[peer_id]
            self._logger.debug("Remaining set of WebRTC Streams {}".format(self._streams))

    def stop(self):
        for peer_id in list(self._streams):
            self.remove_stream(peer_id)
        self._streams = None
