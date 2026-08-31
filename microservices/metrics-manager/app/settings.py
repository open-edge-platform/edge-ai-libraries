# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Settings module using Pydantic Settings for type-safe configuration.

Provides validated, type-safe configuration management with environment
variable support and sensible defaults for production deployment.
"""

from functools import lru_cache
from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings with validation and environment variable support.

    All settings can be overridden via environment variables.
    Environment variables are case-insensitive.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,  # Allow both field name and alias
    )

    # Service Configuration
    service_name: str = Field(default="metrics-manager", description="Service name for logging")
    # Default mirrors the value in ./VERSION (single source of truth used by
    # the build / Makefile). Override at runtime via SERVICE_VERSION env var.
    service_version: str = Field(default="2026.1.0", description="Service version")
    environment: Literal["development", "staging", "production"] = Field(
        default="production", description="Deployment environment"
    )

    # Server Configuration
    metrics_port: int = Field(default=9090, ge=1, le=65535, description="API server port")
    telegraf_port: int = Field(default=9273, ge=1, le=65535, description="Telegraf Prometheus port")
    host: str = Field(default="0.0.0.0", description="Server bind host")

    # Logging Configuration
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", description="Logging level"
    )
    log_format: Literal["json", "text"] = Field(
        default="json", description="Log output format"
    )
    log_include_timestamp: bool = Field(default=True, description="Include timestamp in logs")

    # CORS Configuration
    # Use str type to avoid pydantic-settings JSON parsing issues with env vars
    cors_origins_raw: str = Field(
        default="*",
        validation_alias="CORS_ORIGINS",
        description="Allowed CORS origins (comma-separated or JSON array)"
    )
    cors_allow_credentials: bool = Field(default=False, description="Allow credentials")

    @property
    def cors_origins(self) -> list[str]:
        """Get CORS origins as a list.

        Parses the raw string value which can be:
        - Simple string: "*" or "http://localhost:3000"
        - Comma-separated: "http://localhost:3000,http://example.com"
        - JSON array: '["*"]' or '["http://localhost:3000"]'
        """
        v = self.cors_origins_raw
        if not v or not v.strip():
            return ["*"]
        # Try JSON first
        if v.startswith("["):
            import json
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                pass
        # Otherwise split by comma
        return [origin.strip() for origin in v.split(",") if origin.strip()]

    # Metrics Storage Configuration
    custom_metrics_dir: str = Field(
        default="/app/custom-metrics", description="Directory for custom metrics files"
    )
    metrics_retention_seconds: int = Field(
        default=300, ge=10, le=86400, description="Metrics retention time in seconds"
    )
    max_metrics_batch_size: int = Field(
        default=1000, ge=1, le=10000, description="Maximum metrics per batch"
    )
    max_metrics_in_memory: int = Field(
        default=100000, description="Maximum metrics to keep in memory"
    )

    # Telegraf Configuration
    telegraf_config_path: str = Field(
        default="/etc/telegraf/telegraf.conf", description="Telegraf config path"
    )
    telegraf_http_endpoint: str = Field(
        default="http://localhost:8186/write",
        description="Telegraf HTTP input plugin endpoint for pushing metrics",
    )

    # Prometheus Poller Configuration
    prometheus_poller_interval_ms: int = Field(
        default=500,
        ge=100,
        le=5000,
        description="Polling interval in milliseconds (100-5000)"
    )
    prometheus_telegraf_endpoint: str = Field(
        default="http://localhost:9273",
        description="Telegraf Prometheus endpoint (system metrics)"
    )

    # Security Configuration
    trust_forwarded_headers: bool = Field(
        default=False,
        description=(
            "Honor X-Forwarded-For / X-Real-IP headers "
            "(set True only behind a trusted reverse proxy)"
        ),
    )

    # Rate Limiting Configuration
    rate_limit_enabled: bool = Field(default=True, description="Enable rate limiting")
    rate_limit_requests_per_minute: int = Field(
        default=1000, ge=1, description="Max requests per minute per client"
    )
    rate_limit_burst: int = Field(default=100, ge=1, description="Burst allowance")

    # Performance Configuration
    file_persist_debounce_ms: int = Field(
        default=100, ge=0, le=5000, description="Debounce file writes in milliseconds"
    )
    enable_gzip_compression: bool = Field(default=True, description="Enable response compression")

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, v: Any) -> str:
        """Normalize log level to uppercase."""
        if isinstance(v, str):
            return v.upper()
        return v

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Uses lru_cache to ensure settings are only loaded once.
    """
    return Settings()
