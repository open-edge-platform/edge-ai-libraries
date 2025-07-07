# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import re
from functools import wraps
from http import HTTPStatus
from typing import Any, Optional, TypeVar

from fastapi import HTTPException
from pydantic import ValidationError

from src.common import DataPrepException, logger

T = TypeVar("T")


def sanitize_string(value: Optional[str]) -> Optional[str]:
    """
    Sanitize a string input by stripping whitespace and validating it's not empty.

    Args:
        value (Optional[str]): The string to sanitize

    Returns:
        Optional[str]: The sanitized string or None if empty
    """
    if value is None:
        return None

    sanitized = value.strip()
    logger.debug(f"Sanitizing string: '{value}' -> '{sanitized}'")
    return sanitized


def sanitize_bucket_name(bucket_name: Optional[str]) -> str:
    """
    Sanitize and validate a bucket name

    Args:
        bucket_name (Optional[str]): The bucket name to sanitize

    Returns:
        str: The sanitized bucket name

    Raises:
        DataPrepException: If the bucket name contains invalid characters
    """
    from src.common import settings

    min_length: str = 3

    # Sanitize the bucket name
    bucket_name = sanitize_string(bucket_name or settings.DEFAULT_BUCKET_NAME)

    if len(bucket_name) < min_length:
        raise DataPrepException(
            status_code=HTTPStatus.BAD_REQUEST,
            msg=f"Bucket name must be at least {min_length} characters long.",
        )

    return bucket_name


def sanitize_video_id(video_id: Optional[str], min_length: int = 3) -> str:
    """
    Sanitize and validate a video ID

    Args:
        video_id (Optional[str]): The video ID to sanitize
        min_length (int): Minimum length required (default 3)

    Returns:
        str: The sanitized video ID

    Raises:
        DataPrepException: If the video ID is invalid
    """
    if not video_id:
        raise DataPrepException(status_code=HTTPStatus.BAD_REQUEST, msg="Video ID is required.")

    # Sanitize the video ID
    video_id = sanitize_string(video_id)

    if len(video_id) < min_length:
        raise DataPrepException(
            status_code=HTTPStatus.BAD_REQUEST,
            msg=f"Video ID must be at least {min_length} characters long.",
        )

    # Check for invalid characters in directory path
    if not re.match(r"^[a-zA-Z0-9.\-_/]+$", video_id):
        raise DataPrepException(
            status_code=HTTPStatus.BAD_REQUEST,
            msg="Video ID contains invalid characters. Use only alphanumeric characters, periods, hyphens, underscores, and forward slashes.",
        )

    return video_id


def sanitize_video_name(video_name: Optional[str]) -> Optional[str]:
    """
    Sanitize and validate a video name

    Args:
        video_name (Optional[str]): The video name to sanitize

    Returns:
        Optional[str]: The sanitized video name or None if not provided

    Raises:
        DataPrepException: If the video name is invalid
    """
    if not video_name:
        return None

    # Sanitize the video name
    video_name = sanitize_string(video_name)

    if video_name:
        # Check for invalid characters in filename
        if not re.match(r"^[a-zA-Z0-9.\-_\(\) ]+$", video_name):
            raise DataPrepException(
                status_code=HTTPStatus.BAD_REQUEST,
                msg="Video name contains invalid characters. Use only alphanumeric characters, dots, hyphens, underscores, and spaces.",
            )

    return video_name


def validate_file_content_type(file, allowed_content_types=None):
    """
    Validate the content type of an uploaded file.

    Args:
        file: The uploaded file to validate
        allowed_content_types (list, optional): List of allowed content types. Defaults to ["video/mp4"].

    Raises:
        DataPrepException: If the content type is not allowed
    """

    allowed_content_types = allowed_content_types or ["video/mp4"]

    if not file:
        return

    content_type = file.content_type
    if not content_type or not any(ct in content_type.lower() for ct in allowed_content_types):
        allowed_types_str = ", ".join(allowed_content_types)
        raise DataPrepException(
            status_code=HTTPStatus.BAD_REQUEST,
            msg=f"Uploaded file must be one of the following types: {allowed_types_str}. Got: {content_type}",
        )


