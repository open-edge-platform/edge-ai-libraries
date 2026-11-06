# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: image_feeder/feeder.py
Description: background thread that releases images into a queue at a configured
data rate, fully decoupled from encoder processing time. Used by the TCP batch
encoder runner (semantic_img_comp.encoder.runner).
"""

import math
import os
import queue
import socket
import struct
import threading
import time
from typing import Callable, Iterator, NamedTuple, Optional

import httpx

from semantic_img_comp import healthcheck
from semantic_img_comp.net.connection import connect_with_retry
from semantic_img_comp.utils.logging_helpers import log_json

# Sentinel placed on the queue by the feeder thread to signal end of stream.
FEEDER_DONE = object()


class ImageFeederHandle(NamedTuple):
    """Handles returned by start_image_feeder() for driving the encoder's image loop."""
    thread: threading.Thread
    queue: "queue.Queue[object]"
    duration_stop_event: threading.Event
    run_duration_sec: Optional[float]
    drop_queued_images: Callable[..., int]
    iter_queue: Callable[[], Iterator[object]]

    def is_stopped(
        self,
        sock: "socket.socket | None",
        logger,
        frame_id: int,
    ) -> bool:
        """If the feeder's duration limit has fired, drop queued images, close *sock*, and signal the caller to stop.

        Returns should_stop; the caller remains responsible for setting its own
        sock reference to None once this returns True.
        """
        if not self.duration_stop_event.is_set():
            return False

        dropped_images = self.drop_queued_images(include_current_item=True)
        log_json(logger, {
            "event": "duration_limit_forced_stop",
            "run_duration_sec": self.run_duration_sec,
            "dropped_images": dropped_images,
            "frame_id": frame_id,
        })
        if sock is not None:
            sock.close()
            log_json(logger, {
                "event": "socket_closed",
                "reason": "run_duration_limit",
            })
        return True

    def feed_to_http(
        self,
        encoder_url: str,
        stream_id: str,
        logger,
        *,
        client: Optional[httpx.Client] = None,
    ) -> int:
        """Drain this feeder's out-queue (via iter_queue()) and POST each image to the encoder's REST stream *stream_id*.
        """
        while not healthcheck.HTTP_READY:
            time.sleep(1)

        http_client = client if client is not None else httpx.Client(timeout=30.0)
        try:
            http_client.put(f"{encoder_url}/v1/streams/{stream_id}")

            for img_id, path in enumerate(self.iter_queue(), start=1):
                if self.is_stopped(None, logger, img_id):
                    break

                jpeg_bytes = path.read_bytes() if hasattr(path, "read_bytes") else open(path, "rb").read()
                headers = {"Content-Type": "image/jpeg", "X-Client-Sent-At": f"{time.time():.6f}"}
                request = http_client.post(
                    f"{encoder_url}/v1/streams/{stream_id}/frames",
                    params={"img_id": img_id},
                    content=jpeg_bytes,
                    headers=headers,
                )
                request.raise_for_status()
    
        finally:
            if client is None:
                http_client.close()

    def feed_to_tcp(
        self,
        host: str,
        port: int,
        cfg,
        logger,
        *,
        sock: "socket.socket | None" = None,
    ) -> None:
        """Drain this feeder's out-queue (via iter_queue()) and stream each image to the
        multi-client TCP socket exposed by encoder.runner.run_semantic_encoder (i.e. *host*/*port*
        are that server's listen_host/listen_port). Frames are length-prefixed per cfg.mux_cfg,
        matching the wire format decoded by decoder.demux.recv_frame on the server side.
        """
        while not healthcheck.TCP_READY:
            time.sleep(1)

        mux_cfg = cfg.mux_cfg
        fmt_payload_len = mux_cfg.fmt(mux_cfg.fmt_payload_len)
        tcp_sock = sock if sock is not None else connect_with_retry(logger, host, port)
        try:
            for img_id, path in enumerate(self.iter_queue(), start=1):
                if self.is_stopped(tcp_sock, logger, img_id):
                    tcp_sock = None
                    break

                jpeg_bytes = path.read_bytes() if hasattr(path, "read_bytes") else open(path, "rb").read()
                header = struct.pack(fmt_payload_len, len(jpeg_bytes))
                tcp_sock.sendall(header)
                tcp_sock.sendall(jpeg_bytes)

        finally:
            if sock is None and tcp_sock is not None:
                tcp_sock.close()


