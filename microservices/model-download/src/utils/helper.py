# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import io
import os
import re
import zipfile
import shutil
from fastapi import HTTPException
from .logging import logger


def sanitize_path_part(value: str, field_name: str) -> str:
    lowered = value.lower()

    # Reject if contains invalid characters
    if not re.match(r"^[a-z0-9_\-\s]+$", lowered):
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} contains invalid characters. Only alphanumeric, spaces, underscores, and hyphens allowed.",
        )

    # Sanitize: strip and replace spaces with underscores
    sanitized_value = lowered.strip()
    sanitized_value = sanitized_value.replace(" ", "_")

    if not sanitized_value:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} is empty or invalid.",
        )

    return sanitized_value


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


def validate_zip_contents_within_target(zf: zipfile.ZipFile, target_dir: str) -> None:
    """
    Validate ZIP file for safe extraction:
    1. All entries stay within target directory (prevent ZIP-slip)
    2. Contains required OpenVINO IR files (.xml and .bin)
    """
    has_xml = False
    has_bin = False

    for member_name in zf.namelist():
        # Check for required OpenVINO IR files
        if member_name.lower().endswith(".xml"):
            has_xml = True
        if member_name.lower().endswith(".bin"):
            has_bin = True

        # Path traversal validation
        normalized_name = os.path.normpath(member_name.replace("\\", "/"))

        if normalized_name in ("", "."):
            continue

        if os.path.isabs(normalized_name) or normalized_name.startswith("../") or normalized_name == "..":
            raise ValueError(f"Invalid ZIP archive: '{member_name}' resolves outside target directory.")

        resolved_member_path = os.path.abspath(os.path.join(target_dir, normalized_name))
        if os.path.commonpath([target_dir, resolved_member_path]) != target_dir:
            raise ValueError(f"Invalid ZIP archive: '{member_name}' resolves outside target directory.")

    # Check format requirements
    if not has_xml or not has_bin:
        raise ValueError("ZIP must contain at least one .xml and one .bin file (OpenVINO IR format).")
