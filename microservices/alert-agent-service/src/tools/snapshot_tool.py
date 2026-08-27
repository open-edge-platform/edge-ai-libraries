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
import base64
import binascii
import logging
import os
import time
from typing import Optional

from src.config import settings

logger = logging.getLogger(__name__)

MAX_SNAPSHOT_BYTES = 10 * 1024 * 1024
MAX_BASE64_LENGTH = ((MAX_SNAPSHOT_BYTES + 2) // 3) * 4


def _safe_path_component(value: str, *, replace_spaces: bool = False) -> str:
    safe_value = value.replace("/", "_").replace("\\", "_").replace(":", "_")
    if replace_spaces:
        safe_value = safe_value.replace(" ", "_")
    return "_" if safe_value in {"", ".", ".."} else safe_value


def _decode_image_bytes(image_bytes: bytes | str) -> bytes:
    if isinstance(image_bytes, bytes):
        decoded = image_bytes
    elif isinstance(image_bytes, str):
        if len(image_bytes) > MAX_BASE64_LENGTH:
            raise ValueError(
                f"decoded image exceeds the {MAX_SNAPSHOT_BYTES}-byte limit"
            )
        try:
            decoded = base64.b64decode(image_bytes, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("image_bytes must be a valid Base64 string") from exc
    else:
        raise TypeError("image_bytes must be raw bytes or a Base64 string")

    if len(decoded) > MAX_SNAPSHOT_BYTES:
        raise ValueError(f"decoded image exceeds the {MAX_SNAPSHOT_BYTES}-byte limit")
    return decoded


async def capture_snapshot(
    source_id: str,
    alert_name: str = "alert",
    image_bytes: Optional[bytes | str] = None,
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
    image_bytes : bytes or str, optional
        Raw image bytes or a Base64-encoded string. If None or empty, the tool
        skips gracefully.
    mime_type : str
        MIME type of the image (used to derive file extension).
    """
    if not image_bytes:
        logger.debug(
            f"capture_snapshot: no image bytes provided for source='{source_id}' "
            f"alert='{alert_name}' — skipping"
        )
        return {"status": "skipped", "reason": "no image bytes provided"}

    decoded_image = _decode_image_bytes(image_bytes)

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
    safe_alert = _safe_path_component(alert_name, replace_spaces=True)
    safe_source = _safe_path_component(source_id)
    out_dir = os.path.join(settings.SNAPSHOT_DIR, safe_source)
    os.makedirs(out_dir, exist_ok=True)
    filename = f"{safe_alert}_{ts}.{ext}"
    path = os.path.join(out_dir, filename)

    def _write() -> bool:
        try:
            with open(path, "wb") as fh:
                fh.write(decoded_image)
            return True
        except OSError:
            return False

    success = await asyncio.to_thread(_write)
    if not success:
        logger.error(f"capture_snapshot: write failed for path: {path}")
        return {"status": "error", "reason": f"write failed: {path}"}

    logger.info(f"Snapshot saved: {path} ({len(decoded_image)} bytes)")
    return {"status": "saved", "path": path}
