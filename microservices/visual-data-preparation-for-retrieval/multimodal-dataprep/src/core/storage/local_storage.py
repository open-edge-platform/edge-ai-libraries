# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Local filesystem implementation of :class:`BaseStorage`.

Each bucket maps to a subdirectory under ``settings.LOCAL_STORAGE_PATH`` and
object names map to relative paths within that directory. All path components
are validated to prevent traversal outside the configured root.
"""

from __future__ import annotations

import io
import os
import shutil
from datetime import datetime, timezone
from typing import Iterator, List, Optional

from src.common import logger, sanitize_for_log, settings
from src.core.storage.base import BaseStorage, StorageObject
from src.core.storage.factory import register_backend


@register_backend("local")
class LocalStorage(BaseStorage):
    """Storage backend backed by the local filesystem."""

    def __init__(self, root_path: Optional[str] = None) -> None:
        """Initialize the backend rooted at ``root_path`` (or the configured default)."""
        self._root = os.path.abspath(root_path or settings.LOCAL_STORAGE_PATH)
        os.makedirs(self._root, exist_ok=True)
        logger.info("Local storage initialized at root: %s", self._root)

    # --- path helpers -------------------------------------------------------
    @staticmethod
    def _validate_component(value: str, field_name: str) -> str:
        """Return a trimmed path component, rejecting empty/unsafe values."""
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError(f"{field_name} cannot be empty.")
        if "/" in cleaned or "\\" in cleaned or ".." in cleaned:
            raise ValueError(f"{field_name} contains unsafe path characters.")
        if cleaned in {".", ".."}:
            raise ValueError(f"{field_name} is not valid.")
        return cleaned

    def _bucket_dir(self, bucket_name: str) -> str:
        """Return the absolute directory for a bucket, validating its name."""
        safe_bucket = self._validate_component(bucket_name, "Bucket name")
        return os.path.join(self._root, safe_bucket)

    def _resolve_object_path(self, bucket_name: str, object_name: str) -> str:
        """Resolve an object name to an absolute path, guarding against traversal."""
        bucket_dir = self._bucket_dir(bucket_name)
        # object_name is expected as "<video_id>/<filename>"; validate each part.
        parts = [p for p in object_name.replace("\\", "/").split("/") if p != ""]
        if not parts:
            raise ValueError("Object name cannot be empty.")
        for part in parts:
            if part in {".", ".."}:
                raise ValueError("Object name contains unsafe path characters.")
        candidate = os.path.abspath(os.path.join(bucket_dir, *parts))
        bucket_root = os.path.abspath(bucket_dir)
        if candidate != bucket_root and not candidate.startswith(bucket_root + os.sep):
            raise ValueError("Resolved object path escapes the bucket directory.")
        return candidate

    # --- bucket / container operations -------------------------------------
    def bucket_exists(self, bucket_name: str) -> bool:
        """Implements :meth:`BaseStorage.bucket_exists`."""
        try:
            return os.path.isdir(self._bucket_dir(bucket_name))
        except ValueError:
            return False

    def ensure_bucket_exists(self, bucket_name: str) -> None:
        """Implements :meth:`BaseStorage.ensure_bucket_exists`."""
        os.makedirs(self._bucket_dir(bucket_name), exist_ok=True)

    # --- object existence / naming -----------------------------------------
    def compose_object_name(self, video_id: str, object_name: str) -> str:
        """Implements :meth:`BaseStorage.compose_object_name`."""
        safe_video_id = self._validate_component(video_id, "Video ID")
        safe_object_name = self._validate_component(object_name, "Object name")
        return f"{safe_video_id}/{safe_object_name}"

    def object_exists_by_path(self, bucket_name: str, object_name: str) -> bool:
        """Implements :meth:`BaseStorage.object_exists_by_path`."""
        try:
            return os.path.isfile(self._resolve_object_path(bucket_name, object_name))
        except ValueError:
            return False

    # --- listing ------------------------------------------------------------
    def list_objects_in_directory(
        self, bucket_name: str, video_id: str
    ) -> List[StorageObject]:
        """Implements :meth:`BaseStorage.list_objects_in_directory`."""
        safe_video_id = self._validate_component(video_id, "Video ID")
        dir_path = os.path.join(self._bucket_dir(bucket_name), safe_video_id)
        results: List[StorageObject] = []
        if not os.path.isdir(dir_path):
            return results
        for current_root, _dirs, files in os.walk(dir_path):
            for filename in files:
                abs_path = os.path.join(current_root, filename)
                rel_path = os.path.relpath(abs_path, self._bucket_dir(bucket_name))
                object_name = rel_path.replace(os.sep, "/")
                stat = os.stat(abs_path)
                results.append(
                    StorageObject(
                        object_name=object_name,
                        size=stat.st_size,
                        last_modified=datetime.fromtimestamp(
                            stat.st_mtime, tz=timezone.utc
                        ).isoformat(),
                    )
                )
        return results

    def list_all_videos(self, bucket_name: str) -> List[dict]:
        """Implements :meth:`BaseStorage.list_all_videos`."""
        bucket_dir = self._bucket_dir(bucket_name)
        result: List[dict] = []
        if not os.path.isdir(bucket_dir):
            return result
        for current_root, _dirs, files in os.walk(bucket_dir):
            for filename in files:
                if not filename.lower().endswith(".mp4"):
                    continue
                abs_path = os.path.join(current_root, filename)
                rel_path = os.path.relpath(abs_path, bucket_dir)
                parts = rel_path.replace(os.sep, "/").split("/")
                if len(parts) < 2:
                    continue
                video_id = parts[0]
                stat = os.stat(abs_path)
                result.append(
                    {
                        "video_id": video_id,
                        "video_name": filename,
                        "video_path": rel_path.replace(os.sep, "/"),
                        "creation_ts": datetime.fromtimestamp(
                            stat.st_mtime, tz=timezone.utc
                        ).isoformat(),
                    }
                )
        return result

    def get_video_in_directory(
        self, bucket_name: str, video_id: str, return_prefix: bool = True
    ) -> Optional[str]:
        """Implements :meth:`BaseStorage.get_video_in_directory`."""
        safe_video_id = self._validate_component(video_id, "Video ID")
        dir_path = os.path.join(self._bucket_dir(bucket_name), safe_video_id)
        if not os.path.isdir(dir_path):
            return None
        for current_root, _dirs, files in os.walk(dir_path):
            for filename in sorted(files):
                if filename.lower().endswith(".mp4"):
                    if return_prefix:
                        abs_path = os.path.join(current_root, filename)
                        rel = os.path.relpath(abs_path, self._bucket_dir(bucket_name))
                        return rel.replace(os.sep, "/")
                    return filename
        return None

    # --- read / write -------------------------------------------------------
    def download_video_stream(
        self, bucket_name: str, object_name: str
    ) -> Optional[io.BytesIO]:
        """Implements :meth:`BaseStorage.download_video_stream`."""
        abs_path = self._resolve_object_path(bucket_name, object_name)
        try:
            with open(abs_path, "rb") as handle:
                data = io.BytesIO(handle.read())
            data.seek(0)
            return data
        except FileNotFoundError as exc:
            logger.error(
                "Error downloading %s from bucket %s: not found",
                sanitize_for_log(object_name, max_length=256),
                sanitize_for_log(bucket_name, max_length=128),
            )
            raise Exception(f"Error downloading video: {exc}")

    def stream_object_range(
        self,
        bucket_name: str,
        object_name: str,
        offset: int = 0,
        length: Optional[int] = None,
        chunk_size: int = 1024 * 1024,
    ) -> Iterator[bytes]:
        """Implements :meth:`BaseStorage.stream_object_range` via file seek/read."""
        abs_path = self._resolve_object_path(bucket_name, object_name)

        def _generator() -> Iterator[bytes]:
            """Yield ``[offset, offset+length)`` bytes of the file in chunks."""
            with open(abs_path, "rb") as handle:
                if offset:
                    handle.seek(offset)
                remaining = length
                while True:
                    if remaining is not None:
                        if remaining <= 0:
                            break
                        to_read = min(chunk_size, remaining)
                    else:
                        to_read = chunk_size
                    chunk = handle.read(to_read)
                    if not chunk:
                        break
                    if remaining is not None:
                        remaining -= len(chunk)
                    yield chunk

        return _generator()

    def upload_video(
        self, bucket_name: str, object_name: str, data, file_size: Optional[int] = None
    ) -> None:
        """Implements :meth:`BaseStorage.upload_video`."""
        self.ensure_bucket_exists(bucket_name)
        abs_path = self._resolve_object_path(bucket_name, object_name)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "wb") as handle:
            if hasattr(data, "read"):
                shutil.copyfileobj(data, handle)
            elif isinstance(data, (bytes, bytearray)):
                handle.write(data)
            else:
                raise ValueError("Unsupported data type for upload_video.")
        logger.info(
            "Video uploaded successfully as %s in bucket %s",
            sanitize_for_log(object_name, max_length=256),
            sanitize_for_log(bucket_name, max_length=128),
        )

    def save_metadata_file(
        self,
        bucket_name: str,
        metadata_content: bytes,
        video_id: str,
        filename: str = "metadata.json",
    ) -> str:
        """Implements :meth:`BaseStorage.save_metadata_file`."""
        self.ensure_bucket_exists(bucket_name)
        object_name = self.compose_object_name(video_id, filename)
        abs_path = self._resolve_object_path(bucket_name, object_name)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "wb") as handle:
            handle.write(metadata_content)
        logger.info(f"Metadata file saved as {object_name} in bucket {bucket_name}")
        return object_name

    def get_object_metadata(self, bucket_name: str, object_name: str) -> dict:
        """Implements :meth:`BaseStorage.get_object_metadata`."""
        abs_path = self._resolve_object_path(bucket_name, object_name)
        stat = os.stat(abs_path)
        return {
            "size": stat.st_size,
            "creation_time": datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc
            ).isoformat(),
            "etag": None,
            "content_type": None,
        }

    def get_object_size(self, bucket_name: str, object_name: str) -> int:
        """Implements :meth:`BaseStorage.get_object_size`."""
        abs_path = self._resolve_object_path(bucket_name, object_name)
        return os.stat(abs_path).st_size

    # --- delete -------------------------------------------------------------
    def delete_object(self, bucket_name: str, object_name: str) -> None:
        """Implements :meth:`BaseStorage.delete_object`."""
        abs_path = self._resolve_object_path(bucket_name, object_name)
        try:
            os.remove(abs_path)
            logger.info(
                "Deleted object %s from bucket %s",
                sanitize_for_log(object_name, max_length=256),
                sanitize_for_log(bucket_name, max_length=128),
            )
        except FileNotFoundError:
            logger.warning(
                "Object %s not found in bucket %s during delete",
                sanitize_for_log(object_name, max_length=256),
                sanitize_for_log(bucket_name, max_length=128),
            )
