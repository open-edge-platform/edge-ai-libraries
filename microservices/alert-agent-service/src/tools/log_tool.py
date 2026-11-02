# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
log_alert tool — records an alert event to the application log.

Always the baseline tool; does not require any external service.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def log_alert(
    source_id: str,
    alert_name: str,
    answer: str,
    reason: str,
    consecutive_count: int = 1,
    escalated: bool = False,
    snapshot_path: Optional[str] = None,
) -> dict:
    """Log an alert detection event. Always executed for every YES detection."""
    level = logging.WARNING if answer == "YES" else logging.DEBUG
    logger.log(
        level,
        f"ALERT {answer} | source={source_id} | "
        f"alert={alert_name} | consecutive={consecutive_count} | "
        f"escalated={escalated} | reason={reason!r}"
        + (f" | snapshot={snapshot_path}" if snapshot_path else ""),
    )
    return {
        "status": "logged",
        "source_id": source_id,
        "alert_name": alert_name,
        "answer": answer,
        "consecutive_count": consecutive_count,
        "escalated": escalated,
    }
