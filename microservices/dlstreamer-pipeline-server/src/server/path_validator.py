#
# Apache v2 license
# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

"""File URI validation and file-destination permission hardening.

Fixes: 'source'/'destination' fields in pipeline start/execute requests accepted
file:// URIs with no validation, allowing a client to read/write arbitrary
filesystem paths reachable by the container. Restricts file:// URIs to the
resources directory that the container actually mounts for user-supplied media
(docker/docker-compose.yml: "../resources:/home/pipeline-server/resources/").
Also pre-creates file-type destination output (e.g. /tmp/results.jsonl) with
restrictive permissions before the gvametapublish GStreamer element writes to
it, since that element is compiled native code outside this repository and
does not set permissions itself.
"""

import os
import pathlib

RESOURCES_BASE_DIR = pathlib.Path("/home/pipeline-server/resources")

_FILE_URI_PREFIX = "file://"

# Owner read/write only - gvametapublish output files may contain
# inference results and should not be world/group readable by default.
_DESTINATION_FILE_MODE = 0o640


def validate_file_uri(uri):
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


def validate_request_uris(request):
    """Validate every file:// URI in a pipeline start/execute request's
    'source'/'destination' fields. Returns (True, None) or (False, error_message).
    """
    for field in ("source", "destination"):
        section = request.get(field) if isinstance(request, dict) else None
        if not isinstance(section, dict):
            continue
        uri = section.get("uri")
        if uri is not None and not validate_file_uri(uri):
            return False, "Invalid {} URI: path outside allowed resources directory".format(field)
    return True, None


def restrict_file_destination_permissions(request, logger=None):
    """If the request's destination is a file (e.g. metapublish writing
    /tmp/results.jsonl), pre-create it with restrictive permissions (0640) so
    the GStreamer element that actually opens/writes it does not leave the
    file world/group readable. Best-effort - never blocks pipeline start.
    """
    try:
        metadata = request.get("destination", {}).get("metadata") if isinstance(request, dict) else None
        if not isinstance(metadata, dict) or metadata.get("type") != "file":
            return
        path = metadata.get("path")
        if not path:
            return
        fd = os.open(path, os.O_CREAT | os.O_WRONLY, _DESTINATION_FILE_MODE)
        os.close(fd)
        os.chmod(path, _DESTINATION_FILE_MODE)
    except OSError as e:
        if logger is not None:
            logger.warning("Could not restrict permissions on destination file: %s", e)
