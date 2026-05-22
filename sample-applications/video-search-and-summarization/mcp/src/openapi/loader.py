# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Fetch OpenAPI / Swagger documents from the upstream backend."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

logger = logging.getLogger(__name__)


def fetch_openapi_spec(spec_url: str, timeout: float) -> dict[str, Any]:
    """Download an OpenAPI / Swagger document and decode it as JSON.

    Args:
        spec_url: HTTP(S) URL of the OpenAPI or Swagger 2.0 JSON document.
        timeout: Maximum number of seconds to wait for the network round-trip.

    Returns:
        The parsed JSON document as a Python ``dict``.

    Raises:
        ValueError: If the URL is unreachable, the response is not valid JSON,
            or the top-level document is not a JSON object.
    """

    logger.info("Fetching OpenAPI spec from %s (timeout=%.1fs)", spec_url, timeout)
    try:
        with urlopen(spec_url, timeout=timeout) as response:  # noqa: S310 - trusted internal URL
            raw_bytes = response.read()
            status = getattr(response, "status", None)
    except URLError as exc:
        raise ValueError(f"Unable to reach OpenAPI spec at {spec_url}: {exc.reason}") from exc

    try:
        document = json.loads(raw_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"OpenAPI spec at {spec_url} is not valid JSON: {exc}") from exc

    if not isinstance(document, dict):
        raise ValueError(
            f"OpenAPI spec at {spec_url} must decode to a JSON object, got {type(document).__name__}."
        )

    logger.info(
        "Spec downloaded successfully (status=%s, bytes=%d, paths=%d)",
        status,
        len(raw_bytes),
        len(document.get("paths", {})) if isinstance(document.get("paths"), dict) else 0,
    )
    return document
