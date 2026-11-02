# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Bookkeeping for media ingested *by reference* (``store_copy=false``).

When a directory ingest runs with ``store_copy=false`` the service embeds the
media but never copies its bytes into the storage backend, so the usual
``<bucket>/<video_id>/<filename>`` object does not exist. Without an extra trace
the service would know the file only through the ``source_path`` it wrote into
the vector DB, which the media-management endpoints do not read.

This module records that trace as a **path sidecar**, mirroring the existing
dedup sidecar convention (see :mod:`src.core.dedup`):

* key ``<video_id>/<SOURCE_REF_SIDECAR>``
* body: the media path **relative to** :data:`Settings.INGEST_DATA_ROOT`

Storing a relative path (rather than an absolute one) keeps the marker valid if
the ingest mount is remapped, and makes it impossible for a stale sidecar to
point outside the root. Every read still re-validates the resolved path against
the current ingest root, so the sidecar can never be used to escape the mount.

The sidecar is an ordinary storage object written through the active backend, so
it works for both MinIO and local filesystem storage, and it is not a media file
so the ``video_id``-directory listing/resolution helpers ignore it. It is removed
together with the ``video_id`` directory on delete.

With this marker in place ``GET /media`` can list referenced media and
``GET /media/download`` can stream it (with full HTTP Range support) directly
from the ingest mount, so a reference ingest is observably equivalent to a stored
one from the API's point of view.
"""

from __future__ import annotations

import os
import pathlib
from datetime import datetime, timezone
from typing import List, Optional

from src.common import DataPrepException, logger, settings
from src.core.dedup import DEDUP_PREFIX
from src.core.storage.base import BaseStorage
from src.core.utils.file_utils import resolve_under_ingest_root, to_host_path

# Path sidecar filename stored inside each referenced video's directory. Not a
# media file, so it is ignored by the video listing/resolution helpers.
SOURCE_REF_SIDECAR = ".source_ref"


def register_source_ref(
    storage: BaseStorage, bucket_name: str, video_id: str, source_path: str | pathlib.Path
) -> None:
    """Record where ``video_id``'s media lives on the ingest mount.

    Best-effort: a failure here only costs the ability to list/download the item
    later, so it must never fail the ingest itself.

    Args:
        storage: Active storage backend.
        bucket_name: Bucket the media was ingested into.
        video_id: The owning video identifier.
        source_path: Absolute container path of the referenced media file.
    """
    try:
        root = pathlib.Path(settings.INGEST_DATA_ROOT).resolve()
        relative = pathlib.Path(source_path).resolve().relative_to(root)
        storage.save_metadata_file(
            bucket_name,
            relative.as_posix().encode("utf-8"),
            video_id,
            SOURCE_REF_SIDECAR,
        )
    except Exception as ex:  # noqa: BLE001 - reference bookkeeping is best-effort
        logger.warning(
            "Failed to register source reference for video %s in bucket %s: %s",
            video_id,
            bucket_name,
            ex,
        )


def read_source_ref(storage: BaseStorage, bucket_name: str, video_id: str) -> Optional[str]:
    """Return the ingest-root-relative path recorded for ``video_id``, if any.

    Args:
        storage: Active storage backend.
        bucket_name: Bucket to look in.
        video_id: The video identifier to resolve.

    Returns:
        Optional[str]: The recorded relative path, or ``None`` when the media was
        stored normally (no sidecar) or the sidecar is unreadable.
    """
    object_name = f"{video_id}/{SOURCE_REF_SIDECAR}"
    try:
        if not storage.object_exists_by_path(bucket_name, object_name):
            return None
        stream = storage.download_video_stream(bucket_name, object_name)
        if stream is None:
            return None
        return stream.read().decode("utf-8").strip() or None
    except Exception as ex:  # noqa: BLE001 - reporting only
        logger.warning("Could not read source reference %s: %s", object_name, ex)
        return None


def resolve_referenced_file(
    storage: BaseStorage, bucket_name: str, video_id: str
) -> Optional[pathlib.Path]:
    """Resolve ``video_id`` to a readable file on the ingest mount.

    The recorded path is re-validated against the *current* ingest root, so a
    stale or tampered sidecar can never be used to read outside the mount.

    Args:
        storage: Active storage backend.
        bucket_name: Bucket to look in.
        video_id: The video identifier to resolve.

    Returns:
        Optional[pathlib.Path]: The resolved file, or ``None`` when there is no
        reference sidecar or the referenced file is no longer readable.
    """
    relative = read_source_ref(storage, bucket_name, video_id)
    if not relative:
        return None
    try:
        return resolve_under_ingest_root(relative)
    except DataPrepException as ex:
        logger.warning(
            "Reference sidecar for video %s in bucket %s is not resolvable: %s",
            video_id,
            bucket_name,
            ex.message,
        )
        return None


def referenced_video_ids(storage: BaseStorage, bucket_name: str) -> set:
    """Return the video ids recorded by content markers in a bucket.

    Each forward dedup marker holds the ``video_id`` that owns its content hash,
    which is the only trace left by media ingested by reference
    (``store_copy=false``) and therefore having no stored object to list.

    Args:
        storage: Active storage backend.
        bucket_name: Bucket to enumerate.

    Returns:
        set: Video ids named by the bucket's forward dedup markers. Includes ids
        of normally stored media, which also register markers.
    """
    video_ids = set()
    try:
        for obj in storage.list_objects_in_directory(bucket_name, DEDUP_PREFIX):
            stream = storage.download_video_stream(bucket_name, obj.object_name)
            if stream is None:
                continue
            video_id = stream.read().decode("utf-8").strip()
            if video_id:
                video_ids.add(video_id)
    except Exception as ex:  # noqa: BLE001 - marker bookkeeping is best-effort
        logger.warning("Could not enumerate content markers in %s: %s", bucket_name, ex)
    return video_ids


def list_referenced_media(storage: BaseStorage, bucket_name: str) -> List[dict]:
    """List media ingested by reference into ``bucket_name``.

    Complements ``storage.list_all_videos()``, which can only see stored objects.
    Entries whose referenced file has since been moved or deleted are skipped (and
    logged) so the listing only advertises media that can actually be served.

    Args:
        storage: Active storage backend.
        bucket_name: Bucket to enumerate.

    Returns:
        List[dict]: Entries shaped like ``storage.list_all_videos()`` results,
        with ``video_path`` carrying the host-visible source path.
    """
    results: List[dict] = []
    for video_id in sorted(referenced_video_ids(storage, bucket_name)):
        resolved = resolve_referenced_file(storage, bucket_name, video_id)
        if resolved is None:
            continue
        stat = os.stat(resolved)
        results.append(
            {
                "video_id": video_id,
                "video_name": resolved.name,
                "video_path": to_host_path(resolved),
                "creation_ts": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "stored": False,
                "source_path": to_host_path(resolved),
            }
        )
    return results
