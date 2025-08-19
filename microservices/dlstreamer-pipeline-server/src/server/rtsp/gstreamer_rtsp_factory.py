#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import gi
gi.require_version('GstRtspServer', '1.0')
gi.require_version('Gst', '1.0')
# pylint: disable=wrong-import-position
from gi.repository import Gst, GstRtspServer
from src.server.common.utils import logging
# pylint: enable=wrong-import-position

class GStreamerRtspFactory(GstRtspServer.RTSPMediaFactory):
    _source = "appsrc name=source format=GST_FORMAT_TIME"

    _RtspVideoPipeline_withjpeginput = " ! rtpjpegpay name=pay0"  # removed gvawatermark to avoid duplicate overlay assuming DLStreamer pipeline server pipeline already has gvawatermark
        # ! gvawatermark ! jpegenc name=jpegencoder ! rtpjpegpay name=pay0"

    _RtspVideoPipeline_withjpeginput_overlay = " ! jpegdec ! videoconvert  \
        ! gvawatermark ! jpegenc name=jpegencoder ! rtpjpegpay name=pay0" 

    _RtspVideoPipeline = " ! videoconvert  \
        ! gvawatermark ! jpegenc name=jpegencoder ! rtpjpegpay name=pay0"
    
    # GPU pipeline variants for hardware-accelerated buffers
    # _RtspVideoPipeline_GPU_VASurface = " ! vaapipostproc ! vaapijpegenc ! rtpjpegpay name=pay0"
    
    # _RtspVideoPipeline_GPU_DMABuf = " ! videoconvert ! gvawatermark ! vaapijpegenc ! rtpjpegpay name=pay0"
    
    # _RtspVideoPipeline_GPU_VAMemory = " ! videoconvert ! gvawatermark ! vaapijpegenc ! rtpjpegpay name=pay0" 

    # Decoding audio again as there is issue with audio pipeline element audiomixer
    _RtspAudioPipeline = " ! queue ! decodebin ! audioresample ! audioconvert " \
    " ! avenc_aac ! queue ! mpegtsmux ! rtpmp2tpay  name=pay0 pt=96"

    def replace_with_vaelements_when_VAMemory(self, pipeline):
        """
        Replace elements in the pipeline with VA-API equivalents.
        """
        if "jpegenc" in pipeline:
            pipeline = pipeline.replace("jpegenc", "vajpegenc")
        if "jpegdec" in pipeline:
            pipeline = pipeline.replace("jpegdec", "vajpegdec")
        return pipeline        

    def __init__(self, rtsp_server):
        GstRtspServer.RTSPMediaFactory.__init__(self)
        self._logger = logging.get_logger(
            'GStreamerRtspFactory', is_static=True)
        self._rtsp_server = rtsp_server
        if not self._rtsp_server:
            self._logger.error("GStreamerRtspFactory: Invalid RTSP Server")
            raise Exception("GStreamerRtspFactory: Invalid RTSP Server")

    def _select_caps(self, caps):
        split_caps = caps.split(',')
        new_caps = []
        selected_caps = ['image/jpeg', 'video/x-raw', 'width', 'height',
                         'audio/x-raw', 'rate', 'channels', 'layout',
                         'format']
        for cap in split_caps:
            for selected in selected_caps:
                if selected in cap:
                    new_caps.append(cap)
        return new_caps

    def _is_gpu_buffer(self, caps):
        """
        Determine if the caps indicate GPU buffer based on memory features.
        Returns tuple: (is_gpu, caps_feature_type)
        
        GPU buffer types:
        - VASurface: Video Acceleration Surface (Intel GPU)
        - DMABuf: Direct Memory Access Buffer (cross-device)
        - VAMemory: Video Acceleration Memory (Intel GPU)
        """
        caps_string = caps.to_string()
        
        # Check for GPU buffer indicators
        if "memory:VASurface" in caps_string:
            return True, "VASurface"
        elif "memory:DMABuf" in caps_string:
            return True, "DMABuf"  
        elif "memory:VAMemory" in caps_string:
            return True, "VAMemory"
        else:
            # System memory (CPU)
            return False, "System"

    def do_create_element(self, url):
        # pylint: disable=arguments-differ
        # pylint disable added as pylint comparing do_create_element with some other method with same name.

        stream = self._rtsp_server.get_source(url.abspath)
        if not stream:
            self._logger.error(
                "GStreamerRtspFactory: Missing source for RTSP pipeline path {}".format(url.abspath))
            return None

        source = stream.source
        caps = stream.caps
        overlay = stream.overlay
        new_caps = self._select_caps(caps.to_string())
        s_src = "{} caps=\"{}\"".format(GStreamerRtspFactory._source, ','.join(new_caps))
        
        # Determine if we're dealing with GPU or CPU buffers
        is_gpu, buffer_type = self._is_gpu_buffer(caps)
        
        if "image/jpeg" in new_caps:
            if overlay:
                media_pipeline = GStreamerRtspFactory._RtspVideoPipeline_withjpeginput_overlay
            else:
                media_pipeline = GStreamerRtspFactory._RtspVideoPipeline_withjpeginput
        else:
            media_pipeline = GStreamerRtspFactory._RtspVideoPipeline
            if overlay is False:
                media_pipeline = media_pipeline.replace("gvawatermark ! ", "")

        if is_gpu and buffer_type == "VAMemory":
            self._logger.debug("Using GPU pipeline for caps: {} (type: {})".format(caps.to_string(), buffer_type))
            # Replace elements with VA-API equivalents if necessary
            media_pipeline = self.replace_with_vaelements_when_VAMemory(media_pipeline)
        is_audio_pipeline = False
        if caps.to_string().startswith('audio'):
            media_pipeline = GStreamerRtspFactory._RtspAudioPipeline
            is_audio_pipeline = True
        launch_string = " {} {} ".format(s_src, media_pipeline)
        self._logger.debug("Starting RTSP stream url:{}".format(url))
        self._logger.info(launch_string)
        pipeline = Gst.parse_launch(launch_string)
        pipeline.caps = caps
        appsrc = pipeline.get_by_name("source")
        source.set_app_src(appsrc, is_audio_pipeline, pipeline)
        appsrc.connect('need-data', source.on_need_data)
        appsrc.connect('enough-data', source.on_enough_data)
        return pipeline