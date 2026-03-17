"""Functional tests for the cameras endpoints."""

import logging
from uuid import uuid4

import pytest
import requests

from helpers.api_helpers import fetch_cameras
from helpers.config import BASE_URL

logger = logging.getLogger(__name__)

REQUIRED_CAMERA_KEYS: set[str] = {"device_id", "device_name", "device_type", "details"}
VALID_DEVICE_TYPES: set[str] = {"USB", "NETWORK"}


@pytest.mark.smoke
def test_cameras_endpoint_returns_list(http_client: requests.Session) -> None:
    """Calls GET /cameras and asserts the response is 200 with a list (may be empty)."""
    response = http_client.get(f"{BASE_URL}/cameras", timeout=30)

    assert response.status_code == 200, (
        f"Expected 200 from /cameras, got {response.status_code}, body={response.text}"
    )
    assert isinstance(response.json(), list), "Cameras response must be a list"
    logger.info("Cameras endpoint returned %d camera(s)", len(response.json()))


@pytest.mark.smoke
def test_cameras_endpoint_returns_valid_structure(
    http_client: requests.Session,
) -> None:
    """Asserts every camera object returned by GET /cameras contains all required fields with a valid device_type."""
    cameras = fetch_cameras(http_client)

    if not cameras:
        pytest.skip("No cameras available in current environment")

    for camera in cameras:
        assert isinstance(camera, dict), "Each camera entry must be an object"
        assert REQUIRED_CAMERA_KEYS.issubset(camera.keys()), (
            f"Camera entry missing required keys: {REQUIRED_CAMERA_KEYS - camera.keys()}"
        )
        assert camera["device_type"] in VALID_DEVICE_TYPES, (
            f"Unexpected device_type {camera['device_type']!r}; "
            f"expected one of {VALID_DEVICE_TYPES}"
        )


@pytest.mark.smoke
def test_get_camera_by_id_returns_correct_camera(
    http_client: requests.Session,
) -> None:
    """Fetches the first camera from GET /cameras then retrieves it by ID and asserts the device_id matches."""
    cameras = fetch_cameras(http_client)

    if not cameras:
        pytest.skip("No cameras available in current environment")

    camera_id = cameras[0]["device_id"]
    response = http_client.get(f"{BASE_URL}/cameras/{camera_id}", timeout=30)

    assert response.status_code == 200, (
        f"Expected 200 for GET /cameras/{camera_id}, "
        f"got {response.status_code}, body={response.text}"
    )
    assert response.json().get("device_id") == camera_id, (
        f"Returned camera device_id does not match requested id={camera_id}"
    )


@pytest.mark.smoke
def test_get_camera_by_nonexistent_id_returns_404(
    http_client: requests.Session,
) -> None:
    """Calls GET /cameras/{id} with a random non-existent ID and asserts the response is 404."""
    nonexistent_id = f"does-not-exist-{uuid4().hex[:8]}"
    response = http_client.get(f"{BASE_URL}/cameras/{nonexistent_id}", timeout=30)

    assert response.status_code == 404, (
        f"Expected 404 for non-existent camera id={nonexistent_id}, "
        f"got {response.status_code}, body={response.text}"
    )


@pytest.mark.smoke
def test_load_camera_profiles_for_nonexistent_camera_returns_400(
    http_client: requests.Session,
) -> None:
    """Calls POST /cameras/{id}/profiles with a valid-format but non-existent camera_id and asserts the response is 400."""
    # Network camera IDs follow the pattern "network-camera-<ip>-<port>"
    nonexistent_camera_id = "network-camera-192.0.2.1-80"
    response = http_client.post(
        f"{BASE_URL}/cameras/{nonexistent_camera_id}/profiles",
        json={"username": "admin", "password": "admin"},
        timeout=30,
    )

    assert response.status_code == 400, (
        f"Expected 400 for non-existent camera profiles request, "
        f"got {response.status_code}, body={response.text}"
    )


@pytest.mark.smoke
def test_load_camera_profiles_with_invalid_camera_id_format_returns_400(
    http_client: requests.Session,
) -> None:
    """Calls POST /cameras/{id}/profiles with a malformed camera_id and asserts the response is 400."""
    malformed_id = "not-a-valid-camera-id"
    response = http_client.post(
        f"{BASE_URL}/cameras/{malformed_id}/profiles",
        json={"username": "admin", "password": "admin"},
        timeout=30,
    )

    assert response.status_code == 400, (
        f"Expected 400 for malformed camera id={malformed_id!r}, "
        f"got {response.status_code}, body={response.text}"
    )
