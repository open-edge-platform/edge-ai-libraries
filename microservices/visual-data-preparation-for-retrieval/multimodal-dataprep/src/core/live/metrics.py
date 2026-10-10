# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Fleet-wide throughput publishing for live streams.

The Metrics Manager gauge ``dataprep_embeddings_per_second`` is a single
process-wide value with fixed tags. A live stream never hits the file path's
end-of-request publish, so throughput has to be sampled while sessions run.

The gauge's job is to show the **rate of ingestion** -- how fast the device
turns frames into stored embeddings while it is actually working -- consistent
with the single-upload path, which reports ``embeddings / pipeline_wall`` for a
file processed back-to-back. A live source cannot be measured that way: its
frames arrive in real time (a 30fps camera sampled every N frames feeds only a
few embeddings/second), so dividing by wall-clock time would report the camera's
delivery cadence (~7 eps), not the device's ingestion rate (hundreds of eps).

So the denominator is **active compute time**, not wall time. Each worker reports
the detect+embed+store seconds it spent on every batch (decode is excluded -- for
a live source that stage blocks on real-time packet arrival; detection *is*
included, and is ~0 when object detection is disabled). This module is the single
writer: one background thread wakes on an interval, asks the manager for the
per-stream rolling ``(embeddings, active_seconds)`` totals, and publishes one
combined rate = summed new embeddings / summed new active seconds across every
running stream. Because embedding inference is serialized behind a shared lock,
summing active seconds across streams approximates the device's real busy time,
so the combined figure is the true fleet ingestion rate (not a per-stream rate
that would flap to the last writer, and not an average that would understate the
work). Intervals that produced no embeddings publish nothing; the gauge holds its
last reported rate until the next burst (there is intentionally no decay -- EPS
reflects the last observed ingestion rate, while device capacity is covered by
the separate RAM/CPU/GPU/NPU gauges).
"""

from __future__ import annotations

import threading
import time
from typing import Dict, Optional

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
        self._last_counts: Dict[str, int] = {}
        self._last_active: Dict[str, float] = {}

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
        self._prime(self.manager.running_throughput_by_stream())
        self._thread = threading.Thread(
            target=self._run, name="live-throughput-aggregator", daemon=True
        )
        self._thread.start()
        logger.info(
            "Live-stream throughput aggregation enabled: publishing one combined "
            "embeddings/second ingestion rate every %.1f second(s).",
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

    def _prime(self, samples: Dict[str, "tuple[int, float]"]) -> None:
        """Record the current per-stream totals as the next interval's baseline."""
        self._last_counts = {sid: count for sid, (count, _active) in samples.items()}
        self._last_active = {sid: active for sid, (_count, active) in samples.items()}

    def sample(self, now: Optional[float] = None) -> Optional[float]:
        """Publish one combined ingestion rate for the elapsed interval.

        Returns the published rate, or ``None`` when the interval produced no new
        embeddings (in which case the gauge holds its previous value). The rate is
        summed new embeddings divided by summed new **active compute seconds**
        (detect+embed+store) across every running stream, so it reflects how fast
        the device ingests while processing, not the camera's real-time delivery
        cadence.

        Both deltas are summed **per stream**, counting only streams that were
        already tracked in the previous sample and that produced embeddings this
        interval. This baselines a resumed (or freshly started) stream -- absent
        from the previous snapshot, its already-accumulated backlog contributes 0
        this tick instead of spiking the gauge -- and a stream that leaves the
        running set (paused/stopped/deleted) simply drops out.
        """
        now = time.time() if now is None else now
        samples = self.manager.running_throughput_by_stream()
        rate: Optional[float] = None

        emb_delta = 0
        active_delta = 0.0
        for stream_id, (count, active) in samples.items():
            previous = self._last_counts.get(stream_id)
            prev_active = self._last_active.get(stream_id)
            if previous is None or prev_active is None:
                continue  # newly tracked this tick: baseline it, count nothing yet
            d_emb = count - previous
            d_active = active - prev_active
            if d_emb > 0 and d_active > 0:
                emb_delta += d_emb
                active_delta += d_active

        if emb_delta > 0 and active_delta > 0:
            rate = emb_delta / active_delta
            publish_embeddings_throughput(rate, now)

        self._prime(samples)
        self._last_ts = now
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
