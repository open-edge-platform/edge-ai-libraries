# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
capture_snapshot tool — writes an image artifact payload to disk.

Unlike the live-video-alert-agent version, this tool receives raw image bytes
directly from the request payload — no in-process frame callbacks or
VideoCapture dependency.  The bytes are written as-is (caller is responsible
for JPEG/PNG encoding).

Configuration (environment variables):
    SNAPSHOT_DIR — base directory for snapshot files (default: ``snapshots/``)

File naming:  {SNAPSHOT_DIR}/{source_id}/{alert_name}_{timestamp}.<ext>
"""

import asyncio
import logging
import os
import time
from typing import Optional

from src.config import settings

logger = logging.getLogger(__name__)


async def capture_snapshot(
    source_id: str,
    alert_name: str = "alert",
    image_bytes: Optional[bytes] = None,
    mime_type: str = "image/jpeg",
) -> dict:
    """
    Save image bytes to disk as a snapshot file.

    Parameters
    ----------
    source_id : str
        Source identifier (used as sub-directory name).
    alert_name : str
        Alert name (used in the filename).
    image_bytes : bytes, optional
        Raw image bytes.  If None or empty, the tool skips gracefully.
    mime_type : str
        MIME type of the image (used to derive file extension).
    """
    if not image_bytes:
        logger.debug(
            f"capture_snapshot: no image bytes provided for source='{source_id}' "
            f"alert='{alert_name}' — skipping"
        )
        return {"status": "skipped", "reason": "no image bytes provided"}

    # Derive file extension from mime_type
    ext_map = {
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "image/gif": "gif",
    }
    ext = ext_map.get(mime_type.lower(), "bin")

    ts = time.strftime("%Y%m%d_%H%M%S")
    safe_alert = alert_name.replace(" ", "_").replace("/", "_")
    safe_source = source_id.replace("/", "_").replace(":", "_")
    out_dir = os.path.join(settings.SNAPSHOT_DIR, safe_source)
    os.makedirs(out_dir, exist_ok=True)
    filename = f"{safe_alert}_{ts}.{ext}"
    path = os.path.join(out_dir, filename)

    def _write() -> bool:
        try:
            with open(path, "wb") as fh:
                fh.write(image_bytes)
            return True
        except OSError:
            return False

    success = await asyncio.to_thread(_write)
    if not success:
        logger.error(f"capture_snapshot: write failed for path: {path}")
        return {"status": "error", "reason": f"write failed: {path}"}

    logger.info(f"Snapshot saved: {path} ({len(image_bytes)} bytes)")
    return {"status": "saved", "path": path}
