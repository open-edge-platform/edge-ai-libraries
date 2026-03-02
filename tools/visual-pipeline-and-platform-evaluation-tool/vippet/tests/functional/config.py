"""Shared configuration constants for VIPPET functional tests.

Environment variables:
* ``VIPPET_BASE_URL``            (default ``http://localhost/api/v1``)
* ``VIPPET_JOB_TIMEOUT_SECONDS`` (default ``600``)
* ``VIPPET_JOB_POLL_INTERVAL``   (default ``2.0``)
"""

import os

BASE_URL: str = os.environ.get("VIPPET_BASE_URL", "http://localhost/api/v1")
POLL_TIMEOUT_SECONDS: int = int(os.environ.get("VIPPET_JOB_TIMEOUT_SECONDS", "600"))
POLL_INTERVAL_SECONDS: float = float(os.environ.get("VIPPET_JOB_POLL_INTERVAL", "2.0"))
