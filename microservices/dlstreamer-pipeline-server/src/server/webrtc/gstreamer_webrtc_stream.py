#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import asyncio
import json
import time
from threading import Thread
from socket import gaierror
from websockets.client import connect as WSConnect
from websockets.exceptions import ConnectionClosedOK, ConnectionClosedError
import gi

# pylint: disable=wrong-import-position
gi.require_version('Gst', '1.0')
from gi.repository import Gst
gi.require_version('GstWebRTC', '1.0')
from gi.repository import GstWebRTC
gi.require_version('GstSdp', '1.0')
from gi.repository import GstSdp
# pylint: enable=wrong-import-position
import src.server.gstreamer_pipeline as GstPipeline
from src.server.common.utils import logging

class GStreamerWebRTCStream:
    def __init__(self, peer_id, frame_caps, launch_string, destination_instance,
                 signaling_server):
        self._logger = logging.get_logger('GStreamerWebRTCStream', is_static=True)
        self._peer_id = peer_id
        self._frame_caps = frame_caps
        self._launch_string = launch_string
        self._destination_instance = destination_instance
        self._server = signaling_server
        self._logger.debug("GStreamerWebRTCStream __init__ with Signaling Server at {}".format(self._server))
        self._conn = None
        self._webrtc = None
        self._stopped = False
        self._thread = None
        self._pipe = None
        self._state = None
        self._webrtc_pipeline = None
        self._webrtc_pipeline_type = "GStreamer WebRTC Stream"
        self._retry_limit = 5
        self._retry_delay = 5
        self._retries_attempted = 0

    async def connect(self):
        if self._conn:
            self._logger.warning("Encountered open connection when attempting to re-connect!")
            return
        self._logger.info("WebRTC Stream connect will negotiate with {} to accept connections from peerid {}".format(
            self._server, self._peer_id))
        self._conn = await WSConnect(self._server)
        await self._conn.send("HELLO {peer_id}".format(peer_id=self._peer_id))

    async def _setup_call(self):
        self._logger.debug("WebRTC Stream setup_call entered")
        await self._conn.send('SESSION {peer_id}'.format(peer_id=self._peer_id))

    def _send_sdp_offer(self, offer):
        text = offer.sdp.as_text()
        self._logger.info("WebRTC Stream Sending offer:\n{}".format(text))
        msg = json.dumps({'sdp': {'type': 'offer', 'sdp': text}})
        event_loop = asyncio.new_event_loop()
        event_loop.run_until_complete(self._conn.send(msg))
        event_loop.close()

    def _on_offer_created(self, promise, _, __):
        self._logger.debug("WebRTC Stream on_offer_created entered")
        promise.wait()
        reply = promise.get_reply()
        offer = reply.get_value('offer')
        promise = Gst.Promise.new()
        self._webrtc.emit('set-local-description', offer, promise)
        promise.interrupt()
        self._send_sdp_offer(offer)

    def _on_negotiation_needed(self, element):
        self._logger.debug("WebRTC Stream on_negotiation_needed for element {}".format(element))
        promise = Gst.Promise.new_with_change_func(self._on_offer_created, element, None)
        element.emit('create-offer', None, promise)

    def _send_ice_candidate_message(self, _, mlineindex, candidate):
        icemsg = json.dumps({'ice': {'candidate': candidate, 'sdpMLineIndex': mlineindex}})
        event_loop = asyncio.new_event_loop()
        event_loop.run_until_complete(self._conn.send(icemsg))
        event_loop.close()

    def _on_incoming_decodebin_stream(self, _, pad):
        self._logger.debug("checking pad caps {}".format(pad))
        if not pad.has_current_caps():
            self._logger.warning("WebRTC Stream Pad has no caps, ignoring: {}".format(pad))
            return
        caps = pad.get_current_caps()
        name = caps.to_string()
        self._logger.debug("WebRTC Stream Pad caps: {}".format(name))
        if name.startswith('video'):
            queue = Gst.ElementFactory.make('queue')
            conv = Gst.ElementFactory.make('videoconvert')
            sink = Gst.ElementFactory.make('autovideosink')
            self._pipe.add(queue)
            self._pipe.add(conv)
            self._pipe.add(sink)
            self._pipe.sync_children_states()
            pad.link(queue.get_static_pad('sink'))
            queue.link(conv)
            conv.link(sink)

    def _on_incoming_stream(self, _, pad):
        self._logger.debug("WebRTC Stream preparing incoming stream {}".format(pad))
        if pad.direction != Gst.PadDirection.SRC:
            return
        decodebin = Gst.ElementFactory.make('decodebin')
        decodebin.connect('pad-added', self._on_incoming_decodebin_stream)
        self._pipe.add(decodebin)
        decodebin.sync_state_with_parent()
        self._webrtc.link(decodebin)

    def prepare_destination_pads(self, pipeline):
        self._pipe = pipeline
        self._pipe.caps = self._frame_caps
        appsrc = self._pipe.get_by_name("webrtc_source")
        self._destination_instance.set_app_src(appsrc, self._pipe)
        self._webrtc = self._pipe.get_by_name('webrtc_destination')
        self._webrtc.connect('on-negotiation-needed', self._on_negotiation_needed)
        self._webrtc.connect('on-ice-candidate', self._send_ice_candidate_message)
        self._webrtc.connect('pad-added', self._on_incoming_stream)

    def _finished_callback(self):
        self._logger.info("GStreamerPipeline finished for peer_id:{}".format(self._peer_id))

    def _start_pipeline(self):
        self._logger.info("Starting WebRTC pipeline for peer_id:{}".format(self._peer_id))
        config = {"type": self._webrtc_pipeline_type, "template": self._launch_string,
                  "prepare-pads": self.prepare_destination_pads}
        request = {"source": { "type": "webrtc_destination" }, "peer_id": self._peer_id}
        self._reset()
        self._webrtc_pipeline = GstPipeline.GStreamerPipeline(
            self._peer_id, config, None, request, self._finished_callback, None)
        self._webrtc_pipeline.start()
        self._logger.info("WebRTC pipeline started for peer_id:{}".format(self._peer_id))

    async def _handle_sdp(self, message):
        if self._webrtc:
            try:
                msg = json.loads(message)
            except ValueError:
                self._logger.error("Error processing empty or bad SDP message!")
                return
            self._logger.info("Handle SDP message {}".format(msg))
            if 'sdp' in msg:
                sdp = msg['sdp']
                assert(sdp['type'] == 'answer')
                sdp = sdp['sdp']
                self._logger.warning("WebRTC Received answer: {}".format(sdp))
                _, sdpmsg = GstSdp.SDPMessage.new()
                GstSdp.sdp_message_parse_buffer(bytes(sdp.encode()), sdpmsg)
                answer = GstWebRTC.WebRTCSessionDescription.new(GstWebRTC.WebRTCSDPType.ANSWER, sdpmsg)
                promise = Gst.Promise.new()
                self._webrtc.emit('set-remote-description', answer, promise)
                promise.interrupt()
            elif 'ice' in msg:
                ice = msg['ice']
                candidate = ice['candidate']
                sdpmlineindex = ice['sdpMLineIndex']
                self._webrtc.emit('add-ice-candidate', sdpmlineindex, candidate)
        else:
            self._logger.debug("Peer not yet connected or webrtcbin element missing from frame destination.")

    def _log_banner(self, heading):
        banner = "="*len(heading)
        self._logger.info(banner)
        self._logger.info(heading)
        self._logger.info(banner)

    async def message_loop(self):
        self._logger.debug("Entered WebRTC Stream message_loop")
        assert self._conn
        while not self._stopped:
            message = None
            try:
                message = await asyncio.wait_for(self._conn.recv(), 10)
            except asyncio.TimeoutError:
                continue
            except ConnectionClosedError:
                self._logger.error("ConnectionClosedError in WebRTC message_loop!")
                break
            except ConnectionClosedOK:
                self._logger.info("ConnectionClosedOK in WebRTC message_loop")
                break
            if message:
                self._log_banner("WebRTC Message")
                if message == 'HELLO':
                    await self._setup_call()
                    self._logger.info("Registered to Pipeline Server...")
                elif message == 'START_WEBRTC_STREAM':
                    self._start_pipeline()
                elif message.startswith('ERROR'):
                    self._logger.warning("WebRTC Stream Error: {}".format(message))
                    return 1
                else:
                    await self._handle_sdp(message)
        self._logger.debug("WebRTC Stream exiting message_loop.")
        return 0

    def _check_plugins(self):
        self._log_banner("WebRTC Plugin Check")
        needed = ["opus", "vpx", "nice", "webrtc", "dtls", "srtp", "rtp",
                  "rtpmanager"]
        missing = list(filter(lambda p: Gst.Registry.get().find_plugin(p) is None, needed))
        if missing:
            self._logger.info("Missing gstreamer plugins: {}".format(missing))
            return False
        self._logger.debug("Successfully found required gstreamer plugins")
        return True

    def _listen_for_peer_connections(self):
        self._logger.debug("Listening for peer connections")
        event_loop = asyncio.new_event_loop()
        res = None
        while not self._stopped:
            try:
                event_loop.run_until_complete(self.connect())
                res = event_loop.run_until_complete(self.message_loop())
            except gaierror:
                self._logger.error("Cannot reach WebRTC Signaling Server {}! Is it running?".format(self._server))
            except ConnectionClosedError:
                self._logger.error("ConnectionClosedError in WebRTC listen_for_peer_connections!")
            except ConnectionClosedOK:
                self._logger.info("ConnectionClosedOK in WebRTC listen_for_peer_connections")
            except (KeyboardInterrupt, SystemExit):
                pass
            finally:
                if self._conn:
                    self._logger.debug("closing connection to re-init.")
                    event_loop.run_until_complete(self._conn.close())
                    self._conn = None
            self._retries_attempted += 1
            if self._retries_attempted <= self._retry_limit:
                self._logger.warning("Attempt {}/{} to restart listener begins in {} seconds.".format(
                    self._retries_attempted, self._retry_limit, self._retry_delay))
                time.sleep(self._retry_delay)
            else:
                break
        if res:
            self._logger.info("WebRTC Result: {}".format(res))
        event_loop.close()

    def _thread_launcher(self):
        try:
            self._listen_for_peer_connections()
        except (KeyboardInterrupt, SystemExit):
            pass
        self._logger.info("Exiting WebRTC thread launcher")

    def start(self):
        self._logger.info("Starting WebRTC Stream using Signaling Server at: {}".format(self._server))
        if not self._check_plugins():
            self._logger.error("WebRTC Stream error - dependent plugins are missing!")
        self._thread = Thread(target=self._thread_launcher)
        self._thread.start()

    def _reset(self):
        if self._webrtc_pipeline:
            self._webrtc_pipeline.stop()
        self._webrtc_pipeline = None
        self._pipe = None
        self._webrtc = None

    def stop(self):
        self._reset()
        self._stopped = True
        self._logger.info("Stopping GStreamer WebRTC Stream for peer_id {}".format(self._peer_id))
        if self._thread:
            self._thread.join()
        self._thread = None
        self._logger.debug("GStreamer WebRTC Stream completed pipeline for peer_id {}".format(self._peer_id))
