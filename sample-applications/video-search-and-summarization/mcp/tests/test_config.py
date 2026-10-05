# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for runtime configuration parsing."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from src.core.config import (
    _bool,
    _port,
    _positive_float,
    _read_env,
    _read_path,
    _read_vss_host,
    get_settings,
)


ENV_VARS = (
    "VSS_IP",
    "HOST_IP",
    "APP_HOST_PORT",
    "VSS_INDEX_STRATEGY",
    "MCP_HOST",
    "MCP_PORT",
    "MCP_PATH",
    "MCP_STATELESS_HTTP",
    "REQUEST_TIMEOUT",
    "POLL_INTERVAL",
    "DEFAULT_WAIT_SECONDS",
    "LOG_LEVEL",
    "T",
    "P",
    "B",
)


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    def setenv(**values: str) -> None:
        for name, value in values.items():
            monkeypatch.setenv(name, value)

    return setenv


# Host and primitive parsers


def test_requires_host_ip_or_vss_ip(env: Callable[..., None]) -> None:
    with pytest.raises(ValueError, match="Set HOST_IP"):
        _read_vss_host()


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({"HOST_IP": "192.0.2.10"}, "192.0.2.10"),
        ({"HOST_IP": "192.0.2.10", "VSS_IP": "vss.example.com"}, "vss.example.com"),
        ({"HOST_IP": "192.0.2.10", "VSS_IP": "  "}, "192.0.2.10"),
        ({"VSS_IP": "fe80::1"}, "[fe80::1]"),
        ({"VSS_IP": "[fe80::1]"}, "[fe80::1]"),
    ],
)
def test_reads_vss_host(
    env: Callable[..., None], values: dict[str, str], expected: str
) -> None:
    env(**values)
    assert _read_vss_host() == expected


@pytest.mark.parametrize("bad", ("http://host", "host:12345", "host/manager", "a b", "-x"))
def test_rejects_anything_but_a_bare_host(env: Callable[..., None], bad: str) -> None:
    env(VSS_IP=bad)
    with pytest.raises(ValueError, match="bare IP address"):
        _read_vss_host()


def test_positive_float_returns_default_when_unset(env: Callable[..., None]) -> None:
    assert _read_env("T", 60.0, _positive_float) == 60.0


def test_positive_float_parses_a_value(env: Callable[..., None]) -> None:
    env(T="12.5")
    assert _read_env("T", 60.0, _positive_float) == 12.5


@pytest.mark.parametrize(
    ("bad", "message"),
    [
        ("0", "greater than zero"),
        ("-1", "greater than zero"),
        ("nan", "T must be a finite number"),
        ("inf", "T must be a finite number"),
        ("soon", "valid number"),
    ],
)
def test_positive_float_rejects_invalid_values(
    env: Callable[..., None], bad: str, message: str
) -> None:
    env(T=bad)
    with pytest.raises(ValueError, match=message):
        _read_env("T", 60.0, _positive_float)


def test_port_returns_default_when_unset(env: Callable[..., None]) -> None:
    assert _read_env("P", 8000, _port) == 8000


@pytest.mark.parametrize(
    ("bad", "message"),
    [
        ("0", "between 1 and 65535"),
        ("70000", "between 1 and 65535"),
        ("80.5", "valid integer port"),
    ],
)
def test_port_rejects_invalid_values(
    env: Callable[..., None], bad: str, message: str
) -> None:
    env(P=bad)
    with pytest.raises(ValueError, match=message):
        _read_env("P", 8000, _port)


@pytest.mark.parametrize("value", ("1", "true", "TRUE", "yes", "on"))
def test_bool_accepts_the_documented_truthy_forms(
    env: Callable[..., None], value: str
) -> None:
    env(B=value)
    assert _read_env("B", False, _bool) is True


@pytest.mark.parametrize("value", ("0", "false", "No", "off"))
def test_bool_accepts_the_documented_falsy_forms(
    env: Callable[..., None], value: str
) -> None:
    env(B=value)
    assert _read_env("B", True, _bool) is False


def test_bool_rejects_anything_else(env: Callable[..., None]) -> None:
    env(B="maybe")
    with pytest.raises(ValueError, match="must be one of"):
        _read_env("B", False, _bool)


@pytest.mark.parametrize(("value", "expected"), [("mcp", "/mcp"), ("  ", "/mcp")])
def test_read_path_adds_leading_slash_and_defaults_when_blank(
    env: Callable[..., None], value: str, expected: str
) -> None:
    env(P=value)
    assert _read_path("P", "/mcp") == expected


# Settings assembly


def settings_with(env: Callable[..., None], **values: str):
    env(HOST_IP="host", **values)
    return get_settings()


def test_defaults_are_safe(env: Callable[..., None]) -> None:
    settings = settings_with(env)
    assert settings.vss_base_url == "http://host:12345/manager"
    assert settings.mcp_port == 8000
    assert settings.mcp_path == "/mcp"


def test_reads_overrides(env: Callable[..., None]) -> None:
    settings = settings_with(
        env,
        POLL_INTERVAL="2",
        DEFAULT_WAIT_SECONDS="120",
        MCP_PORT="9001",
    )
    assert settings.poll_interval_seconds == 2.0
    assert settings.default_wait_seconds == 120.0
    assert settings.mcp_port == 9001


@pytest.mark.parametrize(
    ("values", "base_url", "datastore_url"),
    [
        (
            {"HOST_IP": "192.0.2.10"},
            "http://192.0.2.10:12345/manager",
            "http://192.0.2.10:12345/datastore",
        ),
        (
            {"VSS_IP": "192.0.2.20", "APP_HOST_PORT": "23456"},
            "http://192.0.2.20:23456/manager",
            "http://192.0.2.20:23456/datastore",
        ),
    ],
)
def test_all_urls_come_from_the_gateway(
    env: Callable[..., None],
    values: dict[str, str],
    base_url: str,
    datastore_url: str,
) -> None:
    env(**values)
    settings = get_settings()
    assert settings.vss_base_url == base_url
    assert settings.vss_datastore_url == datastore_url


def test_index_strategy_defaults_to_auto(env: Callable[..., None]) -> None:
    assert settings_with(env).index_strategy == "auto"


def test_index_strategy_accepts_an_explicit_path(env: Callable[..., None]) -> None:
    assert settings_with(env, VSS_INDEX_STRATEGY="Embeddings").index_strategy == "embeddings"


def test_index_strategy_typo_fails_at_boot(env: Callable[..., None]) -> None:
    with pytest.raises(ValueError, match="VSS_INDEX_STRATEGY"):
        settings_with(env, VSS_INDEX_STRATEGY="sumary")
