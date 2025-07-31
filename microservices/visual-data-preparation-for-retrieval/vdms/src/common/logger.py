# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging.config
from typing import Any, Dict

from pydantic import BaseModel

from .settings import settings


class Logger(BaseModel):
    """Schema Model for Logging configurations and log display format.
    Inherits from BaseModel class from pydantic.

    Log level is set to DEBUG only in development environment (when FASTAPI_ENV=dev),
    otherwise it's set to INFO for production use.
    """

    LOGGER_NAME: str = settings.APP_NAME
    LOG_FORMAT: str = (
        "%(levelprefix)s | %(asctime)s | %(funcName)s | {%(pathname)s:%(lineno)d} | %(message)s"
    )
    version: int = 1
    disable_existing_loggers: bool = False
    formatters: Dict[str, Any] = {
        "default": {
            "()": "uvicorn.logging.DefaultFormatter",
            "fmt": LOG_FORMAT,
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    }
    handlers: Dict[str, Any] = {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
        },
    }

    @property
    def LOG_LEVEL(self) -> str:
        """
        Determine the log level based on the FASTAPI_ENV setting.
        Returns DEBUG for development environment, INFO otherwise.

        The log level can also be explicitly set via the LOG_LEVEL environment variable,
        which takes precedence over the environment-based default.
        """

        # Check if LOG_LEVEL is explicitly set in environment variables
        if hasattr(settings, "LOG_LEVEL") and settings.LOG_LEVEL:
            return settings.LOG_LEVEL.upper()

        # Otherwise base it on the FASTAPI_ENV environment
        try:
            if hasattr(settings, "FASTAPI_ENV") and settings.FASTAPI_ENV.lower() == "development":
                return "DEBUG"
        except (AttributeError, ValueError, Exception):
            # If FASTAPI_ENV is not set or there's an error accessing it
            pass
        return "INFO"

    @property
    def loggers(self) -> Dict[str, Any]:
        """Dictionary configuration for loggers"""
        return {
            self.LOGGER_NAME: {"handlers": ["default"], "level": self.LOG_LEVEL},
        }


# Configure logging using the Logger class
logger_config = Logger()

# Manually add computed properties to the model dump since they are properties, not fields
config_dict = logger_config.model_dump()
config_dict["loggers"] = logger_config.loggers

logging.config.dictConfig(config_dict)
logger = logging.getLogger(settings.APP_NAME)
