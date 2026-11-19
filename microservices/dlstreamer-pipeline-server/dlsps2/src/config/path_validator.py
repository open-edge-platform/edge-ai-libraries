# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Validation and permission hardening for user-supplied source/destination
file paths before they are injected into a GStreamer pipeline string.

The legacy named-pipeline API (POST /pipelines/{name}/{version}) accepts a
`source.uri` and a `destination.metadata.path`, which are substituted directly
into the pipeline description with no validation (see config/compat.py).
This lets a client read/write arbitrary filesystem paths reachable by the
container via a `file://` URI or a `file`-type destination path. This module
restricts those values to the directory the container actually mounts for
user-supplied media (docker/docker-compose.yml: "../resources:/home/pipeline-server/resources/").
"""

from __future__ import annotations

import os
import pathlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from api.schema import DestinationConfig, SourceConfig

RESOURCES_BASE_DIR = pathlib.Path("/home/pipeline-server/resources")

_FILE_URI_PREFIX = "file://"

# Owner read/write only - gvametapublish output files may contain inference
# results and should not be world/group readable by default.
_DESTINATION_FILE_MODE = 0o640


def validate_file_uri(uri: str | None) -> bool:
    """Return True if `uri` is not a file:// URI, or if it is one that resolves
    inside RESOURCES_BASE_DIR. Return False for any file:// URI that escapes it
    (path traversal, absolute paths elsewhere, symlink escapes, etc.).
    """
    if not isinstance(uri, str) or not uri.startswith(_FILE_URI_PREFIX):
        return True

    raw_path = uri[len(_FILE_URI_PREFIX):]
    try:
        resolved = pathlib.Path(raw_path).resolve()
        base = RESOURCES_BASE_DIR.resolve()
        resolved.relative_to(base)
    except (ValueError, OSError):
        return False
    return True


def validate_file_path(path: str | None) -> bool:
    """Same check as validate_file_uri, but for a plain filesystem path (no
    file:// scheme) such as destination.metadata.path.
    """
    if not path:
        return True
    try:
        resolved = pathlib.Path(path).resolve()
        base = RESOURCES_BASE_DIR.resolve()
        resolved.relative_to(base)
    except (ValueError, OSError):
        return False
    return True


def validate_source_destination(
    source: "SourceConfig | None", destination: "DestinationConfig | None"
) -> tuple[bool, str | None]:
    """Validate a request's source.uri and destination.metadata.path (file
    type only). Returns (True, None) or (False, error_message).
    """
    if source is not None and source.uri is not None and not validate_file_uri(source.uri):
        return False, "Invalid source.uri: path outside allowed resources directory"

    if destination is not None and destination.metadata is not None:
        meta = destination.metadata
        if (meta.type or "").lower() == "file" and not validate_file_path(meta.path):
            return False, "Invalid destination.metadata.path: path outside allowed resources directory"

    return True, None


def restrict_file_destination_permissions(
    destination: "DestinationConfig | None", logger=None
) -> None:
    """If the destination is a file (gvametapublish writing e.g.
    /tmp/results.jsonl), pre-create it with restrictive permissions (0640) so
    the GStreamer element that actually opens/writes it does not leave the
    file world/group readable. Best-effort - never blocks pipeline start.
    """
    if destination is None or destination.metadata is None:
        return
    meta = destination.metadata
    if (meta.type or "").lower() != "file" or not meta.path:
        return
    try:
        fd = os.open(meta.path, os.O_CREAT | os.O_WRONLY, _DESTINATION_FILE_MODE)
        os.close(fd)
        os.chmod(meta.path, _DESTINATION_FILE_MODE)
    except OSError as e:
        if logger is not None:
            logger.warning("Could not restrict permissions on destination file: %s", e)
