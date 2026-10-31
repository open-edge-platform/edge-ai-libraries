# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Video Utilities Module

Media lookup and download helpers for videos stored in object storage or
referenced on the ingest mount.

Functions:
- resolve_video_object(): Resolve a video id to its storage object
- resolve_media_source(): Resolve stored or referenced media for streaming
- get_video_from_minio(): Download video from MinIO storage
"""

import io
import pathlib
from dataclasses import dataclass
from typing import Iterator, Optional, Tuple

from src.common import DataPrepException, Strings, logger, sanitize_for_log
from .common_utils import get_minio_client
from .file_utils import stream_file_range


def resolve_video_object(bucket_name: str, video_id: str) -> Tuple[str, str]:
    """Resolve a stored video's object key and filename without downloading it.

    Each ``video_id`` directory holds exactly one video file, so resolution is
    unambiguous: the single object under the directory is returned.

    Args:
        bucket_name (str): The bucket containing the video.
        video_id (str): The directory (video_id) containing the video.

    Returns:
        Tuple[str, str]: ``(object_name, filename)`` where ``object_name`` is the
        fully composed ``<video_id>/<filename>`` storage key.

    Raises:
        DataPrepException: If no video object can be found in the directory.
    """
    minio_client = get_minio_client()

    object_name = minio_client.get_video_in_directory(bucket_name, video_id)

    if not object_name:
        logger.error(
            "No video found in directory %s",
            sanitize_for_log(video_id, max_length=128),
        )
        raise DataPrepException(status_code=404, msg=Strings.video_id_not_found)

    filename = pathlib.Path(object_name).name
    return object_name, filename


@dataclass
class MediaSource:
    """Where a ``video_id``'s bytes actually live, and how to read them.

    Media ingested normally has an object in the storage backend; media ingested
    by reference (``store_copy=false``) has none and is read from the ingest
    mount instead. Both are byte-range readable, so callers can treat them
    uniformly: use :meth:`size` and :meth:`stream`.
    """

    filename: str
    #: Storage key ``<video_id>/<filename>``; ``None`` for referenced media.
    object_name: Optional[str] = None
    #: Validated path on the ingest mount; ``None`` for stored media.
    file_path: Optional[pathlib.Path] = None

    def size(self, bucket_name: str) -> int:
        """Return the media size in bytes."""
        if self.file_path is not None:
            return self.file_path.stat().st_size
        return get_minio_client().get_object_size(bucket_name, self.object_name)

    def stream(
        self, bucket_name: str, offset: int = 0, length: Optional[int] = None
    ) -> Iterator[bytes]:
        """Stream ``[offset, offset+length)`` bytes of the media."""
        if self.file_path is not None:
            return stream_file_range(self.file_path, offset=offset, length=length)
        return get_minio_client().stream_object_range(
            bucket_name, self.object_name, offset=offset, length=length
        )


def resolve_media_source(
    bucket_name: str, video_id: str, media_path: Optional[str] = None
) -> MediaSource:
    """Resolve ``video_id`` to a readable media source, stored or referenced.

    Tries the storage backend first (the common case), then falls back to the
    reference sidecar written by a ``store_copy=false`` ingest. This keeps
    referenced media servable by ``GET /media/download`` even though no object
    was ever stored for it.

    Args:
        bucket_name (str): The bucket containing the media.
        video_id (str): The media identifier to resolve.
        media_path (str, optional): Relative path to one object inside the
            ``video_id`` directory, e.g. ``"segments/1790655530.mp4"``. Required to
            address live-stream media, which is stored a level below ``video_id``.
            Must already be validated by ``sanitize_media_subpath``.

    Returns:
        MediaSource: A handle exposing the media's size and a byte-range reader.

    Raises:
        DataPrepException: 404 if the media is neither stored nor referenced.
    """
    from src.core.media_ref import resolve_referenced_file

    minio_client = get_minio_client()

    if media_path:
        # Addressing one object directly. The prefix is always the caller's
        # video_id, so a validated relative path cannot reach outside it.
        object_name = f"{video_id}/{media_path}"
        if minio_client.object_exists_by_path(bucket_name, object_name):
            return MediaSource(filename=pathlib.Path(object_name).name, object_name=object_name)
        logger.error(
            "No media found at %s in bucket %s",
            sanitize_for_log(object_name, max_length=256),
            sanitize_for_log(bucket_name, max_length=128),
        )
        raise DataPrepException(status_code=404, msg=Strings.video_id_not_found)

    object_name = minio_client.get_video_in_directory(bucket_name, video_id)
    if object_name:
        return MediaSource(
            filename=pathlib.Path(object_name).name, object_name=object_name
        )

    referenced = resolve_referenced_file(minio_client, bucket_name, video_id)
    if referenced is not None:
        return MediaSource(filename=referenced.name, file_path=referenced)

    logger.error(
        "No media found for video_id %s",
        sanitize_for_log(video_id, max_length=128),
    )
    raise DataPrepException(status_code=404, msg=Strings.video_id_not_found)


def get_video_from_minio(bucket_name: str, video_id: str) -> Tuple[io.BytesIO, str]:
    """Get video data from Minio storage.

    Args:
        bucket_name (str): The bucket containing the video
        video_id (str): The directory (video_id) containing the single video

    Returns:
        Tuple[io.BytesIO, str]: Tuple containing the video data and the video filename

    Raises:
        DataPrepException: If video not found or other Minio error occurs
    """
    try:
        minio_client = get_minio_client()

        # Resolve the object key + filename (no download yet)
        object_name, filename = resolve_video_object(bucket_name, video_id)

        # Get the video data
        data = minio_client.download_video_stream(bucket_name, object_name)
        if not data:
            logger.error(
                "Failed to download video %s",
                sanitize_for_log(object_name, max_length=256),
            )
            raise DataPrepException(status_code=404, msg=Strings.minio_file_not_found)

        return data, filename
    except DataPrepException as ex:
        # Re-raise DataPrepException directly
        raise ex
    except Exception as ex:
        logger.error(f"Error getting video from Minio: {ex}")
        raise DataPrepException(status_code=500, msg=Strings.minio_error)
