# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Shared pytest fixtures for VSS functional tests.

All tests target the nginx gateway (default http://localhost:12345).
Override the host with --host on the CLI or the VSS_HOST env variable.
"""

import os
import pathlib
import time

import pytest
import requests

# ──────────────────────────────────────────────────────────────────────────────
# Path constants — always absolute so pytest can be run from any directory.
# __file__ is this conftest.py file; .parent is the test-functional/ folder.
# ──────────────────────────────────────────────────────────────────────────────
TEST_FUNCTIONAL_DIR = pathlib.Path(__file__).parent
TEST_VIDEO_PATH = TEST_FUNCTIONAL_DIR / "test-data" / "car-detection.mp4"
TEST_NONVIDEO_PATH = TEST_FUNCTIONAL_DIR / "test-data" / "not-a-video.txt"


def pytest_addoption(parser):
    parser.addoption(
        "--host",
        action="store",
        default=os.getenv("VSS_HOST", "http://localhost:12345"),
        help="Base URL of the VSS nginx gateway (default: http://localhost:12345).",
    )
    parser.addoption(
        "--health-timeout",
        action="store",
        type=float,
        default=float(os.getenv("VSS_HEALTH_TIMEOUT", "120")),
        help="Seconds to wait for the stack to become healthy (default: 120).",
    )


@pytest.fixture(scope="session")
def base_url(pytestconfig):
    """Root URL of the VSS nginx gateway, e.g. http://localhost:12345."""
    return pytestconfig.getoption("host").rstrip("/")


@pytest.fixture(scope="session")
def health_timeout(pytestconfig):
    return pytestconfig.getoption("health_timeout")


@pytest.fixture(scope="session")
def vss_health(base_url, health_timeout):
    health_url = f"{base_url}/manager/health"
    deadline = time.time() + health_timeout
    while time.time() < deadline:
        try:
            response = requests.get(health_url, timeout=10)
            if response.status_code == 200:
                return True
        except requests.exceptions.RequestException:
            pass
        time.sleep(5)
    return False


@pytest.fixture(scope="session")
def uploaded_video_id(base_url, vss_health):
    if not vss_health:
        pytest.skip("VSS stack is not healthy — skipping video upload fixture.")

    assert TEST_VIDEO_PATH.exists(), (
        f"Test video not found: {TEST_VIDEO_PATH}\n"
        "Make sure test-data/car-detection.mp4 exists in the test-functional/ folder."
    )

    with open(TEST_VIDEO_PATH, "rb") as video_file:
        response = requests.post(
            f"{base_url}/manager/videos",
            files={"video": ("car-detection.mp4", video_file, "video/mp4")},
            timeout=60,
        )

    assert response.status_code in (200, 201), (
        f"Video upload failed. Status: {response.status_code}. "
        f"Response: {response.text}"
    )

    body = response.json()
    video_id = body.get("videoId")

    assert video_id, (
        f"Upload succeeded but response has no 'videoId': {body}"
    )

    return video_id
