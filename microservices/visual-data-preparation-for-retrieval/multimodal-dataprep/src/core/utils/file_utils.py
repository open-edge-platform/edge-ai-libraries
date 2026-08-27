# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File Utilities Module

This module provides file operation utilities for the VDMS microservice.
Supports in-process embedding generation.

Functions:
- save_video_to_temp(): Save video data to temporary file
- create_temp_directory(): Create unique temporary directory
- cleanup_temp_directory(): Clean up temporary directories
- save_metadata_at_temp(): Save metadata to temporary JSON file

Usage:
    from src.core.utils.file_utils import create_temp_directory, cleanup_temp_directory
    
    # Create temporary directory
    temp_dir = create_temp_directory()
    
    # Save video to temporary location
    video_path = save_video_to_temp(video_data, "video.mp4", temp_dir)
    
    # Clean up when done
    cleanup_temp_directory(temp_dir)
"""

import io
import json
import pathlib
import shutil
import uuid
from typing import Any, Dict, Iterator, Optional

from src.common import logger, settings
from .config_utils import get_config


def save_video_to_temp(data: io.BytesIO, filename: str, temp_dir: str) -> pathlib.Path:
    """Save the video data to a temporary directory.

    Args:
        data (io.BytesIO): The video data
        filename (str): The filename to use
        temp_dir (str): The directory path string where videofile needs to be temporarily saved

    Returns:
        pathlib.Path: Path to the saved file
    """
    temp_file = pathlib.Path(temp_dir) / filename
    temp_file.parent.mkdir(parents=True, exist_ok=True)

    with open(temp_file, "wb") as file:
        file.write(data.read())

    return temp_file


def create_temp_directory(base_path: str = None) -> str:
    """
    Create a unique temporary directory for frame extraction.
    
    Args:
        base_path: Base path for temporary directories. If None, uses config default.
        
    Returns:
        Path to the created temporary directory
    """
    if base_path is None:
        config = get_config()
        base_path = config.get("frames_temp_dir", "/tmp/dataprep/frames")
    
    unique_id = uuid.uuid4().hex
    temp_dir = pathlib.Path(base_path) / f"frames_{unique_id}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return str(temp_dir)


def cleanup_temp_directory(temp_dir: str) -> None:
    """
    Clean up temporary directory and all its contents.
    
    Args:
        temp_dir: Path to the temporary directory to clean up
    """
    try:
        temp_path = pathlib.Path(temp_dir)
        if temp_path.exists():
            shutil.rmtree(temp_path, ignore_errors=True)
            logger.debug(f"Cleaned up temporary directory: {temp_dir}")
    except Exception as e:
        logger.warning(f"Failed to cleanup temporary directory {temp_dir}: {e}")


def save_metadata_at_temp(metadata_temp_path: str, metadata: dict) -> pathlib.Path:
    """
    Dumps the metadata dictionary in json format in a temporary file.

    Args:
        metadata_temp_path (str) : Temporary path where metadata json needs to be saved
        metadata (dict) :  the metadata content as python dict

    Returns:
        metadata_file (Path) : Path of the metadata file location
    """
    metadata_path = pathlib.Path(metadata_temp_path)
    metadata_path.mkdir(parents=True, exist_ok=True)
    metadata_file = metadata_path / settings.METADATA_FILENAME

    logger.info("Saving video metadata to a temporary file...")
    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=4)

    logger.info("Metadata saved!")
    return metadata_file

def resolve_under_ingest_root(path: str, *, must_be_dir: bool = False) -> pathlib.Path:
    """Resolve ``path`` against the configured ingest root, blocking traversal.

    Shared by the directory-ingest endpoint (which validates the requested
    directory) and the batch processor (which re-validates a referenced media
    file, because a reference ingest reads from the mount long after the request
    was accepted).

    Args:
        path: Absolute path, or a path relative to ``INGEST_DATA_ROOT``.
        must_be_dir: Require the resolved target to be a directory.

    Returns:
        The resolved path, guaranteed to live under the ingest root.

    Raises:
        DataPrepException: 400 when the path escapes the root, 404 when the
            target does not exist.
    """
    from http import HTTPStatus

    from src.common import DataPrepException, Strings

    root = pathlib.Path(settings.INGEST_DATA_ROOT).resolve()
    requested = pathlib.Path(path)
    target = (requested if requested.is_absolute() else root / requested).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise DataPrepException(
            status_code=HTTPStatus.BAD_REQUEST, msg=Strings.ingest_path_invalid
        )
    if must_be_dir:
        if not target.is_dir():
            raise DataPrepException(
                status_code=HTTPStatus.NOT_FOUND, msg=Strings.ingest_dir_not_found
            )
    elif not target.is_file():
        raise DataPrepException(
            status_code=HTTPStatus.NOT_FOUND, msg=Strings.ingest_file_not_found
        )
    return target


def to_host_path(path: pathlib.Path | str) -> str:
    """Map a container path under the ingest root to its host-visible path.

    Consumers that share the ingest mount (the host directory bind-mounted at
    ``INGEST_DATA_ROOT``) need the path as it exists *outside* the container.
    When ``INGEST_DATA_ROOT_HOST`` is unset, the container path is returned
    unchanged.
    """
    resolved = str(path)
    host_root = (settings.INGEST_DATA_ROOT_HOST or "").rstrip("/")
    if not host_root:
        return resolved
    container_root = str(pathlib.Path(settings.INGEST_DATA_ROOT).resolve()).rstrip("/")
    if resolved == container_root:
        return host_root
    if resolved.startswith(container_root + "/"):
        return host_root + resolved[len(container_root):]
    return resolved


def stream_file_range(
    path: pathlib.Path | str,
    offset: int = 0,
    length: Optional[int] = None,
    chunk_size: int = 1024 * 1024,
) -> Iterator[bytes]:
    """Yield ``[offset, offset+length)`` bytes of a local file in chunks.

    The filesystem counterpart of ``BaseStorage.stream_object_range``, used to
    serve media that was ingested by reference (``store_copy=false``) and so has
    no object in the storage backend. Reading in chunks keeps large media out of
    memory, and seeking makes HTTP Range requests cheap.

    The caller is responsible for having validated ``path`` (see
    :func:`resolve_under_ingest_root`); this helper performs no path checks.

    Args:
        path: File to read.
        offset: First byte to read.
        length: Number of bytes to read; ``None`` reads to end of file.
        chunk_size: Read granularity in bytes.

    Yields:
        bytes: Successive chunks of the requested range.
    """
    def _generator() -> Iterator[bytes]:
        """Seek to ``offset`` and yield at most ``length`` bytes."""
        with open(path, "rb") as handle:
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
