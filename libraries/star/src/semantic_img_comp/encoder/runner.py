# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: encoder/runner.py
Version: 0.2
Authors: Omid Semiari, Hosein Nikopour
Date: 2026-04-10
Description: wrapper module that runs encoder functions.
"""
from __future__ import annotations

from concurrent.futures import Future
import math
import queue
import socket
import threading
import time

from semantic_img_comp.decoder.demux import recv_frame
from semantic_img_comp.integration.semantic_codec_bridge import EncodeResult, SemanticCodecBridge
from semantic_img_comp.net.connection import accept_clients, connect_with_retry
from semantic_img_comp.encoder.encoder import Encoder
from semantic_img_comp import healthcheck

from semantic_img_comp.utils.runtime import sync
from semantic_img_comp.utils.logging_helpers import (
    setup_logger,
    log_json,
)
from semantic_img_comp.utils.rate_limit import sleep_to_enforce_fps as _sleep_to_enforce_fps


def _image_dispatcher(
    client_conn,
    *,
    cfg,
    bridge: SemanticCodecBridge,
    client_id: str,
    runtime_compression_level: int,
    pending: "queue.Queue[tuple[Future[EncodeResult], float] | None]",
    logger,
) -> None:
    """Receive length-prefixed JPEG frames from one client and submit them for encoding.

    Runs on its own thread for the life of the connection; encode jobs are submitted
    without blocking so this thread keeps receiving new frames while earlier ones are
    still being encoded. Always puts a sentinel `None` on *pending* on exit so the
    companion forwarder thread knows to stop.
    """
    try:
        while True:
            jpeg_bytes = recv_frame(client_conn, cfg.mux_cfg)
            if jpeg_bytes is None:
                break

            sync()
            t_start = time.perf_counter()

            encode_future = bridge.encode_from_jpeg(
                jpeg_bytes,
                client_id=client_id,
                compression_level=runtime_compression_level,
            )
            pending.put((encode_future, t_start))
    except (ConnectionError, OSError, ValueError) as exc:
        log_json(logger, {
            "event": "client_connection_error",
            "client": client_id,
            "error": str(exc),
        })
    finally:
        pending.put(None)


def _image_forwarder(
    client_conn,
    *,
    encoder: Encoder,
    decoder_sock,
    send_lock: threading.Lock,
    client_id: str,
    fps: float,
    pending: "queue.Queue[tuple[Future[EncodeResult], float] | None]",
    last_img_id: list[int],
    logger,
) -> None:
    """Drain encode futures from *pending* in submission order and forward each to the decoder.

    Runs on its own thread for the life of the connection; blocks on each future's
    `.result()` only once it's up next to forward, so a slow encode never stalls the
    companion dispatch thread's frame reception. Stops on the sentinel `None` put by
    the dispatcher, or on the first encode failure (logged here and surfaced to the
    dispatcher by shutting down *client_conn*).
    """
    while True:
        item = pending.get()
        if item is None:
            return
        encode_future, t_start = item
        try:
            encode_result = encode_future.result()
        except BaseException as exc:  # noqa: BLE001 - stop the receive loop via client_conn.shutdown
            log_json(logger, {
                "event": "client_forward_error",
                "client": client_id,
                "error": str(exc),
            })
            try:
                client_conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            return

        last_img_id[0] = encode_result.img_data.img_idx

        log_json(logger, {
            "event": "image_processed",
            "client": client_id,
            "img_id": last_img_id[0],
        })

        with send_lock:
            encoder.send_frame(decoder_sock, encode_result.payload)

        log_json(logger, {
            "event": "client_frame_forwarded",
            "client": client_id,
            "frame_id": last_img_id[0],
        })

        sleep_ms = _sleep_to_enforce_fps(t_start, fps)
        if sleep_ms > 0:
            log_json(logger, {
                "event": "frame_rate_limited",
                "client": client_id,
                "frame_id": last_img_id[0],
                "target_fps": fps,
                "sleep_ms": round(sleep_ms, 2),
            })


def _handle_client(
    client_conn,
    *,
    cfg,
    bridge: SemanticCodecBridge,
    encoder: Encoder,
    decoder_sock,
    send_lock: threading.Lock,
    runtime_compression_level: int,
    fps: float,
    logger,
) -> None:
    """Receive length-prefixed JPEG frames from one client, encode, and forward to the decoder.

    Runs on its own thread for the life of the connection so several clients can stream
    concurrently; every decoded frame is forwarded to the shared decoder socket, guarded
    by *send_lock* so frames from different clients are never interleaved on the wire.
    A dedicated dispatch thread (`_image_dispatcher`) submits encode jobs without blocking
    so frame reception never stalls on an in-flight encode, and a dedicated forwarding
    thread (`_image_forwarder`) drains the resulting futures in submission order, blocking
    on each one's `.result()` only once it's up next to forward, so a slow encode never
    stalls reception.
    """
    client_id = str(getattr(cfg.app, "client_id", "default"))
    # Single-element box so the forwarder thread can report the last processed img_id
    # back to this function for the final client_disconnected log.
    last_img_id = [0]
    # Bounded so a slow/stuck forwarder applies backpressure to the dispatch thread
    # instead of letting in-flight encode futures grow without limit.
    _MAX_PENDING = 200
    pending: "queue.Queue[tuple[Future[EncodeResult], float] | None]" = queue.Queue(maxsize=_MAX_PENDING)

    forwarder = threading.Thread(
        target=_image_forwarder,
        kwargs=dict(
            client_conn=client_conn,
            encoder=encoder,
            decoder_sock=decoder_sock,
            send_lock=send_lock,
            client_id=client_id,
            fps=fps,
            pending=pending,
            last_img_id=last_img_id,
            logger=logger,
        ),
        daemon=True,
        name=f"encoder-forward-{client_id}",
    )
    forwarder.start()

    dispatcher = threading.Thread(
        target=_image_dispatcher,
        kwargs=dict(
            client_conn=client_conn,
            cfg=cfg,
            bridge=bridge,
            client_id=client_id,
            runtime_compression_level=runtime_compression_level,
            pending=pending,
            logger=logger,
        ),
        daemon=True,
        name=f"encoder-dispatch-{client_id}",
    )
    dispatcher.start()
    dispatcher.join()

    forwarder.join()
    client_conn.close()
    log_json(logger, {
        "event": "client_disconnected",
        "client": client_id,
        "frames_processed": last_img_id[0],
    })


def run_semantic_encoder(
    cfg,
    decoder_host: str = "localhost",
    decoder_port: int = 5000,
    fps: float = 1.0,
    *,
    skip_obj_detection: bool = False,
    listen_host: str = "0.0.0.0",  # nosec B104 - service is designed to run in a container and accept any client; overridable via caller
    listen_port: int = 5000,
    bridge: SemanticCodecBridge = None,
) -> None:
    """
    Run the semantic compression encoder as a multi-client TCP server, forwarding to a decoder over TCP.

    High-level flow:
            1) Connect to the decoder (retry until available).
            2) Listen for any number of client connections on (listen_host, listen_port);
               each connection is handled on its own thread.
            3) Per received frame (length-prefixed JPEG bytes):
               - decode via SemanticCodecBridge.encode_from_jpeg (YOLO + compression + mux)
               - send the resulting payload over the shared decoder socket

    :param cfg:         Configuration object
    :param decoder_host: Decoder host (hostname or IP address)
    :param decoder_port: Decoder TCP port.
    :param fps:         Target per-client send rate (frames per second); 0 disables throttling.
    :param listen_host: Address to listen on for incoming client connections.
    :param listen_port: Port to listen on for incoming client connections.
    :param bridge:      Pre-built SemanticCodecBridge (e.g. shared with the REST service side
                        by the caller so both transports use the same encoder model instance
                        and the same adaptive pipeline-manager state). Required -- construct
                        one shared instance and pass it in rather than letting it default to None.
    :return: n/a (runs until interrupted)
    """

    fps = float(fps)
    if not math.isfinite(fps):
        raise ValueError(f"fps must be a finite number, got {fps}")

    logger = setup_logger(
        name="encoder",
        cfg=cfg,
    )

    sock = None

    runtime_compression_level = int(getattr(getattr(cfg, "pipeline_manager", None), "compression_level", 1))
    if runtime_compression_level not in (1, 2):
        raise ValueError(
            f"pipeline_manager.compression_level must be 1 or 2, got {runtime_compression_level}"
        )

    if bridge is None:
        raise ValueError(
            "run_semantic_encoder requires a shared SemanticCodecBridge instance; "
            "construct one and pass it in instead of letting it default to None"
        )

    # Forced skip sources are carried through pipeline_ctx.skip_obj_detection.
    # Note: level != 2 disables object detection, but fast-path bg still follows
    # queue-tier decisions inside EncoderPipelineManager.
    global_skip_obj_detection = (
        skip_obj_detection
        or bool(getattr(bridge.encoder, "skip_obj_detection", False))
        or runtime_compression_level != 2
    )

    healthcheck.TCP_READY = True
    send_lock = threading.Lock()

    try:
        # connect to decoder only after local validation/model initialization succeeds.
        sock = connect_with_retry(logger, decoder_host, decoder_port)

        # Handshake: announce this encoder's stable identity so the decoder can key its
        # per-client frame sequencing on it instead of this socket's (ephemeral) address,
        # which would otherwise change on every reconnect.
        client_id = str(getattr(cfg.app, "client_id", "default"))
        bridge.encoder.send_frame(sock, client_id.encode("utf-8"))

        log_json(logger, {
            "event": "encoder_started",
            "host": decoder_host,
            "port": decoder_port,
            "listen_host": listen_host,
            "listen_port": listen_port,
            "fps": fps,
            "compression_level": runtime_compression_level,
            "skip_obj_detection": global_skip_obj_detection,
            "output_dir": str(cfg.io.output_dir),
            "client_id": client_id,
        })

        # ------------------------------
        # MULTI-CLIENT TCP SOURCE
        # Any number of clients may connect and stream length-prefixed JPEG frames
        # concurrently; each connection is handled on its own thread, and every
        # decoded frame is encoded and forwarded to the decoder over the shared
        # egress socket (guarded by send_lock).
        # ------------------------------
        for conn, addr in accept_clients(logger, listen_host, listen_port):
            threading.Thread(
                target=_handle_client,
                args=(conn,),
                kwargs=dict(
                    cfg=cfg,
                    bridge=bridge,
                    encoder=bridge.encoder,
                    decoder_sock=sock,
                    send_lock=send_lock,
                    runtime_compression_level=runtime_compression_level,
                    fps=fps,
                    logger=logger,
                ),
                daemon=True,
                name=f"encoder-client-{client_id}",
            ).start()

    except Exception as exc:
        # Log error as JSON, then re-raise so the caller/system can handle it.
        log_json(logger, {
            "event": "encoder_failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
        })
        raise

    finally:
        if sock is not None:
            sock.close()
            log_json(logger, {"event": "socket_closed"})

