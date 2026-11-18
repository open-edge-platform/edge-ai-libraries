# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Age-based retention for live-stream data.

A live stream, unlike a file, never finishes. Left alone it grows the vector
index and the media bucket without bound, so the service offers a deliberately
simple control: keep the last ``MM_DATAPREP_LIVE_RETENTION_HOURS`` hours of live
data and drop the rest.

The default is ``0``, meaning *keep everything forever* — the sweeper does not
even start. Operators who enable it get one background thread that wakes every
``MM_DATAPREP_LIVE_RETENTION_SWEEP_MINUTES`` minutes and, for each registered
stream, deletes embeddings whose ``ingest_epoch`` precedes the cutoff along with
the media objects covering the same window. Streams a caller deregistered
without purging leave a tombstone behind so their retained data is swept too,
and the tombstone is dropped once all of that data is past the window.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

from src.common import logger, sanitize_for_log, settings
from src.core.live.manager import LiveStreamManager, get_live_stream_manager


class LiveRetentionSweeper:
    """Periodically prunes live-stream embeddings and media past the cutoff."""

    def __init__(self, manager: Optional[LiveStreamManager] = None) -> None:
        self._manager = manager
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @property
    def manager(self) -> LiveStreamManager:
        """The manager whose streams are swept."""
        if self._manager is None:
            self._manager = get_live_stream_manager()
        return self._manager

    @property
    def enabled(self) -> bool:
        """True when a positive retention window is configured."""
        return float(settings.LIVE_RETENTION_HOURS) > 0

    def start(self) -> bool:
        """Start the sweeper thread; returns False when retention is disabled."""
        if not self.enabled:
            logger.info(
                "Live-stream retention is disabled (MM_DATAPREP_LIVE_RETENTION_HOURS=0); "
                "live embeddings and media are kept indefinitely."
            )
            return False
        if self._thread is not None and self._thread.is_alive():
            return True
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="live-retention-sweeper", daemon=True
        )
        self._thread.start()
        logger.info(
            "Live-stream retention enabled: keeping %.2f hour(s), sweeping every %.1f minute(s).",
            float(settings.LIVE_RETENTION_HOURS),
            float(settings.LIVE_RETENTION_SWEEP_MINUTES),
        )
        return True

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the sweeper to exit and wait briefly for it."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        """Sweep on an interval until stopped."""
        interval = max(1.0, float(settings.LIVE_RETENTION_SWEEP_MINUTES) * 60.0)
        while not self._stop.wait(timeout=interval):
            if not self.enabled:
                continue
            try:
                self.sweep()
            except Exception as exc:  # noqa: BLE001 - the sweeper must never die
                logger.error(
                    "Live-stream retention sweep failed: %s",
                    sanitize_for_log(str(exc), max_length=256),
                )

    def sweep(self, now: Optional[float] = None) -> int:
        """Prune every registered stream once; returns the number swept."""
        if not self.enabled:
            return 0
        now = now or time.time()
        window = float(settings.LIVE_RETENTION_HOURS) * 3600.0
        cutoff = now - window
        streams = self.manager.list()
        for stream in streams:
            self._prune(stream, cutoff)

        # Tombstones are streams a caller deregistered without purging. Their
        # data is orphaned from the registry, so sweep it here too and drop the
        # tombstone once all of it is guaranteed older than the window.
        tombstones = self.manager.list_tombstones()
        for stream in tombstones:
            tombstoned_ts = stream.tombstoned_ts or 0.0
            if now - tombstoned_ts >= window:
                self.manager.drop_tombstone(stream)
            else:
                self._prune(stream, cutoff)

        total = len(streams) + len(tombstones)
        if total:
            logger.info(
                "Live-stream retention sweep pruned data older than %s across %d stream(s) "
                "(%d tombstoned).",
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(cutoff)),
                total,
                len(tombstones),
            )
        return total

    def _prune(self, stream, cutoff: float) -> None:
        """Purge one stream's aged data, logging (not raising) on backend failure."""
        from src.core.live.manager import LivePurgeBackendError

        try:
            self.manager.purge_embeddings(stream, before_epoch=cutoff)
            self.manager.purge_media(stream, before_epoch=cutoff)
        except LivePurgeBackendError as exc:
            logger.error(
                "Retention could not prune live stream %s this pass: %s",
                sanitize_for_log(stream.stream_id, max_length=64),
                sanitize_for_log(str(exc), max_length=256),
            )


_sweeper: Optional[LiveRetentionSweeper] = None
_sweeper_lock = threading.Lock()


def get_retention_sweeper() -> LiveRetentionSweeper:
    """Return the process-wide sweeper, creating it on first use."""
    global _sweeper
    if _sweeper is not None:
        return _sweeper
    with _sweeper_lock:
        if _sweeper is None:
            _sweeper = LiveRetentionSweeper()
    return _sweeper


def reset_retention_sweeper() -> None:
    """Stop and drop the process-wide sweeper (test helper)."""
    global _sweeper
    with _sweeper_lock:
        if _sweeper is not None:
            _sweeper.stop()
        _sweeper = None
