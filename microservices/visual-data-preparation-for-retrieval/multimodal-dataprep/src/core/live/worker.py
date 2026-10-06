# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""The long-running ingestion worker for a single live stream.

One worker owns one registered stream. It repeatedly runs the service's existing
RTSP embedding pipeline (:func:`generate_rtsp_video_embedding_pipeline`) against
the source, records playback media alongside it, and reconnects with a bounded
budget when the source drops.

Nothing about decoding, detection, or embedding is reimplemented here: the
worker is purely lifecycle glue around the same pipeline used for file
ingestion, plus the identity and reconnect behaviour that live sources need.

Identity is the important addition. Every embedding the pipeline stores for this
worker carries ``bucket_name = <LIVE_STREAM_BUCKET>`` and
``video_id = <stream_id>``, which makes a live stream addressable by exactly the
same list/delete machinery as an uploaded video, plus the ``live_*`` metadata
fields (including the **redacted** source URL) described in
:mod:`src.core.vectorstores.metadata`.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Optional

from src.common import logger, sanitize_for_log, settings
from src.common.schema import LiveStreamStateEnum
from src.core.live.clock_check import log_clock_skew
from src.core.live.models import LiveStream
from src.core.live.recorder import SegmentMuxSink
from src.core.live.segments import segment_object_name
from src.core.live.urls import redact_stream_url
from src.core.metrics_manager import publish_embeddings_throughput

#: How often the worker refreshes recorder-derived stats while a session runs.
_STATS_REFRESH_SECONDS = 5.0

#: How long a stopped worker is given to wind its pipeline down.
_STOP_JOIN_TIMEOUT_SECONDS = 30.0


