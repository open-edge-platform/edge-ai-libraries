# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""JSON image ingestion endpoints (base64 / URL sources).

The multipart ``POST /media/upload`` handles binary uploads. These endpoints
accept a typed JSON source mirroring multimodal-embedding-serving's input
discriminator, so callers that produce inline base64 (agents, browsers) or
remote URLs can ingest without multipart:

* ``POST /media/ingest``        -- single typed source, processed synchronously
  (201 Created), sharing the exact storage/dedup/embedding path as multipart.
* ``POST /media/ingest/batch``  -- many typed sources -> one async job (202),
  polled via ``GET /media/jobs/{job_id}`` on the shared batch engine.

Field names stay ``video_id``/``video_name`` (generic media id) for backward
compatibility with existing retrievers.
"""

import datetime
import io
import uuid
from http import HTTPStatus
from typing import Annotated, List

from fastapi import APIRouter, Body, HTTPException

from src.common import DataPrepException, Strings, logger, sanitize_for_log, settings
from src.common.schema import (
    BatchSubmitResponse,
    DataPrepResponse,
    ImageBatchIngestRequest,
    ImageIngestRequest,
)
from src.core.dedup import check_and_register_upload
from src.core.embedding import generate_image_embedding_from_content
from src.core.image_ingest import load_image_source
from src.core.jobs import BatchItem, process_stored_video, submit_job
from src.core.utils.common_utils import get_minio_client
from src.core.utils.config_utils import read_config
from src.core.validation import sanitize_bucket_name, sanitize_string

router = APIRouter(tags=["Media Ingestion APIs"])


def _resolve_detection_defaults(enable_object_detection, detection_confidence):
    """Fill object-detection defaults from config/settings (frame interval is N/A for images)."""
    config = read_config(settings.CONFIG_FILEPATH, type="yaml") or {}
    if enable_object_detection is not None:
        od = bool(enable_object_detection)
    else:
        od = config.get("enable_object_detection", settings.ENABLE_OBJECT_DETECTION)
        od = bool(True if od is None else od)
    dc = detection_confidence or config.get("detection_confidence", settings.DETECTION_CONFIDENCE)
    return od, dc


def _new_image_id(index: int = 0) -> str:
    """Generate a unique ``video_id`` (generic media id) for a stored image."""
    return f"dp_image_{int(datetime.datetime.now().timestamp())}_{index}_{uuid.uuid4().hex[:6]}"


def _stash_image_bytes(bucket_name: str, video_id: str, filename: str, content: bytes) -> str:
    """Store image bytes under ``<video_id>/<filename>`` and enforce the dedup policy.

    Returns the stored object name. On a duplicate rejection (when duplicates are
    disallowed) the just-stored object is rolled back before the 409 propagates.
    """
    minio_client = get_minio_client()
    minio_client.ensure_bucket_exists(bucket_name)
    object_name = f"{video_id}/{filename}"
    minio_client.upload_video(bucket_name, object_name, io.BytesIO(content), len(content))
    logger.info(
        "Stored ingested image %s to %s/%s",
        sanitize_for_log(filename, max_length=256),
        sanitize_for_log(bucket_name, max_length=128),
        sanitize_for_log(object_name, max_length=256),
    )
    try:
        check_and_register_upload(minio_client, bucket_name, video_id, content)
    except DataPrepException:
        try:
            minio_client.delete_object(bucket_name, object_name)
        except Exception as cleanup_ex:  # noqa: BLE001
            logger.warning("Failed to roll back duplicate ingested image: %s", cleanup_ex)
        raise
    return object_name


@router.post(
    "/media/ingest",
    summary="Ingest a single image from a JSON source (base64 or URL).",
    operation_id="ingestImage",
    status_code=HTTPStatus.CREATED,
    response_model=DataPrepResponse,
    response_model_exclude_none=True,
)
async def ingest_image(
    request: Annotated[ImageIngestRequest, Body(description="Typed image source + ingestion params")],
) -> DataPrepResponse:
    """Decode/download a single image, store it, and generate embeddings synchronously.

    The image bytes (from base64 or a downloaded URL) are the trust boundary: the
    real format is sniffed to derive the stored extension, then the image is
    embedded (whole image plus one embedding per detected object crop when object
    detection is enabled) into the shared vector collection with
    ``content_type="image"``.
    """
    try:
        od, dc = _resolve_detection_defaults(
            request.enable_object_detection, request.detection_confidence
        )
        bucket = (
            sanitize_bucket_name(request.bucket_name)
            if request.bucket_name
            else settings.DEFAULT_BUCKET_NAME
        )
        tags = [sanitize_string(t) for t in (request.tags or []) if isinstance(t, str)]

        content, filename = load_image_source(
            request.type.value,
            image_base64=request.image_base64,
            image_url=request.image_url,
            filename=request.filename,
        )

        video_id = _new_image_id()
        _stash_image_bytes(bucket, video_id, filename, content)

        ids = await generate_image_embedding_from_content(
            image_content=content,
            bucket_name=bucket,
            video_id=video_id,
            filename=filename,
            enable_object_detection=od,
            detection_confidence=dc,
            tags=tags,
        )
        logger.info("%d image embeddings created via /media/ingest", len(ids))
        return DataPrepResponse(message=Strings.embedding_success)
    except DataPrepException as ex:
        logger.error(ex)
        raise HTTPException(status_code=ex.status_code, detail=ex.message)
    except ValueError as ex:
        logger.error(ex)
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=str(ex))
    except Exception as ex:  # noqa: BLE001
        logger.error(ex)
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=Strings.server_error)


@router.post(
    "/media/ingest/batch",
    summary="Ingest multiple images from JSON sources (base64/URL) as an async batch job.",
    operation_id="ingestImageBatch",
    status_code=HTTPStatus.ACCEPTED,
    response_model=BatchSubmitResponse,
    response_model_exclude_none=True,
)
async def ingest_image_batch(
    request: Annotated[ImageBatchIngestRequest, Body(description="Typed image sources + params")],
) -> BatchSubmitResponse:
    """Decode/download and stash each image, then submit one async job over them.

    Each image is validated + persisted before the 202 (the base64/URL bytes are
    only available on the request), after which processing is indistinguishable
    from other stored-media batches and runs off the request path.
    """
    try:
        images = request.images or []
        if len(images) <= 0:
            raise DataPrepException(status_code=HTTPStatus.BAD_REQUEST, msg=Strings.batch_empty)
        if len(images) > settings.BATCH_MAX_ITEMS:
            raise DataPrepException(
                status_code=HTTPStatus.BAD_REQUEST,
                msg=f"{Strings.batch_too_large} (max {settings.BATCH_MAX_ITEMS}).",
            )

        od, dc = _resolve_detection_defaults(
            request.enable_object_detection, request.detection_confidence
        )
        bucket = (
            sanitize_bucket_name(request.bucket_name)
            if request.bucket_name
            else settings.DEFAULT_BUCKET_NAME
        )
        request_tags = [sanitize_string(t) for t in (request.tags or []) if isinstance(t, str)]

        items: List[BatchItem] = []
        for index, image in enumerate(images):
            content, filename = load_image_source(
                image.type.value,
                image_base64=image.image_base64,
                image_url=image.image_url,
                filename=image.filename,
            )
            item_tags = [
                sanitize_string(t) for t in (image.tags or []) if isinstance(t, str)
            ] + request_tags
            video_id = _new_image_id(index)
            _stash_image_bytes(bucket, video_id, filename, content)
            items.append(
                BatchItem(
                    identifier=filename,
                    bucket_name=bucket,
                    video_id=video_id,
                    enable_object_detection=od,
                    detection_confidence=dc,
                    tags=item_tags,
                )
            )

        job = submit_job("image_batch", items, process_stored_video)
        return BatchSubmitResponse(
            message=Strings.batch_accepted, job_id=job.job_id, accepted=len(items)
        )
    except DataPrepException as ex:
        logger.error(ex)
        raise HTTPException(status_code=ex.status_code, detail=ex.message)
    except Exception as ex:  # noqa: BLE001
        logger.error(ex)
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=Strings.server_error)
