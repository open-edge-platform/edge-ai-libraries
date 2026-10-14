# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from fastapi import UploadFile
from pathlib import Path
from typing import List, Optional
from .config import config
from .logger import logger
import os


def validate_files(file_objects: List[UploadFile]) -> bool:
    for file_obj in file_objects:
        if not file_obj.filename:
            return False

        file_name = os.path.basename(file_obj.filename)
        file_ext = os.path.splitext(file_name)[1].lower()

        if file_ext not in config._SUPPORTED_FORMATS:
            return False

    return True

async def save_files_to_tmp(file_objects: list[UploadFile]) -> List[str]:
    saved_files = []
    for file_obj in file_objects:
        # Only the basename is trusted; this prevents path traversal via a crafted filename.
        safe_name = os.path.basename(file_obj.filename)
        tmp_path = Path(config._TMP_FILE_PATH) / safe_name

        if not tmp_path.parent.exists():
            tmp_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            await file_obj.seek(0)
            content = await file_obj.read()

            # clean tsv content by replacing spaces with tabs
            if tmp_path.suffix.lower() == ".tsv":
                decoded = content.decode("utf-8")
                lines = decoded.splitlines()

                cleaned_lines = []
                for line in lines:
                    if '\t' in line:
                        cleaned_lines.append(line)
                    elif '    ' in line:  # 4 spaces
                        cleaned_lines.append(line.replace('    ', '\t'))
                    else:
                        cleaned_lines.append(line)

                # Re-encode the cleaned content
                content = "\n".join(cleaned_lines).encode("utf-8")

            # Save the cleaned content to tmp_path
            with tmp_path.open("wb") as buffer:
                buffer.write(content)


            saved_files.append(str(tmp_path))

        except Exception as e:
            logger.exception(f"Error saving file {file_obj.filename}: {e}")
            return None

    return saved_files