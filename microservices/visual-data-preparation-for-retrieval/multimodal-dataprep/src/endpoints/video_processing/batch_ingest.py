# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Batch ingestion endpoints.

Three submit surfaces, one async job engine:

* ``POST /media/upload/batch``  — multipart ``List[UploadFile]``.
* ``POST /media/process/batch``         — process videos already in storage.
* ``POST /media/ingest-dir``    — backward-compatible directory ingest.

Each returns ``202 Accepted`` with a ``job_id``; results are polled via
``GET /media/jobs/{job_id}`` (``DELETE`` requests cooperative cancellation).
Heavy processing runs off the request path on the job engine's background thread,
so the event loop / ``/health`` stay responsive during a batch.
"""

import datetime
import io
import json
import pathlib
import re
import uuid
from http import HTTPStatus
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Body, File, HTTPException, Query, UploadFile

from src.common import DataPrepException, Strings, logger, sanitize_for_log, settings
from src.common.api_responses import (
    INGEST_ERRORS,
    INGEST_ERRORS_NO_CONFLICT,
    READ_ERRORS,
    error_responses,
)
from src.common.schema import (
    BatchItemResult,
    BatchJobStatus,
    BatchProcessExistingRequest,
    BatchSubmitResponse,
    DirectoryIngestRequest,
)
from src.core.dedup import check_and_register_upload
from src.core.jobs import BatchItem, cancel_job, get_job, process_stored_video, submit_job
from src.core.jobs.batch_jobs import BatchJob
from src.core.media import SUPPORTED_MEDIA_EXTENSIONS, detect_media_kind
from src.core.media_ref import register_source_ref
from src.core.utils.common_utils import get_minio_client
from src.core.utils.config_utils import read_config
from src.core.utils.file_utils import resolve_under_ingest_root, to_host_path
from src.core.vectorstores.metadata import CANONICAL_FIELDS
from src.core.validation import (
    sanitize_bucket_name,
    sanitize_string,
    validate_file,
)

router = APIRouter(tags=["Batch Ingestion APIs"])

# Directory-ingest accepts any supported media file (video or image); the
# per-item processor picks the embedding path from the stored filename.
_SUPPORTED_EXTENSIONS = set(SUPPORTED_MEDIA_EXTENSIONS)

# Caller-supplied metadata keys become queryable field names in the vector store,
# so they are restricted to identifier-like tokens.
_RESERVED_METADATA_KEYS = frozenset(CANONICAL_FIELDS)
_METADATA_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


def _resolve_defaults(
    frame_interval: Optional[int],
    enable_object_detection: Optional[bool],
    detection_confidence: Optional[float],
) -> tuple[int, bool, float]:
    """Fill batch-level processing defaults from config/settings (mirrors single endpoints)."""
    config = read_config(settings.CONFIG_FILEPATH, type="yaml") or {}
    fi = frame_interval or config.get("frame_interval", settings.FRAME_INTERVAL)
    if enable_object_detection is not None:
        od = bool(enable_object_detection)
    else:
        od = config.get("enable_object_detection", settings.ENABLE_OBJECT_DETECTION)
        od = bool(True if od is None else od)
    dc = detection_confidence or config.get("detection_confidence", settings.DETECTION_CONFIDENCE)
    return fi, od, dc


def _check_batch_size(count: int) -> None:
    """Validate the batch item count is non-empty and within ``BATCH_MAX_ITEMS``."""
    if count <= 0:
        raise DataPrepException(status_code=HTTPStatus.BAD_REQUEST, msg=Strings.batch_empty)
    if count > settings.BATCH_MAX_ITEMS:
        raise DataPrepException(
            status_code=HTTPStatus.BAD_REQUEST,
            msg=f"{Strings.batch_too_large} (max {settings.BATCH_MAX_ITEMS}).",
        )


def _new_video_id(index: int, filename: str = "") -> str:
    """Generate a unique ``video_id`` for a newly stashed batch item (media-aware prefix)."""
    prefix = "dp_image" if detect_media_kind(filename) == "image" else "dp_video"
    return f"{prefix}_{int(datetime.datetime.now().timestamp())}_{index}_{uuid.uuid4().hex[:6]}"


def _stash_bytes(bucket_name: str, video_id: str, filename: str, content: bytes) -> None:
    """Persist raw upload bytes to storage under ``<video_id>/<filename>``.

    After storing, the duplicate-upload policy is enforced: when duplicates are
    disallowed and this content already exists, the just-stored object is removed
    and a 409 conflict is raised; otherwise the dedup markers are registered.
    """
    minio_client = get_minio_client()
    minio_client.ensure_bucket_exists(bucket_name)
    object_name = f"{video_id}/{filename}"
    minio_client.upload_video(bucket_name, object_name, io.BytesIO(content), len(content))
    logger.info(
        "Stashed batch video %s to %s/%s",
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
            logger.warning("Failed to roll back duplicate batch object: %s", cleanup_ex)
        raise


def _register_reference(
    bucket_name: str, video_id: str, content: bytes, source_path: pathlib.Path
) -> None:
    """Record the markers for referenced media (``store_copy=false``).

    No object is stored, so only sidecars are written. They are tiny and give the
    service everything it needs to treat referenced media like stored media:

    * content markers, so a repeated directory ingest recognises files it has
      already embedded;
    * a path sidecar, so ``GET /media`` can list the item and
      ``GET /media/download`` can stream it from the ingest mount.
    """
    minio_client = get_minio_client()
    minio_client.ensure_bucket_exists(bucket_name)
    check_and_register_upload(minio_client, bucket_name, video_id, content)
    register_source_ref(minio_client, bucket_name, video_id, source_path)


def _job_to_status(job: BatchJob) -> BatchJobStatus:
    """Convert an internal :class:`BatchJob` into the API status response model."""
    completed, failed = job.counts()
    items = [
        BatchItemResult(
            identifier=i.identifier,
            bucket_name=i.bucket_name,
            video_id=i.video_id,
            status=i.status,
            message=i.message,
            embeddings_count=i.embeddings_count,
        )
        for i in job.items
    ]
    return BatchJobStatus(
        job_id=job.job_id,
        state=job.state,
        source=job.source,
        total=len(job.items),
        completed=completed,
        failed=failed,
        items=items,
        created_ts=job.created_ts,
        updated_ts=job.updated_ts,
    )


@router.post(
    "/media/upload/batch",
    summary="Upload and process multiple media files (videos and/or images) as an async batch job.",
    operation_id="uploadAndProcessMediaBatch",
    status_code=HTTPStatus.ACCEPTED,
    response_model=BatchSubmitResponse,
    response_model_exclude_none=True,
    responses=error_responses(*INGEST_ERRORS),
)
async def upload_and_process_video_batch(
    files: Annotated[List[UploadFile], File(description="Media files to upload (MP4 videos or images)")],
    bucket_name: Annotated[Optional[str], Query(description="Target bucket (default if unset).")] = None,
    frame_interval: Annotated[
        Optional[int], Query(ge=1, le=60, description="Extract every Nth frame (defaults to the service's configured frame_interval, 15 unless overridden).")
    ] = None,
    enable_object_detection: Annotated[
        Optional[bool], Query(description="Enable object detection and crop extraction.")
    ] = None,
    detection_confidence: Annotated[
        Optional[float], Query(ge=0.1, le=1.0, description="Object detection confidence threshold.")
    ] = None,
    tags: Annotated[Optional[List[str]], Query(description="Tags for all uploaded videos.")] = None,
) -> BatchSubmitResponse:
    """Accept multiple media uploads (videos and/or images), stash them to storage, and submit one async job."""
    try:
        _check_batch_size(len(files or []))
        fi, od, dc = _resolve_defaults(frame_interval, enable_object_detection, detection_confidence)
        bucket = sanitize_bucket_name(bucket_name) if bucket_name else settings.DEFAULT_BUCKET_NAME
        clean_tags = [sanitize_string(t) for t in (tags or []) if isinstance(t, str)]

        items: List[BatchItem] = []
        for index, upload in enumerate(files):
            validate_file(upload, required=True)
            content = await upload.read()
            filename = pathlib.Path(upload.filename).name
            video_id = _new_video_id(index, filename)
            _stash_bytes(bucket, video_id, filename, content)
            items.append(
                BatchItem(
                    identifier=filename,
                    bucket_name=bucket,
                    video_id=video_id,
                    frame_interval=fi,
                    enable_object_detection=od,
                    detection_confidence=dc,
                    tags=clean_tags,
                )
            )

        job = submit_job("upload_batch", items, process_stored_video)
        return BatchSubmitResponse(
            message=Strings.batch_accepted, job_id=job.job_id, accepted=len(items)
        )
    except DataPrepException as ex:
        logger.error(ex)
        raise HTTPException(status_code=ex.status_code, detail=ex.message)
    except Exception as ex:  # noqa: BLE001
        logger.error(ex)
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=Strings.server_error)


@router.post(
    "/media/process/batch",
    summary="Batch-process media (videos/images) already present in storage (async batch job).",
    operation_id="processMediaBatchExisting",
    status_code=HTTPStatus.ACCEPTED,
    response_model=BatchSubmitResponse,
    response_model_exclude_none=True,
    responses=error_responses(*INGEST_ERRORS_NO_CONFLICT),
)
async def process_video_batch_existing(
    request: Annotated[BatchProcessExistingRequest, Body(description="Batch selection + params")],
) -> BatchSubmitResponse:
    """Submit an async job over videos that already exist in storage.

    Provide either an explicit ``items`` list or a ``bucket_name`` (optionally
    narrowed by ``prefix``) selector.
    """
    try:
        selector_tags = [sanitize_string(t) for t in (request.tags or []) if isinstance(t, str)]
        items: List[BatchItem] = []

        if request.items:
            for req in request.items:
                fi, od, dc = _resolve_defaults(
                    req.frame_interval, req.enable_object_detection, req.detection_confidence
                )
                bucket = (
                    sanitize_bucket_name(req.bucket_name)
                    if req.bucket_name
                    else settings.DEFAULT_BUCKET_NAME
                )
                item_tags = [
                    sanitize_string(t) for t in (req.tags or []) if isinstance(t, str)
                ] or selector_tags
                items.append(
                    BatchItem(
                        identifier=req.video_id or "(unspecified)",
                        bucket_name=bucket,
                        video_id=req.video_id,
                        frame_interval=fi,
                        enable_object_detection=od,
                        detection_confidence=dc,
                        tags=item_tags,
                    )
                )
        elif request.bucket_name:
            fi, od, dc = _resolve_defaults(
                request.frame_interval, request.enable_object_detection, request.detection_confidence
            )
            bucket = sanitize_bucket_name(request.bucket_name)
            prefix = sanitize_string(request.prefix) if request.prefix else None
            minio_client = get_minio_client()
            minio_client.ensure_bucket_exists(bucket)
            for video in minio_client.list_all_videos(bucket):
                video_id = video.get("video_id")
                if not video_id:
                    continue
                if prefix and not str(video_id).startswith(prefix):
                    continue
                items.append(
                    BatchItem(
                        identifier=video_id,
                        bucket_name=bucket,
                        video_id=video_id,
                        frame_interval=fi,
                        enable_object_detection=od,
                        detection_confidence=dc,
                        tags=selector_tags,
                    )
                )
        else:
            raise DataPrepException(
                status_code=HTTPStatus.BAD_REQUEST,
                msg="Provide either 'items' or a 'bucket_name' selector.",
            )

        _check_batch_size(len(items))
        job = submit_job("batch_existing", items, process_stored_video)
        return BatchSubmitResponse(
            message=Strings.batch_accepted, job_id=job.job_id, accepted=len(items)
        )
    except DataPrepException as ex:
        logger.error(ex)
        raise HTTPException(status_code=ex.status_code, detail=ex.message)
    except Exception as ex:  # noqa: BLE001
        logger.error(ex)
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=Strings.server_error)


def _read_sidecar(media_file: pathlib.Path) -> tuple[List[str], Dict[str, Any]]:
    """Read an optional ``<dir>/meta/<basename>.json`` sidecar (milvus-dataprep parity).

    Returns the sidecar's ``tags`` list and every remaining key as caller-supplied
    metadata, so per-file attributes (camera id, capture date, ...) are ingested
    and become filterable without the service knowing any of those field names.
    """
    sidecar = media_file.parent / "meta" / f"{media_file.stem}.json"
    if not sidecar.is_file():
        return [], {}
    try:
        data = json.loads(sidecar.read_text())
        if not isinstance(data, dict):
            return [], {}
        tags = [sanitize_string(t) for t in data.get("tags", []) if isinstance(t, str)]
        extra = _sanitize_custom_metadata(
            {key: value for key, value in data.items() if key != "tags"},
            context=f"sidecar {sidecar.name}",
        )
        return tags, extra
    except DataPrepException:
        raise
    except Exception as ex:  # noqa: BLE001
        logger.warning("Ignoring unreadable sidecar %s: %s", sidecar.name, ex)
        return [], {}


def _sanitize_custom_metadata(
    metadata: Optional[Dict[str, Any]], *, context: str = "request metadata"
) -> Dict[str, Any]:
    """Validate caller-supplied metadata into a flat, storable dict.

    Keys must be identifier-like (a vector store may expose them as queryable
    field names) and values are restricted to scalars or lists of scalars.
    Unsupported values are dropped with a warning rather than failing the
    ingest. A key that collides with the canonical metadata contract is
    rejected with ``400`` instead: the canonical value always wins on storage,
    so silently accepting it would drop the caller's value without notice.
    """
    if not metadata:
        return {}
    cleaned: Dict[str, Any] = {}
    for key, value in metadata.items():
        if not isinstance(key, str) or not _METADATA_KEY_RE.match(key):
            logger.warning("Ignoring invalid custom metadata key: %s", sanitize_for_log(str(key), max_length=64))
            continue
        if key in _RESERVED_METADATA_KEYS:
            raise DataPrepException(
                msg=f"{Strings.reserved_metadata_key} ({context}: '{sanitize_for_log(key, max_length=64)}')",
                status_code=HTTPStatus.BAD_REQUEST,
            )
        if isinstance(value, str):
            cleaned[key] = sanitize_string(value)
        elif isinstance(value, (int, float, bool)) or value is None:
            cleaned[key] = value
        elif isinstance(value, list) and all(
            isinstance(item, (str, int, float, bool)) for item in value
        ):
            cleaned[key] = [
                sanitize_string(item) if isinstance(item, str) else item for item in value
            ]
        else:
            logger.warning("Ignoring unsupported custom metadata value for key: %s", key)
    return cleaned


@router.post(
    "/media/ingest-dir",
    summary="Ingest all supported media (videos and images) from a mounted directory (async batch job).",
    operation_id="ingestDirectory",
    status_code=HTTPStatus.ACCEPTED,
    response_model=BatchSubmitResponse,
    response_model_exclude_none=True,
    responses=error_responses(*INGEST_ERRORS_NO_CONFLICT),
)
async def ingest_directory(
    request: Annotated[DirectoryIngestRequest, Body(description="Directory ingest parameters")],
) -> BatchSubmitResponse:
    """Walk a mounted directory, stash each supported media file into storage, and submit one async job."""
    try:
        target = resolve_under_ingest_root(request.dir_path, must_be_dir=True)
        fi, od, dc = _resolve_defaults(
            request.frame_interval, request.enable_object_detection, request.detection_confidence
        )
        bucket = (
            sanitize_bucket_name(request.bucket_name)
            if request.bucket_name
            else settings.DEFAULT_BUCKET_NAME
        )
        req_tags = [sanitize_string(t) for t in (request.tags or []) if isinstance(t, str)]
        req_metadata = _sanitize_custom_metadata(request.metadata)

        walker = target.rglob("*") if request.recursive else target.glob("*")
        media_files = sorted(
            f
            for f in walker
            if f.is_file()
            and f.suffix.lower() in _SUPPORTED_EXTENSIONS
            and "meta" not in f.relative_to(target).parts
        )
        _check_batch_size(len(media_files))

        items: List[BatchItem] = []
        skipped = 0
        for index, media_file in enumerate(media_files):
            filename = media_file.name
            video_id = _new_video_id(index, filename)
            try:
                if request.store_copy:
                    _stash_bytes(bucket, video_id, filename, media_file.read_bytes())
                else:
                    # Referenced ingest stores no object, but the duplicate policy
                    # still applies: register the content markers so re-ingesting
                    # the same directory does not duplicate embeddings.
                    _register_reference(bucket, video_id, media_file.read_bytes(), media_file)
            except DataPrepException as ex:
                if ex.status_code != HTTPStatus.CONFLICT:
                    raise
                # A duplicate is a per-file condition, not a reason to reject the
                # whole directory: skip it and ingest the rest.
                logger.info(
                    "Skipping duplicate file during directory ingest: %s",
                    sanitize_for_log(filename, max_length=256),
                )
                skipped += 1
                continue
            sidecar_tags, sidecar_metadata = _read_sidecar(media_file)
            # Sidecar metadata is per-file and therefore more specific than the
            # request-level metadata, so it wins on a key collision.
            custom_metadata = {**req_metadata, **sidecar_metadata}
            items.append(
                BatchItem(
                    identifier=str(media_file.relative_to(target)),
                    bucket_name=bucket,
                    video_id=video_id,
                    frame_interval=fi,
                    enable_object_detection=od,
                    detection_confidence=dc,
                    tags=sidecar_tags + req_tags,
                    local_path=None if request.store_copy else str(media_file),
                    source_path=to_host_path(media_file),
                    custom_metadata=custom_metadata,
                )
            )

        job = submit_job("directory", items, process_stored_video)
        message = Strings.batch_accepted
        if skipped:
            message = f"{message} ({skipped} duplicate file(s) skipped)"
        return BatchSubmitResponse(
            message=message, job_id=job.job_id, accepted=len(items)
        )
    except DataPrepException as ex:
        logger.error(ex)
        raise HTTPException(status_code=ex.status_code, detail=ex.message)
    except Exception as ex:  # noqa: BLE001
        logger.error(ex)
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=Strings.server_error)


@router.get(
    "/media/jobs/{job_id}",
    summary="Get the status and per-item results of a batch job.",
    operation_id="getBatchJobStatus",
    response_model=BatchJobStatus,
    response_model_exclude_none=True,
    responses=error_responses(*READ_ERRORS),
)
async def get_batch_job_status(job_id: str) -> BatchJobStatus:
    """Return the current state and per-item results of a batch job (404 if unknown)."""
    job = get_job(sanitize_string(job_id))
    if job is None:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=Strings.batch_job_not_found)
    return _job_to_status(job)


@router.delete(
    "/media/jobs/{job_id}",
    summary="Request cancellation of a pending/running batch job.",
    operation_id="cancelBatchJob",
    response_model=BatchJobStatus,
    response_model_exclude_none=True,
    responses=error_responses(*READ_ERRORS),
)
async def cancel_batch_job(job_id: str) -> BatchJobStatus:
    """Request cooperative cancellation of a batch job (404 if unknown)."""
    job = cancel_job(sanitize_string(job_id))
    if job is None:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=Strings.batch_job_not_found)
    return _job_to_status(job)
