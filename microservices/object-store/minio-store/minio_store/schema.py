# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel

from minio_store.util import Settings

settings = Settings()


class StatusEnum(str, Enum):
    success = "success"
    error = "error"


class DataStoreResponse(BaseModel):
    """Response model for API Responses from DataStore service"""

    status: StatusEnum
    message: Optional[str] = None


class DataStoreErrorResponse(DataStoreResponse):
    """Response model for API Error Responses from DataStore service"""

    status: StatusEnum = StatusEnum.error


class FileListResponse(DataStoreResponse):
    """Response model for list of files present in storage server"""

    bucket_name: str
    files: Optional[List[str]]


class Logger(BaseModel):
    """Schema Model for Logging configurations and log display format.
    Inherits from BaseModel class from pydantic.
    """

    LOGGER_NAME: str = Settings().APP_NAME
    LOG_FORMAT: str = (
        "%(levelprefix)s | %(asctime)s | %(funcName)s | {%(pathname)s:%(lineno)d} | %(message)s"
    )
    LOG_LEVEL: str = "DEBUG"
    version: int = 1
    disable_existing_loggers: bool = False
    formatters: dict = {
        "default": {
            "()": "uvicorn.logging.DefaultFormatter",
            "fmt": LOG_FORMAT,
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    }
    handlers: dict = {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
        },
    }
    loggers: dict = {
        LOGGER_NAME: {"handlers": ["default"], "level": LOG_LEVEL},
    }
