# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os
import stat
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from src.api.models import ModelRequest
from src.utils.logging import logger


STARTUP_MODELS_CONFIG_ENV = "STARTUP_MODELS_CONFIG"
MAX_STARTUP_CONFIG_SIZE_BYTES = 1024 * 1024
MAX_STARTUP_MODELS = 100
MAX_DOWNLOAD_PATH_LENGTH = 4096
SUPPORTED_STARTUP_CONFIG_SUFFIXES = frozenset({".json", ".yaml", ".yml"})


class StartupModelRequest(ModelRequest):
    """A model request with an optional startup-specific destination."""

    model_config = ConfigDict(extra="forbid")

    download_path: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=MAX_DOWNLOAD_PATH_LENGTH,
    )

    @field_validator("download_path")
    @classmethod
    def _validate_download_path(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and (not value.strip() or "\x00" in value):
            raise ValueError("download_path must be a non-empty filesystem path")
        return value


class StartupModelsConfig(BaseModel):
    """Validated configuration for models submitted during service startup."""

    model_config = ConfigDict(extra="forbid")

    download_path: str = Field(
        ...,
        min_length=1,
        max_length=MAX_DOWNLOAD_PATH_LENGTH,
    )
    parallel_downloads: bool = False
    models: list[StartupModelRequest] = Field(
        ...,
        min_length=1,
        max_length=MAX_STARTUP_MODELS,
    )

    @field_validator("download_path")
    @classmethod
    def _validate_download_path(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("download_path must be a non-empty filesystem path")
        return value


def _log_unusable_config(path: Path, reason: str, action: str) -> None:
    logger.error(
        "startup_models_config_unusable",
        path=str(path),
        reason=reason,
        action=action,
    )


def load_startup_models_config(
    config_path: Optional[str | os.PathLike[str]] = None,
) -> Optional[StartupModelsConfig]:
    """Load a bounded startup configuration without raising errors."""

    configured_path = (
        config_path
        if config_path is not None
        else os.getenv(STARTUP_MODELS_CONFIG_ENV)
    )
    if configured_path is None:
        return None

    if not str(configured_path).strip():
        _log_unusable_config(
            Path("."),
            f"{STARTUP_MODELS_CONFIG_ENV} is empty",
            "Set it to a readable startup configuration file, or unset it.",
        )
        return None

    path = Path(configured_path)
    if path.suffix.lower() not in SUPPORTED_STARTUP_CONFIG_SUFFIXES:
        _log_unusable_config(
            path,
            "unsupported file extension",
            "Use a supported startup configuration file.",
        )
        return None

    open_flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
    open_flags |= getattr(os, "O_CLOEXEC", 0)
    file_descriptor = None
    try:
        file_descriptor = os.open(path, open_flags)
        file_stat = os.fstat(file_descriptor)
        if not stat.S_ISREG(file_stat.st_mode):
            _log_unusable_config(
                path,
                "path is not a regular file",
                "Mount a regular startup configuration file at the configured path.",
            )
            return None
        if file_stat.st_size > MAX_STARTUP_CONFIG_SIZE_BYTES:
            _log_unusable_config(
                path,
                "file exceeds the 1 MiB size limit",
                "Reduce the configuration file size.",
            )
            return None
        config_file = os.fdopen(file_descriptor, "rb")
        file_descriptor = None
        with config_file:
            raw_config = config_file.read(MAX_STARTUP_CONFIG_SIZE_BYTES + 1)
    except OSError as error:
        _log_unusable_config(
            path,
            f"file cannot be read ({type(error).__name__})",
            "Verify that the configured path exists and is readable by the service.",
        )
        return None
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)

    if len(raw_config) > MAX_STARTUP_CONFIG_SIZE_BYTES:
        _log_unusable_config(
            path,
            "file exceeds the 1 MiB size limit",
            "Reduce the configuration file size.",
        )
        return None

    try:
        text_config = raw_config.decode("utf-8")
        if path.suffix.lower() == ".json":
            parsed_config = json.loads(text_config)
        else:
            parsed_config = yaml.safe_load(text_config)
        return StartupModelsConfig.model_validate(parsed_config)
    except (UnicodeDecodeError, json.JSONDecodeError, yaml.YAMLError, ValidationError) as error:
        _log_unusable_config(
            path,
            f"configuration parsing or validation failed ({type(error).__name__})",
            (
                "Verify the configuration syntax, required fields, supported model "
                f"values, and the {MAX_STARTUP_MODELS}-model limit."
            ),
        )
        return None
