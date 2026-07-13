# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import logging


def _bool(key: str, default: bool) -> bool:
    val = os.getenv(key, "")
    if not val:
        return default
    return val.strip().lower() in ("1", "true", "yes")


def _int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


def _float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except ValueError:
        return default


class Settings:
    PORT: int = int(os.getenv("PORT", 8000))
    APP_NAME: str = os.getenv("APP_NAME", "Alert Agent Service")
    DEBUG: bool = _bool("DEBUG", False)
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    API_V1_PREFIX: str = os.getenv("API_V1_PREFIX", "/api/v1")

    # ADK / LLM backend
    AGENT_MODE: bool = _bool("AGENT_MODE", True)
    LLM_URL: str = os.getenv("LLM_URL", "http://ovms-llm:8000/v3")
    LLM_REPO: str = os.getenv("LLM_MODEL", "OpenVINO/Phi-4-mini-instruct-int4-ov")
    LLM_MODEL: str = LLM_REPO.split("/")[-1]
    LLM_TIMEOUT: float = _float("LLM_TIMEOUT", 10.0)

    # Worker pool size
    ACTION_WORKERS: int = _int("ACTION_WORKERS", 2)

    # Webhook action tool
    WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")
    WEBHOOK_SECRET: str = os.getenv("WEBHOOK_SECRET", "")

    # MQTT action tool
    MQTT_MODE: str = os.getenv("MQTT_MODE", "external")
    MQTT_BROKER: str = os.getenv("MQTT_BROKER", os.getenv("MQTT_HOST", ""))
    MQTT_PORT: int = _int("MQTT_PORT", 1883)
    MQTT_USERNAME: str = os.getenv("MQTT_USERNAME", "")
    MQTT_PASSWORD: str = os.getenv("MQTT_PASSWORD", "")
    MQTT_BASE_TOPIC: str = os.getenv("MQTT_BASE_TOPIC", "alerts")
    DELIVERY_HANDLERS: str = os.getenv("DELIVERY_HANDLERS", "")

    # Snapshot tool
    SNAPSHOT_DIR: str = os.getenv("SNAPSHOT_DIR", "snapshots")

    # Retry
    RETRY_ATTEMPTS: int = _int("RETRY_ATTEMPTS", 3)
    RETRY_INTERVAL_SECONDS: float = _float("RETRY_INTERVAL_SECONDS", 2.0)

    # Subscription config (optional default routing)
    SUBSCRIPTION_CONFIG_PATH: str = os.getenv(
        "SUBSCRIPTION_CONFIG_PATH", os.getenv("CONFIG_PATH", "resources/config.yaml")
    )

    # MCP
    MCP_ENABLED: bool = _bool("MCP_ENABLED", True)
    MCP_CONFIG_FILE: str = os.getenv("MCP_CONFIG_FILE", "resources/mcp_servers.json")


settings = Settings()


def setup_logging():
    """Configure structured logging."""
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    for noisy in ("httpx", "httpcore", "multipart", "uvicorn.access", "paho"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
