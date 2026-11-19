# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Dedicated, persistent audit trail for pipeline lifecycle actions
(start/stop), separate from general application logs so it can be
shipped/retained independently.
"""

from __future__ import annotations

import logging
import os
import sys

# Defaults to the app-owned pipeline_root scratch dir (not the shared,
# world-writable /tmp - CWE-377) matching the convention used elsewhere in
# this service.
AUDIT_LOG_PATH = os.environ.get("AUDIT_LOG_PATH", "/var/cache/pipeline_root/dlsps_audit.log")


def get_audit_logger() -> logging.Logger:
    """Get the shared structured audit logger."""
    logger = logging.getLogger("audit")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        formatter = logging.Formatter("%(message)s")

        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

        try:
            file_handler = logging.FileHandler(AUDIT_LOG_PATH)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except OSError:
            pass  # best-effort - audit entries still reach stdout

    return logger
