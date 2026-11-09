# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: decoder/service.py
Description: REST service that exposes the semantic decoder to multiple encoder
services (as ingest producers) and multiple receiver clients (as independent
readers). Frames are matched to receivers via named streams: every receiver
polling a stream sees every frame posted to it (pub/sub-style fan-out), each
tracking its own cursor via a client-supplied `consumer_id`, similar to SQS
`ReceiveMessage` semantics.

Decoded frames are held in a small in-memory, per-stream ring buffer (bounded by
`buffer_size`); once full, the oldest frame is evicted even if a slow consumer
hasn't read it yet -- the same "may drop under backpressure" tradeoff as message
queue retention limits. State is process-local and does not survive a restart;
running multiple decoder replicas for the same stream is out of scope (would need
a shared store).

Concurrency model: `asyncio.to_thread` keeps the blocking decode+buffer-append
work off the event loop; `state.lock` serializes it per-stream so frame
sequencing stays consistent, while different streams still decode in parallel.
There is no separate worker-thread pool to size/tune.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi import Path as ApiPath

from semantic_img_comp.decoder.decoder import Decoder
from semantic_img_comp.integration.semantic_codec_bridge import SemanticCodecBridge
from semantic_img_comp.utils.logging_helpers import log_json, setup_logger
from semantic_img_comp.utils.service_http import STREAM_ID_PATTERN as _STREAM_ID_PATTERN
from semantic_img_comp.utils.service_http import install_common_endpoints
from semantic_img_comp.utils.visualization import save_composite_img

LOGGER = logging.getLogger("semantic_img_comp.decoder.service")

_POLL_TICK_SEC = 0.05

# SDL425/T-002: stream_id is also used here to build filesystem paths
# (recon_images); see STREAM_ID_PATTERN in utils/service_http.py.


@dataclass
class DecodedFrame:
    frame_seq: int
    img_idx: int
    jpeg_bytes: bytes
    client_sent_at: Optional[str] = None


@dataclass
class DecoderStreamState:
    stream_id: str
    bridge: SemanticCodecBridge
    buffer_size: int
    lock: threading.Lock = field(default_factory=threading.Lock)
    buffer: deque = field(default_factory=deque)
    frames_received: int = 0
    cursors: dict[str, int] = field(default_factory=dict)
    cursors_lock: threading.Lock = field(default_factory=threading.Lock)


