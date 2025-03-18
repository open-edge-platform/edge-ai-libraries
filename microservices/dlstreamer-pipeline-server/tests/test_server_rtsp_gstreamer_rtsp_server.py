#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import pytest
from unittest.mock import MagicMock, patch
from src.server.rtsp.gstreamer_rtsp_server import GStreamerRtspServer

@pytest.fixture
def Gstrtsp(mocker):
    return mocker.patch('src.server.rtsp.gstreamer_rtsp_server.GstRtspServer')

@pytest.fixture
def Gst(mocker):
    return mocker.patch('src.server.rtsp.gstreamer_rtsp_server.Gst')

@pytest.fixture
def mock_logging(mocker):
    return mocker.patch('src.server.rtsp.gstreamer_rtsp_server.logging')

@pytest.fixture
def mock_factory(mocker):
    return mocker.patch('src.server.rtsp.gstreamer_rtsp_server.GStreamerRtspFactory')

@pytest.fixture
def gstreamer_rtsp_server(mock_logging, mock_factory,Gstrtsp,Gst):
    return GStreamerRtspServer(port=8888)

class TestGStreamerRtspServer:

    def test_check_if_path_exists(self, gstreamer_rtsp_server):
        gstreamer_rtsp_server._streams = {'/test': MagicMock()}
        with pytest.raises(Exception, match="RTSP Stream at /test already exists, use different path"):
            gstreamer_rtsp_server.check_if_path_exists('/test')

    def test_add_stream(self, gstreamer_rtsp_server, mocker,mock_logging):
        mock_stream = mocker.patch('src.server.rtsp.gstreamer_rtsp_server.Stream', return_value=MagicMock())
        mock_mount_points = MagicMock()
        gstreamer_rtsp_server._mount_points = mock_mount_points
        gstreamer_rtsp_server.add_stream('test_id', '/test', 'caps', 'source')
        assert '/test' in gstreamer_rtsp_server._streams
        mock_stream.assert_called_once_with('source', 'caps')
        gstreamer_rtsp_server._mount_points.add_factory.assert_called_once_with('/test',gstreamer_rtsp_server._factory)
        mock_logging.get_logger.return_value.info.assert_called_once_with("Created RTSP Stream for instance test_id at rtsp:://<host ip>:8888/test")

    def test_remove_stream(self, gstreamer_rtsp_server):
        gstreamer_rtsp_server._streams = {'/test': MagicMock()}
        gstreamer_rtsp_server.remove_stream('/test')
        assert '/test' not in gstreamer_rtsp_server._streams
        assert gstreamer_rtsp_server._streams == {}
        gstreamer_rtsp_server._mount_points.remove_factory.assert_called_once_with('/test')
        gstreamer_rtsp_server._streams = {'/test1': MagicMock()}
        gstreamer_rtsp_server.remove_stream('/test')
        assert '/test1' in gstreamer_rtsp_server._streams

    def test_get_source(self, gstreamer_rtsp_server):
        mock_stream = MagicMock()
        gstreamer_rtsp_server._streams = {'/test': mock_stream('source', 'caps')}
        source = gstreamer_rtsp_server.get_source('/test')
        assert source == mock_stream('source', 'caps')
        source = gstreamer_rtsp_server.get_source('/na')
        assert source is None

    def test_start(self, gstreamer_rtsp_server, mocker):
        mock_context = MagicMock()
        mock_mainloop = MagicMock()
        mock_glibcontext = mocker.patch('src.server.rtsp.gstreamer_rtsp_server.GLib.MainContext', return_value=mock_context)
        mock_glibmainloop = mocker.patch('src.server.rtsp.gstreamer_rtsp_server.GLib.MainLoop.new', return_value=mock_mainloop)
        mock_thread = mocker.patch('src.server.rtsp.gstreamer_rtsp_server.Thread')
        gstreamer_rtsp_server.start()
        assert gstreamer_rtsp_server._context == mock_context
        assert gstreamer_rtsp_server._mainloop == mock_mainloop
        gstreamer_rtsp_server._server.attach.assert_called_once()
        mock_thread.assert_called_once_with(target=gstreamer_rtsp_server._loop, daemon=True)
        mock_thread.return_value.start.assert_called_once()
        gstreamer_rtsp_server._logger.info.assert_called_once_with("Gstreamer RTSP Server Started on port: 8888")
        mock_glibcontext.assert_called_once()
        mock_glibmainloop.assert_called_once()

    def test_stop(self, gstreamer_rtsp_server, mocker):
        mock_stream = MagicMock()
        mock_main_loop = MagicMock()
        mock_thread = MagicMock()
        mock_context = MagicMock()
        gstreamer_rtsp_server._stopped = False
        gstreamer_rtsp_server._streams = {'/test': mock_stream(None, None)}
        gstreamer_rtsp_server._mainloop = mock_main_loop
        gstreamer_rtsp_server._thread = mock_thread
        gstreamer_rtsp_server._context = mock_context
        gstreamer_rtsp_server.stop()
        assert gstreamer_rtsp_server._stopped is True
        assert gstreamer_rtsp_server._streams is None
        mock_main_loop.quit.assert_called_once()
        mock_thread.join.assert_called_once()
        mock_context.unref.assert_called_once()

    def test_loop(self,gstreamer_rtsp_server,mocker):
        gstreamer_rtsp_server._mainloop = MagicMock()
        gstreamer_rtsp_server._mainloop.run.side_effect = [KeyboardInterrupt,SystemExit]
        try:
            gstreamer_rtsp_server._loop()
        except Exception:
            pytest.fail("Exception")
        try:
            gstreamer_rtsp_server._loop()
        except Exception:
            pytest.fail("Exception")