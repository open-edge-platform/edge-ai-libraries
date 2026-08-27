# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import base64
from pathlib import Path

import httpx
import pytest

from src.config import settings
from src.main import app
from src.tools.snapshot_tool import capture_snapshot


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)
PNG_BASE64 = base64.b64encode(PNG_BYTES).decode("ascii")


@pytest.mark.asyncio
async def test_capture_snapshot_decodes_base64(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "SNAPSHOT_DIR", str(tmp_path))

    result = await capture_snapshot(
        source_id="cam-01",
        alert_name="Fire Detection",
        image_bytes=PNG_BASE64,
        mime_type="image/png",
    )

    assert result["status"] == "saved"
    assert Path(result["path"]).read_bytes() == PNG_BYTES


@pytest.mark.asyncio
async def test_capture_snapshot_rejects_invalid_base64(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "SNAPSHOT_DIR", str(tmp_path))

    with pytest.raises(ValueError, match="valid Base64"):
        await capture_snapshot(
            source_id="cam-01",
            image_bytes="not-valid-base64!",
            mime_type="image/png",
        )

    assert list(tmp_path.rglob("*")) == []


@pytest.mark.asyncio
async def test_capture_snapshot_keeps_parent_source_inside_snapshot_dir(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(settings, "SNAPSHOT_DIR", str(tmp_path))

    result = await capture_snapshot(
        source_id="..",
        image_bytes=PNG_BASE64,
        mime_type="image/png",
    )

    snapshot_path = Path(result["path"]).resolve()
    assert snapshot_path.is_relative_to(tmp_path.resolve())
    assert snapshot_path.read_bytes() == PNG_BYTES


@pytest.mark.asyncio
async def test_capture_snapshot_endpoint_accepts_base64(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "SNAPSHOT_DIR", str(tmp_path))
    transport = httpx.ASGITransport(app=app)
    payload = {
        "parameters": {
            "source_id": "cam-01",
            "alert_name": "Fire Detection",
            "image_bytes": PNG_BASE64,
            "mime_type": "image/png",
        }
    }

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"{settings.API_V1_PREFIX}/tools/capture_snapshot/invoke",
            json=payload,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert Path(body["result"]["path"]).read_bytes() == PNG_BYTES
