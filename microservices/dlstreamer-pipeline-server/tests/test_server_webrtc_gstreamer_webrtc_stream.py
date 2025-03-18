#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import pytest
from unittest.mock import MagicMock, AsyncMock
import asyncio
import json

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
    return GStreamerWebRTCStream("peer1", "video/x-raw", "launch_string", MagicMock(), "ws://localhost:8080")

class TestGStreamerWebRTCStream:

    def test_on_offer_created(self, gstreamer_webrtc_stream, mocker,Gst):
        mock_promise = MagicMock()
        mock_reply = MagicMock()
        mock_offer = MagicMock()
        mock_webrtc = MagicMock()
        mock_reply.get_value.return_value = mock_offer
        mock_promise.get_reply.return_value = mock_reply
        gstreamer_webrtc_stream._webrtc = mock_webrtc
        mock_send_sdp_offer = mocker.patch.object(gstreamer_webrtc_stream,'_send_sdp_offer')
        gstreamer_webrtc_stream._on_offer_created(mock_promise, None, None)
        mock_promise.wait.assert_called_once()
        mock_promise.get_reply.assert_called_once()
        mock_reply.get_value.assert_called_once_with('offer')
        mock_webrtc.emit.assert_called_once_with('set-local-description', mock_offer, Gst.Promise.new())
        mock_send_sdp_offer.assert_called_once_with(mock_offer)

    def test_on_negotiation_needed(self, gstreamer_webrtc_stream, mocker,Gst):
        mock_element = MagicMock()
        mock_promise = MagicMock()
        mock_on_offer_created = mocker.patch.object(gstreamer_webrtc_stream,'_on_offer_created')
        Gst.Promise.new_with_change_func.return_value = mock_promise
        gstreamer_webrtc_stream._on_negotiation_needed(mock_element)
        Gst.Promise.new_with_change_func.assert_called_once_with(mock_on_offer_created,mock_element,None)
        mock_element.emit.assert_called_once_with('create-offer', None, mock_promise)
    
    def test_on_incoming_decodebin_stream(self, gstreamer_webrtc_stream, mocker,Gst):
        mock_pad = MagicMock()
        mock_caps = MagicMock()
        mock_queue = MagicMock()
        mock_conv = MagicMock()
        mock_sink = MagicMock()
        mock_pad.has_current_caps.return_value = None
        gstreamer_webrtc_stream._on_incoming_decodebin_stream(None,mock_pad)
        mock_pad.get_current_caps.assert_not_called()
        mock_pad.has_current_caps.return_value = True
        mock_pad.get_current_caps.return_value = mock_caps
        mock_caps.to_string.return_value = "video/x-raw"
        Gst.ElementFactory.make.side_effect = [mock_queue,mock_conv,mock_sink]
        gstreamer_webrtc_stream._pipe = MagicMock()
        gstreamer_webrtc_stream._on_incoming_decodebin_stream(None, mock_pad)
        mock_pad.get_current_caps.assert_called_once()
        mock_caps.to_string.assert_called_once()
        assert gstreamer_webrtc_stream._pipe.add.call_count == 3
        Gst.ElementFactory.make.assert_any_call('queue')
        Gst.ElementFactory.make.assert_any_call('videoconvert')
        Gst.ElementFactory.make.assert_any_call('autovideosink')
        gstreamer_webrtc_stream._pipe.sync_children_states.assert_called_once()
        mock_pad.link.assert_called_once_with(mock_queue.get_static_pad('sink'))
        mock_queue.link.assert_called_once_with(mock_conv)
        mock_conv.link.assert_called_once_with(mock_sink)

    def test_on_incoming_stream_negative(self, gstreamer_webrtc_stream, mocker,Gst):
        mock_pad = MagicMock()
        mock_decodbin = MagicMock()
        mock_pipe = MagicMock()
        mock_webrtc = MagicMock()
        mock_on_incoming_decodebin_stream = mocker.patch.object(gstreamer_webrtc_stream,'_on_incoming_decodebin_stream')
        mock_pad.direction = Gst.PadDirection.SRC
        Gst.ElementFactory.make.return_value = mock_decodbin
        gstreamer_webrtc_stream._pipe = mock_pipe
        gstreamer_webrtc_stream._webrtc = mock_webrtc
        gstreamer_webrtc_stream._on_incoming_stream(None, mock_pad)
        mock_decodbin.connect.assert_called_once_with('pad-added',mock_on_incoming_decodebin_stream)
        mock_pipe.add.assert_called_once_with(mock_decodbin)
        mock_decodbin.sync_state_with_parent.assert_called_once()
        mock_webrtc.link.assert_called_once_with(mock_decodbin)

    def test_on_incoming_stream(self, gstreamer_webrtc_stream, mocker,Gst):
        mock_pad = MagicMock()
        gstreamer_webrtc_stream._on_incoming_stream(None, mock_pad)
        Gst.ElementFactory.make.assert_not_called()

    def test_prepare_destination_pads(self, gstreamer_webrtc_stream, mock_pipeline,mocker):
        mock_appsrc = MagicMock()
        mock_webrtc = MagicMock()
        mock_on_negotiation = mocker.patch.object(gstreamer_webrtc_stream,'_on_negotiation_needed')
        mock_send_ice = mocker.patch.object(gstreamer_webrtc_stream,'_send_ice_candidate_message')
        mock_on_incoming = mocker.patch.object(gstreamer_webrtc_stream,'_on_incoming_stream')
        mock_pipeline.get_by_name.side_effect = [mock_appsrc,mock_webrtc]
        gstreamer_webrtc_stream.prepare_destination_pads(mock_pipeline)
        mock_pipeline.get_by_name.assert_any_call("webrtc_source")
        mock_pipeline.get_by_name.assert_any_call("webrtc_destination")
        gstreamer_webrtc_stream._destination_instance.set_app_src.assert_called_once_with(mock_appsrc,mock_pipeline)
        mock_webrtc.connect.assert_any_call('on-negotiation-needed',mock_on_negotiation)
        mock_webrtc.connect.assert_any_call('on-ice-candidate',mock_send_ice)
        mock_webrtc.connect.assert_any_call('pad-added',mock_on_incoming)
        assert mock_pipeline.caps == "video/x-raw"

    def test_finished_callback(self, gstreamer_webrtc_stream):
        gstreamer_webrtc_stream._logger.info = MagicMock()
        gstreamer_webrtc_stream._finished_callback()
        gstreamer_webrtc_stream._logger.info.assert_called_once_with("GStreamerPipeline finished for peer_id:peer1")

    def test_start_pipeline(self, gstreamer_webrtc_stream, mocker):
        mock_pipeline = MagicMock()
        mock_reset = mocker.patch.object(gstreamer_webrtc_stream,'_reset')
        mock_prepads = mocker.patch.object(gstreamer_webrtc_stream,'prepare_destination_pads')
        mock_gstpipeline = mocker.patch('src.server.webrtc.gstreamer_webrtc_stream.GstPipeline.GStreamerPipeline', return_value=mock_pipeline)
        gstreamer_webrtc_stream._start_pipeline()
        mock_gstpipeline.assert_called_once_with("peer1",{"type": gstreamer_webrtc_stream._webrtc_pipeline_type,"template": gstreamer_webrtc_stream._launch_string,"prepare-pads": gstreamer_webrtc_stream.prepare_destination_pads},None,{"source": { "type": "webrtc_destination" }, "peer_id": "peer1"},gstreamer_webrtc_stream._finished_callback,None)
        mock_reset.assert_called_once()
        mock_pipeline.start.assert_called_once()

    def test_check_plugins(self, gstreamer_webrtc_stream,Gst):
        Gst.Registry.get.find_plugin.side_effect = lambda x: x
        assert gstreamer_webrtc_stream._check_plugins() is True
        Gst.Registry.get.return_value.find_plugin.return_value = None
        assert gstreamer_webrtc_stream._check_plugins() is False

    def test_thread_launcher(self, gstreamer_webrtc_stream, mocker):
        mock_listen = mocker.patch.object(gstreamer_webrtc_stream, '_listen_for_peer_connections')
        gstreamer_webrtc_stream._thread_launcher()
        mock_listen.assert_called_once()
        assert gstreamer_webrtc_stream._peer_id == "peer1"
    
    def test_thread_launcher_exception(self, gstreamer_webrtc_stream, mocker):
        gstreamer_webrtc_stream._listen_for_peer_connections = MagicMock()
        gstreamer_webrtc_stream._listen_for_peer_connections.side_effect = [KeyboardInterrupt,SystemExit]
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
        mock_webrtc.stop.assert_called_once()
        assert gstreamer_webrtc_stream._webrtc_pipeline is None
        assert gstreamer_webrtc_stream._pipe is None
        assert gstreamer_webrtc_stream._webrtc is None

    def test_stop(self, gstreamer_webrtc_stream,mocker):
        mock_reset = mocker.patch.object(gstreamer_webrtc_stream,'_reset')
        mock_thread = MagicMock()
        gstreamer_webrtc_stream._thread = mock_thread
        gstreamer_webrtc_stream.stop()
        mock_reset.assert_called_once()
        mock_thread.join.assert_called_once()
        assert gstreamer_webrtc_stream._thread is None
        assert gstreamer_webrtc_stream._stopped is True

    @pytest.mark.asyncio
    async def test_connect(self, gstreamer_webrtc_stream, mocker):
        mock_ws = MagicMock()
        mock_ws.send = AsyncMock()
        mock_conn_ws = mocker.patch('src.server.webrtc.gstreamer_webrtc_stream.WSConnect',new=mocker.AsyncMock(return_value=mock_ws))
        await gstreamer_webrtc_stream.connect()
        mock_ws.send.assert_called_once_with("HELLO peer1")
        mock_conn_ws.assert_called_once_with("ws://localhost:8080")

    @pytest.mark.asyncio
    async def test_connect_negative(self, gstreamer_webrtc_stream, mocker):
        gstreamer_webrtc_stream._conn = MagicMock()
        mock_ws = MagicMock()
        mock_ws.send = AsyncMock()
        mock_conn_ws = mocker.patch('src.server.webrtc.gstreamer_webrtc_stream.WSConnect',new=mocker.AsyncMock(return_value=mock_ws))
        await gstreamer_webrtc_stream.connect()
        mock_conn_ws.assert_not_called()

    @pytest.mark.asyncio
    async def test_setup_call(self, gstreamer_webrtc_stream):
        gstreamer_webrtc_stream._conn = AsyncMock()
        await gstreamer_webrtc_stream._setup_call()
        gstreamer_webrtc_stream._conn.send.assert_called_once_with('SESSION peer1')

    def test_send_sdp_offer(self, gstreamer_webrtc_stream, mocker):
        mock_offer = MagicMock()
        mock_offer.sdp.as_text.return_value = "sdp_value"
        mock_conn = MagicMock()
        mock_event_loop = MagicMock()
        gstreamer_webrtc_stream._conn = mock_conn
        mocker.patch.object(mock_conn,'send')
        mock_new_event = mocker.patch('asyncio.new_event_loop', return_value=mock_event_loop)
        gstreamer_webrtc_stream._send_sdp_offer(mock_offer)
        mock_offer.sdp.as_text.assert_called_once()
        mock_conn.send.assert_called_once_with(json.dumps({'sdp': {'type': 'offer', 'sdp': 'sdp_value'}}))
        mock_new_event.assert_called_once()
        mock_event_loop.run_until_complete.assert_called_once_with(mock_conn.send())
        mock_event_loop.close.assert_called_once()

    def test_send_ice_candidate_message(self, gstreamer_webrtc_stream, mocker):
        mock_conn = MagicMock()
        mock_event_loop = MagicMock()
        gstreamer_webrtc_stream._conn = mock_conn
        mock_new_event = mocker.patch('asyncio.new_event_loop', return_value=mock_event_loop)
        gstreamer_webrtc_stream._send_ice_candidate_message(None, 0, "candidate")
        mock_conn.send.assert_called_once_with(json.dumps({'ice': {'candidate': 'candidate', 'sdpMLineIndex': 0}}))
        mock_new_event.assert_called_once()
        mock_event_loop.run_until_complete.assert_called_once_with(mock_conn.send())

    @pytest.mark.asyncio
    async def test_handle_sdp(self, gstreamer_webrtc_stream, mocker,Gst):
        mock_promise = MagicMock()
        mock_answer = MagicMock()
        Gst.Promise.new.return_value = mock_promise
        mock_web_rtc = MagicMock()
        gstreamer_webrtc_stream._webrtc = mock_web_rtc
        mock_message = json.dumps({'sdp': {'type': 'answer', 'sdp': 'sdp_value'}})
        mock_sdpmsg = MagicMock()
        mock_sdp = mocker.patch('src.server.webrtc.gstreamer_webrtc_stream.GstSdp.SDPMessage.new', return_value=(None, mock_sdpmsg))
        mock_parse = mocker.patch('src.server.webrtc.gstreamer_webrtc_stream.GstSdp.sdp_message_parse_buffer')
        mock_gst_webrtc = mocker.patch('src.server.webrtc.gstreamer_webrtc_stream.GstWebRTC.WebRTCSessionDescription.new',return_value = mock_answer)
        await gstreamer_webrtc_stream._handle_sdp(mock_message)
        gstreamer_webrtc_stream._webrtc.emit.assert_called_once_with('set-remote-description', mock_answer, mock_promise)
        mock_sdp.assert_called_once()
        mock_parse.assert_called_once()
        mock_gst_webrtc.assert_called_once()
        mock_promise.interrupt.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_sdp_ice(self, gstreamer_webrtc_stream, mocker,Gst):
        mock_web_rtc = MagicMock()
        gstreamer_webrtc_stream._webrtc = mock_web_rtc
        mock_message = json.dumps({'ice': {'candidate': 'candidate1', 'sdpMLineIndex': 0}})
        await gstreamer_webrtc_stream._handle_sdp(mock_message)
        mock_web_rtc.emit.assert_called_once_with("add-ice-candidate",0,"candidate1")

    @pytest.mark.asyncio
    async def test_handle_sdp_exception(self, gstreamer_webrtc_stream, mocker,Gst):
        gstreamer_webrtc_stream._logger = MagicMock()
        mock_web_rtc = MagicMock()
        gstreamer_webrtc_stream._webrtc = mock_web_rtc
        mock_message = '{"ice": {"candidate": "candidate1", "sdpMLineIndex": 0'
        await gstreamer_webrtc_stream._handle_sdp(mock_message)
        gstreamer_webrtc_stream._logger.error.assert_called_once_with("Error processing empty or bad SDP message!")
        gstreamer_webrtc_stream._webrtc = None
        await gstreamer_webrtc_stream._handle_sdp(mock_message)
        gstreamer_webrtc_stream._logger.debug.assert_called_once_with("Peer not yet connected or webrtcbin element missing from frame destination.")

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

    @pytest.mark.asyncio
    async def test_message_loop(self, gstreamer_webrtc_stream, mocker):
        mock_setup_call = mocker.patch.object(gstreamer_webrtc_stream,'_setup_call',return_value = AsyncMock())
        mock_start_pipeline = mocker.patch.object(gstreamer_webrtc_stream,'_start_pipeline',return_value = AsyncMock())
        mock_handle_sdp = mocker.patch.object(gstreamer_webrtc_stream,'_handle_sdp',return_value = AsyncMock())
        gstreamer_webrtc_stream._conn = AsyncMock()
        gstreamer_webrtc_stream._conn.recv = AsyncMock(side_effect=["HELLO", "START_WEBRTC_STREAM","NA", "ERROR fail"])
        result = await gstreamer_webrtc_stream.message_loop()
        assert result == 1
        mock_setup_call.assert_called_once()
        mock_start_pipeline.assert_called_once()
        mock_handle_sdp.assert_called_once()

    @pytest.mark.asyncio
    async def test_message_loop_stopped(self, gstreamer_webrtc_stream, mocker):
        gstreamer_webrtc_stream._stopped = True
        gstreamer_webrtc_stream._conn = AsyncMock()
        result = await gstreamer_webrtc_stream.message_loop()
        assert result == 0