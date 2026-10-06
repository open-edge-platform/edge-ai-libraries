# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Process-wide registry and lifecycle control for live streams.

This is the module the API layer talks to. It owns the mapping from
``stream_id`` to a running :class:`~src.core.live.worker.LiveStreamWorker`,
persists every registration through the configured
:class:`~src.core.live.store.LiveStreamStore`, and restores streams after a
service restart.

Design notes
------------
* **Persisted intent, observed state.** A record carries both what the caller
  asked for (``desired_state``) and what the worker currently sees (``state``).
  Restart restores the intent; the worker then reports reality.
* **Bounded concurrency.** Each running stream holds decode/detect/embed threads
  and shared-memory blocks, so ``MM_DATAPREP_LIVE_STREAM_MAX_CONCURRENT`` is
  enforced at create/resume time rather than letting the shared pools starve.
* **Credential hygiene.** The credentialed URL never leaves a record: callers
  receive :meth:`LiveStream.to_info`, which redacts it.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

from src.common import logger, sanitize_for_log, settings
from src.common.schema import LiveStreamStateEnum
from src.core.live.models import LiveStream
from src.core.live.segments import SEGMENT_PREFIX
from src.core.live.store import LiveStreamStore, get_live_stream_store
from src.core.live.urls import redact_stream_url, validate_stream_url
from src.core.live.worker import LiveStreamWorker


class LiveStreamLimitError(RuntimeError):
    """Raised when starting a stream would exceed the concurrency limit."""


class LiveStreamNotFoundError(KeyError):
    """Raised when an operation references an unknown ``stream_id``."""