def validate_file_extension(file, allowed_extensions=None):
    """
    Validate the extension of an uploaded file.

    Args:
        file: The uploaded file to validate
        allowed_extensions (list, optional): List of allowed file extensions. Defaults to [".mp4"]

    Raises:
        DataPrepException: If the file extension is not allowed
    """

    allowed_extensions = allowed_extensions or [".mp4"]

    if not file:
        return

    filename = file.filename
    if not any(filename.lower().endswith(ext) for ext in allowed_extensions):
        allowed_ext_str = ", ".join(allowed_extensions)
        raise DataPrepException(
            status_code=HTTPStatus.BAD_REQUEST,
            msg=f"Uploaded file must have one of the following extensions: {allowed_ext_str}",
        )


def validate_file(file, *, required=True, allowed_content_types=None, allowed_extensions=None):
    """
    Wrapper function that performs complete validation of an uploaded file.
    Validates if file is required, has allowed content type and allowed extension.

    Args:
        file: The uploaded file to validate
        required (bool, optional): Whether the file is required. Defaults to True.
        allowed_content_types (list, optional): List of allowed content types. Defaults to ["video/mp4"].
        allowed_extensions (list, optional): List of allowed file extensions. Defaults to [".mp4"].

    Raises:
        DataPrepException: If validation fails with appropriate error message
    """
    # Check if file is required but not provided
    if required and not file:
        raise DataPrepException(
            status_code=HTTPStatus.BAD_REQUEST,
            msg="File upload is required but no file was provided",
        )

    # If file is not required and not provided, skip further validation
    if not file:
        return

    # Validate content type
    validate_file_content_type(file, allowed_content_types)

    # Validate file extension
    validate_file_extension(file, allowed_extensions)


def validate_params(func):
    """
    Decorator to sanitize and validate function parameters

    This decorator examines the function parameters and applies appropriate
    sanitization based on parameter names and types.
    """

    @wraps(func)
    async def wrapper(*args, **kwargs):
        sanitized_kwargs = {}

        try:
            # Apply sanitization based on parameter names
            for key, value in kwargs.items():
                if key == "bucket_name":
                    sanitized_kwargs[key] = sanitize_bucket_name(value)
                elif key == "video_id":
                    sanitized_kwargs[key] = sanitize_video_id(value)
                elif key == "video_name":
                    sanitized_kwargs[key] = sanitize_video_name(value)
                elif key == "file":
                    # Use the wrapper function to validate the file with default settings
                    validate_file(value, required=True)
                    sanitized_kwargs[key] = value
                elif isinstance(value, str):
                    # Apply basic string sanitization to other string parameters
                    sanitized_kwargs[key] = sanitize_string(value)
                elif isinstance(value, list):
                    # Sanitize list of strings
                    sanitized_kwargs[key] = [
                        sanitize_string(item) for item in value if isinstance(item, str)
                    ]
                else:
                    # Pass through non-string values
                    sanitized_kwargs[key] = value

            # Replace original kwargs with sanitized ones and call the function

            return await func(*args, **sanitized_kwargs)
        except DataPrepException as ex:
            # Re-raise DataPrepException directly
            logger.error(ex)
            raise HTTPException(status_code=ex.status_code, detail=ex.message)
        except ValidationError as ex:
            # Handle Pydantic validation errors
            logger.error(f"Validation error: {ex}")
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=str(ex))
        except ValueError as ex:
            # Handle ValueError exceptions
            logger.error(f"Value error: {ex}")
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=str(ex))

    return wrapper


# Add a function to sanitize request models (Pydantic models)
def sanitize_model(model: Any) -> Any:
    """
    Sanitize fields in a Pydantic model

    Args:
        model (Any): The Pydantic model to sanitize

    Returns:
        Any: The sanitized model
    """
    # Get model data as a dictionary
    model_dict = model.model_dump()

    # Sanitize string fields
    for field_name, value in model_dict.items():
        if isinstance(value, str | None):
            if field_name == "bucket_name":
                model_dict[field_name] = sanitize_bucket_name(value)
            elif field_name == "video_id":
                model_dict[field_name] = sanitize_video_id(value)
            elif field_name == "video_name":
                sanitized = sanitize_video_name(value)
                if sanitized:
                    model_dict[field_name] = sanitized
            else:
                # Apply basic string sanitization to other string fields
                sanitized = sanitize_string(value)
                model_dict[field_name] = sanitized
        elif isinstance(value, list):
            if field_name == "tags":
                # Ensure tags are sanitized as a list of strings
                model_dict[field_name] = [sanitize_string(tag) for tag in value if tag]

    # Update the model with sanitized values
    for field_name, value in model_dict.items():
        setattr(model, field_name, value)

    return model
