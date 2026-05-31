# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Storage client — HTTP calls to the storage-service REST API."""

import os
import logging
from typing import Optional
import requests

log = logging.getLogger(__name__)

_STORAGE_URL = os.environ.get("STORAGE_SERVICE_URL", "http://apm-storage:5001")
_TIMEOUT = 10


def get_detections(
    label: str | None = None,
    min_confidence: float | None = None,
    limit: int | None = None,
) -> list[dict]:
    params: dict = {}
    if label:
        params["label"] = label
    if min_confidence is not None:
        params["min_confidence"] = min_confidence
    if limit is not None:
        params["limit"] = limit
    r = requests.get(f"{_STORAGE_URL}/detections", params=params, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()


def get_summary() -> dict:
    r = requests.get(f"{_STORAGE_URL}/detections/summary", timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()


def post_detection(payload: dict) -> dict:
    r = requests.post(f"{_STORAGE_URL}/detections", json=payload, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()
