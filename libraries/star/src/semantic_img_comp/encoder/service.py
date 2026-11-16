# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: encoder/service.py
Description: REST service that exposes the semantic encoder to multiple concurrent
sender clients and forwards encoded payloads to a decoder service over HTTP.

Unlike the batch `encoder/runner.py` (one hardcoded TCP peer, one input directory),
this module lets any number of clients PUT/POST into independently tracked
"streams" (named, pub/sub-style: many senders may push into one stream, and the
decoder service fans each frame out to every receiver polling that stream).

Concurrency model: `encode_from_jpeg` only submits a frame and returns a `Future`
immediately (the bridge serializes actual encode work onto its own dedicated worker
thread); a per-stream forwarder thread -- started once when the stream is created --
drains those futures in submission order, blocks on `.result()`, and hands the result
off to a second per-stream poster thread (over its own queue) that does the actual
decoder POST, so request handlers never block on encode or forward.
A single `Encoder` instance (and its loaded YOLO/OpenVINO model) is created once at
startup and shared by every stream's `SemanticCodecBridge` so the model is loaded
once, not once per stream.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import Future
import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi import Path as ApiPath
from pydantic import BaseModel, Field, field_validator

from semantic_img_comp import healthcheck
from semantic_img_comp.integration.semantic_codec_bridge import SemanticCodecBridge
from semantic_img_comp.utils.logging_helpers import log_json, setup_logger
from semantic_img_comp.utils.rate_limit import sleep_to_enforce_fps as _sleep_to_enforce_fps
from semantic_img_comp.utils.service_http import STREAM_ID_PATTERN as _STREAM_ID_PATTERN
from semantic_img_comp.utils.service_http import install_common_endpoints

LOGGER = logging.getLogger("semantic_img_comp.encoder.service")


class StreamCreateRequest(BaseModel):
    # compression_level is only ever compared to 1 or 2 elsewhere (see
    # pipeline_manager.py / semantic_codec_bridge.py); bound it accordingly.
    compression_level: int = Field(default=2, ge=1, le=2)
    # SDL443: client-supplied decoder_url is used to build outgoing requests
    # from this service (see _stream_forwarder); restrict to http(s)
    # to block non-HTTP schemes (file://, gopher://, etc.). This does not by
    # itself prevent SSRF to other internal hosts -- see evidence report.
    decoder_url: Optional[str] = Field(default=None, max_length=2048)
    decoder_stream_id: Optional[str] = Field(default=None, min_length=1, max_length=128, pattern=_STREAM_ID_PATTERN)

    @field_validator("decoder_url")
    @classmethod
    def _decoder_url_scheme(cls, v):
        if v is not None and not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("decoder_url must start with http:// or https://")
        return v


@dataclass
class StreamState:
    stream_id: str
    bridge: SemanticCodecBridge
    decoder_url: str
    decoder_stream_id: str
    compression_level: int = 2
    lock: threading.Lock = field(default_factory=threading.Lock)
    frames_processed: int = 0
    created_at: float = field(default_factory=time.monotonic)
    fps: float = 0.0
    encode_queue: "queue.Queue" = field(default_factory=lambda: queue.Queue(maxsize=200))
    encoding_thread: Optional[threading.Thread] = None
    ready_to_send_queue: "queue.Queue" = field(default_factory=lambda: queue.Queue(maxsize=200))
    sender_thread: Optional[threading.Thread] = None


def _post_frame_to_decoder(service: "EncoderService", state: StreamState) -> None:
    """Drain *state.post_queue* and POST each already-encoded payload to the decoder.

    Started once per stream (in `get_or_create_stream`) and runs for the stream's whole
    lifetime, fed by `_stream_forwarder` over `state.post_queue` so a slow/throttled POST
    never delays that thread from picking up the next encode future. Stops on the
    sentinel `None` put by `close_stream`. Forward failures are logged and skipped (not
    raised) since the HTTP caller that submitted the frame has already gotten an
    "accepted" response.
    """
    while True:
        item = state.ready_to_send_queue.get()
        if item is None:
            return
        result, client_sent_at, t_start = item

        headers = {"Content-Type": "application/octet-stream"}
        if client_sent_at is not None:
            headers["X-Client-Sent-At"] = client_sent_at

        try:
            resp = service.http_client.post(
                f"{state.decoder_url}/v1/streams/{state.decoder_stream_id}/payloads",
                content=result.payload,
                headers=headers,
            )
            resp.raise_for_status()
            frame_seq = resp.json().get("frame_seq")
        except httpx.HTTPError as exc:
            log_json(service.logger, {
                "event": "stream_forward_error", "stream_id": state.stream_id,
                "img_id": result.img_data.img_idx, "error": str(exc),
            })
            continue

        # Read the bridge's own per-client sequence instead of a separate local
        # increment, so this stays correct even when callers pass explicit img_id.
        with state.lock:
            state.frames_processed = result.img_data.img_idx

        log_json(service.logger, {
            "event": "frame_forwarded", "stream_id": state.stream_id,
            "img_id": result.img_data.img_idx, "frame_seq": frame_seq,
            "payload_bytes": int(sum(result.size_log.values())),
        })

        sleep_ms = _sleep_to_enforce_fps(t_start, state.fps)
        if sleep_ms > 0:
            log_json(service.logger, {
                "event": "frame_rate_limited", "stream_id": state.stream_id,
                "img_id": result.img_data.img_idx, "target_fps": state.fps,
                "sleep_ms": round(sleep_ms, 2),
            })


