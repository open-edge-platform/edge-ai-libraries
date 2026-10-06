# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Live (RTSP) stream ingestion: registry, lifecycle, recording, and retention.

Live ingestion is modelled as a set of long-lived, addressable resources rather
than a blocking request. The pieces:

* :mod:`~src.core.live.models` -- the persisted stream record.
* :mod:`~src.core.live.store` -- pluggable registry persistence (SQLite default).
* :mod:`~src.core.live.manager` -- process-wide registry and lifecycle control.
* :mod:`~src.core.live.worker` -- per-stream ingestion supervisor with reconnect.
* :mod:`~src.core.live.recorder` -- segment/frame recording for playback.
* :mod:`~src.core.live.retention` -- optional age-based pruning.
* :mod:`~src.core.live.urls` -- URL validation and credential redaction.
* :mod:`~src.core.live.segments` -- wall-clock segment bucketing.

Nothing here imports the embedding pipeline at module scope: the worker resolves
it lazily so importing the registry stays cheap (and import-cycle free).
"""

from src.core.live.manager import (
    LiveStreamLimitError,
    LiveStreamManager,
    LiveStreamNotFoundError,
    LiveStreamPurgeError,
    get_live_stream_manager,
    reset_live_stream_manager,
    set_live_stream_manager,
)
from src.core.live.metrics import (
    LiveThroughputAggregator,
    get_throughput_aggregator,
    reset_throughput_aggregator,
)
from src.core.live.models import LiveStream
from src.core.live.retention import (
    LiveRetentionSweeper,
    get_retention_sweeper,
    reset_retention_sweeper,
)
from src.core.live.store import (
    InMemoryLiveStreamStore,
    LiveStreamStore,
    SqliteLiveStreamStore,
    get_live_stream_store,
    reset_live_stream_store,
    set_live_stream_store,
)
from src.core.live.urls import InvalidStreamUrlError, redact_stream_url, validate_stream_url

__all__ = [
    "LiveStream",
    "LiveStreamManager",
    "LiveStreamLimitError",
    "LiveStreamNotFoundError",
    "LiveStreamPurgeError",
    "get_live_stream_manager",
    "set_live_stream_manager",
    "reset_live_stream_manager",
    "LiveStreamStore",
    "InMemoryLiveStreamStore",
    "SqliteLiveStreamStore",
    "get_live_stream_store",
    "set_live_stream_store",
    "reset_live_stream_store",
    "LiveRetentionSweeper",
    "get_retention_sweeper",
    "reset_retention_sweeper",
    "LiveThroughputAggregator",
    "get_throughput_aggregator",
    "reset_throughput_aggregator",
    "InvalidStreamUrlError",
    "redact_stream_url",
    "validate_stream_url",
]
