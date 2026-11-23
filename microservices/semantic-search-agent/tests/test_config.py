"""Tests for configuration source precedence."""

from pathlib import Path

from app.core.config import Settings

YAML_CONTENT = """
matching:
  default_strategy: exact
  semantic_match:
    confidence_threshold: 0.85
cache:
  enabled: true
"""


def _write_yaml(tmp_path: Path) -> Path:
    path = tmp_path / "service_config.yaml"
    path.write_text(YAML_CONTENT)
    return path


def test_yaml_values_used_when_env_unset(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CONFIDENCE_THRESHOLD", raising=False)
    monkeypatch.delenv("CACHE_ENABLED", raising=False)

    settings = Settings.from_yaml(_write_yaml(tmp_path))

    assert settings.confidence_threshold == 0.85
    assert settings.cache_enabled is True


def test_env_overrides_yaml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONFIDENCE_THRESHOLD", "0.99")
    monkeypatch.setenv("CACHE_ENABLED", "false")

    settings = Settings.from_yaml(_write_yaml(tmp_path))

    assert settings.confidence_threshold == 0.99
    assert settings.cache_enabled is False


def test_dotenv_overrides_yaml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CONFIDENCE_THRESHOLD", raising=False)
    (tmp_path / ".env").write_text("CONFIDENCE_THRESHOLD=0.95\n")

    settings = Settings.from_yaml(_write_yaml(tmp_path))

    assert settings.confidence_threshold == 0.95
