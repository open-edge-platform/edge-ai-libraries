# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Live-stream media recording.

Embeddings alone are not enough for a search experience: a retrieval hit on a
live frame needs something a user can actually look at. This module records a
running stream into

* fixed-length MP4 **segments** (``MM_DATAPREP_LIVE_SEGMENT_DURATION_SECONDS``,
  default 10s), used for playback, and
* sampled **JPEG frames** (every ``MM_DATAPREP_FRAME_INTERVAL``-th frame), used
  for thumbnails and previews,

both written to the configured storage backend under
``<LIVE_STREAM_BUCKET>/<stream_id>/``.

Segments are **remuxed**, not re-encoded: packets are copied straight from the
RTSP source into an MP4 container, which keeps CPU cost close to zero. Frame
sampling does require decoding, so it can be switched off with
``MM_DATAPREP_LIVE_STORE_FRAMES=false`` for a pure remux (near-zero CPU)
recording path.

The recorder holds its own connection to the camera, independent of the
embedding pipeline's. That isolation is deliberate: a recording failure must not
stop embedding generation, and vice versa. The two paths stay in agreement about
*which* segment covers a given instant through the wall-clock bucketing in
:mod:`src.core.live.segments` — no shared state is required.
"""

from __future__ import annotations

import io
import threading
import time
from bisect import bisect_right
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import List, Optional

from src.common import logger, sanitize_for_log, settings
from src.core.live.segments import frame_object_name, segment_object_name, segment_start
from src.core.live.urls import redact_stream_url

#: PyAV open options for an RTSP source: TCP transport with bounded timeouts so
#: a dead camera surfaces as an error instead of blocking forever.
RTSP_OPEN_OPTIONS = {
    "rtsp_transport": "tcp",
    "rtsp_flags": "prefer_tcp",
    "stimeout": "10000000",
    "max_delay": "500000",
    "analyzeduration": "10000000",
    "probesize": "10000000",
}


@dataclass
class RecorderStats:
    """Counters reported back to the owning stream worker."""

    segments_stored: int = 0
    frames_stored: int = 0


class LiveMediaRecorder:
    """Records one live stream into storage until asked to stop.

    The recorder is intentionally forgiving: any failure to record is logged and
    retried on the next segment rather than propagated, because losing playback
    media is far less severe than losing the embedding stream.
    """

    def __init__(
        self,
        *,
        stream_id: str,
        stream_url: str,
        bucket_name: str,
        shutdown_event: threading.Event,
        segment_duration_seconds: Optional[int] = None,
        frame_interval: Optional[int] = None,
        store_segments: Optional[bool] = None,
        store_frames: Optional[bool] = None,
        frame_upload_workers: Optional[int] = None,
        storage=None,
    ) -> None:
        self.stream_id = stream_id
        self.stream_url = stream_url
        self.bucket_name = bucket_name
        self.shutdown_event = shutdown_event
        self.segment_duration = int(
            segment_duration_seconds or settings.LIVE_SEGMENT_DURATION_SECONDS
        )
        self.frame_interval = int(frame_interval or settings.FRAME_INTERVAL)
        self.store_segments = (
            settings.LIVE_STORE_SEGMENTS if store_segments is None else store_segments
        )
        self.store_frames = settings.LIVE_STORE_FRAMES if store_frames is None else store_frames
        self.frame_upload_workers = max(
            1,
            int(
                settings.LIVE_FRAME_UPLOAD_WORKERS
                if frame_upload_workers is None
                else frame_upload_workers
            ),
        )
        self.stats = RecorderStats()
        self._stats_lock = threading.Lock()
        self._storage = storage
        self._thread: Optional[threading.Thread] = None
        self._redacted_url = redact_stream_url(stream_url)
        self._bucket_ready = False
        self._bucket_lock = threading.Lock()
        # Frame JPEGs are uploaded through a bounded pool so the decode loop is
        # not blocked on per-object storage latency (object stores have no
        # multi-object batch PUT; each frame is its own request). ``_frame_pool``
        # and ``_frame_inflight`` are created lazily when recording starts.
        self._frame_pool: Optional[ThreadPoolExecutor] = None
        self._frame_inflight: Optional[threading.BoundedSemaphore] = None
        # Actual start epochs of the segments this recorder has opened. Segments
        # are cut on keyframes, so with a GOP longer than ``segment_duration`` a
        # segment can span several time buckets. The embedding pipeline resolves
        # a frame to the segment that *covers* it via ``resolve_segment_start``
        # rather than guessing a bucket, which would reference a file that was
        # never written (404 on playback).
        self._segment_starts: List[float] = []
        self._segment_lock = threading.Lock()

    # -- lifecycle ---------------------------------------------------------
    @property
    def enabled(self) -> bool:
        """True when the recorder has anything to do."""
        return bool(self.store_segments or self.store_frames)

    def start(self) -> None:
        """Start recording on a background daemon thread."""
        if not self.enabled:
            logger.info(
                "Live media recording disabled for stream %s; embeddings only",
                sanitize_for_log(self.stream_id, max_length=64),
            )
            return
        self._thread = threading.Thread(
            target=self.run,
            name=f"live-recorder-{self.stream_id[:8]}",
            daemon=True,
        )
        self._thread.start()

    def join(self, timeout: Optional[float] = None) -> None:
        """Wait for the recording thread to exit."""
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    # -- segment boundary tracking -----------------------------------------
    def _record_segment_start(self, start_epoch: float) -> None:
        """Remember that a segment was opened at ``start_epoch``."""
        with self._segment_lock:
            if not self._segment_starts or start_epoch > self._segment_starts[-1]:
                self._segment_starts.append(float(start_epoch))

    def resolve_segment_start(self, epoch: float) -> Optional[float]:
        """Start epoch of the recorded segment that covers ``epoch``.

        Returns the greatest segment start at or before ``epoch`` (the segment
        actually containing that instant), or ``None`` if no segment has been
        opened yet. Callers fall back to time-bucketing in that case.
        """
        with self._segment_lock:
            if not self._segment_starts:
                return None
            idx = bisect_right(self._segment_starts, float(epoch))
            if idx == 0:
                # Frame predates the first recorded segment; best-effort anchor
                # to the earliest one rather than a bucket that was never stored.
                return self._segment_starts[0]
            return self._segment_starts[idx - 1]

    # -- storage helpers ---------------------------------------------------
    def _get_storage(self):
        """Resolve the storage backend lazily so construction stays cheap."""
        if self._storage is None:
            from src.core.storage import get_storage

            self._storage = get_storage()
        return self._storage

    def _put_object(self, object_name: str, payload: bytes) -> bool:
        """Write ``payload`` to storage, returning success."""
        try:
            storage = self._get_storage()
            if not self._bucket_ready:
                # Frame uploads now run on a pool, so this can be entered by
                # several threads at once (plus the record-loop thread writing
                # segments). Serialise the one-time bucket setup so the bucket is
                # created and made public exactly once, with no racing creates.
                with self._bucket_lock:
                    if not self._bucket_ready:
                        storage.ensure_bucket_exists(self.bucket_name)
                        # Recorded segments/frames are played back by the browser
                        # directly from the object store (via the gateway's
                        # /datastore proxy), so the live-stream bucket needs the
                        # same anonymous read policy as the uploaded-video bucket,
                        # or MinIO returns 403.
                        storage.ensure_public_read(self.bucket_name)
                        self._bucket_ready = True
            storage.upload_video(self.bucket_name, object_name, io.BytesIO(payload), len(payload))
            return True
        except Exception as exc:  # noqa: BLE001 - media loss must not kill ingestion
            logger.error(
                "Failed to store live media object %s: %s",
                sanitize_for_log(object_name, max_length=256),
                sanitize_for_log(str(exc), max_length=256),
            )
            return False

    # -- frame upload pool -------------------------------------------------
    def _ensure_frame_pool(self) -> None:
        """Lazily create the bounded frame-upload pool."""
        if self._frame_pool is None:
            self._frame_pool = ThreadPoolExecutor(
                max_workers=self.frame_upload_workers,
                thread_name_prefix=f"live-frameup-{self.stream_id[:8]}",
            )
            # Bound in-flight uploads (queued + running) to apply backpressure:
            # when storage cannot keep up, the decode loop blocks on acquire
            # instead of accumulating unbounded JPEG payloads in memory.
            self._frame_inflight = threading.BoundedSemaphore(self.frame_upload_workers * 2)

    def _shutdown_frame_pool(self) -> None:
        """Drain and dispose of the frame-upload pool, waiting for in-flight PUTs."""
        pool = self._frame_pool
        if pool is None:
            return
        self._frame_pool = None
        self._frame_inflight = None
        try:
            pool.shutdown(wait=True)
        except Exception:  # noqa: BLE001 - best-effort cleanup
            logger.debug("Error shutting down live frame-upload pool", exc_info=True)

    def _submit_frame_upload(self, object_name: str, payload: bytes) -> None:
        """Hand a JPEG payload to the pool, blocking only when it is saturated."""
        self._ensure_frame_pool()
        semaphore = self._frame_inflight
        pool = self._frame_pool
        if semaphore is None or pool is None:  # pragma: no cover - defensive
            return
        semaphore.acquire()
        try:
            pool.submit(self._upload_frame_task, object_name, payload, semaphore)
        except RuntimeError:
            # Pool already shut down (stream stopping); release and drop.
            semaphore.release()

    def _upload_frame_task(
        self, object_name: str, payload: bytes, semaphore: threading.BoundedSemaphore
    ) -> None:
        """Pool worker: upload one frame JPEG and update stats."""
        try:
            if self._put_object(object_name, payload):
                with self._stats_lock:
                    self.stats.frames_stored += 1
        finally:
            semaphore.release()

    # -- recording ---------------------------------------------------------
    def run(self) -> None:
        """Record until the shutdown event is set or the source ends."""
        import av

        logger.info(
            "Recording live stream %s (%s): segments=%s frames=%s interval=%ds",
            sanitize_for_log(self.stream_id, max_length=64),
            sanitize_for_log(self._redacted_url, max_length=256),
            self.store_segments,
            self.store_frames,
            self.segment_duration,
        )

        container = None
        try:
            container = av.open(self.stream_url, options=RTSP_OPEN_OPTIONS)
            in_stream = container.streams.video[0]
            self._record_loop(av, container, in_stream)
        except Exception as exc:  # noqa: BLE001 - recorder failures are non-fatal
            logger.error(
                "Live recording stopped for stream %s: %s",
                sanitize_for_log(self.stream_id, max_length=64),
                sanitize_for_log(str(exc), max_length=256),
            )
        finally:
            if container is not None:
                try:
                    container.close()
                except Exception:  # noqa: BLE001 - best-effort cleanup
                    logger.debug("Error closing recorder container", exc_info=True)
            # Wait for any frame uploads still in flight before the thread exits.
            self._shutdown_frame_pool()

    @staticmethod
    def _add_remux_stream(out_container, in_stream):
        """Add an output stream that mirrors ``in_stream`` for packet remuxing.

        PyAV renamed this operation: modern versions expose
        ``add_stream_from_template``, older ones only accept
        ``add_stream(template=...)``. Both are tried so the recorder works
        across the versions this service may be built against.
        """
        adder = getattr(out_container, "add_stream_from_template", None)
        if adder is not None:
            return adder(in_stream)
        return out_container.add_stream(template=in_stream)

    def _record_loop(self, av, container, in_stream) -> None:
        """Demux the source, rolling over to a new segment every N seconds."""
        buffer: Optional[io.BytesIO] = None
        out_container = None
        out_stream = None
        current_start: Optional[float] = None
        # Decode-timestamp of the first packet written to the current segment.
        # Every segment is rebased to start at 0 (see the mux block below).
        segment_base_dts: Optional[int] = None
        frame_counter = 0

        def flush() -> None:
            """Close the open segment and push it to storage."""
            nonlocal buffer, out_container, out_stream, current_start
            if out_container is None or buffer is None or current_start is None:
                return
            try:
                out_container.close()
                payload = buffer.getvalue()
                if payload and self._put_object(
                    segment_object_name(self.stream_id, current_start), payload
                ):
                    self.stats.segments_stored += 1
            except Exception as exc:  # noqa: BLE001 - never fail the stream on a segment
                logger.error(
                    "Failed to finalize live segment for stream %s: %s",
                    sanitize_for_log(self.stream_id, max_length=64),
                    sanitize_for_log(str(exc), max_length=256),
                )
            finally:
                buffer = None
                out_container = None
                out_stream = None
                current_start = None

        try:
            for packet in container.demux(in_stream):
                if self.shutdown_event.is_set():
                    break
                if packet.dts is None:
                    continue

                # Sample frames before muxing: writing a packet to the output
                # container rebinds ``packet.stream``, after which the packet can
                # no longer be decoded.
                if self.store_frames:
                    frame_counter = self._sample_frames(packet, frame_counter)

                if self.store_segments:
                    bucket_start = segment_start(time.time(), self.segment_duration)
                    if current_start is None or bucket_start != current_start:
                        # Only cut on a keyframe: a segment that starts mid-GOP is
                        # not independently decodable and will not play back.
                        if current_start is None or packet.is_keyframe:
                            flush()
                            buffer = io.BytesIO()
                            try:
                                out_container = av.open(
                                    buffer,
                                    mode="w",
                                    format="mp4",
                                    # NOTE: do NOT enable movflags +faststart
                                    # here. The segment is muxed to an in-memory
                                    # BytesIO (no real filename); faststart runs
                                    # a second pass that reopens the output by
                                    # name, which fails with "No such file or
                                    # directory: '<none>'" and loses every
                                    # segment. Correct duration comes from the
                                    # per-segment DTS/PTS rebase below, not from
                                    # faststart; small segments download fully so
                                    # a trailing moov atom is fine for playback.
                                )
                                out_stream = self._add_remux_stream(out_container, in_stream)
                                current_start = bucket_start
                                segment_base_dts = None
                                self._record_segment_start(bucket_start)
                            except Exception as exc:  # noqa: BLE001
                                logger.warning(
                                    "Live stream %s cannot be remuxed to MP4 (%s); "
                                    "segment recording disabled for this session",
                                    sanitize_for_log(self.stream_id, max_length=64),
                                    sanitize_for_log(str(exc), max_length=256),
                                )
                                self.store_segments = False
                                buffer = None
                                out_container = None
                                if not self.store_frames:
                                    return

                    if out_container is not None and out_stream is not None:
                        try:
                            # Rebase every segment to start at DTS 0. Packets
                            # arrive carrying the source's running timestamps, so
                            # a segment cut 40s into the stream would otherwise
                            # open at DTS ~40s. Browsers then read a moov whose
                            # duration spans that offset and only converge on the
                            # true length after decoding to the end (the player's
                            # end time visibly jumps on play). Subtracting the
                            # first packet's DTS makes the container duration
                            # exact and keeps seeking accurate.
                            if segment_base_dts is None:
                                segment_base_dts = packet.dts
                            packet.stream = out_stream
                            if packet.dts is not None:
                                packet.dts = packet.dts - segment_base_dts
                            if packet.pts is not None:
                                packet.pts = packet.pts - segment_base_dts
                            out_container.mux(packet)
                        except Exception as exc:  # noqa: BLE001
                            logger.debug(
                                "Dropped a packet while writing a live segment: %s",
                                sanitize_for_log(str(exc), max_length=128),
                            )

        finally:
            flush()

    def _sample_frames(self, packet, frame_counter: int) -> int:
        """Decode ``packet`` and store every ``frame_interval``-th frame."""
        try:
            frames = packet.decode()
        except Exception:  # noqa: BLE001 - a bad packet must not stop recording
            return frame_counter

        for frame in frames:
            if self.shutdown_event.is_set():
                break
            if frame_counter % self.frame_interval == 0:
                self._store_frame(frame, frame_counter)
            frame_counter += 1
        return frame_counter

    def _store_frame(self, frame, frame_number: int) -> None:
        """Encode one decoded frame as JPEG and queue it for upload.

        Encoding happens on the recording thread, but the upload is handed to a
        bounded pool so per-object storage latency does not stall decoding.
        """
        try:
            image = frame.to_image()
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=85)
            object_name = frame_object_name(
                self.stream_id,
                segment_start(time.time(), self.segment_duration),
                frame_number,
            )
            self._submit_frame_upload(object_name, buffer.getvalue())
        except Exception as exc:  # noqa: BLE001 - frame loss is non-fatal
            logger.debug(
                "Failed to store a sampled live frame: %s",
                sanitize_for_log(str(exc), max_length=128),
            )