def feed_images(
    image_paths: list,
    out_queue: "queue.Queue[object]",
    target_mbps: float | None,
    run_duration_sec: float | None,
    log_feeder_events: bool,
    duration_stop_event: threading.Event,
    logger,
    catalog_random_seed: int | None = None,
) -> None:
    """Feed image paths into *out_queue* at a cadence controlled by *target_mbps*.

    Runs in a dedicated background thread so that the image-arrival rate is
    completely independent of encoder processing time.  If the encoder is
    slower than the configured rate, paths accumulate in the queue (backlog).
    If the encoder is faster, it blocks on the queue until the next image
    is released.

    When *run_duration_sec* is set, the feeder stops releasing new images once
    that many wall-clock seconds have elapsed since the feeder started, even if
    there are more images remaining.  The encoder loop drains whatever is
    already in the queue before finishing.

    When *target_mbps* is None or non-positive, images are enqueued immediately
    with no throttling.
    """
    rate_active = (
        target_mbps is not None
        and math.isfinite(target_mbps)
        and target_mbps > 0
    )
    duration_active = (
        run_duration_sec is not None
        and math.isfinite(run_duration_sec)
        and run_duration_sec > 0
    )

    feeder_start = time.perf_counter()
    next_release_at = feeder_start
    images_released = 0
    total_input_bytes_enqueued = 0

    def _duration_exceeded() -> bool:
        return duration_active and (time.perf_counter() - feeder_start) >= run_duration_sec

    ordered_paths = list(image_paths)

    try:
        for feed_index, path in enumerate(ordered_paths, start=1):
            # Stop early if the configured run duration has elapsed.
            if _duration_exceeded():
                duration_stop_event.set()
                log_json(logger, {
                    "event": "feeder_duration_limit_reached",
                    "run_duration_sec": run_duration_sec,
                    "images_released": images_released,
                    "total_input_bytes_enqueued": total_input_bytes_enqueued,
                })
                return

            file_bytes = os.path.getsize(path)

            if rate_active:
                now = time.perf_counter()
                wait = next_release_at - now
                if wait > 0:
                    time.sleep(wait)
                    # Re-check duration after waking from sleep.
                    if _duration_exceeded():
                        duration_stop_event.set()
                        log_json(logger, {
                            "event": "feeder_duration_limit_reached",
                            "run_duration_sec": run_duration_sec,
                            "images_released": images_released,
                            "total_input_bytes_enqueued": total_input_bytes_enqueued,
                        })
                        return
                    if log_feeder_events:
                        log_json(logger, {
                            "event": "feeder_rate_limited",
                            "path": str(path),
                            "feed_index": feed_index,
                            "catalog_random_seed": catalog_random_seed,
                            "target_mbps": target_mbps,
                            "input_img_bytes": file_bytes,
                            "sleep_ms": round(wait * 1000.0, 2),
                        })

                # Advance deadline by this image's transmission time at target rate.
                next_release_at = time.perf_counter() + (file_bytes * 8) / (target_mbps * 1e6)

            out_queue.put(path)
            images_released += 1
            total_input_bytes_enqueued += file_bytes
            if log_feeder_events:
                log_json(logger, {
                    "event": "feeder_enqueued",
                    "path": str(path),
                    "feed_index": feed_index,
                    "catalog_random_seed": catalog_random_seed,
                    "input_img_bytes": file_bytes,
                    "images_released": images_released,
                    "total_input_bytes_enqueued": total_input_bytes_enqueued,
                    "queue_backlog": out_queue.qsize(),
                })

        log_json(logger, {
            "event": "feeder_enqueue_completed",
            "images_released": images_released,
            "total_input_bytes_enqueued": total_input_bytes_enqueued,
        })
    finally:
        # Always signal completion even if an exception occurs.
        out_queue.put(FEEDER_DONE)


def start_image_feeder(
    image_paths: list,
    cfg,
    logger,
    catalog_random_seed: int | None = None,
) -> ImageFeederHandle:
    """Start the background feeder thread and return the queue/helpers the encoder loop drives."""
    target_mbps = getattr(cfg.image_feeder, "target_input_rate_mbps", None)
    run_duration_sec = getattr(cfg.image_feeder, "run_duration_sec", None)
    log_feeder_events = bool(getattr(cfg.image_feeder, "log_feeder_events", False))
    duration_stop_event = threading.Event()
    image_queue: queue.Queue = queue.Queue()
    feeder_thread = threading.Thread(
        target=feed_images,
        args=(
            image_paths,
            image_queue,
            target_mbps,
            run_duration_sec,
            log_feeder_events,
            duration_stop_event,
            logger,
            catalog_random_seed,
        ),
        daemon=True,
        name="image-feeder",
    )
    feeder_thread.start()

    def drop_queued_images(*, include_current_item: bool = False) -> int:
        dropped = 1 if include_current_item else 0
        while True:
            try:
                item = image_queue.get_nowait()
            except queue.Empty:
                break
            if item is FEEDER_DONE:
                continue
            dropped += 1
        return dropped

    def iter_queue():
        while True:
            item = image_queue.get()
            if item is FEEDER_DONE:
                break
            yield item

    return ImageFeederHandle(
        thread=feeder_thread,
        queue=image_queue,
        duration_stop_event=duration_stop_event,
        run_duration_sec=run_duration_sec,
        drop_queued_images=drop_queued_images,
        iter_queue=iter_queue,
    )

