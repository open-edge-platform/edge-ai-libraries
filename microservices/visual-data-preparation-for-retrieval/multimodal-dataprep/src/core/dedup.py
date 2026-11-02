# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Content-based duplicate-upload detection for video ingestion.

The service can optionally reject re-uploads of a file whose bytes are identical
to a previously ingested video. Detection is content-based (SHA-256 of the raw
bytes) rather than filename-based, so a renamed copy is still recognised as a
duplicate and two genuinely different files that happen to share a name are not
falsely blocked.

Design (storage-backend agnostic, O(1) lookup): a **bidirectional index pair**.

Two different questions must be answered at two different times, and each needs
the opposite lookup direction, so we maintain two tiny companion objects — one
per direction (like a forward index paired with an inverted index):

* **Forward hash marker** — key ``<DEDUP_PREFIX>/<sha256>``, body ``video_id``.
    - *"marker"*: a sentinel object whose mere existence is the signal ("this
      content is already ingested"); it holds no media.
    - *"hash"*: its key *is* the content hash, so the duplicate check is a single
      keyed ``object_exists_by_path`` (a HEAD/stat point lookup) — constant time
      regardless of how many videos exist (no bucket scan).
    - *"forward"*: resolves the primary direction **hash -> video_id**, the
      question the upload path asks.
  Read by :func:`find_duplicate_video_id` during the upload duplicate check.

* **Reverse sidecar** — key ``<video_id>/<CONTENT_HASH_SIDECAR>``, body ``sha256``.
    - *"sidecar"*: a small companion file stored next to the media it describes
      (inside the ``video_id`` directory, beside the ``.mp4``); it is therefore
      deleted automatically when that directory is deleted.
    - *"reverse"*: resolves the opposite direction **video_id -> hash**. Delete
      knows only the ``video_id``; without this reverse lookup it would have to
      scan every forward marker (O(n)) to find the one pointing back at this
      video. The sidecar turns that into an O(1) read.
  Read by :func:`remove_dedup_marker` during delete to find which forward marker
  to remove, so identical content can be re-uploaded after the video is deleted.

Both objects are ordinary storage objects written through the active storage
backend interface, so the same logic works for MinIO and local filesystem
storage. They live outside any ``video_id`` media directory (forward marker) or
are non-``.mp4`` files (reverse sidecar), so they are invisible to the
``.mp4``-filtered video listing/resolution helpers.

Behaviour is gated by :data:`Settings.ALLOW_DUPLICATE_UPLOADS`
(env ``MM_DATAPREP_ALLOW_DUPLICATE_UPLOADS``). When duplicates are allowed
(the default), markers are still maintained so that enforcement can be turned on
later, but no upload is rejected.

Note: the check-then-register sequence is not atomic; two concurrent uploads of
the same brand-new content could both pass the check before either registers.
This is an accepted edge case — at worst one duplicate slips through — and is not
worth a distributed lock for this feature.
"""

from __future__ import annotations

import hashlib
from http import HTTPStatus
from typing import Optional

from src.common import DataPrepException, Strings, logger, settings
from src.core.storage.base import BaseStorage

# Pseudo ``video_id`` directory that holds forward hash markers. The leading dot
# keeps it visually distinct and out of the way of real ``video_id`` prefixes.
DEDUP_PREFIX = ".dedup"

# Reverse-lookup sidecar filename stored inside each video's directory. Not an
# ``.mp4`` file, so it is ignored by the video listing/resolution helpers and is
# removed together with the directory on delete.
CONTENT_HASH_SIDECAR = ".content_sha256"


def compute_content_hash(content: bytes) -> str:
    """Return the lowercase hex SHA-256 digest of ``content``.

    Args:
        content: The raw uploaded file bytes.

    Returns:
        str: 64-character lowercase hexadecimal SHA-256 digest.
    """
    return hashlib.sha256(content).hexdigest()


def _marker_object_name(content_hash: str) -> str:
    """Return the forward-marker object key for a content hash."""
    return f"{DEDUP_PREFIX}/{content_hash}"


def find_duplicate_video_id(
    storage: BaseStorage, bucket_name: str, content_hash: str
) -> Optional[str]:
    """Return the ``video_id`` that already owns ``content_hash``, if any.

    Performs a single existence check on the forward marker (O(1)); only when a
    marker exists is its tiny body read to recover the owning ``video_id`` for
    reporting. A read failure degrades gracefully to a non-empty sentinel so the
    caller still treats the content as a duplicate.

    Args:
        storage: Active storage backend.
        bucket_name: Bucket the upload targets.
        content_hash: SHA-256 hex digest of the candidate upload.

    Returns:
        Optional[str]: The existing owner ``video_id`` (or ``"<unknown>"`` if the
        marker exists but its body could not be read); ``None`` if no duplicate.
    """
    object_name = _marker_object_name(content_hash)
    if not storage.object_exists_by_path(bucket_name, object_name):
        return None
    try:
        stream = storage.download_video_stream(bucket_name, object_name)
        if stream is not None:
            owner = stream.read().decode("utf-8").strip()
            if owner:
                return owner
    except Exception as ex:  # noqa: BLE001 - reporting only; existence already proven
        logger.warning("Could not read dedup marker %s: %s", object_name, ex)
    return "<unknown>"


def register_upload(
    storage: BaseStorage, bucket_name: str, video_id: str, content_hash: str
) -> None:
    """Record ``content_hash`` -> ``video_id`` mappings for future dedup checks.

    Writes the forward marker (``<DEDUP_PREFIX>/<hash>`` -> ``video_id``) and the
    reverse sidecar (``<video_id>/<CONTENT_HASH_SIDECAR>`` -> ``hash``). Marker
    persistence must never fail the ingest, so errors are logged and swallowed.

    Args:
        storage: Active storage backend.
        bucket_name: Bucket the video was stored in.
        video_id: The owning video directory / identifier.
        content_hash: SHA-256 hex digest of the stored content.
    """
    try:
        storage.save_metadata_file(
            bucket_name, video_id.encode("utf-8"), DEDUP_PREFIX, content_hash
        )
        storage.save_metadata_file(
            bucket_name, content_hash.encode("utf-8"), video_id, CONTENT_HASH_SIDECAR
        )
    except Exception as ex:  # noqa: BLE001 - dedup bookkeeping is best-effort
        logger.warning(
            "Failed to register dedup marker for video %s in bucket %s: %s",
            video_id,
            bucket_name,
            ex,
        )


def remove_dedup_marker(
    storage: BaseStorage, bucket_name: str, video_id: str
) -> None:
    """Remove the forward hash marker owned by ``video_id`` (best-effort).

    Reads the reverse sidecar to recover the content hash, then deletes the
    forward marker so the same content can be re-uploaded after this video is
    deleted. The reverse sidecar itself is removed as part of deleting the video
    directory by the caller. Never raises — dedup cleanup must not block a delete.

    Args:
        storage: Active storage backend.
        bucket_name: Bucket the video lives in.
        video_id: The video directory / identifier being deleted.
    """
    sidecar = f"{video_id}/{CONTENT_HASH_SIDECAR}"
    try:
        if not storage.object_exists_by_path(bucket_name, sidecar):
            return
        stream = storage.download_video_stream(bucket_name, sidecar)
        if stream is None:
            return
        content_hash = stream.read().decode("utf-8").strip()
    except Exception as ex:  # noqa: BLE001 - cleanup is best-effort
        logger.warning("Could not read content-hash sidecar %s: %s", sidecar, ex)
        return
    if not content_hash:
        return
    try:
        storage.delete_object(bucket_name, _marker_object_name(content_hash))
    except Exception as ex:  # noqa: BLE001 - cleanup is best-effort
        logger.warning(
            "Could not delete dedup marker for hash %s in bucket %s: %s",
            content_hash,
            bucket_name,
            ex,
        )


def check_and_register_upload(
    storage: BaseStorage, bucket_name: str, video_id: str, content: bytes
) -> str:
    """Enforce the duplicate policy for ``content`` and register its markers.

    Computes the content hash. When ``ALLOW_DUPLICATE_UPLOADS`` is ``False`` and
    an identical file already exists in the bucket, raises a 409 conflict naming
    the existing ``video_id``. Otherwise registers the dedup markers for this
    upload and returns the hash.

    Call this AFTER the video bytes have been stored under ``video_id`` so that a
    registered marker always points at a real object.

    Args:
        storage: Active storage backend.
        bucket_name: Bucket the video was stored in.
        video_id: The owning video directory / identifier.
        content: The raw uploaded file bytes.

    Returns:
        str: The SHA-256 hex digest of ``content``.

    Raises:
        DataPrepException: 409 Conflict if duplicates are disallowed and an
            identical file already exists.
    """
    content_hash = compute_content_hash(content)
    if not settings.ALLOW_DUPLICATE_UPLOADS:
        existing = find_duplicate_video_id(storage, bucket_name, content_hash)
        if existing is not None:
            logger.info(
                "Rejected duplicate upload in bucket %s (matches existing video %s)",
                bucket_name,
                existing,
            )
            raise DataPrepException(
                status_code=HTTPStatus.CONFLICT,
                msg=f"{Strings.duplicate_upload} (existing video_id: '{existing}').",
            )
    register_upload(storage, bucket_name, video_id, content_hash)
    return content_hash
