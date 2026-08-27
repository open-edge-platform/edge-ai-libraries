import importlib

import pytest

from src import config as config_module


@pytest.fixture(autouse=True)
def restore_config_module(monkeypatch):
    yield
    monkeypatch.delenv("AGENT_MODE", raising=False)
    importlib.reload(config_module)


@pytest.mark.parametrize(
    ("value", "default", "expected"),
    [
        ("true", False, True),
        ("1", False, True),
        ("yes", False, True),
        ("false", True, False),
        ("0", True, False),
        ("no", True, False),
        ("", True, True),
    ],
)
def test_bool_parses_expected_values(monkeypatch, value, default, expected):
    monkeypatch.setenv("TEST_BOOL", value)
    assert config_module._bool("TEST_BOOL", default) is expected


def test_int_returns_parsed_value(monkeypatch):
    monkeypatch.setenv("TEST_INT", "42")
    assert config_module._int("TEST_INT", 7) == 42


def test_int_returns_default_for_invalid_value(monkeypatch):
    monkeypatch.setenv("TEST_INT", "invalid")
    assert config_module._int("TEST_INT", 7) == 7


def test_float_returns_parsed_value(monkeypatch):
    monkeypatch.setenv("TEST_FLOAT", "3.14")
    assert config_module._float("TEST_FLOAT", 1.5) == pytest.approx(3.14)


def test_float_returns_default_for_invalid_value(monkeypatch):
    monkeypatch.setenv("TEST_FLOAT", "invalid")
    assert config_module._float("TEST_FLOAT", 1.5) == pytest.approx(1.5)


def test_settings_agent_mode_defaults_to_true(monkeypatch):
    monkeypatch.delenv("AGENT_MODE", raising=False)
    reloaded = importlib.reload(config_module)

    assert reloaded.settings.AGENT_MODE is True


def test_settings_agent_mode_honors_env_override(monkeypatch):
    monkeypatch.setenv("AGENT_MODE", "false")
    reloaded = importlib.reload(config_module)

    assert reloaded.settings.AGENT_MODE is False

