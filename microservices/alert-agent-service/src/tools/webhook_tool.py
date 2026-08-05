# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
trigger_webhook tool — HTTP POST to a configured external endpoint.

Configuration (environment variables):
    WEBHOOK_URL     — default endpoint (overridable per call)
    WEBHOOK_SECRET  — if set, adds an HMAC-SHA256 signature header
                      ``X-Alert-Signature: sha256=<hex>``

Uses a shared aiohttp.ClientSession for connection pooling and reuse,
avoiding the overhead of creating a new TCP connection per webhook call.

Requires: aiohttp
"""

import hashlib
import hmac
import json
import logging
from typing import Any, Dict, Optional

import aiohttp

from src.config import settings

logger = logging.getLogger(__name__)

_session: Optional[aiohttp.ClientSession] = None


async def _get_session() -> aiohttp.ClientSession:
    """Return the shared aiohttp session, creating it lazily on first use."""
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10),
        )
    return _session


async def shutdown_webhook_session():
    """Close the shared session gracefully during app shutdown."""
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
        _session = None


async def trigger_webhook(
    payload: Dict[str, Any],
    url: Optional[str] = None,
) -> dict:
    """POST a JSON payload to a webhook URL, optionally HMAC-signed."""
    endpoint = url or settings.WEBHOOK_URL
    if not endpoint:
        logger.warning("trigger_webhook: WEBHOOK_URL not configured — skipping")
        return {"status": "skipped", "reason": "WEBHOOK_URL not configured"}

    try:
        body = json.dumps(payload, default=str).encode()
        headers = {"Content-Type": "application/json"}

        if settings.WEBHOOK_SECRET:
            sig = hmac.new(
                settings.WEBHOOK_SECRET.encode(),
                body,
                hashlib.sha256,
            ).hexdigest()
            headers["X-Alert-Signature"] = f"sha256={sig}"

        session = await _get_session()
        async with session.post(
            endpoint,
            data=body,
            headers=headers,
        ) as resp:
            http_status = resp.status
            text = await resp.text()

        log_fn = logger.info if http_status < 400 else logger.error
        log_fn(f"Webhook POST {endpoint} → HTTP {http_status}")
        return {
            "status": "ok" if http_status < 400 else "error",
            "http_status": http_status,
            "response": text[:200],
        }

    except Exception as exc:
        logger.error(f"trigger_webhook failed: {exc}")
        return {"status": "error", "reason": str(exc)}