def _stream_forwarder(service: "EncoderService", state: StreamState) -> None:
    """Drain encode futures from *state.forward_queue* in submission order and hand each off to the poster.

    Started once per stream (in `get_or_create_stream`) and runs for the stream's whole
    lifetime; blocks on each future's `.result()` only once it's up next to forward, so a
    slow encode never stalls new frame submissions. Stops on the sentinel `None` put by
    `close_stream`. The resolved result is handed to `_post_frame_to_decoder` over
    `state.post_queue` (its own persistent thread) so a slow/throttled POST never delays
    picking up the next future off `state.forward_queue`.
    """
    while True:
        item = state.encode_queue.get()
        if item is None:
            return
        encode_future, client_sent_at, t_start = item
        try:
            result = encode_future.result()
        except BaseException as exc:  # noqa: BLE001 - logged here, nothing left to propagate to
            log_json(service.logger, {
                "event": "stream_forward_error", "stream_id": state.stream_id, "error": str(exc),
            })
            continue

        state.ready_to_send_queue.put((result, client_sent_at, t_start))


class EncoderService:
    """Shared model state + per-stream bridges backing the encoder REST API."""

    def __init__(
        self,
        cfg,
        *,
        decoder_url: str,
        bridge: SemanticCodecBridge,
        http_transport: Optional[httpx.BaseTransport] = None,
        fps: float = 1.0,
    ):
        if bridge is None:
            raise ValueError(
                "EncoderService requires a shared SemanticCodecBridge instance; "
                "construct one and pass it in instead of letting it default to None"
            )
        self.cfg = cfg
        self.fps = fps
        self.default_decoder_url = decoder_url.rstrip("/")
        self.logger = setup_logger(
            name="encoder-service", cfg=cfg
        )
        # trust_env=False: this client talks only to the decoder over the internal
        # service network, so it must never pick up a host/corporate HTTP(S)_PROXY.
        self.http_client = httpx.Client(timeout=30.0, transport=http_transport, trust_env=False)
        # Shared bridge (e.g. constructed once by main.py) so the TCP and REST
        # transports use the same model instance + counters; every stream reuses it
        # instead of each getting its own bridge/encode-worker-thread.
        self._shared_bridge = bridge
        self.shared_encoder = bridge.encoder
        self._streams: dict[str, StreamState] = {}
        self._registry_lock = threading.Lock()
        healthcheck.HTTP_READY = True


    def get_or_create_stream(
        self,
        stream_id: str,
        *,
        compression_level: int = 2,
        decoder_url: Optional[str] = None,
        decoder_stream_id: Optional[str] = None,
    ) -> StreamState:
        with self._registry_lock:
            existing = self._streams.get(stream_id)
            if existing is not None:
                return existing
            bridge = self._shared_bridge
            state = StreamState(
                stream_id=stream_id,
                bridge=bridge,
                decoder_url=(decoder_url or self.default_decoder_url).rstrip("/"),
                decoder_stream_id=decoder_stream_id or stream_id,
                compression_level=compression_level,
                fps=self.fps,
            )
            state.encoding_thread = threading.Thread(
                target=_stream_forwarder,
                args=(self, state),
                daemon=True,
                name=f"encoder-service-forward-{stream_id}",
            )
            state.encoding_thread.start()
            state.sender_thread = threading.Thread(
                target=_post_frame_to_decoder,
                args=(self, state),
                daemon=True,
                name=f"encoder-service-post-{stream_id}",
            )
            state.sender_thread.start()
            self._streams[stream_id] = state
            log_json(self.logger, {
                "event": "stream_created", "stream_id": stream_id, "decoder_url": state.decoder_url,
                "decoder_stream_id": state.decoder_stream_id,
            })
            return state

    def get_stream(self, stream_id: str) -> StreamState:
        with self._registry_lock:
            state = self._streams.get(stream_id)
        if state is None:
            raise KeyError(stream_id)
        return state

    def close_stream(self, stream_id: str) -> bool:
        with self._registry_lock:
            state = self._streams.pop(stream_id, None)
        if state is None:
            return False
        # Sentinel + join so every future already submitted for this stream is
        # forwarded (or logged as failed) before the stream is considered gone.
        state.encode_queue.put(None)
        if state.encoding_thread is not None:
            state.encoding_thread.join(timeout=5.0)
        state.ready_to_send_queue.put(None)
        if state.sender_thread is not None:
            state.sender_thread.join(timeout=5.0)
        return True

    def shutdown(self) -> None:
        self.http_client.close()

    def submit_frame(
        self,
        state: StreamState,
        jpeg_bytes: bytes,
        *,
        img_id: Optional[int],
        client_sent_at: Optional[str],
    ) :
        """Hand one frame off to the bridge and the stream's forwarder thread; returns queue_length.

        Does not wait for the encode or the decoder forward -- `bridge.encode_from_jpeg`
        returns a `Future` immediately, which is queued for the stream's forwarder thread
        (started once in `get_or_create_stream`) to resolve and forward in submission order.
        Only raises for synchronous submission errors (e.g. malformed jpeg_bytes).
        """
        # Held across submit+enqueue so the order futures land in state.forward_queue
        # matches the order they were submitted to the bridge's own encode queue;
        # different streams still run fully in parallel (each has its own forwarder).
        with state.lock:
            t_start = time.perf_counter()
            # img_id=None is handled by the bridge itself (auto-increments its own
            # per-client_id sequence) -- do not pre-resolve it here.
            encode_future: "Future" = state.bridge.encode_from_jpeg(
                jpeg_bytes,
                img_id=img_id,
                client_id=state.stream_id,
                compression_level=state.compression_level,
            )
            state.encode_queue.put((encode_future, client_sent_at, t_start))



