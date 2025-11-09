# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import shutil
from .logging import logger

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
