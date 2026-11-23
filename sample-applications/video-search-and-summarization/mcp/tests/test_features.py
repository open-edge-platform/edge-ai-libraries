# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for the startup feature read."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from src.clients import VssClient, VssError
from src.features import detect_features
from tests.fakes import BASE_URL

pytestmark = pytest.mark.anyio


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> VssClient:
    return VssClient(
        BASE_URL,
        client=httpx.AsyncClient(
            base_url=BASE_URL, transport=httpx.MockTransport(handler)
        ),
    )


def _reporting(
    summary: str, search: str, image_search_enabled: bool = False
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "summary": summary,
                "search": search,
                "imageSearchEnabled": image_search_enabled,
            },
        )

    return handler


async def test_reads_the_deployment() -> None:
    features = await detect_features(_client(_reporting("FEATURE_ON", "FEATURE_OFF")))
    assert features.summary is True
    assert features.search is False
    assert features.describe() == "summary"


async def test_anything_but_feature_on_is_off() -> None:
    """Matches features.service.ts, which compares the string exactly."""
    features = await detect_features(_client(_reporting("FEATURE_ON", "")))
    assert features.search is False


async def test_deployment_with_neither_feature_is_reported_not_rejected() -> None:
    """Library tools still work, so this is a shape, not a failure."""
    features = await detect_features(_client(_reporting("FEATURE_OFF", "FEATURE_OFF")))
    assert features.describe() == "none"


async def test_reads_whether_a_frame_embedding_index_is_deployed() -> None:
    """Only imageSearchEnabled distinguishes dual mode from unified mode."""
    dual = await detect_features(
        _client(_reporting("FEATURE_ON", "FEATURE_ON", image_search_enabled=True))
    )
    unified = await detect_features(
        _client(_reporting("FEATURE_ON", "FEATURE_ON", image_search_enabled=False))
    )
    assert dual.image_search_enabled is True
    assert unified.image_search_enabled is False


async def test_unreachable_backend_raises() -> None:
    """Fatal at startup; guessing would expose the wrong tool surface."""

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(VssError, match="Could not reach VSS"):
        await detect_features(_client(refuse))