class LiveStreamManager:
    """Owns every registered live stream and its worker."""

    def __init__(
        self,
        store: Optional[LiveStreamStore] = None,
        *,
        worker_factory: Optional[Callable[..., LiveStreamWorker]] = None,
    ) -> None:
        self._store = store
        #: Injectable so tests (and future alternative runtimes) can supply a
        #: worker that does not open a real RTSP connection.
        self._worker_factory = worker_factory or LiveStreamWorker
        self._workers: Dict[str, LiveStreamWorker] = {}
        self._lock = threading.RLock()

    # -- plumbing ----------------------------------------------------------
    @property
    def store(self) -> LiveStreamStore:
        """The registry store, resolved lazily."""
        if self._store is None:
            self._store = get_live_stream_store()
        return self._store

    def _persist(self, stream: LiveStream) -> None:
        """Write a record back to the registry, tolerating store failures."""
        try:
            self.store.upsert(stream)
        except Exception as exc:  # noqa: BLE001 - a store hiccup must not kill a worker
            logger.error(
                "Failed to persist live stream %s: %s",
                sanitize_for_log(stream.stream_id, max_length=64),
                sanitize_for_log(str(exc), max_length=256),
            )

    def _running_count(self) -> int:
        """Number of workers currently ingesting (paused ones do not count)."""
        return sum(
            1
            for worker in self._workers.values()
            if worker.is_alive()
            and worker.stream.state
            not in (
                LiveStreamStateEnum.paused,
                LiveStreamStateEnum.stopped,
                LiveStreamStateEnum.error,
            )
        )

    def _assert_capacity(self) -> None:
        """Raise when another running stream would exceed the configured cap."""
        limit = int(settings.LIVE_STREAM_MAX_CONCURRENT)
        if self._running_count() >= limit:
            raise LiveStreamLimitError(
                f"Maximum of {limit} concurrent live streams already running. "
                "Pause or delete a stream, or raise MM_DATAPREP_LIVE_STREAM_MAX_CONCURRENT."
            )

    def _spawn(self, stream: LiveStream, paused: bool) -> LiveStreamWorker:
        """Create, register, and start a worker for ``stream``."""
        worker = self._worker_factory(stream, on_update=self._persist)
        self._workers[stream.stream_id] = worker
        worker.start(paused=paused)
        return worker

    # -- CRUD --------------------------------------------------------------
    def create(
        self,
        *,
        stream_url: str,
        stream_name: Optional[str] = None,
        description: Optional[str] = None,
        sensor_id: Optional[str] = None,
        frame_interval: Optional[int] = None,
        enable_object_detection: Optional[bool] = None,
        detection_confidence: Optional[float] = None,
        tags: Optional[List[str]] = None,
        start: bool = True,
    ) -> LiveStream:
        """Register a stream and (by default) start ingesting it."""
        validated_url = validate_stream_url(stream_url)

        stream = LiveStream.new(
            stream_url=validated_url,
            stream_name=stream_name,
            description=description,
            sensor_id=sensor_id,
            frame_interval=int(
                frame_interval if frame_interval is not None else settings.FRAME_INTERVAL
            ),
            enable_object_detection=bool(
                enable_object_detection
                if enable_object_detection is not None
                else settings.ENABLE_OBJECT_DETECTION
            ),
            detection_confidence=float(
                detection_confidence
                if detection_confidence is not None
                else settings.DETECTION_CONFIDENCE
            ),
            bucket_name=settings.LIVE_STREAM_BUCKET,
            tags=tags,
            start=start,
        )

        with self._lock:
            if start:
                self._assert_capacity()
            self._persist(stream)
            self._spawn(stream, paused=not start)

        logger.info(
            "Registered live stream %s (%s) start=%s",
            sanitize_for_log(stream.stream_id, max_length=64),
            sanitize_for_log(stream.redacted_url, max_length=256),
            start,
        )
        return stream

    def get(self, stream_id: str) -> LiveStream:
        """Return a registered stream, preferring the in-memory worker record."""
        with self._lock:
            worker = self._workers.get(stream_id)
            if worker is not None:
                return worker.stream
        stream = self.store.get(stream_id)
        if stream is None:
            raise LiveStreamNotFoundError(stream_id)
        return stream

    def list(
        self,
        *,
        state: Optional[LiveStreamStateEnum] = None,
        tags: Optional[List[str]] = None,
    ) -> List[LiveStream]:
        """Return registered streams, optionally filtered by state and tags."""
        with self._lock:
            live_records = {sid: w.stream for sid, w in self._workers.items()}
        streams = [live_records.get(s.stream_id, s) for s in self.store.list()]
        # Include workers not yet flushed to the store (belt and braces).
        known = {s.stream_id for s in streams}
        streams.extend(s for sid, s in live_records.items() if sid not in known)

        if state is not None:
            streams = [s for s in streams if s.state == state]
        if tags:
            wanted = set(tags)
            streams = [s for s in streams if wanted.issubset(set(s.tags))]
        return streams

    def update(
        self,
        stream_id: str,
        *,
        stream_name: Optional[str] = None,
        description: Optional[str] = None,
        frame_interval: Optional[int] = None,
        enable_object_detection: Optional[bool] = None,
        detection_confidence: Optional[float] = None,
        tags: Optional[List[str]] = None,
        state: Optional[LiveStreamStateEnum] = None,
    ) -> LiveStream:
        """Update a stream's configuration and/or pause/resume it.

        Processing parameters take effect on the next ingestion session. When
        one of them changes on a *running* stream, the current session is
        restarted so the new value applies immediately.
        """
        with self._lock:
            stream = self.get(stream_id)
            worker = self._workers.get(stream_id)

            processing_changed = False
            if stream_name is not None:
                stream.stream_name = stream_name
            if description is not None:
                stream.description = description
            if tags is not None:
                stream.tags = list(tags)
                processing_changed = True
            if frame_interval is not None and frame_interval != stream.frame_interval:
                stream.frame_interval = int(frame_interval)
                processing_changed = True
            if (
                enable_object_detection is not None
                and enable_object_detection != stream.enable_object_detection
            ):
                stream.enable_object_detection = bool(enable_object_detection)
                processing_changed = True
            if (
                detection_confidence is not None
                and detection_confidence != stream.detection_confidence
            ):
                stream.detection_confidence = float(detection_confidence)
                processing_changed = True

            stream.updated_ts = time.time()
            self._persist(stream)

            if state is LiveStreamStateEnum.paused:
                self._pause_locked(stream, worker)
            elif state is LiveStreamStateEnum.running:
                self._resume_locked(stream, worker)
            elif processing_changed and worker is not None and worker.is_alive():
                if stream.state in (
                    LiveStreamStateEnum.running,
                    LiveStreamStateEnum.starting,
                    LiveStreamStateEnum.reconnecting,
                ):
                    # Bounce the session so the new parameters take effect now.
                    self._pause_locked(stream, worker)
                    self._resume_locked(stream, worker)

            return stream

    def _pause_locked(self, stream: LiveStream, worker: Optional[LiveStreamWorker]) -> None:
        """Pause a stream (caller holds the lock)."""
        stream.desired_state = LiveStreamStateEnum.paused
        if worker is not None and worker.is_alive():
            worker.pause()
        else:
            stream.state = LiveStreamStateEnum.paused
        self._persist(stream)

    def _resume_locked(self, stream: LiveStream, worker: Optional[LiveStreamWorker]) -> None:
        """Resume (or start) a stream (caller holds the lock)."""
        stream.desired_state = LiveStreamStateEnum.running
        stream.last_error = None
        if worker is not None and worker.is_alive():
            self._assert_capacity()
            worker.resume()
        else:
            self._assert_capacity()
            self._spawn(stream, paused=False)
        self._persist(stream)

    def delete(
        self,
        stream_id: str,
        *,
        purge_embeddings: bool = False,
        purge_media: bool = False,
    ) -> Tuple[LiveStream, Optional[int], Optional[int]]:
        """Stop, deregister, and optionally purge a stream's data.

        Returns ``(stream, embeddings_purged, media_purged)``; the purge counts
        are ``None`` when the corresponding purge was not requested and ``-1``
        when a backend cannot report an exact count.
        """
        with self._lock:
            stream = self.get(stream_id)
            worker = self._workers.pop(stream_id, None)

        if worker is not None:
            worker.stop()

        embeddings_purged: Optional[int] = None
        media_purged: Optional[int] = None
        if purge_embeddings:
            embeddings_purged = self.purge_embeddings(stream)
        if purge_media:
            media_purged = self.purge_media(stream)

        self.store.delete(stream_id)
        stream.state = LiveStreamStateEnum.stopped
        logger.info(
            "Deleted live stream %s (purge_embeddings=%s purge_media=%s)",
            sanitize_for_log(stream_id, max_length=64),
            purge_embeddings,
            purge_media,
        )
        return stream, embeddings_purged, media_purged

    # -- purge helpers -----------------------------------------------------
    @staticmethod
    def purge_embeddings(stream: LiveStream, before_epoch: Optional[float] = None) -> int:
        """Delete a stream's vectors, optionally only those older than a cutoff."""
        from src.core.vectorstores import get_vector_store

        bucket = stream.bucket_name or settings.LIVE_STREAM_BUCKET
        store = get_vector_store()
        try:
            if before_epoch is None:
                return store.delete_embeddings(bucket, stream.stream_id)
            return store.delete_embeddings_before(bucket, stream.stream_id, before_epoch)
        except Exception as exc:  # noqa: BLE001 - reported, not fatal
            logger.error(
                "Failed to purge embeddings for live stream %s: %s",
                sanitize_for_log(stream.stream_id, max_length=64),
                sanitize_for_log(str(exc), max_length=256),
            )
            # -1 distinguishes "the backend failed" from "nothing to delete".
            return -1

    @staticmethod
    def purge_media(stream: LiveStream, before_epoch: Optional[float] = None) -> int:
        """Delete a stream's recorded media, optionally only older objects.

        Object names embed the segment's start epoch (see
        :mod:`src.core.live.segments`), so age filtering needs no object
        metadata lookup.
        """
        from src.core.storage import get_storage

        bucket = stream.bucket_name or settings.LIVE_STREAM_BUCKET
        deleted = 0
        try:
            storage = get_storage()
            if not storage.bucket_exists(bucket):
                return 0
            objects = storage.list_objects_in_directory(bucket, stream.stream_id)
        except Exception as exc:  # noqa: BLE001 - reported, not fatal
            logger.error(
                "Failed to list live media for stream %s: %s",
                sanitize_for_log(stream.stream_id, max_length=64),
                sanitize_for_log(str(exc), max_length=256),
            )
            return 0

        for obj in objects:
            name = getattr(obj, "object_name", None) or getattr(obj, "name", "")
            if before_epoch is not None and not _object_is_older_than(name, before_epoch):
                continue
            try:
                storage.delete_object(bucket, name)
                deleted += 1
            except Exception as exc:  # noqa: BLE001 - keep purging the rest
                logger.warning(
                    "Failed to delete live media object %s: %s",
                    sanitize_for_log(name, max_length=256),
                    sanitize_for_log(str(exc), max_length=256),
                )
        return deleted

    # -- startup / shutdown ------------------------------------------------
    def restore(self) -> List[LiveStream]:
        """Restore persisted registrations, restarting those meant to be running.

        Called from the app lifespan. Every restored stream is logged explicitly
        so an operator can see, at startup, exactly what ingestion the service
        resumed on its own.
        """
        if not settings.LIVE_STREAM_ENABLED:
            logger.info("Live-stream ingestion is disabled; skipping restore.")
            return []

        try:
            streams = self.store.list()
        except Exception as exc:  # noqa: BLE001 - never block startup
            logger.error(
                "Could not read the live-stream registry: %s",
                sanitize_for_log(str(exc), max_length=256),
            )
            return []

        if not streams:
            logger.info("No live streams registered; nothing to restore.")
            return []

        limit = int(settings.LIVE_STREAM_MAX_CONCURRENT)
        started = 0
        logger.info("Restoring %d registered live stream(s):", len(streams))
        for stream in streams:
            should_run = stream.desired_state == LiveStreamStateEnum.running
            action = "paused"
            with self._lock:
                if should_run and started < limit:
                    self._spawn(stream, paused=False)
                    started += 1
                    action = "started"
                else:
                    if should_run:
                        stream.last_error = (
                            "Not restarted automatically: concurrency limit "
                            f"({limit}) reached. Resume it with PATCH."
                        )
                        action = "deferred (limit reached)"
                    stream.state = LiveStreamStateEnum.paused
                    self._spawn(stream, paused=True)
                self._persist(stream)

            logger.info(
                "  - %s | %s | name=%s | tags=%s | %s",
                sanitize_for_log(stream.stream_id, max_length=64),
                sanitize_for_log(redact_stream_url(stream.stream_url), max_length=256),
                sanitize_for_log(stream.stream_name, max_length=128),
                sanitize_for_log(",".join(stream.tags), max_length=128) or "-",
                action,
            )
        return streams

    def stop_all(self) -> None:
        """Stop every worker (called on service shutdown)."""
        with self._lock:
            workers = list(self._workers.values())
            self._workers.clear()
        for worker in workers:
            try:
                worker.stop()
            except Exception as exc:  # noqa: BLE001 - shutdown must not raise
                logger.warning(
                    "Error stopping live stream worker %s: %s",
                    sanitize_for_log(worker.stream_id, max_length=64),
                    sanitize_for_log(str(exc), max_length=256),
                )
        if workers:
            logger.info("Stopped %d live stream worker(s).", len(workers))

    def running_embeddings_total(self) -> int:
        """Sum embeddings created across all currently-ingesting workers.

        The Metrics Manager ``dataprep_embeddings_per_second`` gauge is a single
        process-wide value, so the fleet throughput must be computed centrally:
        if every worker published its own per-stream rate the last writer would
        win and the panel would show one stream's rate (~5-7 eps) instead of the
        combined total across, say, four streams (>20 eps). The process-wide
        :class:`~src.core.live.metrics.LiveThroughputAggregator` reads this
        rolling total each tick and publishes one combined rate. Paused, stopped
        and errored streams are excluded so their frozen counters neither inflate
        the rate nor produce a negative delta.
        """
        with self._lock:
            return sum(
                worker.stream.stats.embeddings_created
                for worker in self._workers.values()
                if worker.is_alive()
                and worker.stream.state
                not in (
                    LiveStreamStateEnum.paused,
                    LiveStreamStateEnum.stopped,
                    LiveStreamStateEnum.error,
                )
            )

    def counts(self) -> Dict[str, int]:
        """Return a state histogram, used by the health endpoint."""
        histogram: Dict[str, int] = {}
        for stream in self.list():
            histogram[stream.state.value] = histogram.get(stream.state.value, 0) + 1
        histogram["total"] = sum(value for key, value in histogram.items() if key != "total")
        return histogram


def _object_is_older_than(object_name: str, cutoff_epoch: float) -> bool:
    """True when a live media object's encoded start epoch precedes the cutoff."""
    if not object_name:
        return False
    parts = object_name.split("/")
    if len(parts) < 3 or parts[1] != SEGMENT_PREFIX:
        return False
    stem = parts[-1].split(".")[0]
    epoch_token = stem.split("_")[0]
    try:
        return float(epoch_token) < float(cutoff_epoch)
    except ValueError:
        return False


_manager: Optional[LiveStreamManager] = None
_manager_lock = threading.Lock()


def get_live_stream_manager() -> LiveStreamManager:
    """Return the process-wide manager, creating it on first use."""
    global _manager
    if _manager is not None:
        return _manager
    with _manager_lock:
        if _manager is None:
            _manager = LiveStreamManager()
    return _manager


def set_live_stream_manager(manager: Optional[LiveStreamManager]) -> None:
    """Override the process-wide manager (test helper)."""
    global _manager
    with _manager_lock:
        _manager = manager


def reset_live_stream_manager() -> None:
    """Stop and drop the process-wide manager."""
    global _manager
    with _manager_lock:
        if _manager is not None:
            _manager.stop_all()
        _manager = None
