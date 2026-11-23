# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File Utilities Module

Path validation and streaming helpers for media on the ingest mount.

Functions:
- resolve_under_ingest_root(): Resolve a path under the ingest root, blocking traversal
- to_host_path(): Translate a container ingest path to its host path
- stream_file_range(): Stream a byte range of a local file
"""

import pathlib
from typing import Iterator, Optional

from src.common import settings


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
