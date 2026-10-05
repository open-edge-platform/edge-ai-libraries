# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Best-effort camera clock-skew diagnostic for live streams.

Ingestion timestamps a live frame from the host clock anchored at connection
time (``capture_time_source = stream_anchored``) because IP cameras in this
class frequently emit no RTCP Sender Report, leaving no NTP-to-RTP mapping to
recover. A camera whose own clock is badly wrong is therefore invisible to
ingestion -- but it is exactly what makes correlation with an external recorder
(see ``docs/integration/stream-manager-readiness.md``) untrustworthy, and it is
a strong hint that the device has no working NTP sync.

This module surfaces that condition as a log warning. It is **purely
diagnostic**: it never affects registration, ingestion, or the timestamps we
store.

Why the HTTP ``Date`` header
----------------------------
Every HTTP server emits ``Date``, generated from its own system clock, and it
is present on the *unauthenticated* ``401`` response. That makes this probe:

* vendor-neutral -- no ISAPI/VAPIX/ONVIF dialect required;
* credential-free -- nothing is sent to the device beyond a ``HEAD``;
* sufficient -- ``Date`` has one-second resolution, which cannot time a frame
  but is ample for spotting a clock that is tens of seconds or more adrift.

Timezone mislabelling
---------------------
Embedded web servers commonly stamp *local* time while labelling it ``GMT``.
A Hikvision DS-2CD1023G0E-I in a ``UTC+05:30`` zone reports ``14:43:26 GMT``
when UTC is ``09:12:33``. Read naively that is a 5.5-hour skew; the real drift
is 53 seconds.

Since every real timezone offset is a whole multiple of 15 minutes, the raw
difference is split into the nearest such multiple (the apparent mislabelled
offset) and the remainder (the genuine drift). Both are reported: a mislabelled
timezone is itself worth knowing about when comparing timestamps across
services.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Final, Optional
from urllib.parse import urlsplit

import httpx

from src.common import logger, sanitize_for_log
from src.core.live.urls import redact_stream_url

#: Timezone offsets are always whole multiples of this many seconds, so a raw
#: difference near a multiple of it indicates a mislabelled zone rather than drift.
_TZ_QUANTUM_SECONDS: Final[int] = 900

#: Ceiling on the probe, so an unreachable or slow HTTP port cannot delay the
#: start of ingestion.
_PROBE_TIMEOUT_SECONDS: Final[float] = 3.0


@dataclass(frozen=True)
class ClockSkew:
    """Outcome of a camera clock probe.

    ``drift_seconds`` is the meaningful number: the camera's clock error after
    discounting any mislabelled timezone. Positive means the camera is ahead.
    """

    drift_seconds: float
    timezone_offset_seconds: int
    raw_difference_seconds: float

    @property
    def timezone_mislabelled(self) -> bool:
        """True when the device's ``Date`` header appears to carry local time."""
        return self.timezone_offset_seconds != 0


def probe_camera_clock(
    stream_url: str, timeout: float = _PROBE_TIMEOUT_SECONDS
) -> Optional[ClockSkew]:
    """Return the clock skew of ``stream_url``'s host, or ``None`` if unavailable.

    Never raises and never blocks longer than ``timeout``: a camera with no HTTP
    service, a firewalled port 80, or a missing ``Date`` header simply yields
    ``None``. Only the host is contacted -- the same host ingestion already
    connects to for RTSP -- and no credentials are transmitted.
    """
    host = _http_host(stream_url)
    if not host:
        return None

    try:
        # The request is deliberately unauthenticated: a 401 carries Date too,
        # and any status is acceptable as long as the header is present.
        # trust_env=False is essential -- the camera is a LAN device, so honouring
        # HTTP_PROXY would send the probe to a corporate proxy, which answers with
        # its own status and clock (or refuses), silently making the check useless.
        # It also keeps the device's internal address out of a proxy's logs.
        sent_at = time.time()
        response = httpx.head(
            f"http://{host}/",
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
        )
        received_at = time.time()
    except Exception:  # noqa: BLE001 - diagnostic only; any failure means "unknown"
        return None

    header = response.headers.get("Date")
    if not header:
        return None

    try:
        camera_time = parsedate_to_datetime(header).timestamp()
    except (TypeError, ValueError):
        return None

    # Compare against the midpoint of the request to halve round-trip bias. The
    # residual error is well under the header's one-second resolution.
    raw_difference = camera_time - (sent_at + received_at) / 2
    tz_offset = round(raw_difference / _TZ_QUANTUM_SECONDS) * _TZ_QUANTUM_SECONDS
    return ClockSkew(
        drift_seconds=raw_difference - tz_offset,
        timezone_offset_seconds=int(tz_offset),
        raw_difference_seconds=raw_difference,
    )


def log_clock_skew(stream_url: str, stream_id: str, warn_threshold: float) -> None:
    """Probe ``stream_url``'s host and log a warning when its clock is adrift.

    Intended to be called from a background worker thread, never from a request
    handler. All logging uses the redacted URL so credentials embedded in the
    source cannot reach the log.
    """
    safe_url = sanitize_for_log(redact_stream_url(stream_url))
    safe_id = sanitize_for_log(stream_id)

    skew = probe_camera_clock(stream_url)
    if skew is None:
        logger.debug(
            "Camera clock check unavailable for stream %s (%s); ingestion "
            "timestamps are host-anchored regardless.",
            safe_id,
            safe_url,
        )
        return

    if abs(skew.drift_seconds) < warn_threshold and not skew.timezone_mislabelled:
        logger.info(
            "Camera clock for stream %s (%s) is within %.1fs of this host " "(drift %+.1fs).",
            safe_id,
            safe_url,
            warn_threshold,
            skew.drift_seconds,
        )
        return

    detail = ""
    if skew.timezone_mislabelled:
        detail = (
            f" Its HTTP Date header also appears to report local time labelled as "
            f"GMT (apparent offset {skew.timezone_offset_seconds / 3600:+.2f}h)."
        )

    logger.warning(
        "Camera clock for stream %s (%s) is %+.1fs off this host.%s Ingestion "
        "is unaffected - frames are timestamped from the host clock - but the "
        "camera cannot be used as a shared time reference when correlating "
        "these embeddings with an external recording service. Enabling NTP on "
        "the device is recommended.",
        safe_id,
        safe_url,
        skew.drift_seconds,
        detail,
    )


def _http_host(stream_url: str) -> Optional[str]:
    """Extract the bare host (no port, no credentials) from an RTSP URL."""
    try:
        parts = urlsplit(str(stream_url).strip())
    except ValueError:
        return None
    host = parts.hostname
    if not host:
        return None
    return f"[{host}]" if ":" in host else host
