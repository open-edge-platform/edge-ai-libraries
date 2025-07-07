# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from .process_minio_video import router as process_minio_video_router
from .process_video_legacy import router as prep_video_router_legacy
from .upload_and_process_video import router as upload_and_process_video_router

__all__ = [
    "process_minio_video_router",
    "upload_and_process_video_router",
    "prep_video_router_legacy",
]
