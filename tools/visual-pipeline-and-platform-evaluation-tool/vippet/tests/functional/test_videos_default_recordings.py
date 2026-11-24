# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Functional tests for the optional sample video endpoints:

- ``GET /videos/default-recordings``
- ``POST /videos/download-default``
- ``POST /videos/convert-hevc``

Only the listing and rejection paths are exercised so the suite does not
depend on external download hosts or on HEVC encoder availability.

Tests are marked ``smoke`` since they only make simple API queries.
"""

import uuid

import pytest
import requests

from helpers.config import BASE_URL

_DOWNLOAD_STATES = {
    "available",
    "queued",
    "downloading",
    "downloaded",
    "failed",
    "conflict",
}
_CONVERSION_STATES = {
    "not_converted",
    "queued",
    "converting",
    "converted",
    "failed",
    "conflict",
    "unsupported",
}


def _fetch_default_recordings(session: requests.Session) -> list[dict]:
    response = session.get(f"{BASE_URL}/videos/default-recordings", timeout=30)
    assert response.status_code == 200, (
        f"GET /videos/default-recordings returned {response.status_code}: "
        f"{response.text}"
    )
    payload = response.json()
    assert isinstance(payload, list)
    return payload


def _unknown_filename() -> str:
    return f"not_a_sample_{uuid.uuid4().hex[:8]}.mp4"


@pytest.mark.smoke
def test_default_recordings_listing_schema(http_client: requests.Session) -> None:
    """Every listed sample exposes valid download and conversion states."""
    recordings = _fetch_default_recordings(http_client)

    for item in recordings:
        assert item["filename"]
        assert item["hevc_filename"]
        assert item["hevc_filename"] != item["filename"]
        assert isinstance(item["source"], str)
        assert item["status"] in _DOWNLOAD_STATES, item
        assert item["conversion_status"] in _CONVERSION_STATES, item


@pytest.mark.smoke
def test_download_default_unknown_filename_returns_404(
    http_client: requests.Session,
) -> None:
    response = http_client.post(
        f"{BASE_URL}/videos/download-default",
        json={"filename": _unknown_filename()},
        timeout=30,
    )
    assert response.status_code == 404, response.text


@pytest.mark.smoke
def test_download_default_missing_filename_returns_422(
    http_client: requests.Session,
) -> None:
    response = http_client.post(
        f"{BASE_URL}/videos/download-default", json={}, timeout=30
    )
    assert response.status_code == 422, response.text


@pytest.mark.smoke
def test_convert_hevc_unknown_filename_returns_404(
    http_client: requests.Session,
) -> None:
    response = http_client.post(
        f"{BASE_URL}/videos/convert-hevc",
        json={"filename": _unknown_filename()},
        timeout=30,
    )
    assert response.status_code == 404, response.text


@pytest.mark.smoke
def test_convert_hevc_before_download_returns_409(
    http_client: requests.Session,
) -> None:
    """Converting a sample that has not been downloaded yet is rejected."""
    recordings = _fetch_default_recordings(http_client)
    not_downloaded = next((r for r in recordings if r["status"] == "available"), None)
    if not_downloaded is None:
        pytest.skip("No sample video in 'available' state to test against")

    response = http_client.post(
        f"{BASE_URL}/videos/convert-hevc",
        json={"filename": not_downloaded["filename"]},
        timeout=30,
    )
    assert response.status_code == 409, response.text
