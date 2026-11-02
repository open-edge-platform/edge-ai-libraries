#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

from collections import namedtuple

import pytest
from unittest.mock import MagicMock, patch
from src.server.rtsp.gstreamer_rtsp_factory import GStreamerRtspFactory

EncodingCase = namedtuple(
    "EncodingCase", ["encoding", "caps_list", "buffer_type", "expect_h264", "expect_va"]
)
LegacyStream = namedtuple("LegacyStream", ["overlay", "overlay_properties", "caps", "source"])

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
        "overlay, overlay_properties, expected",
        [
            (False, {}, ""),
            (True, None, " ! gvawatermark"),
            (True, {}, " ! gvawatermark"),
            (True, ["not", "a", "dict"], " ! gvawatermark"),
            (True, {"enabled": True, "x": 10, "mode": "center", "ignored": None}, " ! gvawatermark displ-cfg=enabled=true,x=10,mode=center"),
        ],
    )
    def test_build_gvawatermark_stage(self, gstreamer_rtsp_factory, overlay, overlay_properties, expected):
        result = gstreamer_rtsp_factory._build_gvawatermark_stage(overlay, overlay_properties)
        assert result == expected

    @pytest.mark.parametrize(
    "to_string, is_audio, expected_launch_string,overlay,caps,launch_string",
    [
        ("Video Pipeline", False, " ! videoconvert  ! gvawatermark         ! jpegenc name=jpegencoder ! rtpjpegpay name=pay0",True,["video/x-raw","width=1920","height=1080","framerate=30","layout=temp_layout","format=temp_format"],'appsrc name=source format=GST_FORMAT_TIME caps="video/x-raw,width=1920,height=1080,framerate=30,layout=temp_layout,format=temp_format"'),
        ("audio Pipeline", True, " ! queue ! decodebin ! audioresample ! audioconvert  ! avenc_aac ! queue ! mpegtsmux ! rtpmp2tpay  name=pay0 pt=96",True,["video/x-raw","width=1920","height=1080","framerate=30","layout=temp_layout","format=temp_format"],'appsrc name=source format=GST_FORMAT_TIME caps="video/x-raw,width=1920,height=1080,framerate=30,layout=temp_layout,format=temp_format"'),
        ("Video Pipeline", False, " ! videoconvert          ! jpegenc name=jpegencoder ! rtpjpegpay name=pay0",False,["video/x-raw","width=1920","height=1080","framerate=30","layout=temp_layout","format=temp_format"],'appsrc name=source format=GST_FORMAT_TIME caps="video/x-raw,width=1920,height=1080,framerate=30,layout=temp_layout,format=temp_format"'),
        ("Video Pipeline", False, " ! rtpjpegpay name=pay0",False,["image/jpeg","width=1920","height=1080","framerate=30","layout=temp_layout","format=temp_format"],'appsrc name=source format=GST_FORMAT_TIME caps="image/jpeg,width=1920,height=1080,framerate=30,layout=temp_layout,format=temp_format"'),
        ("Video Pipeline", False, " ! jpegdec ! videoconvert  ! gvawatermark         ! jpegenc name=jpegencoder ! rtpjpegpay name=pay0",True,["image/jpeg","width=1920","height=1080","framerate=30","layout=temp_layout","format=temp_format"],'appsrc name=source format=GST_FORMAT_TIME caps="image/jpeg,width=1920,height=1080,framerate=30,layout=temp_layout,format=temp_format"')
    ])
    def test_do_create_element_audio_and_video(self, gstreamer_rtsp_factory, mock_rtsp_server,mocker,mock_gst,to_string, is_audio, expected_launch_string,overlay,caps,launch_string):
        mock_url = MagicMock()
        mock_stream = MagicMock()
        mock_stream.overlay = overlay
        mock_stream.caps = MagicMock()
        mock_stream.caps.to_string.return_value = to_string
        mock_pipeline = MagicMock()
        mock_appsrc = MagicMock()
        mock_pipeline.get_by_name.return_value = mock_appsrc
        mock_parse_launch = mocker.patch.object(mock_gst,'parse_launch',return_value = mock_pipeline)
        mock_get_source = mocker.patch.object(mock_rtsp_server,'get_source',return_value = mock_stream)
        mock_select_caps = mocker.patch.object(gstreamer_rtsp_factory,'_select_caps',return_value = caps)
        mock_launch_string = f' {launch_string} {expected_launch_string} '
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
        
    def test_do_create_element_missing_source(self, request):
        """do_create_element must log an error and return None when the
        RTSP server has no registered source for the requested path."""
        factory = request.getfixturevalue("gstreamer_rtsp_factory")
        rtsp_server = request.getfixturevalue("mock_rtsp_server")
        rtsp_server.get_source.return_value = None
        url = MagicMock()
        url.abspath = "/test"
        pipeline = factory.do_create_element(url)
        assert pipeline is None
        getattr(factory, '_logger').error.assert_called_once_with(
            "GStreamerRtspFactory: Missing source for RTSP pipeline path /test"
        )

    @pytest.mark.parametrize(
        "case",
        [
            # raw video + h264 requested -> openh264enc software path
            EncodingCase(
                "h264", ["video/x-raw", "width=1920", "height=1080"], "System", True, False
            ),
            # raw video + h264 requested + VAMemory buffer -> vah264enc swap
            EncodingCase(
                "h264", ["video/x-raw", "width=1920", "height=1080"], "VAMemory", True, True
            ),
            # mjpeg (default) stays on the jpeg path even with raw video input
            EncodingCase(
                "mjpeg", ["video/x-raw", "width=1920", "height=1080"], "System", False, False
            ),
            # h264 requested but input caps are already JPEG -> falls back to MJPEG
            EncodingCase(
                "h264", ["image/jpeg", "width=1920", "height=1080"], "System", False, False
            ),
        ],
        ids=["h264_software", "h264_va", "mjpeg_default", "h264_jpeg_fallback"],
    )
    def test_do_create_element_encoding_selection(self, request, mocker, case):
        """do_create_element must select the openh264enc/vah264enc/jpegenc
        branch according to the stream's encoding and buffer type."""
        factory = request.getfixturevalue("gstreamer_rtsp_factory")
        rtsp_server = request.getfixturevalue("mock_rtsp_server")
        gst_mod = request.getfixturevalue("mock_gst")
        mock_url = MagicMock()
        mock_stream = MagicMock()
        mock_stream.overlay = False
        mock_stream.encoding = case.encoding
        mock_stream.caps = MagicMock()
        mock_stream.caps.to_string.return_value = "Video Pipeline"
        mock_pipeline = MagicMock()
        mock_appsrc = MagicMock()
        mock_pipeline.get_by_name.return_value = mock_appsrc
        mocker.patch.object(gst_mod, 'parse_launch', return_value=mock_pipeline)
        mocker.patch.object(rtsp_server, 'get_source', return_value=mock_stream)
        mocker.patch.object(factory, '_select_caps', return_value=case.caps_list)
        mocker.patch.object(factory, '_is_gpu_buffer',
                             return_value=(case.buffer_type != "System", case.buffer_type))

        factory.do_create_element(mock_url)

        launch_string = getattr(factory, '_logger').info.call_args[0][0]
        if case.expect_h264:
            assert "openh264enc" in launch_string or "vah264enc" in launch_string
            assert "rtph264pay" in launch_string
            assert "jpegenc" not in launch_string
        else:
            assert "jpegenc" in launch_string or "rtpjpegpay" in launch_string
            assert "openh264enc" not in launch_string
            assert "vah264enc" not in launch_string
        if case.expect_va:
            assert "vah264enc" in launch_string
            assert "openh264enc" not in launch_string
        elif case.expect_h264:
            assert "openh264enc" in launch_string

    def test_do_create_element_defaults_to_mjpeg_when_encoding_absent(self, request, mocker):
        """A stream object with no 'encoding' attribute (e.g. legacy callers/tests)
        must keep producing the existing MJPEG pipeline, confirming the new
        getattr(stream, 'encoding', 'mjpeg') fallback preserves old behavior."""
        factory = request.getfixturevalue("gstreamer_rtsp_factory")
        rtsp_server = request.getfixturevalue("mock_rtsp_server")
        gst_mod = request.getfixturevalue("mock_gst")
        mock_url = MagicMock()
        mock_stream = LegacyStream(overlay=False, overlay_properties=None,
                                    caps=MagicMock(), source=MagicMock())
        mock_stream.caps.to_string.return_value = "Video Pipeline"
        mock_pipeline = MagicMock()
        mock_appsrc = MagicMock()
        mock_pipeline.get_by_name.return_value = mock_appsrc
        mocker.patch.object(gst_mod, 'parse_launch', return_value=mock_pipeline)
        mocker.patch.object(rtsp_server, 'get_source', return_value=mock_stream)
        mocker.patch.object(factory, '_select_caps',
                             return_value=["video/x-raw", "width=1920", "height=1080"])
        mocker.patch.object(factory, '_is_gpu_buffer', return_value=(False, "System"))

        factory.do_create_element(mock_url)

        launch_string = getattr(factory, '_logger').info.call_args[0][0]
        assert "jpegenc" in launch_string
        assert "openh264enc" not in launch_string
