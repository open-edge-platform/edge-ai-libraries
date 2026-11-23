# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""ZIP validation helpers that depend only on the Python standard library.

This module is also imported by scripts/download_public_models.sh, which runs
in a throwaway virtualenv without the service dependencies (fastapi,
structlog). Do not add third-party or service-internal imports here.
"""

import os
import zipfile


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