class DecoderService:
    """Shared decoder state + per-stream buffers backing the decoder REST API."""

    def __init__(
        self,
        cfg,
        *,
        buffer_size: int = 200,
        output_dir: Optional[Path] = None,
        save_visualizations: bool = False,
        bridge: SemanticCodecBridge,
    ):
        if bridge is None:
            raise ValueError(
                "DecoderService requires a shared SemanticCodecBridge instance; "
                "construct one and pass it in instead of letting it default to None"
            )
        self.cfg = cfg
        self.buffer_size = buffer_size
        self.output_dir = Path(output_dir) if output_dir is not None else None
        self.save_visualizations = save_visualizations
        self.logger = setup_logger(
            name="decoder-service", cfg=cfg
        )
        # Shared bridge (e.g. constructed once by main.py) so the TCP and REST
        # transports use the same model instance + counters; every stream reuses it
        # instead of each getting its own bridge.
        self._shared_bridge = bridge
        self._streams: dict[str, DecoderStreamState] = {}
        self._registry_lock = threading.Lock()

        if self.save_visualizations and self.output_dir is not None:
            (self.output_dir / "recon_images").mkdir(parents=True, exist_ok=True)

    def get_or_create_stream(self, stream_id: str) -> DecoderStreamState:
        with self._registry_lock:
            existing = self._streams.get(stream_id)
            if existing is not None:
                return existing
            bridge = self._shared_bridge
            state = DecoderStreamState(stream_id=stream_id, bridge=bridge, buffer_size=self.buffer_size)
            self._streams[stream_id] = state
            log_json(self.logger, {"event": "stream_created", "stream_id": stream_id})
            return state

    def get_stream(self, stream_id: str) -> DecoderStreamState:
        with self._registry_lock:
            state = self._streams.get(stream_id)
        if state is None:
            raise KeyError(stream_id)
        return state

    def close_stream(self, stream_id: str) -> bool:
        with self._registry_lock:
            return self._streams.pop(stream_id, None) is not None

    async def submit_ingest(
        self, state: DecoderStreamState, payload: bytes, *, client_sent_at: Optional[str]
    ) -> DecodedFrame:
        """Decode+buffer one payload off the event loop thread; see module docstring for the concurrency model."""

        def _work() -> DecodedFrame:
            with state.lock:
                result = state.bridge.decode_payload(payload, client_id=state.stream_id)
                # frame_seq is the bridge's own per-stream sequence (keyed by client_id),
                # so it stays consistent with the TCP decoder path instead of drifting.
                frame_seq = result.img_idx
                state.frames_received = frame_seq

                buf = BytesIO()
                result.image.save(buf, format="JPEG", quality=95)
                jpeg_bytes = buf.getvalue()

                if self.save_visualizations and self.output_dir is not None:
                    out_path = self.output_dir / "recon_images" / f"{state.stream_id}_{frame_seq}.jpeg"
                    save_composite_img(result.image, out_path)

                frame = DecodedFrame(
                    frame_seq=frame_seq,
                    img_idx=result.img_idx,
                    jpeg_bytes=jpeg_bytes,
                    client_sent_at=client_sent_at,
                )
                state.buffer.append(frame)
                while len(state.buffer) > state.buffer_size:
                    state.buffer.popleft()

            return frame

        return await asyncio.to_thread(_work)

    @staticmethod
    def _next_ready_frame(state: DecoderStreamState, consumer_id: str) -> Optional[DecodedFrame]:
        with state.cursors_lock:
            cursor = state.cursors.get(consumer_id, 1)
            for frame in state.buffer:
                if frame.frame_seq >= cursor:
                    state.cursors[consumer_id] = frame.frame_seq + 1
                    return frame
        return None

    async def wait_for_next_frame(
        self, state: DecoderStreamState, consumer_id: str, wait_ms: int
    ) -> Optional[DecodedFrame]:
        """Cursor-based read with optional (async, non-blocking) long-poll wait."""
        deadline = time.monotonic() + max(0, wait_ms) / 1000.0
        while True:
            frame = self._next_ready_frame(state, consumer_id)
            if frame is not None:
                return frame
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            await asyncio.sleep(min(_POLL_TICK_SEC, remaining))

    def frame_file_path(self, state: DecoderStreamState, frame_seq: int) -> Optional[Path]:
        """Path a saved visualization for frame_seq would live at, or None if persistence is disabled."""
        if not self.save_visualizations or self.output_dir is None:
            return None
        return self.output_dir / "recon_images" / f"{state.stream_id}_{frame_seq}.jpeg"


def _frame_headers(frame: DecodedFrame) -> dict[str, str]:
    headers = {"X-Frame-Seq": str(frame.frame_seq), "X-Img-Idx": str(frame.img_idx)}
    if frame.client_sent_at is not None:
        headers["X-Client-Sent-At"] = frame.client_sent_at
    return headers