def create_app(service: EncoderService) -> FastAPI:
    app = FastAPI(title="Semantic Encoder Service")
    app.state.service = service
    max_body_bytes = service.cfg.enc.max_body_bytes
    install_common_endpoints(app, LOGGER, max_body_bytes=max_body_bytes)

    @app.put("/v1/streams/{stream_id}")
    def put_stream(stream_id: str = ApiPath(..., pattern=_STREAM_ID_PATTERN), body: StreamCreateRequest = StreamCreateRequest()):
        state = service.get_or_create_stream(
            stream_id,
            compression_level=body.compression_level,
            decoder_url=body.decoder_url,
            decoder_stream_id=body.decoder_stream_id,
        )
        return {
            "stream_id": stream_id,
            "decoder_url": state.decoder_url,
            "decoder_stream_id": state.decoder_stream_id,
            "compression_level": state.compression_level,
        }

    @app.get("/v1/streams/{stream_id}")
    def get_stream_stats(stream_id: str = ApiPath(..., pattern=_STREAM_ID_PATTERN)):
        try:
            state = service.get_stream(stream_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"unknown stream {stream_id}")
        return {
            "stream_id": stream_id,
            "frames_processed": state.frames_processed,
            "decoder_url": state.decoder_url,
            "decoder_stream_id": state.decoder_stream_id,
        }

    @app.delete("/v1/streams/{stream_id}", status_code=204)
    def delete_stream(stream_id: str = ApiPath(..., pattern=_STREAM_ID_PATTERN)):
        if not service.close_stream(stream_id):
            raise HTTPException(status_code=404, detail=f"unknown stream {stream_id}")
        return Response(status_code=204)

    @app.post("/v1/streams/{stream_id}/frames", status_code=202)
    async def post_frame(
        request: Request,
        stream_id: str = ApiPath(..., pattern=_STREAM_ID_PATTERN),
        img_id: Optional[int] = Query(default=None),
    ):
        jpeg_bytes = await request.body()
        if not jpeg_bytes:
            raise HTTPException(status_code=400, detail="empty request body; expected raw JPEG bytes")
        if len(jpeg_bytes) > service.cfg.enc.max_body_bytes:
            # SDL443/T-004: safety net for chunked bodies with no/incorrect Content-Length header
            raise HTTPException(status_code=413, detail="request body too large")

        state = service.get_or_create_stream(stream_id)
        client_sent_at = request.headers.get("X-Client-Sent-At")
        try:
            service.submit_frame(
                state, jpeg_bytes, img_id=img_id, client_sent_at=client_sent_at
            )
        except (TypeError, ValueError) as exc:
            LOGGER.exception("malformed frame for stream %s", stream_id)
            raise HTTPException(status_code=422, detail="malformed frame") from exc

        # Encoding and the decoder forward happen off this request on the stream's
        # forwarder thread (see _stream_forwarder); this only confirms acceptance.
        return {
            "status": "accepted",
            "stream_id": stream_id,
        }

    return app


def serve(
    cfg,
    *,
    host: str = "0.0.0.0",  # nosec B104 - service is designed to run in a container and listen on all interfaces; host is operator-configurable
    port: int = 8000,
    decoder_url: str,
    bridge: SemanticCodecBridge,
    fps: float = 1.0,
) -> None:
    import uvicorn

    service = EncoderService(cfg, decoder_url=decoder_url, bridge=bridge, fps=fps)
    app = create_app(service)
    log_json(service.logger, {
        "event": "encoder_service_started", "host": host, "port": port,
        "decoder_url": service.default_decoder_url,
    })
    uvicorn.run(app, host=host, port=port, log_level="info")
