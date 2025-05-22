#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

from src.server.webrtc.gstreamer_webrtc_stream import GStreamerWebRTCStream
from src.server.common.utils import logging
class GStreamerWebRTCManager:

    _source_mediamtx = "appsrc name=webrtc_source format=GST_FORMAT_TIME "
    _WebRTCVideoPipeline = " ! videoconvert ! gvawatermark " \
                " ! x264enc speed-preset=ultrafast name=h264enc" \
                " ! video/x-h264,profile=baseline " \
                " ! whipclientsink signaller::whip-endpoint="
    _WebRTCVideoPipeline_jpeg = " ! jpegdec ! videoconvert ! gvawatermark " \
                " ! x264enc speed-preset=ultrafast name=h264enc " \
                " ! video/x-h264,profile=baseline " \
                " ! whipclientsink signaller::whip-endpoint="

    def __init__(self, whip_endpoint):
        self._logger = logging.get_logger('GStreamerWebRTCManager', is_static=True)
        self._whip_endpoint = whip_endpoint
        self._streams = {}

    def _peerid_in_use(self, peer_id):
        if not peer_id:
            raise Exception("Empty peer_id was passed to WebRTCManager!")
        if peer_id in self._streams:
            return True
        return False

    def add_stream(self, peer_id, frame_caps, destination_instance, overlay):
        stream_caps = self._select_caps(frame_caps.to_string())
        if not self._peerid_in_use(peer_id):
            launch_string = self._get_launch_string(stream_caps, peer_id,overlay)
            self._streams[peer_id] = GStreamerWebRTCStream(peer_id, stream_caps, launch_string, destination_instance,
                                                           self._whip_endpoint)
            self._logger.info("Starting WebRTC Stream for peer_id:{}".format(peer_id))
            self._streams[peer_id].start()

    def _select_caps(self, caps):
        split_caps = caps.split(',')
        new_caps = []
        selected_caps = ['image/jpeg', 'video/x-raw', 'width', 'height', 'framerate',
                         'layout', 'format']
        for cap in split_caps:
            for selected in selected_caps:
                if selected in cap:
                    new_caps.append(cap)
        return new_caps

    def _get_launch_string(self, stream_caps, peer_id,overlay):
        s_src = "{} caps=\"{}\"".format(self._source_mediamtx, ','.join(stream_caps))
        if "image/jpeg" in stream_caps:
            video_pipeline = self._WebRTCVideoPipeline_jpeg
        else:
            video_pipeline = self._WebRTCVideoPipeline
        if overlay is False:
            video_pipeline = video_pipeline.replace("! gvawatermark ", "")
        elif overlay is True:
            video_pipeline = video_pipeline
        pipeline_launch = " {} {} ".format(s_src, video_pipeline)
        pipeline_launch = pipeline_launch + self._whip_endpoint + "/" + peer_id + "/whip"
        self._logger.info("Final launch WebRTC Streams {}".format(pipeline_launch))
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