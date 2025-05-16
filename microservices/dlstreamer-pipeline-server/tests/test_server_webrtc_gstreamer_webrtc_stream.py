#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import pytest
from unittest.mock import MagicMock, AsyncMock
import requests
from requests.exceptions import RequestException
@pytest.fixture
def mock_pipeline():
    return MagicMock()

@pytest.fixture
def Gst(mocker):
    return mocker.patch('src.server.webrtc.gstreamer_webrtc_stream.Gst')

@pytest.fixture
def gstreamer_webrtc_stream(mocker):
    mocker.patch('src.server.gstreamer_pipeline.GStreamerPipeline')
    from src.server.webrtc.gstreamer_webrtc_stream import GStreamerWebRTCStream
    return GStreamerWebRTCStream("peer1", "video/x-raw", "launch_string", MagicMock(), "http://10.10.10.10.8889")

class TestGStreamerWebRTCStream:
    def test_prepare_destination_pads(self, gstreamer_webrtc_stream, mock_pipeline,mocker):
        mock_appsrc = MagicMock()
        mock_pipeline.get_by_name.return_value = mock_appsrc
        gstreamer_webrtc_stream.prepare_destination_pads(mock_pipeline)
        assert gstreamer_webrtc_stream._pipe == mock_pipeline
        assert mock_pipeline.caps == "video/x-raw"
        mock_pipeline.get_by_name.assert_any_call("webrtc_source")
        gstreamer_webrtc_stream._destination_instance.set_app_src.assert_called_once_with(mock_appsrc,mock_pipeline)

    def test_finished_callback(self, gstreamer_webrtc_stream):
        gstreamer_webrtc_stream._logger.info = MagicMock()
        gstreamer_webrtc_stream._finished_callback()
        gstreamer_webrtc_stream._logger.info.assert_called_once_with("GStreamerPipeline finished for peer_id:peer1")

    def test_check_plugins(self, gstreamer_webrtc_stream,Gst):
        Gst.Registry.get.find_plugin.side_effect = lambda x: x
        assert gstreamer_webrtc_stream._check_plugins() is True
        Gst.Registry.get.return_value.find_plugin.return_value = None
        assert gstreamer_webrtc_stream._check_plugins() is False

    def test_start_pipeline(self, gstreamer_webrtc_stream, mocker):
        mock_pipeline = MagicMock()
        mock_reset = mocker.patch.object(gstreamer_webrtc_stream,'_reset')
        mock_response = MagicMock()
        mock_request = mocker.patch.object(requests,'get',return_value=mock_response)
        mock_response.status_code = 404
        mock_response.headers = {'Server': 'mediamtx'}
        mock_logger = MagicMock()
        gstreamer_webrtc_stream._logger = mock_logger
        mock_pipeline = MagicMock()
        mock_gstpipeline = mocker.patch('src.server.webrtc.gstreamer_webrtc_stream.GstPipeline.GStreamerPipeline', return_value=mock_pipeline)
        mocker.patch.object(gstreamer_webrtc_stream,'prepare_destination_pads')
        gstreamer_webrtc_stream._start_pipeline()
        mock_request.assert_called_once_with(gstreamer_webrtc_stream._server)
        mock_logger.info.assert_any_call("Mediamtx server is up and running.")
        mock_gstpipeline.assert_called_once_with("peer1",{"type": gstreamer_webrtc_stream._webrtc_pipeline_type,"template": gstreamer_webrtc_stream._launch_string,"prepare-pads": gstreamer_webrtc_stream.prepare_destination_pads},None,{"source": { "type": "webrtc_destination" }, "peer_id": "peer1"},gstreamer_webrtc_stream._finished_callback,None)
        mock_reset.assert_called_once()
        mock_pipeline.start.assert_called_once()
        mock_response.status_code = 200
        gstreamer_webrtc_stream._start_pipeline()
        mock_logger.error.assert_called_once_with("Error connecting to Mediamtx server.")
        mock_request.side_effect = RequestException("Connection error")
        gstreamer_webrtc_stream._start_pipeline()
        mock_logger.error.assert_any_call("Error connecting to http://10.10.10.10.8889: Connection error")

    def test_thread_launcher(self, gstreamer_webrtc_stream, mocker):
        mock_start_pipeline = mocker.patch.object(gstreamer_webrtc_stream, '_start_pipeline')
        gstreamer_webrtc_stream._thread_launcher()
        mock_start_pipeline.assert_called_once()
        assert gstreamer_webrtc_stream._peer_id == "peer1"
    
    def test_thread_launcher_exception(self, gstreamer_webrtc_stream, mocker):
        gstreamer_webrtc_stream._start_pipeline = MagicMock()
        gstreamer_webrtc_stream._start_pipeline.side_effect = [KeyboardInterrupt,SystemExit]
        try:
            gstreamer_webrtc_stream._thread_launcher()
        except Exception:
            pytest.fail("Exception")
        try:
            gstreamer_webrtc_stream._thread_launcher()
        except Exception:
            pytest.fail("Exception")
    
    def test_reset(self, gstreamer_webrtc_stream):
        mock_webrtc = MagicMock()
        gstreamer_webrtc_stream._webrtc_pipeline = mock_webrtc
        gstreamer_webrtc_stream._reset()
        if mock_webrtc is not None:
            mock_webrtc.stop.assert_called_once()
        assert gstreamer_webrtc_stream._webrtc_pipeline is None
        assert gstreamer_webrtc_stream._pipe is None

    def test_stop(self, gstreamer_webrtc_stream,mocker):
        mock_reset = mocker.patch.object(gstreamer_webrtc_stream,'_reset')
        mock_thread = MagicMock()
        gstreamer_webrtc_stream._thread = mock_thread
        gstreamer_webrtc_stream.stop()
        mock_reset.assert_called_once()
        if mock_thread is not None:
            mock_thread.join.assert_called_once()
        assert gstreamer_webrtc_stream._thread is None
        assert gstreamer_webrtc_stream._stopped is True
    
    def test_start(self, gstreamer_webrtc_stream, mocker):
        gstreamer_webrtc_stream._logger = MagicMock()
        mock_check_plugins = mocker.patch.object(gstreamer_webrtc_stream, '_check_plugins', return_value=True)
        mock_thread = mocker.patch('src.server.webrtc.gstreamer_webrtc_stream.Thread')
        gstreamer_webrtc_stream.start()
        mock_check_plugins.assert_called_once()
        mock_thread.assert_called_once_with(target=gstreamer_webrtc_stream._thread_launcher)
        mock_thread.return_value.start.assert_called_once()
        mock_check_plugins = mocker.patch.object(gstreamer_webrtc_stream, '_check_plugins', return_value=False)
        gstreamer_webrtc_stream.start()
        gstreamer_webrtc_stream._logger.error.assert_called_once_with("WebRTC Stream error - dependent plugins are missing!")