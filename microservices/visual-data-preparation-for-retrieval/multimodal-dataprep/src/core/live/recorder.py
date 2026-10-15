# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Live-stream segment recording.

Embeddings alone are not enough for a search experience: a retrieval hit on a
live frame needs something a user can actually look at. This module records a
running stream into fixed-length MP4 **segments**
(``MM_DATAPREP_LIVE_SEGMENT_DURATION_SECONDS``, default 10s) written to the
configured storage backend under ``<LIVE_STREAM_BUCKET>/<stream_id>/segments/``.

Segments are **remuxed**, not re-encoded: packets are copied straight from the
source into an MP4 container, which keeps CPU cost close to zero.

Single decode connection
------------------------
This is a *sink*, not a self-contained recorder: it does **not** open its own
connection to the camera. Instead it implements
:class:`src.core.embedding.decoder.PacketSink` and receives every demuxed packet
from the embedding pipeline's single RTSP connection via :meth:`submit`. The
packets arrive already decoded for embedding, so the sink may take ownership of
them (muxing rebinds ``packet.stream``).

Why one connection? The embedding and the recorded segment must agree, frame for
frame, on *where* a given moment is. Two independent RTSP connections have
independent jitter buffers and GOP phase, so the same visual frame is received
seconds apart on each -- which showed up as a variable multi-second drift
between a search hit's timestamp and the moment that actually played back.
Sharing one connection makes the embedding's presentation timestamp
(``media_pts``) and the segment's packet timestamps come from the *same* clock,
so the playback seek (``media_pts - segment_first_pts``) is exact by
construction. See :meth:`resolve_segment`.

