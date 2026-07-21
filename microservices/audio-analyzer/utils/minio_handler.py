# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""MinIO object-storage helper for the VSS-compatibility endpoints.

This is only used by ``POST /transcriptions`` (see api/custom_endpoints.py)
to mirror the previous Edge AI Libraries release's contract with VSS's
pipeline-manager: it downloads the source video from a MinIO bucket and
uploads the resulting transcript back into that same bucket, since VSS reads
the transcript directly from MinIO itself rather than via this service's API.

No other endpoint depends on MinIO; if it is not configured (``minio.endpoint``
empty), ``is_configured()`` returns False and callers should respond with a
clear error instead of failing on a missing client.
"""
import logging
import os
import traceback
from pathlib import Path
from typing import Optional, Tuple

from utils.app_paths import STORAGE_ROOT
from utils.config_loader import config

logger = logging.getLogger(__name__)


class MinioHandler:
    """Lazy-initialized MinIO client wrapper.

    Kept as a thin wrapper (rather than importing ``minio`` at module import
    time) so the rest of the service works even when the ``minio`` package is
    not installed or MinIO is not configured for a given deployment.
    """

    _client = None

    @classmethod
    def is_configured(cls) -> bool:
        """Return True if a MinIO endpoint has been configured."""
        return bool(getattr(config.minio, "endpoint", ""))

    @classmethod
    def get_client(cls):
        """Get or create the MinIO client.

        Raises:
            RuntimeError: if MinIO is not configured or the client cannot be
                created (e.g. the ``minio`` package is missing).
        """
        if cls._client is None:
            if not cls.is_configured():
                raise RuntimeError("MinIO is not configured (minio.endpoint is empty)")
            try:
                from minio import Minio
            except ImportError as exc:
                raise RuntimeError(
                    "The 'minio' package is required for MinIO support but is not installed"
                ) from exc

            try:
                logger.debug("Creating MinIO client with endpoint: %s", config.minio.endpoint)
                cls._client = Minio(
                    config.minio.endpoint,
                    access_key=config.minio.access_key,
                    secret_key=config.minio.secret_key,
                    secure=bool(config.minio.secure),
                )
                logger.info("MinIO client created successfully")
            except Exception as exc:
                logger.error("Failed to create MinIO client: %s", exc)
                logger.debug("Error details: %s", traceback.format_exc())
                raise RuntimeError(f"Failed to create MinIO client: {exc}") from exc

        return cls._client

    @classmethod
    def ensure_bucket_exists(cls, bucket_name: str) -> bool:
        """Check whether a bucket exists (does not create it)."""
        client = cls.get_client()
        try:
            if client.bucket_exists(bucket_name):
                return True
            logger.warning("Bucket %s does not exist", bucket_name)
            return False
        except Exception as exc:
            logger.error("Failed to check if bucket %s exists: %s", bucket_name, exc)
            logger.debug("Error details: %s", traceback.format_exc())
            return False

    @classmethod
    async def get_video_from_minio(
        cls, bucket_name: str, video_id: str, video_name: str
    ) -> Tuple[Optional[Path], Optional[str]]:
        """Download a source video from MinIO to a local scratch path.

        Args:
            bucket_name: MinIO bucket containing the video.
            video_id: Prefix/ID of the video object within the bucket.
            video_name: Name of the video file.

        Returns:
            Tuple of (local Path, error message). On success error is None.
        """
        try:
            client = cls.get_client()
        except RuntimeError as exc:
            return None, str(exc)

        object_name = f"{video_id}/{video_name}" if video_id else video_name
        download_dir = os.path.join(STORAGE_ROOT, "minio_downloads", video_id or "_")
        os.makedirs(download_dir, exist_ok=True)
        local_path = Path(download_dir) / video_name

        try:
            logger.info("Retrieving video %s from bucket %s", object_name, bucket_name)

            if not client.bucket_exists(bucket_name):
                error_msg = f"Bucket {bucket_name} does not exist"
                logger.error(error_msg)
                return None, error_msg

            client.fget_object(bucket_name, object_name, str(local_path))
            logger.debug("Video downloaded successfully to %s", local_path)
            return local_path, None
        except Exception as exc:
            error_msg = f"Error retrieving video from MinIO: {exc}"
            logger.error(error_msg)
            logger.debug("Error details: %s", traceback.format_exc())
            return None, error_msg

    @classmethod
    def save_transcript_to_minio(
        cls, file_path: Path, bucket_name: str, object_name: str
    ) -> Tuple[bool, Optional[str]]:
        """Upload a transcript file to MinIO.

        Args:
            file_path: Local path of the transcript file to upload.
            bucket_name: Destination bucket.
            object_name: Object key to store the transcript under.

        Returns:
            Tuple of (success flag, error message). On success error is None.
        """
        try:
            client = cls.get_client()
        except RuntimeError as exc:
            return False, str(exc)

        try:
            logger.info("Uploading transcript %s to MinIO bucket %s", file_path, bucket_name)

            if not cls.ensure_bucket_exists(bucket_name):
                error_msg = f"Bucket {bucket_name} does not exist"
                logger.error(error_msg)
                return False, error_msg

            client.fput_object(
                bucket_name,
                object_name,
                str(file_path),
                content_type="text/plain",
            )
            logger.debug("Transcript uploaded successfully to %s/%s", bucket_name, object_name)
            return True, None
        except Exception as exc:
            error_msg = f"Error uploading transcript to MinIO: {exc}"
            logger.error(error_msg)
            logger.debug("Error details: %s", traceback.format_exc())
            return False, error_msg
