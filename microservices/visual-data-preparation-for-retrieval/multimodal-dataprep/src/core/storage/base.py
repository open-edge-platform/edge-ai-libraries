# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Abstract base class describing the storage contract used by the DataPrep service.

The contract is intentionally framed around the video + metadata object-storage
operations the service actually performs, so that any backend (object store or
local filesystem) is interchangeable behind it.
"""

from __future__ import annotations

import io
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class StorageObject:
    """Backend-neutral representation of a stored object.

    Mirrors the subset of MinIO object attributes consumed by the service so
    callers can iterate listings uniformly regardless of backend.
    """

    object_name: str
    size: Optional[int] = None
    last_modified: Optional[str] = None
    etag: Optional[str] = None
    content_type: Optional[str] = None


class BaseStorage(ABC):
    """Common interface every storage backend must implement.

    Object names follow the ``<video_id>/<filename>`` convention used throughout
    the service. Implementations must validate untrusted path components to avoid
    traversal outside their root/bucket.
    """

    # --- bucket / container operations -------------------------------------
    @abstractmethod
    def bucket_exists(self, bucket_name: str) -> bool:
        """Return True if the bucket/container exists."""

    @abstractmethod
    def ensure_bucket_exists(self, bucket_name: str) -> None:
        """Create the bucket/container if it does not already exist."""

    # --- object existence / naming -----------------------------------------
    @abstractmethod
    def compose_object_name(self, video_id: str, object_name: str) -> str:
        """Build a safe ``<video_id>/<object_name>`` key, rejecting unsafe input."""

    @abstractmethod
    def validate_object_name(self, video_id: str, video_name: str) -> bool:
        """Validate a (video_id, video_name) pair against backend naming rules."""

    @abstractmethod
    def object_exists_by_path(self, bucket_name: str, object_name: str) -> bool:
        """Return True if an object exists at the fully composed path."""

    @abstractmethod
    def object_exists(self, bucket_name: str, video_id: str, video_name: str) -> bool:
        """Return True if ``<video_id>/<video_name>`` exists in the bucket."""

    # --- listing ------------------------------------------------------------
    @abstractmethod
    def list_objects_in_directory(
        self, bucket_name: str, video_id: str
    ) -> List[StorageObject]:
        """List all objects under a ``video_id`` directory prefix."""

    @abstractmethod
    def list_all_videos(self, bucket_name: str) -> List[dict]:
        """List videos in the bucket as dicts (video_id, video_name, video_path, creation_ts)."""

    @abstractmethod
    def get_video_in_directory(
        self, bucket_name: str, video_id: str, return_prefix: bool = True
    ) -> Optional[str]:
        """Return the first video object in a ``video_id`` directory, or None."""

    # --- read / write -------------------------------------------------------
    @abstractmethod
    def download_video_stream(
        self, bucket_name: str, object_name: str
    ) -> Optional[io.BytesIO]:
        """Download an object into an in-memory stream."""

    @abstractmethod
    def upload_video(
        self, bucket_name: str, object_name: str, data, file_size: Optional[int] = None
    ) -> None:
        """Upload a video object."""

    @abstractmethod
    def save_metadata_file(
        self,
        bucket_name: str,
        metadata_content: bytes,
        video_id: str,
        filename: str = "metadata.json",
    ) -> str:
        """Persist a metadata file under a ``video_id`` directory; return its key."""

    @abstractmethod
    def get_object_metadata(self, bucket_name: str, object_name: str) -> dict:
        """Return object metadata (size, creation_time, etag, content_type)."""

    @abstractmethod
    def get_object_size(self, bucket_name: str, object_name: str) -> int:
        """Return the object size in bytes."""

    # --- delete -------------------------------------------------------------
    @abstractmethod
    def delete_object(self, bucket_name: str, object_name: str) -> None:
        """Delete a single object."""