The sink is intentionally forgiving: any failure to record is logged and retried
on the next segment rather than propagated, because losing playback media is far
less severe than losing the embedding stream. ``submit`` never blocks the decode
loop -- a saturated queue drops packets (degrading the current segment) rather
than stalling embedding.
"""

from __future__ import annotations

import io
import queue
import threading
import time
from bisect import bisect_right
from dataclasses import dataclass
from typing import List, Optional, Tuple

from src.common import logger, sanitize_for_log, settings
from src.core.live.segments import segment_object_name, segment_start
from src.core.live.urls import redact_stream_url

#: Sentinel enqueued by :meth:`SegmentMuxSink.close` to flush and exit the drain
#: loop cleanly.
_CLOSE_SENTINEL = object()


@dataclass
class RecorderStats:
    """Counters reported back to the owning stream worker."""

    segments_stored: int = 0


class SegmentMuxSink:
    """Remuxes packets teed off the live decode loop into MP4 segments.

    One sink serves one ingestion session. The owning worker calls
    :meth:`start` before running the pipeline, passes the sink to the pipeline as
    its ``packet_sink`` (the decode loop then calls :meth:`submit` for every
    packet), and calls :meth:`close` once the session ends to flush the final
    segment.
    """

    def __init__(
        self,
        *,
        stream_id: str,
        stream_url: str,
        bucket_name: str,
        shutdown_event: threading.Event,
        segment_duration_seconds: Optional[int] = None,
        store_segments: Optional[bool] = None,
        queue_maxsize: Optional[int] = None,
        storage=None,
    ) -> None:
        self.stream_id = stream_id
        self.stream_url = stream_url
        self.bucket_name = bucket_name
        self.shutdown_event = shutdown_event
        self.segment_duration = int(
            segment_duration_seconds or settings.LIVE_SEGMENT_DURATION_SECONDS
        )
        self.store_segments = (
            settings.LIVE_STORE_SEGMENTS if store_segments is None else store_segments
        )
        self.stats = RecorderStats()
        self._stats_lock = threading.Lock()
        self._storage = storage
        self._redacted_url = redact_stream_url(stream_url)
        self._bucket_ready = False
        self._bucket_lock = threading.Lock()

        # Bounded hand-off queue: the decode loop enqueues packets and the drain
        # thread muxes them. Bounded so a stalled storage backend applies
        # backpressure by dropping packets instead of growing memory without
        # limit. Default comfortably covers a few seconds of packets.
        self._queue: queue.Queue = queue.Queue(
            maxsize=int(queue_maxsize or settings.LIVE_SEGMENT_QUEUE_MAXSIZE)
        )
        self._thread: Optional[threading.Thread] = None
        self._dropped_packets = 0

        # Recorded segments as ``(wall_start_epoch, first_packet_pts_seconds)``.
        # ``wall_start_epoch`` names the object / builds the playback URL
        # (unchanged, keeps retention and URLs stable); ``first_packet_pts`` is
        # the shared-clock anchor the embedding pipeline subtracts to get an
        # exact in-segment seek offset. Kept sorted by pts for bisect lookups.
        self._segments: List[Tuple[float, float]] = []
        self._segment_lock = threading.Lock()

    # -- lifecycle ---------------------------------------------------------
    @property
    def enabled(self) -> bool:
        """True when the sink has anything to do."""
        return bool(self.store_segments)

    def start(self) -> None:
        """Start the background drain/mux thread."""
        if not self.enabled:
            logger.info(
                "Live segment recording disabled for stream %s; embeddings only",
                sanitize_for_log(self.stream_id, max_length=64),
            )
            return
        logger.info(
            "Recording live stream %s (%s) into %ds segments",
            sanitize_for_log(self.stream_id, max_length=64),
            sanitize_for_log(self._redacted_url, max_length=256),
            self.segment_duration,
        )
        self._thread = threading.Thread(
            target=self._drain_loop,
            name=f"live-recorder-{self.stream_id[:8]}",
            daemon=True,
        )
        self._thread.start()

    def submit(self, packet, pts_seconds: Optional[float] = None) -> None:
        """Enqueue one demuxed packet for muxing (:class:`PacketSink`).

        Non-blocking by contract: a saturated queue drops the packet (degrading
        the current segment) rather than stalling the decode loop that feeds
        embedding. ``pts_seconds`` is the packet's presentation time computed by
        the decoder from the live stream's time base -- passed in so the drain
        thread never has to touch ``packet.stream`` (which the muxer rebinds).
        """
        if not self.store_segments or self._thread is None:
            return
        try:
            self._queue.put_nowait((packet, pts_seconds))
        except queue.Full:
            self._dropped_packets += 1
            if self._dropped_packets % 100 == 1:
                logger.warning(
                    "Live segment queue saturated for stream %s; dropped %d packets "
                    "(recording degraded, embedding unaffected)",
                    sanitize_for_log(self.stream_id, max_length=64),
                    self._dropped_packets,
                )

    def close(self) -> None:
        """Signal the drain thread to flush the open segment and exit."""
        if self._thread is None:
            return
        try:
            self._queue.put_nowait(_CLOSE_SENTINEL)
        except queue.Full:
            # Make room for the sentinel so shutdown is never wedged by a full
            # queue; one dropped packet at teardown is immaterial.
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(_CLOSE_SENTINEL)
            except queue.Full:  # pragma: no cover - defensive
                pass

    def join(self, timeout: Optional[float] = None) -> None:
        """Wait for the drain thread to exit (flushing the final segment)."""
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    # -- segment lookup ----------------------------------------------------
    def _record_segment(self, wall_start: float, first_pts: Optional[float]) -> None:
        """Remember a segment opened at ``wall_start`` anchored at ``first_pts``."""
        if first_pts is None:
            return
        with self._segment_lock:
            if not self._segments or wall_start > self._segments[-1][0]:
                self._segments.append((float(wall_start), float(first_pts)))

    def resolve_segment(self, frame_pts: Optional[float]) -> Optional[Tuple[float, float]]:
        """Segment covering ``frame_pts``, as ``(wall_start, first_packet_pts)``.

        ``frame_pts`` is a sampled frame's presentation time (``media_pts``), on
        the *same* clock as the muxed packets. Returns the most recent segment
        opened at or before that time, so the pipeline can build the playback URL
        from ``wall_start`` and the exact in-segment seek from
        ``frame_pts - first_packet_pts``. ``None`` until the first segment opens,
        in which case the caller falls back to wall-clock bucketing.
        """
        if frame_pts is None:
            return None
        with self._segment_lock:
            if not self._segments:
                return None
            pts_starts = [pts for _, pts in self._segments]
            idx = bisect_right(pts_starts, float(frame_pts))
            if idx == 0:
                # Frame predates the first recorded segment; anchor to it rather
                # than to a bucket that was never stored.
                return self._segments[0]
            return self._segments[idx - 1]

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
                with self._bucket_lock:
                    if not self._bucket_ready:
                        storage.ensure_bucket_exists(self.bucket_name)
                        # Recorded segments are played back by the browser
                        # directly from the object store (via the gateway's
                        # /datastore proxy), so the live-stream bucket needs the
                        # same anonymous read policy as the uploaded-video
                        # bucket, or MinIO returns 403.
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

    # -- recording ---------------------------------------------------------
    def _drain_loop(self) -> None:
        """Drain the packet queue, rolling over to a new segment every N seconds."""
        import av

        buffer: Optional[io.BytesIO] = None
        out_container = None
        out_stream = None
        current_start: Optional[float] = None
        # Decode-timestamp of the first packet written to the current segment.
        # Every segment is rebased to start at 0 (see the mux block below).
        segment_base_dts: Optional[int] = None

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
                    with self._stats_lock:
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
            while True:
                try:
                    item = self._queue.get(timeout=0.5)
                except queue.Empty:
                    if self.shutdown_event.is_set():
                        break
                    continue

                if item is _CLOSE_SENTINEL:
                    break

                packet, pts_seconds = item
                if self.shutdown_event.is_set():
                    break
                if packet.dts is None:
                    continue

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
                                # NOTE: do NOT enable movflags +faststart here.
                                # The segment is muxed to an in-memory BytesIO (no
                                # real filename); faststart runs a second pass that
                                # reopens the output by name, which fails with "No
                                # such file or directory: '<none>'" and loses every
                                # segment. Correct duration comes from the
                                # per-segment DTS/PTS rebase below.
                            )
                            out_stream = self._add_remux_stream(out_container, packet.stream)
                            current_start = bucket_start
                            segment_base_dts = None
                            self._record_segment(bucket_start, pts_seconds)
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
                            return

                if out_container is not None and out_stream is not None:
                    try:
                        # Rebase every segment to start at DTS 0. Packets carry
                        # the source's running timestamps, so a segment cut 40s
                        # into the stream would otherwise open at DTS ~40s and
                        # browsers would read a moov whose duration spans that
                        # offset. Subtracting the first packet's DTS makes the
                        # container duration exact and keeps seeking accurate.
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
        except Exception as exc:  # noqa: BLE001 - recorder failures are non-fatal
            logger.error(
                "Live recording stopped for stream %s: %s",
                sanitize_for_log(self.stream_id, max_length=64),
                sanitize_for_log(str(exc), max_length=256),
            )
        finally:
            flush()


#: Backward-compatible alias. The class was previously a self-connecting
#: recorder; it is now a packet sink fed by the single decode connection.
LiveMediaRecorder = SegmentMuxSink
