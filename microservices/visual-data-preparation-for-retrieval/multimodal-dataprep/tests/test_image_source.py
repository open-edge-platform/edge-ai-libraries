# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the JSON image-source loader (``src.core.image_ingest``)."""

import base64
import io

import pytest
from PIL import Image

from src.common import DataPrepException
from src.core import image_ingest
from src.core.image_ingest import (
    MAX_IMAGE_BYTES,
    decode_base64_image,
    fetch_image_from_url,
    load_image_source,
    resolve_image_filename,
    sniff_image_extension,
)


def _png_bytes(size=(16, 16)):
    buf = io.BytesIO()
    Image.new("RGB", size, (0, 128, 255)).save(buf, format="PNG")
    return buf.getvalue()


def test_decode_bare_base64():
    raw = _png_bytes()
    b64 = base64.b64encode(raw).decode()
    assert decode_base64_image(b64) == raw


def test_decode_data_url_prefix_stripped():
    raw = _png_bytes()
    b64 = base64.b64encode(raw).decode()
    data_url = f"data:image/png;base64,{b64}"
    assert decode_base64_image(data_url) == raw


def test_decode_invalid_base64_raises():
    with pytest.raises(DataPrepException) as ei:
        decode_base64_image("!!!not-base64!!!")
    assert ei.value.status_code == 400


def test_decode_oversized_base64_precheck_raises():
    # A base64 string whose decoded size exceeds the cap is rejected pre-decode.
    oversized = "A" * ((MAX_IMAGE_BYTES + 10) * 4 // 3 + 8)
    with pytest.raises(DataPrepException) as ei:
        decode_base64_image(oversized)
    assert ei.value.status_code == 413


def test_sniff_extension_png():
    assert sniff_image_extension(_png_bytes()) == ".png"


def test_sniff_rejects_non_image():
    with pytest.raises(DataPrepException) as ei:
        sniff_image_extension(b"totally not an image")
    assert ei.value.status_code == 400


@pytest.mark.parametrize(
    "given,url,ext,expected",
    [
        ("cat.jpeg", None, ".png", "cat.png"),
        (None, "http://h/x/dog.jpg", ".png", "dog.png"),
        ("dir/../evil.png", None, ".png", "evil.png"),
    ],
)
def test_resolve_image_filename(given, url, ext, expected):
    assert resolve_image_filename(given, url, ext) == expected


def test_resolve_image_filename_generated_when_no_hint():
    name = resolve_image_filename(None, None, ".png")
    assert name.startswith("image_") and name.endswith(".png")


@pytest.mark.parametrize("url", ["ftp://h/x.png", "file:///etc/passwd", "notaurl", ""])
def test_fetch_rejects_non_http_scheme(url):
    with pytest.raises(DataPrepException) as ei:
        fetch_image_from_url(url)
    assert ei.value.status_code == 400


class _FakeResponse:
    def __init__(self, chunks, headers=None, status=200):
        self._chunks = chunks
        self.headers = headers or {}
        self._status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        if self._status >= 400:
            import requests

            raise requests.HTTPError("bad status")

    def iter_content(self, chunk_size=None):
        for c in self._chunks:
            yield c


def test_fetch_streams_and_returns_bytes(monkeypatch):
    raw = _png_bytes()
    monkeypatch.setattr(
        image_ingest.requests, "get", lambda *a, **k: _FakeResponse([raw])
    )
    assert fetch_image_from_url("https://example.com/a.png") == raw


def test_fetch_aborts_when_stream_exceeds_cap(monkeypatch):
    big = b"x" * (1024 * 1024)
    # Enough chunks to exceed MAX_IMAGE_BYTES mid-stream.
    chunks = [big] * (MAX_IMAGE_BYTES // len(big) + 2)
    monkeypatch.setattr(
        image_ingest.requests, "get", lambda *a, **k: _FakeResponse(chunks)
    )
    with pytest.raises(DataPrepException) as ei:
        fetch_image_from_url("https://example.com/big.png")
    assert ei.value.status_code == 413


def test_load_image_source_base64_end_to_end():
    raw = _png_bytes()
    b64 = base64.b64encode(raw).decode()
    content, filename = load_image_source("image_base64", image_base64=b64, filename="pic.gif")
    assert content == raw
    assert filename == "pic.png"  # extension corrected to the sniffed format


def test_load_image_source_unknown_type():
    with pytest.raises(DataPrepException) as ei:
        load_image_source("image_bogus")
    assert ei.value.status_code == 400
