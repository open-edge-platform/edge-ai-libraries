"""Shared configuration constants for VIPPET functional tests."""

import os

BASE_URL: str = os.environ.get("VIPPET_BASE_URL", "http://localhost/api/v1")
POLL_TIMEOUT_SECONDS: int = int(os.environ.get("VIPPET_JOB_TIMEOUT_SECONDS", "600"))
POLL_INTERVAL_SECONDS: float = float(os.environ.get("VIPPET_JOB_POLL_INTERVAL", "2.0"))
