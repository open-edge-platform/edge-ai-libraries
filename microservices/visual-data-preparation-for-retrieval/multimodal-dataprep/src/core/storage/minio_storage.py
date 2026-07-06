# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""MinIO-backed implementation of :class:`BaseStorage`.

Wraps the existing :class:`~src.core.minio_client.MinioClient` so all behavior
historically provided by that client is preserved, while additionally
implementing the operations the endpoints expect but that were missing on the
raw client (``bucket_exists``, ``object_exists_by_path``,
``list_objects_in_directory``, ``delete_object``).
"""

from __future__ import annotations

import io
from typing import List, Optional

from minio.error import S3Error

from src.common import Strings, logger, sanitize_for_log, settings
from src.core.minio_client import MinioClient
from src.core.storage.base import BaseStorage, StorageObject


class MinioStorage(BaseStorage):
    """Storage backend backed by a MinIO object store."""

    def __init__(self) -> None:
        if (
            not settings.MINIO_ENDPOINT
            or not settings.MINIO_ACCESS_KEY
            or not settings.MINIO_SECRET_KEY
        ):
            logger.error("Minio configuration is incomplete")
            raise Exception(Strings.minio_conn_error)

        try:
            self._client = MinioClient(
                endpoint=settings.MINIO_ENDPOINT,
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=settings.MINIO_SECRET_KEY,
                secure=settings.MINIO_SECURE,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(f"Failed to create Minio client: {exc}")
            raise Exception(Strings.minio_conn_error)

    @property
    def client(self) -> MinioClient:
        """Expose the underlying MinioClient for advanced/legacy callers."""
        return self._client

    # --- bucket / container operations -------------------------------------
    def bucket_exists(self, bucket_name: str) -> bool:
        try:
            return bool(self._client.client.bucket_exists(bucket_name))
        except S3Error as exc:
            logger.error(
                "Error checking bucket '%s': %s",
                sanitize_for_log(bucket_name, max_length=128),
                sanitize_for_log(exc, max_length=256),
            )
            return False

    def ensure_bucket_exists(self, bucket_name: str) -> None:
        self._client.ensure_bucket_exists(bucket_name)

    # --- object existence / naming -----------------------------------------
    def compose_object_name(self, video_id: str, object_name: str) -> str:
        return self._client.compose_object_name(video_id, object_name)

    def validate_object_name(self, video_id: str, video_name: str) -> bool:
        return self._client.validate_object_name(video_id, video_name)

    def object_exists_by_path(self, bucket_name: str, object_name: str) -> bool:
        try:
            self._client.client.stat_object(bucket_name, object_name)
            return True
        except S3Error:
            return False
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(f"Error checking if object exists: {exc}")
            return False

    def object_exists(self, bucket_name: str, video_id: str, video_name: str) -> bool:
        return self._client.object_exists(bucket_name, video_id, video_name)

    # --- listing ------------------------------------------------------------
    def list_objects_in_directory(
        self, bucket_name: str, video_id: str
    ) -> List[StorageObject]:
        safe_video_id = self._client._validate_object_component(video_id, "Video ID")
        prefix = f"{safe_video_id}/"
        try:
            objects = self._client.client.list_objects(
                bucket_name, prefix=prefix, recursive=True
            )
            return [
                StorageObject(
                    object_name=obj.object_name,
                    size=getattr(obj, "size", None),
                    last_modified=(
                        obj.last_modified.isoformat()
                        if getattr(obj, "last_modified", None)
                        else None
                    ),
                    etag=getattr(obj, "etag", None),
                    content_type=getattr(obj, "content_type", None),
                )
                for obj in objects
            ]
        except S3Error as exc:
            logger.error(
                "Error listing objects in directory %s: %s",
                sanitize_for_log(video_id, max_length=128),
                sanitize_for_log(exc, max_length=256),
            )
            raise Exception(f"Error listing objects in directory {video_id}: {exc}")

    def list_all_videos(self, bucket_name: str) -> List[dict]:
        return self._client.list_all_videos(bucket_name)

    def get_video_in_directory(
        self, bucket_name: str, video_id: str, return_prefix: bool = True
    ) -> Optional[str]:
        return self._client.get_video_in_directory(bucket_name, video_id, return_prefix)

    # --- read / write -------------------------------------------------------
    def download_video_stream(
        self, bucket_name: str, object_name: str
    ) -> Optional[io.BytesIO]:
        return self._client.download_video_stream(bucket_name, object_name)

    def upload_video(
        self, bucket_name: str, object_name: str, data, file_size: Optional[int] = None
    ) -> None:
        self._client.upload_video(bucket_name, object_name, data, file_size)

    def save_metadata_file(
        self,
        bucket_name: str,
        metadata_content: bytes,
        video_id: str,
        filename: str = "metadata.json",
    ) -> str:
        return self._client.save_metadata_file(
            bucket_name, metadata_content, video_id, filename
        )

    def get_object_metadata(self, bucket_name: str, object_name: str) -> dict:
        return self._client.get_object_metadata(bucket_name, object_name)

    def get_object_size(self, bucket_name: str, object_name: str) -> int:
        return self._client.get_object_size(bucket_name, object_name)

    # --- delete -------------------------------------------------------------
    def delete_object(self, bucket_name: str, object_name: str) -> None:
        try:
            self._client.client.remove_object(bucket_name, object_name)
            logger.info(
                "Deleted object %s from bucket %s",
                sanitize_for_log(object_name, max_length=256),
                sanitize_for_log(bucket_name, max_length=128),
            )
        except S3Error as exc:
            logger.error(
                "Error deleting object %s from bucket %s: %s",
                sanitize_for_log(object_name, max_length=256),
                sanitize_for_log(bucket_name, max_length=128),
                sanitize_for_log(exc, max_length=256),
            )
            raise Exception(f"Error deleting object {object_name}: {exc}")