class LiveStreamWorker:
    """Runs and supervises ingestion for one registered live stream."""

    def __init__(
        self,
        stream: LiveStream,
        *,
        on_update: Callable[[LiveStream], None],
        pipeline: Optional[Callable[..., Dict[str, Any]]] = None,
        recorder_factory: Optional[Callable[..., SegmentMuxSink]] = None,
    ) -> None:
        self.stream = stream
        self._on_update = on_update
        self._pipeline = pipeline
        self._recorder_factory = recorder_factory or SegmentMuxSink

        self._thread: Optional[threading.Thread] = None
        #: Set when the worker should exit entirely.
        self._stop = threading.Event()
        #: Cleared while paused; the supervisor loop waits on it.
        self._resume = threading.Event()
        #: Passed into the pipeline/recorder; set to end the current session.
        self._session_shutdown = threading.Event()
        self._lock = threading.Lock()

    # -- introspection -----------------------------------------------------
    @property
    def stream_id(self) -> str:
        """Identifier of the stream this worker owns."""
        return self.stream.stream_id

    def is_alive(self) -> bool:
        """True while the supervisor thread is running."""
        return self._thread is not None and self._thread.is_alive()

    # -- lifecycle ---------------------------------------------------------
    def start(self, paused: bool = False) -> None:
        """Start the supervisor thread, optionally in the paused state."""
        if self.is_alive():
            return
        self._stop.clear()
        self._session_shutdown.clear()
        if paused:
            self._resume.clear()
            self._set_state(LiveStreamStateEnum.paused)
        else:
            self._resume.set()
            self._set_state(LiveStreamStateEnum.starting)
        self._thread = threading.Thread(
            target=self._run,
            name=f"live-stream-{self.stream_id[:8]}",
            daemon=True,
        )
        self._thread.start()

    def pause(self) -> None:
        """Stop ingesting without deregistering the stream."""
        self._resume.clear()
        self._session_shutdown.set()
        self.stream.desired_state = LiveStreamStateEnum.paused
        self._set_state(LiveStreamStateEnum.paused)

    def resume(self) -> None:
        """Resume ingestion after a pause."""
        self.stream.desired_state = LiveStreamStateEnum.running
        self._session_shutdown = threading.Event()
        self._set_state(LiveStreamStateEnum.starting)
        self._resume.set()

    def stop(self, join: bool = True, timeout: float = _STOP_JOIN_TIMEOUT_SECONDS) -> None:
        """Stop ingestion and terminate the supervisor thread."""
        self._stop.set()
        self._session_shutdown.set()
        self._resume.set()  # release a paused supervisor so it can exit
        if join and self._thread is not None:
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning(
                    "Live stream worker %s did not stop within %.0fs",
                    sanitize_for_log(self.stream_id, max_length=64),
                    timeout,
                )
        self._set_state(LiveStreamStateEnum.stopped)

    # -- state persistence -------------------------------------------------
    def _set_state(self, state: LiveStreamStateEnum, error: Optional[str] = None) -> None:
        """Update and persist the stream's observed state."""
        with self._lock:
            self.stream.state = state
            self.stream.last_error = error
            self.stream.updated_ts = time.time()
            snapshot = self.stream
        self._on_update(snapshot)

    def _persist(self) -> None:
        """Persist the current record without changing its state."""
        with self._lock:
            self.stream.updated_ts = time.time()
            snapshot = self.stream
        self._on_update(snapshot)

    # -- pipeline plumbing -------------------------------------------------
    def _resolve_pipeline(self) -> Callable[..., Dict[str, Any]]:
        """Import the embedding pipeline lazily to keep startup cheap."""
        if self._pipeline is not None:
            return self._pipeline
        from src.core.embedding.embedding_helper import generate_rtsp_video_embedding_pipeline

        return generate_rtsp_video_embedding_pipeline

    def _metadata_dict(self, recorder: Optional[Any] = None) -> Dict[str, Any]:
        """Build the pipeline metadata that gives this stream a stable identity."""
        stream = self.stream
        bucket = stream.bucket_name or settings.LIVE_STREAM_BUCKET
        redacted = redact_stream_url(stream.stream_url)

        def segment_url(start_epoch: Optional[float]) -> str:
            """Object-store path of the segment covering ``start_epoch``.

            Emitted as a root-relative path (leading ``/``) rather than a bare
            ``bucket/key``: consumers resolve it by prefixing their own object
            store gateway, and a path without the leading slash is
            indistinguishable from a relative URL, so it gets rejected and the
            caller silently falls back to a non-existent object.
            """
            if start_epoch is None:
                return ""
            return f"/{bucket}/{segment_object_name(stream.stream_id, start_epoch)}"

        live: Dict[str, Any] = {
            "stream_id": stream.stream_id,
            "stream_name": stream.stream_name,
            "sensor_id": stream.effective_sensor_id,
            # Redacted at the source: credentials must never reach the
            # vector database.
            "stream_url": redacted,
            "segment_duration_seconds": settings.LIVE_SEGMENT_DURATION_SECONDS,
            "segment_url_builder": segment_url,
        }
        if recorder is not None:
            # Let the pipeline map each frame to the segment that actually
            # covers it. The single-connection sink exposes resolve_segment,
            # which returns (segment_wall_start, segment_first_pts) keyed by the
            # frame's presentation time -- so the URL comes from the wall-clock
            # bucket (stable naming) and the playback seek is an exact PTS delta.
            resolver = getattr(recorder, "resolve_segment", None)
            if callable(resolver):
                live["segment_resolver"] = resolver
            # Legacy wall-clock resolver kept as a fallback for recorders that do
            # not expose the PTS-based one.
            legacy_resolver = getattr(recorder, "resolve_segment_start", None)
            if callable(legacy_resolver):
                live["segment_start_resolver"] = legacy_resolver

        return {
            "bucket_name": bucket,
            "video_id": stream.stream_id,
            "filename": f"{stream.stream_id}.live",
            "tags": list(stream.tags),
            "live": live,
        }

    # -- supervisor --------------------------------------------------------
    def _check_camera_clock(self) -> None:
        """Log a warning when the camera's own clock is badly adrift.

        Diagnostic only, and dispatched to its own short-lived daemon thread:
        the probe involves DNS resolution and a TCP connect to a device that may
        be slow, firewalled, or blackholing port 80, and ingestion must never
        wait on that. Runs once per worker start, not per reconnect.
        """
        if not settings.LIVE_CLOCK_CHECK_ENABLED:
            return

        def _probe() -> None:
            try:
                log_clock_skew(
                    self.stream.stream_url,
                    self.stream_id,
                    settings.LIVE_CLOCK_SKEW_WARN_SECONDS,
                )
            except Exception:  # noqa: BLE001 - a diagnostic must never stop ingestion
                logger.debug(
                    "Camera clock check failed for stream %s; continuing.",
                    sanitize_for_log(self.stream_id),
                    exc_info=True,
                )

        threading.Thread(
            target=_probe,
            name=f"live-clock-check-{self.stream_id[:8]}",
            daemon=True,
        ).start()

    def _run(self) -> None:
        """Supervise ingestion sessions, reconnecting within the configured budget."""
        self._check_camera_clock()
        attempts = 0
        while not self._stop.is_set():
            # Honour pause without tearing the registration down.
            if not self._resume.wait(timeout=1.0):
                continue
            if self._stop.is_set():
                break

            self._session_shutdown = threading.Event()
            session_started = time.time()
            self.stream.stats.started_ts = session_started
            self._set_state(LiveStreamStateEnum.running)

            error = self._run_session()

            if self._stop.is_set() or not self._resume.is_set():
                # Stopped or paused deliberately; not a failure.
                continue

            healthy_for = time.time() - session_started
            if healthy_for >= settings.LIVE_RECONNECT_WINDOW_SECONDS:
                # The stream ran long enough to be considered healthy, so the
                # reconnect budget starts again from zero.
                attempts = 0

            attempts += 1
            max_attempts = int(settings.LIVE_RECONNECT_MAX_ATTEMPTS)
            if max_attempts and attempts > max_attempts:
                logger.error(
                    "Live stream %s exhausted %d reconnect attempts; marking as error",
                    sanitize_for_log(self.stream_id, max_length=64),
                    max_attempts,
                )
                self._set_state(
                    LiveStreamStateEnum.error,
                    error or f"Stream unavailable after {max_attempts} reconnect attempts.",
                )
                return

            self.stream.stats.reconnect_count += 1
            self._set_state(LiveStreamStateEnum.reconnecting, error)
            logger.warning(
                "Live stream %s disconnected (attempt %d/%s); retrying in %.1fs",
                sanitize_for_log(self.stream_id, max_length=64),
                attempts,
                max_attempts or "unlimited",
                settings.LIVE_RECONNECT_INTERVAL_SECONDS,
            )
            # Interruptible backoff: a stop/pause during the wait takes effect
            # immediately instead of after the full delay.
            if self._stop.wait(timeout=settings.LIVE_RECONNECT_INTERVAL_SECONDS):
                break

        if not self._stop.is_set():
            return
        self._set_state(LiveStreamStateEnum.stopped)

    def _run_session(self) -> Optional[str]:
        """Run one ingestion session; return an error message when it failed."""
        session_started_ts = time.time()
        recorder = self._recorder_factory(
            stream_id=self.stream_id,
            stream_url=self.stream.stream_url,
            bucket_name=self.stream.bucket_name or settings.LIVE_STREAM_BUCKET,
            shutdown_event=self._session_shutdown,
        )
        recorder.start()

        pipeline = self._resolve_pipeline()
        result: Dict[str, Any] = {}
        error: Optional[str] = None
        # Counters are advanced from the pipeline's store thread, so guard them.
        progress_lock = threading.Lock()
        # Stream stats are cumulative across sessions, so remember where this
        # session started to report its own contribution in telemetry.
        session_start_frames = self.stream.stats.frames_processed
        session_start_embeddings = self.stream.stats.embeddings_created

        def _on_batch_stored(frames_in_batch: int, embeddings_stored: int) -> None:
            with progress_lock:
                self.stream.stats.frames_processed += int(frames_in_batch or 0)
                self.stream.stats.embeddings_created += int(embeddings_stored or 0)

        def _invoke() -> None:
            """Run the blocking pipeline and capture its outcome."""
            nonlocal result, error
            try:
                result = (
                    pipeline(
                        video_uris=[self.stream.stream_url],
                        metadata_dict=self._metadata_dict(recorder),
                        frame_interval=self.stream.frame_interval,
                        enable_object_detection=self.stream.enable_object_detection,
                        detection_confidence=self.stream.detection_confidence,
                        shutdown_event=self._session_shutdown,
                        progress_callback=_on_batch_stored,
                        # Single RTSP connection: the decode loop tees every
                        # packet to the recorder, so the embedding and the
                        # recorded segment share one clock (no playback drift).
                        packet_sink=recorder,
                    )
                    or {}
                )
            except Exception as exc:  # noqa: BLE001 - surfaced as stream state
                error = sanitize_for_log(str(exc), max_length=512)
                logger.error(
                    "Live ingestion session failed for stream %s: %s",
                    sanitize_for_log(self.stream_id, max_length=64),
                    error,
                )

        session_thread = threading.Thread(
            target=_invoke,
            name=f"live-pipeline-{self.stream_id[:8]}",
            daemon=True,
        )
        session_thread.start()

        # Keep recorder-derived counters fresh while the session runs, so
        # GET /media/streams/{id} reports progress instead of going silent.
        # Live ingestion is continuous and never hits the file path's
        # end-of-request telemetry publish, so the embeddings/second metric would
        # stay blank for the whole stream. Publish a ROLLING rate each refresh
        # tick (embeddings stored in the interval / wall-clock elapsed) so Metrics
        # Manager -- and the VSS telemetry panel -- track a live stream in real
        # time instead of only at session end.
        last_publish_ts = session_started_ts
        last_publish_embeddings = session_start_embeddings
        while session_thread.is_alive():
            session_thread.join(timeout=_STATS_REFRESH_SECONDS)
            self.stream.stats.segments_stored = recorder.stats.segments_stored
            # Segments only close every ~N seconds; use embedding progress as the
            # liveness signal so GET does not look stalled between segment cuts.
            if (
                self.stream.stats.frames_processed > session_start_frames
                or recorder.stats.segments_stored
            ):
                self.stream.stats.last_frame_ts = time.time()
            self._persist()

            now_ts = time.time()
            elapsed = now_ts - last_publish_ts
            if elapsed > 0:
                delta = self.stream.stats.embeddings_created - last_publish_embeddings
                publish_embeddings_throughput(max(0.0, delta / elapsed), now_ts)
                last_publish_ts = now_ts
                last_publish_embeddings = self.stream.stats.embeddings_created

        # Pipeline (and thus the single decode connection) has ended; flush the
        # open segment before tearing the session down.
        self._session_shutdown.set()
        recorder.close()
        recorder.join(timeout=_STOP_JOIN_TIMEOUT_SECONDS)

        # frames_processed/embeddings_created are already accumulated per batch by
        # _on_batch_stored; adding the final totals here would double-count them.
        self.stream.stats.segments_stored = recorder.stats.segments_stored
        self._persist()

        self._record_telemetry(
            result,
            session_started_ts,
            frames=self.stream.stats.frames_processed - session_start_frames,
            embeddings=self.stream.stats.embeddings_created - session_start_embeddings,
        )

        if error is None and not self._session_shutdown_requested():
            # The pipeline returned on its own: the source ended or dropped.
            error = "Live source ended or became unavailable."
        return error

    def _session_shutdown_requested(self) -> bool:
        """True when the session ended because of a stop/pause request."""
        return self._stop.is_set() or not self._resume.is_set()

    # -- telemetry ---------------------------------------------------------
    def _record_telemetry(
        self,
        result: Dict[str, Any],
        session_started_ts: float,
        *,
        frames: int = 0,
        embeddings: int = 0,
    ) -> None:
        """Publish one telemetry record per completed ingestion session.

        Live ingestion is continuous, so a record is emitted when a session
        ends (stop, pause, or disconnect) rather than per frame. This reuses the
        same recorder as file ingestion so ``GET /telemetry`` reports live and
        file work in one place.

        ``frames``/``embeddings`` are this session's own contribution, measured
        by the per-batch progress callback. The live pipeline aggregates its
        totals per stream and does not surface them at the top level of its
        result, so without this the record would be published with zero counts.
        """
        if not result and not (frames or embeddings):
            return
        try:
            from src.core.embedding.embedding_orchestrator import record_pipeline_telemetry

            metadata = self._metadata_dict()
            # The builder is a callable and would not survive serialization.
            metadata.pop("live", None)
            enriched = dict(result or {})
            enriched.setdefault("total_frames_processed", max(0, int(frames)))
            enriched.setdefault("total_stored_ids", max(0, int(embeddings)))
            record_pipeline_telemetry(
                context={
                    "request_id": f"live-{self.stream_id}-{int(session_started_ts)}",
                    "source": "live_stream",
                    "requested_at": session_started_ts,
                },
                bucket_name=self.stream.bucket_name or settings.LIVE_STREAM_BUCKET,
                video_id=self.stream_id,
                filename=f"{self.stream_id}.live",
                frame_interval=self.stream.frame_interval,
                tags=list(self.stream.tags),
                enable_object_detection=self.stream.enable_object_detection,
                detection_confidence=self.stream.detection_confidence,
                metadata_dict=metadata,
                pipeline_result=enriched,
            )
        except Exception as exc:  # pragma: no cover - telemetry is best-effort
            logger.debug(
                "Unable to record live telemetry for stream %s: %s",
                sanitize_for_log(self.stream_id, max_length=64),
                exc,
            )