def create_app(service: DecoderService) -> FastAPI:
    app = FastAPI(title="Semantic Decoder Service")
    app.state.service = service
    max_body_bytes = service.cfg.dec.max_body_bytes
    install_common_endpoints(app, LOGGER, max_body_bytes=max_body_bytes)

    @app.put("/v1/streams/{stream_id}")
    def put_stream(stream_id: str = ApiPath(..., pattern=_STREAM_ID_PATTERN)):
        service.get_or_create_stream(stream_id)
        return {"stream_id": stream_id}

    @app.get("/v1/streams/{stream_id}")
    def get_stream_stats(stream_id: str = ApiPath(..., pattern=_STREAM_ID_PATTERN)):
        try:
            state = service.get_stream(stream_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"unknown stream {stream_id}")
        return {
            "stream_id": stream_id,
            "frames_received": state.frames_received,
            "buffer_depth": len(state.buffer),
            "consumer_cursors": dict(state.cursors),
        }

    @app.delete("/v1/streams/{stream_id}", status_code=204)
    def delete_stream(stream_id: str = ApiPath(..., pattern=_STREAM_ID_PATTERN)):
        if not service.close_stream(stream_id):
            raise HTTPException(status_code=404, detail=f"unknown stream {stream_id}")
        return Response(status_code=204)

    @app.post("/v1/streams/{stream_id}/payloads", status_code=202)
    async def post_payload(request: Request, stream_id: str = ApiPath(..., pattern=_STREAM_ID_PATTERN)):
        payload = await request.body()
        if not payload:
            raise HTTPException(status_code=400, detail="empty request body; expected a mux payload")
        if len(payload) > service.cfg.dec.max_body_bytes:
            # SDL443/T-004: safety net for chunked bodies with no/incorrect Content-Length header
            raise HTTPException(status_code=413, detail="request body too large")

        state = service.get_or_create_stream(stream_id)
        client_sent_at = request.headers.get("X-Client-Sent-At")

        try:
            frame = await service.submit_ingest(state, payload, client_sent_at=client_sent_at)
        except (TypeError, ValueError) as exc:
            # SDL423/T-010: log the internal detail (byte offsets etc.); never echo it to the client
            LOGGER.exception("malformed payload for stream %s", stream_id)
            raise HTTPException(status_code=422, detail="malformed payload") from exc

        return {"frame_seq": frame.frame_seq, "img_idx": frame.img_idx}

    @app.get("/v1/streams/{stream_id}/frames/next")
    async def get_next_frame(
        stream_id: str = ApiPath(..., pattern=_STREAM_ID_PATTERN),
        consumer_id: str = Query(..., min_length=1, max_length=128),
        wait_ms: int = Query(default=0, ge=0, le=30_000),
    ):
        try:
            state = service.get_stream(stream_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"unknown stream {stream_id}")

        frame = await service.wait_for_next_frame(state, consumer_id, wait_ms)
        if frame is None:
            return Response(status_code=204)
        return Response(content=frame.jpeg_bytes, media_type="image/jpeg", headers=_frame_headers(frame))

    @app.get("/v1/streams/{stream_id}/frames/{frame_seq}")
    def get_frame_by_seq(frame_seq: int, stream_id: str = ApiPath(..., pattern=_STREAM_ID_PATTERN)):
        try:
            state = service.get_stream(stream_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"unknown stream {stream_id}")

        # Served from the saved visualization file on disk (not the bounded in-memory
        # ring buffer), so older frames remain fetchable as long as they were persisted.
        frame_path = service.frame_file_path(state, frame_seq)
        if frame_path is None or not frame_path.is_file():
            raise HTTPException(status_code=404, detail=f"frame {frame_seq} not found on disk")
        jpeg_bytes = frame_path.read_bytes()
        return Response(content=jpeg_bytes, media_type="image/jpeg", headers={"X-Frame-Seq": str(frame_seq)})

    return app


def serve(
    cfg,
    *,
    host: str = "0.0.0.0",  # nosec B104 - service is designed to run in a container and listen on all interfaces; host is operator-configurable
    port: int = 8000,
    buffer_size: int = 200,
    output_dir: Optional[Path] = None,
    save_visualizations: bool = False,
    bridge: SemanticCodecBridge,
) -> None:
    import uvicorn

    service = DecoderService(
        cfg,
        buffer_size=buffer_size,
        output_dir=output_dir,
        save_visualizations=save_visualizations,
        bridge=bridge,
    )
    app = create_app(service)
    log_json(service.logger, {
        "event": "decoder_service_started", "host": host, "port": port,
        "buffer_size": buffer_size,
    })
    uvicorn.run(app, host=host, port=port, log_level="info")
