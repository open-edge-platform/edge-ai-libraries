"""Tests for config loading."""

from __future__ import annotations

import os
import pytest

from src.core.config import load_config


class TestLoadConfig:
    def test_load_valid_config(self, config_file):
        """Loads config with correct retry settings and subscription count."""
        config = load_config(config_file)

        assert config.service.retry_attempts == 2
        assert config.service.retry_interval_seconds == 1
        assert len(config.subscriptions) == 3

    def test_concealment_subscription(self, config_file):
        """Parses CONCEALMENT subscription with dedup fields and hash config."""
        config = load_config(config_file)
        sub = config.get_subscription("CONCEALMENT")

        assert sub is not None
        assert sub.dedup.enabled is True
        assert sub.dedup.strategy == "field_hash"
        assert sub.dedup.fields == ["metadata.poi_id", "metadata.camera_id"]
        assert sub.dedup.window_seconds == 30
        assert sub.dedup.hash.algorithm == "sha1"
        assert sub.dedup.hash.truncate == 16

    def test_intrusion_dedup_disabled(self, config_file):
        """INTRUSION subscription has dedup disabled."""
        config = load_config(config_file)
        sub = config.get_subscription("INTRUSION")

        assert sub is not None
        assert sub.dedup.enabled is False

    def test_unknown_subscription_returns_none(self, config_file):
        """Looking up a non-existent subscription returns None."""
        config = load_config(config_file)
        assert config.get_subscription("NONEXISTENT") is None

    def test_missing_config_file_raises(self, tmp_path):
        """Raises FileNotFoundError for a missing YAML file."""
        with pytest.raises(FileNotFoundError):
            load_config(str(tmp_path / "nonexistent.yaml"))

    def test_env_var_resolution(self, tmp_path):
        """Resolves ${ENV_VAR} placeholders in YAML values."""
        os.environ["TEST_WEBHOOK_URL"] = "http://example.com/hook"
        saved_dh = os.environ.pop("DELIVERY_HANDLERS", None)
        yaml_content = """\
service:
  retry_attempts: 1
  retry_interval_seconds: 1

subscriptions:
  - alert_type: TEST
    dedup:
      enabled: false
    delivery:
      - type: webhook
        url: ${TEST_WEBHOOK_URL}
"""
        p = tmp_path / "env_config.yaml"
        p.write_text(yaml_content)

        config = load_config(str(p))
        sub = config.get_subscription("TEST")
        assert sub is not None
        assert sub.delivery[0].url == "http://example.com/hook"

        del os.environ["TEST_WEBHOOK_URL"]
        if saved_dh is not None:
            os.environ["DELIVERY_HANDLERS"] = saved_dh
