#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import pytest
from unittest.mock import MagicMock, patch
from src.server.rtsp.gstreamer_rtsp_destination import GStreamerRtspDestination

@pytest.fixture
def mock_pipeline():
    return MagicMock()

@pytest.fixture
def Gst(mocker):
    return mocker.patch('src.server.rtsp.gstreamer_rtsp_destination.Gst')

@pytest.fixture
def mock_request():
    return {
                "cache-length": 30,
                "sync-with-source": True,
                "sync-with-destination": True,
                "encode-quality": 10,
                "overlay": True
            }

@pytest.fixture
def gstreamer_rtsp_destination(mock_request, mock_pipeline,mocker,Gst):
    mocker.patch('src.server.rtsp.gstreamer_rtsp_destination.AppDestination')
    return GStreamerRtspDestination(mock_request, mock_pipeline)

class TestGStreamerRtspDestination:
    def test_init(self, mock_request, mock_pipeline, Gst,gstreamer_rtsp_destination):
        assert gstreamer_rtsp_destination._pipeline == mock_pipeline
        assert gstreamer_rtsp_destination._rtsp_path == mock_pipeline.rtsp_path
        assert gstreamer_rtsp_destination._identifier == mock_pipeline.identifier
        assert gstreamer_rtsp_destination._clock == Gst.SystemClock()

    def test_get_request_parameters(self, gstreamer_rtsp_destination, mock_request):
        gstreamer_rtsp_destination._get_request_parameters(mock_request)
        assert gstreamer_rtsp_destination._cache_length == 30
        assert gstreamer_rtsp_destination._sync_with_source is True
        assert gstreamer_rtsp_destination._sync_with_destination is True
        assert gstreamer_rtsp_destination._encode_quality == 10
        assert gstreamer_rtsp_destination.overlay is True

    def test_init_stream(self, gstreamer_rtsp_destination, mock_pipeline):
        mock_sample = MagicMock()
        mock_buffer = MagicMock()
        mock_sample.get_buffer.return_value = mock_buffer
        mock_buffer.get_size.return_value = 1000
        mock_caps = MagicMock()
        mock_sample.get_caps.return_value = mock_caps
        mock_clock = MagicMock()
        gstreamer_rtsp_destination._clock = mock_clock
        mock_clock.get_time.return_value = 500
        gstreamer_rtsp_destination._init_stream(mock_sample)
        assert gstreamer_rtsp_destination._frame_size == 1000
        assert gstreamer_rtsp_destination._need_data is False
        mock_pipeline.rtsp_server.add_stream.assert_called_once_with(mock_pipeline.identifier, mock_pipeline.rtsp_path, mock_caps, gstreamer_rtsp_destination,gstreamer_rtsp_destination.overlay)
        assert gstreamer_rtsp_destination._last_timestamp == 500
        mock_pipeline.appsink_element.set_property.assert_called_once_with("sync", True)

    def test_on_need_data(self, gstreamer_rtsp_destination):
        gstreamer_rtsp_destination.on_need_data(None, None)
        assert gstreamer_rtsp_destination._need_data is True

    def test_on_enough_data(self, gstreamer_rtsp_destination):
        gstreamer_rtsp_destination.on_enough_data(None)
        assert gstreamer_rtsp_destination._need_data is False

    def test_set_app_src(self, gstreamer_rtsp_destination, mock_pipeline):
        mock_app_src = MagicMock()
        mock_rtsp_pipeline = MagicMock()
        mock_encoder = MagicMock()
        mock_rtsp_pipeline.get_by_name.return_value = mock_encoder
        gstreamer_rtsp_destination._frame_size = 1000
        gstreamer_rtsp_destination.set_app_src(mock_app_src, False, mock_rtsp_pipeline)
        assert gstreamer_rtsp_destination._app_src == mock_app_src
        assert gstreamer_rtsp_destination._is_audio_pipeline is False
        assert gstreamer_rtsp_destination._pts == 0
        mock_app_src.set_property.assert_any_call("is-live", True)
        mock_app_src.set_property.assert_any_call("do-timestamp", True)
        mock_app_src.set_property.assert_any_call("blocksize", 1000)
        mock_app_src.set_property.assert_any_call("block", True)
        mock_app_src.set_property.assert_any_call("min-percent", 100)
        mock_app_src.set_property.assert_any_call("max-bytes", 30000)
        mock_encoder.set_property.assert_called_once_with("quality", 10)
        mock_rtsp_pipeline.get_by_name.assert_called_once_with("jpegencoder")

    def test_push_buffer(self, gstreamer_rtsp_destination, mock_pipeline,Gst,mocker):
        mock_buffer = MagicMock()
        mock_clock = MagicMock()
        gstreamer_rtsp_destination._clock = mock_clock
        mock_clock.get_time.return_value = 2000
        gstreamer_rtsp_destination._last_timestamp = 500
        gstreamer_rtsp_destination._pts = 0
        mock_app_src = MagicMock()
        gstreamer_rtsp_destination._app_src = mock_app_src
        mock_end_stream = mocker.patch.object(gstreamer_rtsp_destination,'_end_stream')
        gstreamer_rtsp_destination._push_buffer(mock_buffer)
        assert mock_buffer.pts == 0
        assert mock_buffer.dts == 0
        assert mock_buffer.duration == 1500
        assert gstreamer_rtsp_destination._pts == 1500
        assert gstreamer_rtsp_destination._last_timestamp == 2000
        mock_app_src.emit.assert_called_once_with('push-buffer', mock_buffer)
        mock_end_stream.assert_called_once()

    def test_process_frame(self, gstreamer_rtsp_destination, mock_pipeline):
        mock_frame = MagicMock()
        mock_init = MagicMock()
        mock_process_frame = MagicMock()
        gstreamer_rtsp_destination._init_stream = mock_init
        gstreamer_rtsp_destination._process_frame = mock_process_frame
        gstreamer_rtsp_destination.process_frame(mock_frame)
        mock_init.assert_called_once_with(mock_frame)
        mock_process_frame.assert_called_once_with(mock_frame)

    def test_process_frame_after_init(self, gstreamer_rtsp_destination, mock_pipeline):
        mock_frame = MagicMock()
        mock_buffer = MagicMock()
        mock_clock = MagicMock()
        gstreamer_rtsp_destination._clock = mock_clock
        mock_clock.get_time.return_value = 10000
        mock_frame.get_buffer.return_value = mock_buffer
        gstreamer_rtsp_destination._need_data = True
        gstreamer_rtsp_destination._push_buffer = MagicMock()
        gstreamer_rtsp_destination._process_frame(mock_frame)
        gstreamer_rtsp_destination._push_buffer.assert_called_once_with(mock_buffer)
        gstreamer_rtsp_destination._need_data = False
        gstreamer_rtsp_destination._process_frame(mock_frame)
        mock_clock.get_time.assert_called_once()
        gstreamer_rtsp_destination._last_timestamp = 10000

    def test_end_stream(self, gstreamer_rtsp_destination):
        mock_app_src = MagicMock()
        gstreamer_rtsp_destination._app_src = mock_app_src
        gstreamer_rtsp_destination._end_stream()
        assert gstreamer_rtsp_destination._need_data is False
        if mock_app_src is not None:
            mock_app_src.end_of_stream.assert_called_once()
        assert gstreamer_rtsp_destination._app_src is None

    def test_finish(self, gstreamer_rtsp_destination,mocker):
        mock_rtsp_server = MagicMock()
        gstreamer_rtsp_destination._rtsp_server = mock_rtsp_server
        mock_end_stream = mocker.patch.object(gstreamer_rtsp_destination,'_end_stream')
        gstreamer_rtsp_destination.finish()
        mock_end_stream.assert_called_once()
        mock_rtsp_server.remove_stream.assert_called_once_with(gstreamer_rtsp_destination._rtsp_path)