# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Fleet-wide throughput publishing for live streams.

The Metrics Manager gauge ``dataprep_embeddings_per_second`` is a single
process-wide value with fixed tags. A live stream never hits the file path's
end-of-request publish, so throughput has to be sampled while sessions run --
but if every stream worker published its own per-stream rate they would all
write the *same* gauge and the last writer would win. With four cameras each
embedding ~5-7 frames/second the panel would then show ~7 eps (one stream)
instead of the combined ~25 eps, flapping to whichever worker published last.

This module is the single writer for live ingestion. One background thread wakes
on an interval, asks the manager for the rolling embedding total across every
running stream, and publishes one combined interval rate. Because embeddings
arrive in bursts, most ticks observe no new embeddings; publishing 0 on those
idle ticks would drop the gauge, so the window always advances but a sample is
only published when the interval actually produced embeddings. The gauge then
holds the last real fleet rate until the next burst (parity with the
single-upload path).
"""

from __future__ import annotations

import threading
import time
from typing import Optional

from src.common import logger, sanitize_for_log, settings
from src.core.live.manager import LiveStreamManager, get_live_stream_manager
from src.core.metrics_manager import publish_embeddings_throughput

#: How often the fleet throughput is sampled and (when non-idle) published.
_REFRESH_SECONDS = 5.0


class LiveThroughputAggregator:
    """Publishes one combined embeddings/second gauge for all live streams."""

    def __init__(self, manager: Optional[LiveStreamManager] = None) -> None:
        self._manager = manager
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_ts = 0.0
        self._last_total = 0

    @property
    def manager(self) -> LiveStreamManager:
        """The manager whose running streams are aggregated."""
        if self._manager is None:
            self._manager = get_live_stream_manager()
        return self._manager

    def start(self) -> bool:
        """Start the aggregator thread; idempotent."""
        if self._thread is not None and self._thread.is_alive():
            return True
        self._stop.clear()
        self._last_ts = time.time()
        self._last_total = self.manager.running_embeddings_total()
        self._thread = threading.Thread(
            target=self._run, name="live-throughput-aggregator", daemon=True
        )
        self._thread.start()
        logger.info(
            "Live-stream throughput aggregation enabled: publishing one combined "
            "embeddings/second gauge every %.1f second(s).",
            _REFRESH_SECONDS,
        )
        return True

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the aggregator to exit and wait briefly for it."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        """Sample and publish fleet throughput until stopped."""
        interval = max(0.5, float(_REFRESH_SECONDS))
        while not self._stop.wait(timeout=interval):
            try:
                self.sample()
            except Exception as exc:  # noqa: BLE001 - the aggregator must never die
                logger.error(
                    "Live-stream throughput aggregation failed: %s",
                    sanitize_for_log(str(exc), max_length=256),
                )

    def sample(self, now: Optional[float] = None) -> Optional[float]:
        """Publish one combined rate when the interval produced embeddings.

        Returns the published rate, or ``None`` on an idle interval (no new
        embeddings, in which case the gauge holds its previous value). The
        measurement window always advances so a later burst is measured over its
        own interval, and a shrinking total (a stream paused or stopped) yields a
        negative delta that is likewise held rather than published.
        """
        now = time.time() if now is None else now
        total = self.manager.running_embeddings_total()
        elapsed = now - self._last_ts
        rate: Optional[float] = None
        if elapsed > 0:
            delta = total - self._last_total
            if delta > 0:
                rate = delta / elapsed
                publish_embeddings_throughput(rate, now)
            self._last_ts = now
            self._last_total = total
        return rate


_aggregator: Optional[LiveThroughputAggregator] = None
_aggregator_lock = threading.Lock()


def get_throughput_aggregator() -> LiveThroughputAggregator:
    """Return the process-wide aggregator, creating it on first use."""
    global _aggregator
    if _aggregator is not None:
        return _aggregator
    with _aggregator_lock:
        if _aggregator is None:
            _aggregator = LiveThroughputAggregator()
    return _aggregator


def reset_throughput_aggregator() -> None:
    """Stop and drop the process-wide aggregator (test helper)."""
    global _aggregator
    with _aggregator_lock:
        if _aggregator is not None:
            _aggregator.stop()
        _aggregator = None
