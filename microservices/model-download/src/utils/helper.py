# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import io
import os
import re
import zipfile
import shutil
from fastapi import HTTPException
from .logging import logger
from .zip_safety import validate_zip_contents_within_target  # noqa: F401  (re-exported)


def sanitize_path_part(value: str, field_name: str, strict: bool = False) -> str:
    """Validate and sanitize a user-supplied value that will be used as a
    directory name.

    strict=False (default): For model name field. Allows letters, numbers, periods,
    underscores, hyphens, and spaces. Spaces are normalized to underscores.

    strict=True: For technical identifiers (provider, framework, precision).
    Allows only letters, numbers, underscores, and hyphens, and must start
    with a letter or digit.
    """
    stripped = value.strip()

    if not stripped:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} must not be empty.",
        )

    if strict:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", stripped):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{field_name} may contain only letters, numbers, "
                    "underscores, and hyphens, and must start with a letter or digit."
                ),
            )
        return stripped

    if not re.fullmatch(r"[A-Za-z0-9._ -]+", stripped):
        raise HTTPException(
            status_code=400,
            detail=(
                f"{field_name} may contain only letters, numbers, periods, "
                "underscores, hyphens, and spaces."
            ),
        )

    if (stripped.startswith(".") or stripped.endswith(".") or ".." in stripped):
        raise HTTPException(
            status_code=400,
            detail=(
                f"{field_name} must not start or end with a period "
                "or contain consecutive periods."
            ),
        )

    # Normalize spaces for filesystem-friendly directory names.
    return stripped.replace(" ", "_")


def validate_zip_file(content: bytes) -> None:
    if not zipfile.is_zipfile(io.BytesIO(content)):
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is not a valid ZIP archive.",
        )


def cleanup_model_directory(model_dir_path: str):
    subdirs = [
        os.path.join(model_dir_path, d)
        for d in os.listdir(model_dir_path)
        if os.path.isdir(os.path.join(model_dir_path, d))
    ]
    if not os.listdir(model_dir_path) or all(not os.listdir(d) for d in subdirs):
        try:
            logger.warning(
                f"No files found in the directory {model_dir_path}. Removing empty directory."
            )
            shutil.rmtree(model_dir_path)

        except OSError as e:
            logger.error(f"Failed to remove empty directory {model_dir_path}: {str(e)}")


def get_hub_config_keys(plugin, hub: str) -> list[dict]:
        """
        Extract and serialize configuration keys for a given hub/plugin directly via hub_config_keys(hub).
        """
        hub_config_fn = getattr(plugin, "hub_config_keys", None)
        if not callable(hub_config_fn):
            return []
        try:
            # Connection/configuration keys the plugin understands. These can be
            # overridden per request via the 'override_credentials' field of
            # POST /models/download; environment variables remain the fallback default.
            raw_keys = hub_config_fn(hub)
            return [
                {
                    "name": key.name,
                    "description": getattr(key, "description", ""),
                    "sensitive": getattr(key, "is_sensitive", getattr(key, "sensitive", False)),
                    "required": getattr(key, "required", False),
                    "group": getattr(key, "group", None),
                }
                for key in raw_keys
            ]
        except Exception:
            # Handles mocks or unconfigured test plugins gracefully
            return []