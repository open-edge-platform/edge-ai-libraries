# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from .document_processing import process_document_router
from .health import check_health_router
from .video_management import delete_video_router, download_video_router, list_videos_router
from .video_processing import (
    process_minio_video_router,
    upload_and_process_video_router,
)

__all__ = [
    "check_health_router",
    "process_document_router",
    "process_minio_video_router",
    "upload_and_process_video_router",
    "list_videos_router",
    "download_video_router",
    "delete_video_router",
]
