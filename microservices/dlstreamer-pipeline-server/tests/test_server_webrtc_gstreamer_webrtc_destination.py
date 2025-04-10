#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import pytest
from unittest.mock import MagicMock, patch
from src.server.webrtc.gstreamer_webrtc_destination import GStreamerWebRTCDestination

@pytest.fixture
def mock_pipeline():
    return MagicMock()
@pytest.fixture
def Gst(mocker):
    return mocker.patch('src.server.webrtc.gstreamer_webrtc_destination.Gst')
@pytest.fixture
def mock_request():
    return {
                "peer-id": "peer1",
                "cache-length": 30,
                "sync-with-source": True,
                "sync-with-destination": True,
                "encode-cq-level": 10
            }

@pytest.fixture
def gstreamer_webrtc_destination(mock_request, mock_pipeline,mocker,Gst):
    mocker.patch('src.server.webrtc.gstreamer_webrtc_destination.AppDestination')
    return GStreamerWebRTCDestination(mock_request, mock_pipeline)

class TestGStreamerWebRTCDestination:

    def test_init(self, gstreamer_webrtc_destination, mock_request, mock_pipeline,Gst,mocker):
        assert gstreamer_webrtc_destination._pipeline == mock_pipeline
        assert gstreamer_webrtc_destination._webrtc_manager == mock_pipeline.webrtc_manager
        assert gstreamer_webrtc_destination._clock is not None
        assert gstreamer_webrtc_destination._webrtc_peerid == "peer1"
        assert gstreamer_webrtc_destination._cache_length == 30
        assert gstreamer_webrtc_destination._sync_with_source is True
        assert gstreamer_webrtc_destination._sync_with_destination is True
        assert gstreamer_webrtc_destination._encode_cq_level == 10
        assert gstreamer_webrtc_destination._clock == Gst.SystemClock()
        assert gstreamer_webrtc_destination.overlay == True

    def test_get_request_parameters(self, gstreamer_webrtc_destination, mock_request):
        gstreamer_webrtc_destination._get_request_parameters(mock_request)
        assert gstreamer_webrtc_destination._webrtc_peerid == "peer1"
        assert gstreamer_webrtc_destination._cache_length == 30
        assert gstreamer_webrtc_destination._sync_with_source is True
        assert gstreamer_webrtc_destination._sync_with_destination is True
        assert gstreamer_webrtc_destination._encode_cq_level == 10

    def test_init_stream(self, gstreamer_webrtc_destination, mock_pipeline):
        mock_sample = MagicMock()
        mock_buffer = MagicMock()
        mock_sample.get_buffer.return_value = mock_buffer
        mock_buffer.get_size.return_value = 1000
        mock_caps = MagicMock()
        mock_sample.get_caps.return_value = mock_caps
        mock_clock = MagicMock()
        gstreamer_webrtc_destination._clock = mock_clock
        mock_clock.get_time.return_value = 500
        gstreamer_webrtc_destination._init_stream(mock_sample)
        assert gstreamer_webrtc_destination._frame_size == 1000
        assert gstreamer_webrtc_destination._need_data is False
        assert gstreamer_webrtc_destination._last_timestamp == 500
        mock_pipeline.appsink_element.set_property.assert_called_once_with("sync", True)
        gstreamer_webrtc_destination._webrtc_manager.add_stream.assert_called_once_with("peer1", mock_caps, gstreamer_webrtc_destination,True)

    def test_on_need_data(self, gstreamer_webrtc_destination):
        gstreamer_webrtc_destination._on_need_data(None, None)
        assert gstreamer_webrtc_destination._need_data is True

    def test_on_enough_data(self, gstreamer_webrtc_destination):
        gstreamer_webrtc_destination._on_enough_data(None)
        assert gstreamer_webrtc_destination._need_data is False

    def test_set_app_src(self, gstreamer_webrtc_destination, mock_pipeline,mocker):
        mock_app_src = MagicMock()
        mock_webrtc_pipeline = MagicMock()
        mock_encoder = MagicMock()
        mock_webrtc_pipeline.get_by_name.return_value = mock_encoder
        gstreamer_webrtc_destination._frame_size = 1000
        gstreamer_webrtc_destination.set_app_src(mock_app_src, mock_webrtc_pipeline)
        assert gstreamer_webrtc_destination._app_src == mock_app_src
        assert gstreamer_webrtc_destination._pts == 0
        mock_app_src.set_property.assert_any_call("is-live", True)
        mock_app_src.set_property.assert_any_call("do-timestamp", True)
        mock_app_src.set_property.assert_any_call("blocksize", 1000)
        mock_app_src.set_property.assert_any_call("block", True)
        mock_app_src.set_property.assert_any_call("min-percent", 100)
        mock_app_src.set_property.assert_any_call("max-bytes", 30000)
        mock_encoder.set_property.assert_called_once_with("cq-level", 10)
        mock_app_src.connect.assert_any_call('need-data', gstreamer_webrtc_destination._on_need_data)
        mock_app_src.connect.assert_any_call('enough-data', gstreamer_webrtc_destination._on_enough_data)
        mock_webrtc_pipeline.get_by_name.assert_called_once_with("vp8encoder")

    def test_push_buffer(self, gstreamer_webrtc_destination, mock_pipeline,Gst,mocker):
        mock_buffer = MagicMock()
        mock_clock = MagicMock()
        gstreamer_webrtc_destination._clock = mock_clock
        mock_clock.get_time.return_value = 2000
        gstreamer_webrtc_destination._last_timestamp = 500
        gstreamer_webrtc_destination._pts = 5
        mock_appsrc = MagicMock()
        gstreamer_webrtc_destination._app_src = mock_appsrc
        mock_end_stream = mocker.patch.object(gstreamer_webrtc_destination,'_end_stream')
        gstreamer_webrtc_destination._push_buffer(mock_buffer)
        assert mock_buffer.pts == 5
        assert mock_buffer.dts == 5
        assert mock_buffer.duration == 1500
        assert gstreamer_webrtc_destination._pts == 1505
        assert gstreamer_webrtc_destination._last_timestamp == 2000
        mock_appsrc.emit.assert_called_once_with('push-buffer', mock_buffer)
        mock_end_stream.assert_called_once()

    def test_process_frame(self, gstreamer_webrtc_destination, mock_pipeline,mocker):
        mock_frame = MagicMock()
        mock_process_frame = MagicMock()
        mock_init = MagicMock()
        gstreamer_webrtc_destination._init_stream = mock_init
        gstreamer_webrtc_destination._process_frame = mock_process_frame
        gstreamer_webrtc_destination.process_frame(mock_frame)
        mock_init.assert_called_once_with(mock_frame)
        mock_process_frame.assert_called_once_with(mock_frame)

    def test_process_frame_after_init(self, gstreamer_webrtc_destination, mock_pipeline,mocker):
        mock_frame = MagicMock()
        mock_clock = MagicMock()
        gstreamer_webrtc_destination._clock = mock_clock
        mock_clock.get_time.return_value = 123
        gstreamer_webrtc_destination._need_data = True
        mock_push_buffer = mocker.patch.object(gstreamer_webrtc_destination,'_push_buffer')
        gstreamer_webrtc_destination._process_frame(mock_frame)
        mock_push_buffer.assert_called_once_with(mock_frame.get_buffer())
        gstreamer_webrtc_destination._need_data = False
        gstreamer_webrtc_destination._process_frame(mock_frame)
        mock_clock.get_time.assert_called_once()
        assert gstreamer_webrtc_destination._last_timestamp == 123

    def test_end_stream(self, gstreamer_webrtc_destination):
        mock_app_src = MagicMock()
        gstreamer_webrtc_destination._app_src = mock_app_src
        gstreamer_webrtc_destination._end_stream()
        assert gstreamer_webrtc_destination._need_data is False
        mock_app_src.end_of_stream.assert_called_once()
        assert gstreamer_webrtc_destination._app_src is None

    def test_finish(self, gstreamer_webrtc_destination,mocker):
        mock_end_stream = mocker.patch.object(gstreamer_webrtc_destination,'_end_stream')
        mock_webrtc_manager = MagicMock()
        gstreamer_webrtc_destination._webrtc_manager = mock_webrtc_manager
        gstreamer_webrtc_destination.finish()
        mock_end_stream.assert_called_once()
        mock_webrtc_manager.remove_stream.assert_called_once_with("peer1")