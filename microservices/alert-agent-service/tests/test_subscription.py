# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import textwrap

from src.core.subscription import load_subscription_config


def _write(tmp_path, content):
    p = tmp_path / "config.yaml"
    p.write_text(textwrap.dedent(content))
    return str(p)


def test_missing_file_returns_empty(tmp_path):
    cfg = load_subscription_config(str(tmp_path / "nope.yaml"))
    assert cfg.subscriptions == []
    assert cfg.default is None


def test_loads_explicit_subscription(tmp_path):
    path = _write(tmp_path, """
        subscriptions:
          - alert_name: vehicle
            tools: [log_alert, capture_snapshot]
            dedup:
              enabled: true
              strategy: field_hash
              fields: [source_id]
              window_seconds: 30
    """)
    cfg = load_subscription_config(path)
    entry = cfg.get("vehicle")
    assert entry is not None
    assert entry.tools == ["log_alert", "capture_snapshot"]
    assert entry.dedup["window_seconds"] == 30


def test_default_template_parsed(tmp_path):
    path = _write(tmp_path, """
        default:
          tools: [log_alert]
          dedup:
            enabled: true
            strategy: field_hash
            fields: [source_id]
            window_seconds: 45
        subscriptions:
          - alert_name: vehicle
            tools: [log_alert]
    """)
    cfg = load_subscription_config(path)
    assert cfg.default is not None
    assert cfg.default.alert_name == "__default__"
    assert cfg.default.dedup["window_seconds"] == 45


def test_resolve_exact_match_wins_over_default(tmp_path):
    path = _write(tmp_path, """
        default:
          tools: [log_alert]
        subscriptions:
          - alert_name: vehicle
            tools: [log_alert, capture_snapshot]
    """)
    cfg = load_subscription_config(path)
    resolved = cfg.resolve("vehicle")
    assert resolved.alert_name == "vehicle"
    assert resolved.tools == ["log_alert", "capture_snapshot"]


def test_resolve_falls_back_to_default_for_unknown_alert(tmp_path):
    path = _write(tmp_path, """
        default:
          tools: [log_alert]
          dedup:
            enabled: true
            strategy: field_hash
            fields: [source_id]
            window_seconds: 60
        subscriptions:
          - alert_name: vehicle
            tools: [log_alert]
    """)
    cfg = load_subscription_config(path)
    # "Loitering" is not an explicit subscription — should get the default.
    resolved = cfg.resolve("Loitering", None)
    assert resolved is cfg.default
    assert resolved.dedup["window_seconds"] == 60


def test_resolve_returns_none_when_no_default(tmp_path):
    path = _write(tmp_path, """
        subscriptions:
          - alert_name: vehicle
            tools: [log_alert]
    """)
    cfg = load_subscription_config(path)
    assert cfg.resolve("Unknown") is None


def test_resolve_prefers_alert_name_then_alert_type(tmp_path):
    path = _write(tmp_path, """
        subscriptions:
          - alert_name: CONCEALMENT
            tools: [log_alert, trigger_webhook]
    """)
    cfg = load_subscription_config(path)
    # alert_name miss, alert_type hit
    resolved = cfg.resolve("nope", "CONCEALMENT")
    assert resolved is not None
    assert resolved.alert_name == "CONCEALMENT"
