#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import pytest
from unittest.mock import MagicMock

@pytest.fixture
def mock_stream(mocker):
    mocker.patch('src.server.gstreamer_pipeline.GStreamerPipeline')
    return mocker.patch('src.server.webrtc.gstreamer_webrtc_manager.GStreamerWebRTCStream')

@pytest.fixture
def gstreamer_webrtc_manager(mocker,mock_stream):
    from src.server.webrtc.gstreamer_webrtc_manager import GStreamerWebRTCManager
    return GStreamerWebRTCManager("http://10.10.10.10:8889")

class TestGStreamerWebRTCManager:

    def test_init(self, gstreamer_webrtc_manager):
        assert gstreamer_webrtc_manager._whip_endpoint == "http://10.10.10.10:8889"
        assert gstreamer_webrtc_manager._streams == {}

    def test_peerid_in_use(self, gstreamer_webrtc_manager):
        gstreamer_webrtc_manager._streams = {'peer1': MagicMock()}
        assert gstreamer_webrtc_manager._peerid_in_use('peer1') is True
        assert gstreamer_webrtc_manager._peerid_in_use('peer2') is False
        with pytest.raises(Exception, match="Empty peer_id was passed to WebRTCManager!"):
            gstreamer_webrtc_manager._peerid_in_use('')
    
    def test_add_stream(self, gstreamer_webrtc_manager,mocker,mock_stream):
        mocker.patch.object(gstreamer_webrtc_manager, '_select_caps',return_value="video/x-raw")
        mocker.patch.object(gstreamer_webrtc_manager, '_get_launch_string',return_value="launch_string")
        mocker.patch.object(gstreamer_webrtc_manager, '_peerid_in_use',return_value=False)
        mock_frame = MagicMock()
        mock_destination = MagicMock()
        gstreamer_webrtc_manager.add_stream("peer1", mock_frame, mock_destination, True)
        gstreamer_webrtc_manager._select_caps.assert_called_once_with(mock_frame.to_string())
        gstreamer_webrtc_manager._peerid_in_use.assert_called_once_with("peer1")
        gstreamer_webrtc_manager._get_launch_string.assert_called_once_with("video/x-raw", "peer1",True)
        mock_stream.assert_any_call("peer1", "video/x-raw", "launch_string", mock_destination, "http://10.10.10.10:8889")
        gstreamer_webrtc_manager._streams['peer1'].start.assert_called_once()

    def test_select_caps(self, gstreamer_webrtc_manager):
        mock_caps = "video/x-raw,width=1920,height=1080,frame=30/1,layout=interlaced,format=I420"
        result = gstreamer_webrtc_manager._select_caps(mock_caps)
        result == ['video/x-raw', 'width', 'height', 'layout', 'format']

    def test_get_launch_string(self, gstreamer_webrtc_manager):
        mock_caps = ['video/x-raw', 'width=1920', 'height=1080']
        result2 = gstreamer_webrtc_manager._get_launch_string(mock_caps, "peer1",True)
        assert result2 == ' appsrc name=webrtc_source format=GST_FORMAT_TIME  caps="video/x-raw,width=1920,height=1080"  ! videoconvert ! gvawatermark  ! x264enc speed-preset=ultrafast name=h264enc ! video/x-h264,profile=baseline  ! whipclientsink signaller::whip-endpoint= http://10.10.10.10:8889/peer1/whip'
        result = gstreamer_webrtc_manager._get_launch_string(mock_caps, "peer1",False)
        assert result == ' appsrc name=webrtc_source format=GST_FORMAT_TIME  caps="video/x-raw,width=1920,height=1080"  ! videoconvert  ! x264enc speed-preset=ultrafast name=h264enc ! video/x-h264,profile=baseline  ! whipclientsink signaller::whip-endpoint= http://10.10.10.10:8889/peer1/whip'
        mock_caps = ['image/jpeg', 'width=1920', 'height=1080']
        result_jpeg = gstreamer_webrtc_manager._get_launch_string(mock_caps, "peer1",True)
        assert result_jpeg == ' appsrc name=webrtc_source format=GST_FORMAT_TIME  caps="image/jpeg,width=1920,height=1080"  ! jpegdec ! videoconvert ! gvawatermark  ! x264enc speed-preset=ultrafast name=h264enc  ! video/x-h264,profile=baseline  ! whipclientsink signaller::whip-endpoint= http://10.10.10.10:8889/peer1/whip'
    
    def test_remove_stream(self, gstreamer_webrtc_manager):
        mock_stream = MagicMock()
        gstreamer_webrtc_manager._streams = {'peer1': mock_stream}
        gstreamer_webrtc_manager.remove_stream('peer1')
        mock_stream.stop.assert_called_once()
        assert 'peer1' not in gstreamer_webrtc_manager._streams

    def test_stop(self, gstreamer_webrtc_manager,mocker):
        mocker.patch.object(gstreamer_webrtc_manager, 'remove_stream')
        mock_stream = MagicMock()
        gstreamer_webrtc_manager._streams = {'peer1': mock_stream}
        gstreamer_webrtc_manager.stop()
        gstreamer_webrtc_manager.remove_stream.assert_called_once_with('peer1')
        assert gstreamer_webrtc_manager._streams is None