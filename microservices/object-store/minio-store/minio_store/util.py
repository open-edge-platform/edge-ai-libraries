# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuration settings for the application
    Inherits from BaseSettings class from Pydantic
    """

    APP_NAME: str = "DataStore"
    APP_DISPLAY_NAME: str = "Intel GenAI DataStore Microservice"
    APP_DESC: str = "A minio based object storage API service."

    ALLOW_ORIGINS: str = "*"  # Comma separated values for allowed origins
    ALLOW_METHODS: str = "*"  # Comma separated values for allowed HTTP Methods
    ALLOW_HEADERS: str = "*"  # Comma separated values for allowed HTTP Headers

    DEFAULT_BUCKET: str = "intel.gai.ragfiles"
    OBJECT_PREFIX: str = "intelgai"

    MINIO_HOST: str = "localhost"
    MINIO_API_PORT: str = "9000"
    MINIO_ACCESS_KEY: str = ""
    MINIO_SECRET_KEY: str = ""


class Strings:
    s3_error_msg: str = "Storage Service is facing some issues. Please try later!"
    server_error: str = "Some error ocurred at API server. Please try later!"
    invalid_bucket: str = "No such bucket exists!"
    file_not_found: str = "No such file was found!"
    bucket_empty: str = "No files present in the bucket!"
    delete_error: str = "One or more files were not successfully deleted. Please try again!"
    del_req_validation_error: str = "file_name is required if not deleting all files in bucket."


class DataStoreException(Exception):
    """Custom exception for DataStore application."""

    def __init__(self, msg: str, status_code: int):
        self.message = msg
        self.status_code = status_code
        super().__init__(self.message)


class Validation:
    @staticmethod
    def sanitize_input(input: str) -> str | None:
        """Takes an string input and strips whitespaces. Returns None if
        string is empty else returns the string.
        """
        input = str.strip(input)
        if len(input) == 0:
            return None

        return input

    @staticmethod
    def strip_input(input: str) -> str:
        """Takes and string input and returns whitespace stripped string."""
        return str.strip(input)
