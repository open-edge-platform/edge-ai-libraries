# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from .process_minio_video import router as process_minio_video_router
from .upload_and_process_video import router as upload_and_process_video_router

__all__ = [
    "process_minio_video_router",
    "upload_and_process_video_router",
]
