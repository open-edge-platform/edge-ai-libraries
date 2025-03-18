#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import pytest
from unittest.mock import MagicMock, patch
from src.server.rtsp.gstreamer_rtsp_factory import GStreamerRtspFactory

@pytest.fixture
def mock_logging(mocker):
    return mocker.patch('src.server.rtsp.gstreamer_rtsp_factory.logging')

@pytest.fixture
def mock_rtsp_media(mocker):
    return mocker.patch('src.server.rtsp.gstreamer_rtsp_factory.GstRtspServer.RTSPMediaFactory.__init__')
@pytest.fixture
def mock_gst(mocker):
    return mocker.patch('src.server.rtsp.gstreamer_rtsp_factory.Gst')

@pytest.fixture
def mock_rtsp_server():
    return MagicMock()

@pytest.fixture
def gstreamer_rtsp_factory(mock_logging, mock_rtsp_server,mocker,mock_rtsp_media):
    return GStreamerRtspFactory(mock_rtsp_server)

class TestGStreamerRtspFactory:
    
    def test_init_exception(session_mocker,mock_rtsp_media,mock_logging):
        with pytest.raises(Exception, match="GStreamerRtspFactory: Invalid RTSP Server"):
            GStreamerRtspFactory(None)

    def test_select_caps(self, gstreamer_rtsp_factory,mock_gst):
        caps = "video/x-raw,width=1920,height=1080,framerate=30,layout=temp_layout,format=temp_format,na"
        selected_caps = gstreamer_rtsp_factory._select_caps(caps)
        expected_caps = ["video/x-raw","width=1920","height=1080","framerate=30","layout=temp_layout","format=temp_format"]
        assert selected_caps == expected_caps

    @pytest.mark.parametrize(
    "to_string, is_audio, expected_launch_string",
    [
        ("Video Pipeline", False, " ! videoconvert ! video/x-raw,format=I420 \
        ! jpegenc name=jpegencoder ! rtpjpegpay name=pay0"),
        ("audio Pipeline", True, " ! queue ! decodebin ! audioresample ! audioconvert  ! avenc_aac ! queue ! mpegtsmux ! rtpmp2tpay  name=pay0 pt=96")
    ])
    def test_do_create_element_audio_and_video(self, gstreamer_rtsp_factory, mock_rtsp_server,mocker,mock_gst,to_string, is_audio, expected_launch_string):
        mock_url = MagicMock()
        mock_stream = MagicMock()
        mock_stream.caps = MagicMock()
        mock_stream.caps.to_string.return_value = to_string
        mock_pipeline = MagicMock()
        mock_appsrc = MagicMock()
        mock_pipeline.get_by_name.return_value = mock_appsrc
        mock_parse_launch = mocker.patch.object(mock_gst,'parse_launch',return_value = mock_pipeline)
        mock_get_source = mocker.patch.object(mock_rtsp_server,'get_source',return_value = mock_stream)
        mock_select_caps = mocker.patch.object(gstreamer_rtsp_factory,'_select_caps',return_value = ["video/x-raw","width=1920","height=1080","framerate=30","layout=temp_layout","format=temp_format"])
        mock_launch_string = ' appsrc name=source format=GST_FORMAT_TIME caps="video/x-raw,width=1920,height=1080,framerate=30,layout=temp_layout,format=temp_format" {} '.format(expected_launch_string)
        pipeline = gstreamer_rtsp_factory.do_create_element(mock_url)
        mock_get_source.assert_called_once_with(mock_url.abspath)
        mock_select_caps.assert_called_once_with(to_string)
        mock_parse_launch.assert_called_once_with(mock_launch_string)
        assert mock_pipeline.caps == mock_stream.caps
        mock_pipeline.get_by_name.assert_called_once_with("source")
        mock_stream.source.set_app_src.assert_called_once_with(mock_appsrc,is_audio,mock_pipeline)
        mock_appsrc.connect.assert_any_call('need-data', mock_stream.source.on_need_data)
        mock_appsrc.connect.assert_any_call('enough-data', mock_stream.source.on_enough_data)
        assert pipeline == mock_pipeline
        
    def test_do_create_element_missing_source(self, gstreamer_rtsp_factory, mock_rtsp_server):
        mock_rtsp_server.get_source.return_value = None
        url = MagicMock()
        url.abspath = "/test"
        pipeline = gstreamer_rtsp_factory.do_create_element(url)
        assert pipeline is None
        gstreamer_rtsp_factory._logger.error.assert_called_once_with("GStreamerRtspFactory: Missing source for RTSP pipeline path /test")