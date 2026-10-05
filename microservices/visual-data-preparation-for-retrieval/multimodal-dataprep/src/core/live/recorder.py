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
from dataclasses import dataclass
from typing import Optional

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
        self.stats = RecorderStats()
        self._storage = storage
        self._thread: Optional[threading.Thread] = None
        self._redacted_url = redact_stream_url(stream_url)

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
            storage.ensure_bucket_exists(self.bucket_name)
            storage.upload_video(self.bucket_name, object_name, io.BytesIO(payload), len(payload))
            return True
        except Exception as exc:  # noqa: BLE001 - media loss must not kill ingestion
            logger.error(
                "Failed to store live media object %s: %s",
                sanitize_for_log(object_name, max_length=256),
                sanitize_for_log(str(exc), max_length=256),
            )
            return False

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
                                out_container = av.open(buffer, mode="w", format="mp4")
                                out_stream = self._add_remux_stream(out_container, in_stream)
                                current_start = bucket_start
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
                            packet.stream = out_stream
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
        """Encode one decoded frame as JPEG and write it to storage."""
        try:
            image = frame.to_image()
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=85)
            object_name = frame_object_name(
                self.stream_id,
                segment_start(time.time(), self.segment_duration),
                frame_number,
            )
            if self._put_object(object_name, buffer.getvalue()):
                self.stats.frames_stored += 1
        except Exception as exc:  # noqa: BLE001 - frame loss is non-fatal
            logger.debug(
                "Failed to store a sampled live frame: %s",
                sanitize_for_log(str(exc), max_length=128),
            )
