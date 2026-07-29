# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Validated runtime settings for the standalone agent service."""

import os
import math
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


_DEFAULTS_DIR = Path(__file__).resolve().parents[2] / "defaults"


class ConfigurationError(ValueError):
    """Raised when runtime settings cannot support the selected mode."""


def _as_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{name} must be true or false, got {value!r}")


def _as_port(name: str, default: int) -> int:
    value = os.environ.get(name, str(default))
    try:
        port = int(value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer, got {value!r}") from exc
    if not 1 <= port <= 65535:
        raise ConfigurationError(f"{name} must be between 1 and 65535")
    return port


def _as_qos(name: str, default: int) -> int:
    value = os.environ.get(name, str(default))
    try:
        qos = int(value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be 0, 1, or 2") from exc
    if qos not in {0, 1, 2}:
        raise ConfigurationError(f"{name} must be 0, 1, or 2")
    return qos


def _as_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    value = os.environ.get(name, str(default))
    try:
        result = int(value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer, got {value!r}") from exc
    if not minimum <= result <= maximum:
        raise ConfigurationError(
            f"{name} must be between {minimum} and {maximum}"
        )
    return result


def _as_float(
    name: str, default: float, *, minimum: float, maximum: float
) -> float:
    value = os.environ.get(name, str(default))
    try:
        result = float(value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number, got {value!r}") from exc
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ConfigurationError(
            f"{name} must be between {minimum} and {maximum}"
        )
    return result


def _validate_mqtt_topic(name: str, value: str, *, subscription: bool) -> str:
    topic = value.strip()
    if not topic:
        raise ConfigurationError(f"{name} must not be empty")
    if "\x00" in topic or len(topic.encode("utf-8")) > 65_535:
        raise ConfigurationError(f"{name} is not a valid MQTT topic")
    if subscription:
        segments = topic.split("/")
        if any(("+" in segment and segment != "+") for segment in segments):
            raise ConfigurationError(f"{name} has an invalid '+' wildcard")
        if any(
            ("#" in segment and (segment != "#" or index != len(segments) - 1))
            for index, segment in enumerate(segments)
        ):
            raise ConfigurationError(f"{name} has an invalid '#' wildcard")
    elif "+" in topic or "#" in topic:
        raise ConfigurationError(f"{name} must not contain MQTT wildcards")
    return topic


def _validate_http_url(name: str, value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigurationError(f"{name} must be an absolute HTTP(S) URL")
    return value.rstrip("/")


def _require_file(name: str, value: str) -> str:
    path = Path(value)
    if not path.is_file():
        raise ConfigurationError(f"{name} does not exist or is not a file: {path}")
    return str(path)


@dataclass(frozen=True)
class RuntimeSettings:
    storage_service_url: str
    storage_connect_timeout_seconds: float
    storage_read_timeout_seconds: float
    storage_read_max_attempts: int
    storage_retry_backoff_seconds: float
    mqtt_enabled: bool
    mqtt_host: str
    mqtt_port: int
    mqtt_batch_topic: str
    mqtt_qos: int
    mqtt_keepalive: int
    mqtt_max_payload_bytes: int
    mqtt_batch_client_id: str
    mqtt_username: str | None
    mqtt_password: str | None
    llm_mode: str
    llm_base_url: str
    llm_model_name: str
    llm_api_key: str
    agents_config_path: str
    prompts_dir: str
    fallback_policy_path: str


def load_runtime_settings(*, validate_assets: bool = True) -> RuntimeSettings:
    """Load and validate settings from the current process environment."""
    llm_mode = os.environ.get("LLM_MODE", "fallback").strip().lower()
    if llm_mode not in {"llm", "fallback"}:
        raise ConfigurationError("LLM_MODE must be 'llm' or 'fallback'")

    storage_url = _validate_http_url(
        "STORAGE_SERVICE_URL",
        os.environ.get("STORAGE_SERVICE_URL", "http://host.docker.internal:5001"),
    )
    storage_connect_timeout = _as_float(
        "STORAGE_CONNECT_TIMEOUT_SECONDS", 3.0, minimum=0.1, maximum=300.0
    )
    storage_read_timeout = _as_float(
        "STORAGE_READ_TIMEOUT_SECONDS", 10.0, minimum=0.1, maximum=300.0
    )
    storage_read_max_attempts = _as_int(
        "STORAGE_READ_MAX_ATTEMPTS", 3, minimum=1, maximum=10
    )
    storage_retry_backoff = _as_float(
        "STORAGE_RETRY_BACKOFF_SECONDS", 0.25, minimum=0.0, maximum=60.0
    )
    mqtt_enabled = not _as_bool("MQTT_DISABLED", False)
    mqtt_host = os.environ.get("MQTT_HOST", "mqtt-broker").strip()
    if mqtt_enabled and not mqtt_host:
        raise ConfigurationError("MQTT_HOST is required when batch events are enabled")
    mqtt_batch_topic = os.environ.get(
        "MQTT_BATCH_TOPIC", "apm/batch-complete"
    ).strip()
    if mqtt_enabled:
        mqtt_batch_topic = _validate_mqtt_topic(
            "MQTT_BATCH_TOPIC", mqtt_batch_topic, subscription=True
        )

    mqtt_port = _as_port("MQTT_PORT", 1883) if mqtt_enabled else 1883
    mqtt_qos = _as_qos("MQTT_QOS", 1) if mqtt_enabled else 1
    mqtt_keepalive = (
        _as_int("MQTT_KEEPALIVE", 60, minimum=1, maximum=65_535)
        if mqtt_enabled
        else 60
    )
    mqtt_max_payload_bytes = (
        _as_int(
            "MQTT_MAX_PAYLOAD_BYTES",
            1_048_576,
            minimum=1,
            maximum=268_435_455,
        )
        if mqtt_enabled
        else 1_048_576
    )
    mqtt_batch_client_id = (
        os.environ.get(
            "MQTT_BATCH_CLIENT_ID", "agent-quality-handler-batch"
        ).strip()
        if mqtt_enabled
        else "agent-quality-handler-batch"
    )
    if mqtt_enabled and not mqtt_batch_client_id:
        raise ConfigurationError("MQTT_BATCH_CLIENT_ID must not be empty")
    mqtt_username = (os.environ.get("MQTT_USERNAME") or None) if mqtt_enabled else None
    mqtt_password = (os.environ.get("MQTT_PASSWORD") or None) if mqtt_enabled else None
    if mqtt_enabled and mqtt_password and not mqtt_username:
        raise ConfigurationError("MQTT_USERNAME is required when MQTT_PASSWORD is set")

    llm_base_url = os.environ.get(
        "LLM_BASE_URL", "http://aqh-ovms:8000/v1"
    ).rstrip("/")
    if llm_mode == "llm":
        llm_base_url = _validate_http_url("LLM_BASE_URL", llm_base_url)
    llm_model_name = os.environ.get("LLM_MODEL_NAME", "Phi-4-mini-instruct").strip()
    if llm_mode == "llm" and not llm_model_name:
        raise ConfigurationError("LLM_MODEL_NAME is required in LLM mode")
    llm_api_key = os.environ.get("LLM_API_KEY", "UNUSED").strip() or "UNUSED"

    configs_dir = Path(
        os.environ.get("USE_CASE_CONFIGS_DIR", str(_DEFAULTS_DIR / "config"))
    )
    agents_config_path = os.environ.get(
        "AGENTS_CONFIG_PATH", str(configs_dir / "agents.yaml")
    )
    prompts_dir = os.environ.get(
        "USE_CASE_PROMPTS_DIR",
        str(_DEFAULTS_DIR / "prompts"),
    )
    fallback_policy_path = os.environ.get(
        "FALLBACK_POLICY_PATH", str(configs_dir / "policy_fallback.json")
    )
    if validate_assets:
        agents_config_path = _require_file("AGENTS_CONFIG_PATH", agents_config_path)
        if llm_mode == "fallback":
            fallback_policy_path = _require_file(
                "FALLBACK_POLICY_PATH", fallback_policy_path
            )
        else:
            use_case_id = _load_use_case_id(agents_config_path)
            _require_file(
                "USE_CASE_PROMPTS_DIR prompt",
                str(Path(prompts_dir) / f"{use_case_id}.txt"),
            )

    return RuntimeSettings(
        storage_service_url=storage_url,
        storage_connect_timeout_seconds=storage_connect_timeout,
        storage_read_timeout_seconds=storage_read_timeout,
        storage_read_max_attempts=storage_read_max_attempts,
        storage_retry_backoff_seconds=storage_retry_backoff,
        mqtt_enabled=mqtt_enabled,
        mqtt_host=mqtt_host,
        mqtt_port=mqtt_port,
        mqtt_batch_topic=mqtt_batch_topic,
        mqtt_qos=mqtt_qos,
        mqtt_keepalive=mqtt_keepalive,
        mqtt_max_payload_bytes=mqtt_max_payload_bytes,
        mqtt_batch_client_id=mqtt_batch_client_id,
        mqtt_username=mqtt_username,
        mqtt_password=mqtt_password,
        llm_mode=llm_mode,
        llm_base_url=llm_base_url,
        llm_model_name=llm_model_name,
        llm_api_key=llm_api_key,
        agents_config_path=agents_config_path,
        prompts_dir=prompts_dir,
        fallback_policy_path=fallback_policy_path,
    )


def _load_use_case_id(config_path: str) -> str:
    import yaml

    with open(config_path, encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file) or {}
    use_case_id = config.get("use_case_id")
    if not isinstance(use_case_id, str) or not use_case_id.strip():
        raise ConfigurationError(
            f"AGENTS_CONFIG_PATH must define a non-empty use_case_id: {config_path}"
        )
    return use_case_id
