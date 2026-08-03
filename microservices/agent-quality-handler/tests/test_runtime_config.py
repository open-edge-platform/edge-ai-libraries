# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest

from src.utility.runtime_config import ConfigurationError, load_runtime_settings


def test_defaults_are_standalone_fallback():
    settings = load_runtime_settings()

    assert settings.llm_mode == "fallback"
    assert settings.mqtt_enabled is True
    assert settings.mqtt_host == "mqtt-broker"
    assert settings.mqtt_qos == 1
    assert settings.mqtt_batch_client_id == "agent-quality-handler-batch"
    assert settings.mqtt_batch_topic == "apm/batch-complete"
    assert settings.mqtt_max_payload_bytes == 1_048_576
    assert settings.storage_connect_timeout_seconds == 3.0
    assert settings.storage_read_timeout_seconds == 10.0
    assert settings.storage_read_max_attempts == 3
    assert settings.storage_retry_backoff_seconds == 0.25


def test_external_integrations_are_configurable(monkeypatch):
    monkeypatch.setenv("STORAGE_SERVICE_URL", "https://storage.example.test/api")
    monkeypatch.setenv("STORAGE_CONNECT_TIMEOUT_SECONDS", "1.5")
    monkeypatch.setenv("STORAGE_READ_TIMEOUT_SECONDS", "20")
    monkeypatch.setenv("STORAGE_READ_MAX_ATTEMPTS", "5")
    monkeypatch.setenv("STORAGE_RETRY_BACKOFF_SECONDS", "0.5")
    monkeypatch.setenv("MQTT_HOST", "mqtt.example.test")
    monkeypatch.setenv("MQTT_PORT", "8883")
    monkeypatch.setenv("MQTT_USERNAME", "agent")
    monkeypatch.setenv("MQTT_PASSWORD", "secret")
    monkeypatch.setenv("MQTT_QOS", "2")
    monkeypatch.setenv("MQTT_BATCH_TOPIC", "pipelines/+/batch-complete")
    monkeypatch.setenv("MQTT_BATCH_CLIENT_ID", "aqh-batch-west")
    monkeypatch.setenv("MQTT_KEEPALIVE", "90")

    settings = load_runtime_settings()

    assert settings.storage_service_url == "https://storage.example.test/api"
    assert settings.storage_connect_timeout_seconds == 1.5
    assert settings.storage_read_timeout_seconds == 20.0
    assert settings.storage_read_max_attempts == 5
    assert settings.storage_retry_backoff_seconds == 0.5
    assert settings.mqtt_port == 8883
    assert settings.mqtt_username == "agent"
    assert settings.mqtt_qos == 2
    assert settings.mqtt_batch_topic == "pipelines/+/batch-complete"
    assert settings.mqtt_batch_client_id == "aqh-batch-west"
    assert settings.mqtt_keepalive == 90


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("LLM_MODE", "server", "LLM_MODE"),
        ("STORAGE_SERVICE_URL", "storage:5001", "STORAGE_SERVICE_URL"),
        ("STORAGE_CONNECT_TIMEOUT_SECONDS", "0", "STORAGE_CONNECT_TIMEOUT_SECONDS"),
        ("STORAGE_READ_TIMEOUT_SECONDS", "nan", "STORAGE_READ_TIMEOUT_SECONDS"),
        ("STORAGE_READ_MAX_ATTEMPTS", "11", "STORAGE_READ_MAX_ATTEMPTS"),
        ("STORAGE_RETRY_BACKOFF_SECONDS", "-1", "STORAGE_RETRY_BACKOFF_SECONDS"),
        ("MQTT_PORT", "70000", "MQTT_PORT"),
        ("MQTT_QOS", "3", "MQTT_QOS"),
        ("MQTT_BATCH_CLIENT_ID", " ", "MQTT_BATCH_CLIENT_ID"),
        ("MQTT_DISABLED", "sometimes", "MQTT_DISABLED"),
        ("MQTT_BATCH_TOPIC", "pipelines/#/complete", "MQTT_BATCH_TOPIC"),
        ("MQTT_KEEPALIVE", "0", "MQTT_KEEPALIVE"),
        ("MQTT_MAX_PAYLOAD_BYTES", "0", "MQTT_MAX_PAYLOAD_BYTES"),
    ],
)
def test_invalid_settings_fail(monkeypatch, name, value, message):
    monkeypatch.setenv(name, value)

    with pytest.raises(ConfigurationError, match=message):
        load_runtime_settings()


def test_password_requires_username(monkeypatch):
    monkeypatch.setenv("MQTT_PASSWORD", "secret")
    monkeypatch.delenv("MQTT_USERNAME", raising=False)

    with pytest.raises(ConfigurationError, match="MQTT_USERNAME"):
        load_runtime_settings()


def test_disabled_integrations_ignore_unused_endpoint_settings(monkeypatch):
    monkeypatch.setenv("MQTT_DISABLED", "true")
    monkeypatch.setenv("MQTT_PORT", "not-a-port")
    monkeypatch.setenv("MQTT_PASSWORD", "unused")
    monkeypatch.setenv("LLM_MODE", "fallback")
    monkeypatch.setenv("LLM_BASE_URL", "not-a-url")

    settings = load_runtime_settings()

    assert settings.mqtt_enabled is False
    assert settings.llm_mode == "fallback"


def test_llm_mode_requires_prompt_for_configured_use_case(monkeypatch, tmp_path):
    config = tmp_path / "agents.yaml"
    config.write_text("use_case_id: missing-prompt\n")
    monkeypatch.setenv("LLM_MODE", "llm")
    monkeypatch.setenv("AGENTS_CONFIG_PATH", str(config))
    monkeypatch.setenv("USE_CASE_PROMPTS_DIR", str(tmp_path))

    with pytest.raises(ConfigurationError, match="prompt"):
        load_runtime_settings()
