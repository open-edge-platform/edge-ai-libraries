# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for on-demand single-frame extraction (``/media/frame``).

A tiny synthetic MP4 is generated with PyAV so the real decode/seek/crop path is
exercised end to end; only the storage lookup (``resolve_media_source``) is
mocked, keeping the test query-agnostic and offline.
"""

import base64
import io
from dataclasses import dataclass
from typing import Iterator, Optional

import av
import numpy as np
import pytest

from src.common import DataPrepException
from src.core import frame_capture


# --- synthetic media -------------------------------------------------------

#: Solid RGB colors, one per second, so a decoded frame's dominant color tells
#: us which timestamp was returned.
_SECOND_COLORS = [
    (200, 0, 0),    # t in [0,1)  -> red
    (0, 200, 0),    # t in [1,2)  -> green
    (0, 0, 200),    # t in [2,3)  -> blue
]
_WIDTH, _HEIGHT, _FPS, _SECONDS = 64, 48, 10, len(_SECOND_COLORS)


def _make_mp4_bytes() -> bytes:
    """Encode a short H.264 MP4 whose color changes every second."""
    buffer = io.BytesIO()
    with av.open(buffer, mode="w", format="mp4") as container:
        stream = container.add_stream("libx264", rate=_FPS)
        stream.width = _WIDTH
        stream.height = _HEIGHT
        stream.pix_fmt = "yuv420p"
        for i in range(_FPS * _SECONDS):
            color = _SECOND_COLORS[min(i // _FPS, _SECONDS - 1)]
            arr = np.empty((_HEIGHT, _WIDTH, 3), dtype=np.uint8)
            arr[:, :] = color
            frame = av.VideoFrame.from_ndarray(arr, format="rgb24")
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return buffer.getvalue()


_MP4_BYTES = _make_mp4_bytes()


@dataclass
class _FakeSource:
    """Minimal stand-in for ``MediaSource`` streaming the synthetic clip."""

    filename: str = "clip.mp4"

    def stream(self, bucket_name: str, offset: int = 0, length: Optional[int] = None) -> Iterator[bytes]:
        data = _MP4_BYTES[offset : (offset + length) if length is not None else None]
        yield data


@pytest.fixture
def patched_resolve(monkeypatch):
    """Point frame extraction at the synthetic clip regardless of inputs."""
    monkeypatch.setattr(
        frame_capture, "resolve_media_source", lambda *a, **k: _FakeSource()
    )


def _dominant_color(jpeg_bytes: bytes):
    from PIL import Image

    img = Image.open(io.BytesIO(jpeg_bytes)).convert("RGB")
    arr = np.asarray(img).reshape(-1, 3).mean(axis=0)
    return arr


# --- helper-level tests ----------------------------------------------------


def test_extract_frame_returns_jpeg_with_expected_size(patched_resolve):
    frame = frame_capture.extract_frame(
        bucket_name="b", video_id="v", timestamp=0.0
    )
    assert frame.jpeg_bytes[:2] == b"\xff\xd8"  # JPEG SOI marker
    assert (frame.width, frame.height) == (_WIDTH, _HEIGHT)
    assert frame.cropped is False


def test_extract_frame_seeks_to_requested_timestamp(patched_resolve):
    """Frame at ~2.5s should be the blue second, not the red first."""
    frame = frame_capture.extract_frame(
        bucket_name="b", video_id="v", timestamp=2.5
    )
    r, g, b = _dominant_color(frame.jpeg_bytes)
    assert b > r and b > g


def test_extract_frame_past_end_returns_last_frame(patched_resolve):
    frame = frame_capture.extract_frame(
        bucket_name="b", video_id="v", timestamp=999.0
    )
    # Does not raise; returns the final (blue) frame.
    r, g, b = _dominant_color(frame.jpeg_bytes)
    assert b > r and b > g


def test_extract_frame_crop_reduces_dimensions(patched_resolve):
    frame = frame_capture.extract_frame(
        bucket_name="b", video_id="v", timestamp=0.0, crop_bbox=[10, 5, 40, 30]
    )
    assert frame.cropped is True
    assert frame.width == 30 and frame.height == 25


def test_extract_frame_crop_clamped_to_bounds(patched_resolve):
    frame = frame_capture.extract_frame(
        bucket_name="b", video_id="v", timestamp=0.0, crop_bbox=[-100, -100, 9999, 9999]
    )
    assert frame.cropped is True
    assert frame.width == _WIDTH and frame.height == _HEIGHT


def test_extract_frame_degenerate_crop_ignored(patched_resolve):
    frame = frame_capture.extract_frame(
        bucket_name="b", video_id="v", timestamp=0.0, crop_bbox=[20, 20, 20, 20]
    )
    assert frame.cropped is False
    assert frame.width == _WIDTH and frame.height == _HEIGHT


def test_extract_frame_rejects_negative_timestamp(patched_resolve):
    with pytest.raises(DataPrepException) as exc:
        frame_capture.extract_frame(bucket_name="b", video_id="v", timestamp=-1.0)
    assert exc.value.status_code == 400


@pytest.mark.parametrize("raw", ["1,2,3", "a,b,c,d", "1,2,3,4,5"])
def test_parse_crop_bbox_rejects_bad_input(raw):
    with pytest.raises(DataPrepException):
        frame_capture.parse_crop_bbox(raw)


def test_parse_crop_bbox_valid_and_empty():
    assert frame_capture.parse_crop_bbox("1, 2, 3, 4") == [1.0, 2.0, 3.0, 4.0]
    assert frame_capture.parse_crop_bbox("") is None
    assert frame_capture.parse_crop_bbox(None) is None


# --- endpoint tests --------------------------------------------------------


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(
        "src.core.frame_capture.resolve_media_source", lambda *a, **k: _FakeSource()
    )
    from fastapi.testclient import TestClient

    from src.main import app

    return TestClient(app)


def test_frame_endpoint_returns_raw_jpeg(client):
    resp = client.get("/media/frame", params={"video_id": "vid1", "timestamp": 0.0})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.content[:2] == b"\xff\xd8"
    assert resp.headers["X-Frame-Width"] == str(_WIDTH)
    assert resp.headers["X-Frame-Variant"] == "full"


def test_frame_endpoint_json_variant(client):
    resp = client.get(
        "/media/frame",
        params={"video_id": "vid1", "timestamp": 1.5, "format": "json"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mime"] == "image/jpeg"
    decoded = base64.b64decode(body["image_base64"])
    assert decoded[:2] == b"\xff\xd8"
    assert body["frame"]["video_id"] == "vid1"
    assert body["frame"]["requested_timestamp"] == 1.5
    assert body["frame"]["variant"] == "full"


def test_frame_endpoint_crop_variant(client):
    resp = client.get(
        "/media/frame",
        params={
            "video_id": "vid1",
            "timestamp": 0.0,
            "variant": "crop",
            "crop_bbox": "10,5,40,30",
            "format": "json",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["frame"]["cropped"] is True
    assert body["frame"]["width"] == 30 and body["frame"]["height"] == 25


def test_frame_endpoint_rejects_bad_variant(client):
    resp = client.get(
        "/media/frame",
        params={"video_id": "vid1", "timestamp": 0.0, "variant": "thumbnail"},
    )
    assert resp.status_code == 422


def test_frame_endpoint_rejects_bad_crop_bbox(client):
    resp = client.get(
        "/media/frame",
        params={
            "video_id": "vid1",
            "timestamp": 0.0,
            "variant": "crop",
            "crop_bbox": "1,2,3",
        },
    )
    assert resp.status_code == 400
