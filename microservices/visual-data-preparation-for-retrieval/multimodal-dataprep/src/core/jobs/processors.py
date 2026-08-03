# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Per-item processors for the batch-job engine.

The engine is source-agnostic: a batch item either refers to media that already
lives in the storage backend (multipart upload stashes bytes; directory ingest
copies files in) or, for a ``store_copy=false`` directory ingest, references a
file in place on the mounted ingest root. :func:`process_stored_video` is
therefore the single unit of work shared by all surfaces. It mirrors the
``POST /media/process`` flow: resolve/validate the media, load its bytes, and run
the in-process embedding pipeline.

The heavy pipeline call is ``async`` but ultimately synchronous/CPU-bound; it is
driven here via :func:`asyncio.run` because processors execute on the job's own
background thread, keeping the main event loop free.
"""

from __future__ import annotations

import asyncio
import datetime
import pathlib
import shutil
import time
import uuid

from src.common import Strings, logger, settings
from src.core.embedding import (
    generate_image_embedding_from_content,
    generate_video_embedding_from_content,
)
from src.core.media import detect_media_kind
from src.core.utils.config_utils import read_config
from src.core.utils.file_utils import resolve_under_ingest_root
from src.core.utils.video_utils import get_video_from_minio

from .batch_jobs import BatchItem


def process_stored_video(item: BatchItem) -> int:
    """Process a single already-stored media file and return the embedding count.

    The stored filename's extension selects the embedding path (image vs video),
    so a single job can mix images and videos. Raises on any failure so the
    engine can isolate it to this item.
    """
    config = read_config(settings.CONFIG_FILEPATH, type="yaml")
    if config is None:
        raise Exception(Strings.config_error)

    bucket_name = item.bucket_name
    video_id = item.video_id

    metadata_root = pathlib.Path(
        config.get("metadata_local_temp_dir", "/tmp/dataprep/metadata")
    )
    request_id = f"{video_id}_{int(datetime.datetime.now().timestamp())}"
    metadata_temp_dir = metadata_root / request_id
    metadata_temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        if item.local_path:
            # Reference ingest (``store_copy=false``): the media was never copied
            # into the storage backend, so read it from the mounted ingest root.
            # The path is re-validated against the root here because the job runs
            # asynchronously, long after the request was validated.
            media_path = resolve_under_ingest_root(item.local_path)
            content = media_path.read_bytes()
            filename = media_path.name
        else:
            video_data, filename = get_video_from_minio(bucket_name, video_id)
            content = video_data.read()

        telemetry_context = {
            "request_id": str(uuid.uuid4()),
            "source": "batch",
            "requested_at": time.time(),
        }

        if detect_media_kind(filename) == "image":
            ids = asyncio.run(
                generate_image_embedding_from_content(
                    image_content=content,
                    bucket_name=bucket_name,
                    video_id=video_id,
                    filename=filename,
                    enable_object_detection=item.enable_object_detection,
                    detection_confidence=item.detection_confidence,
                    tags=item.tags or [],
                    source_path=item.source_path,
                    custom_metadata=item.custom_metadata or {},
                    telemetry_context=telemetry_context,
                )
            )
        else:
            ids = asyncio.run(
                generate_video_embedding_from_content(
                    video_content=content,
                    bucket_name=bucket_name,
                    video_id=video_id,
                    filename=filename,
                    metadata_temp_path=metadata_temp_dir,
                    frame_interval=item.frame_interval,
                    enable_object_detection=item.enable_object_detection,
                    detection_confidence=item.detection_confidence,
                    tags=item.tags or [],
                    source_path=item.source_path,
                    custom_metadata=item.custom_metadata or {},
                    telemetry_context=telemetry_context,
                )
            )
        return len(ids)
    finally:
        try:
            if metadata_temp_dir.exists():
                shutil.rmtree(metadata_temp_dir, ignore_errors=True)
        except Exception as ex:  # noqa: BLE001
            logger.warning("Failed to clean up batch metadata temp dir: %s", ex)
