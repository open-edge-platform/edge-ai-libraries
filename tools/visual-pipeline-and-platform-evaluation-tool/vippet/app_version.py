"""
Application build version for ViPPET.

Resolves the release/build identifier exposed via ``GET /status`` and the FastAPI OpenAPI document.
"""

import os
from datetime import datetime, timezone

# Raw value injected at build time (see Dockerfile).
_RAW_VERSION = os.environ.get("VIPPET_VERSION", "").strip()

# Labels that don't identify a specific build are suffixed with a timestamp
# so distinct dev/test runs remain distinguishable via GET /status.
_FALLBACK_LABELS = ("", "test")

if _RAW_VERSION in _FALLBACK_LABELS:
    _label = _RAW_VERSION or "dev"
    _timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    VIPPET_VERSION: str = f"{_label}-{_timestamp}"
else:
    VIPPET_VERSION = _RAW_VERSION
