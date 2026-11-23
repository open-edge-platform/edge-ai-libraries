# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared pytest configuration for the VSS MCP server tests.

Run the suite from ``mcp/`` with::

    uv run pytest              # everything
    uv run pytest tests/test_tools.py -k search   # a subset

The tests are plain pytest: ``assert``, fixtures and ``parametrize``. Async
tests use the anyio plugin that ships with anyio (a FastMCP dependency), so no
extra plugin is needed; mark a module with ``pytestmark = pytest.mark.anyio``.

The suite is hermetic: no test may reach a real VSS deployment.

Every backend call goes through :class:`tests.fakes.FakeVss`. A test that
forgets to inject it would otherwise pass or fail depending on whether VSS
happens to be running on the machine, so outbound connections and DNS lookups
fail loudly instead.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator

import pytest

from src.core.config import Settings
from src.tools import Deps
from tests.fakes import FakeVss, NetworkAccessError, make_settings


_LOCAL_FAMILIES = {getattr(socket, "AF_UNIX", None)} - {None}


def _refuse(*args: object, **kwargs: object) -> None:
    raise NetworkAccessError(
        "Tests must not use the network; inject tests.fakes.FakeVss().client()."
    )


@pytest.fixture(autouse=True, scope="session")
def _block_network() -> Iterator[None]:
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def guarded(original):
        def connect(self: socket.socket, address, *args, **kwargs):
            if self.family in _LOCAL_FAMILIES:
                return original(self, address, *args, **kwargs)
            _refuse()

        return connect

    patcher = pytest.MonkeyPatch()
    patcher.setattr(socket.socket, "connect", guarded(original_connect))
    patcher.setattr(socket.socket, "connect_ex", guarded(original_connect_ex))
    patcher.setattr(socket, "getaddrinfo", _refuse)
    patcher.setattr(socket, "create_connection", _refuse)
    try:
        yield
    finally:
        patcher.undo()


@pytest.fixture
def anyio_backend() -> str:
    """Run async tests on asyncio only; the server never runs on trio."""

    return "asyncio"


@pytest.fixture
def fake() -> FakeVss:
    """An empty fake Pipeline Manager; tests fill ``videos``/``states``/``hits``."""

    return FakeVss()


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def deps(fake: FakeVss, settings: Settings) -> Deps:
    """Tool dependencies wired to ``fake`` with every feature on."""

    return Deps(client=fake.client(), settings=settings)
