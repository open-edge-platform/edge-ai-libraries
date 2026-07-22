# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Batch ingestion endpoints.

Three submit surfaces, one async job engine:

* ``POST /videos/upload/batch``  — multipart ``List[UploadFile]``.
* ``POST /videos/batch``         — process videos already in storage.
* ``POST /videos/ingest-dir``    — backward-compatible directory ingest.

Each returns ``202 Accepted`` with a ``job_id``; results are polled via
``GET /videos/batch/{job_id}`` (``DELETE`` requests cooperative cancellation).
Heavy processing runs off the request path on the job engine's background thread,
so the event loop / ``/health`` stay responsive during a batch.
"""

import datetime
import io
import json
import pathlib
import uuid
from http import HTTPStatus
from typing import Annotated, List, Optional

from fastapi import APIRouter, Body, File, HTTPException, Query, UploadFile

from src.common import DataPrepException, Strings, logger, sanitize_for_log, settings
from src.common.schema import (
    BatchItemResult,
    BatchJobStatus,
    BatchProcessExistingRequest,
    BatchSubmitResponse,
    DirectoryIngestRequest,
)
from src.core.jobs import BatchItem, cancel_job, get_job, process_stored_video, submit_job
from src.core.jobs.batch_jobs import BatchJob
from src.core.utils.common_utils import get_minio_client
from src.core.utils.config_utils import read_config
from src.core.validation import (
    sanitize_bucket_name,
    sanitize_string,
    validate_file,
)

router = APIRouter(tags=["Batch Ingestion APIs"])

_SUPPORTED_EXTENSIONS = {".mp4"}


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


def _new_video_id(index: int) -> str:
    """Generate a unique ``video_id`` for a newly stashed batch upload."""
    return f"dp_video_{int(datetime.datetime.now().timestamp())}_{index}_{uuid.uuid4().hex[:6]}"


def _stash_bytes(bucket_name: str, video_id: str, filename: str, content: bytes) -> None:
    """Persist raw upload bytes to storage under ``<video_id>/<filename>``."""
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
    "/videos/upload/batch",
    summary="Upload and process multiple video files (async batch job).",
    operation_id="uploadAndProcessVideoBatch",
    status_code=HTTPStatus.ACCEPTED,
    response_model=BatchSubmitResponse,
    response_model_exclude_none=True,
)
async def upload_and_process_video_batch(
    files: Annotated[List[UploadFile], File(description="Video files to upload (MP4 only)")],
    bucket_name: Annotated[Optional[str], Query(description="Target bucket (default if unset).")] = None,
    frame_interval: Annotated[
        Optional[int], Query(ge=1, le=60, description="Extract every Nth frame (default: 15).")
    ] = None,
    enable_object_detection: Annotated[
        Optional[bool], Query(description="Enable object detection and crop extraction.")
    ] = None,
    detection_confidence: Annotated[
        Optional[float], Query(ge=0.1, le=1.0, description="Object detection confidence threshold.")
    ] = None,
    tags: Annotated[Optional[List[str]], Query(description="Tags for all uploaded videos.")] = None,
) -> BatchSubmitResponse:
    """Accept multiple MP4 uploads, stash them to storage, and submit one async job."""
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
            video_id = _new_video_id(index)
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
    "/videos/batch",
    summary="Batch-process videos already present in storage (async batch job).",
    operation_id="processVideoBatchExisting",
    status_code=HTTPStatus.ACCEPTED,
    response_model=BatchSubmitResponse,
    response_model_exclude_none=True,
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


def _resolve_ingest_dir(dir_path: str) -> pathlib.Path:
    """Resolve ``dir_path`` under the configured ingest root, blocking traversal."""
    root = pathlib.Path(settings.INGEST_DATA_ROOT).resolve()
    requested = pathlib.Path(dir_path)
    target = (requested if requested.is_absolute() else root / requested).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise DataPrepException(status_code=HTTPStatus.BAD_REQUEST, msg=Strings.ingest_path_invalid)
    if not target.is_dir():
        raise DataPrepException(status_code=HTTPStatus.NOT_FOUND, msg=Strings.ingest_dir_not_found)
    return target


def _read_sidecar_tags(media_file: pathlib.Path) -> List[str]:
    """Read optional ``<dir>/meta/<basename>.json`` tags (milvus-dataprep parity)."""
    sidecar = media_file.parent / "meta" / f"{media_file.stem}.json"
    if not sidecar.is_file():
        return []
    try:
        data = json.loads(sidecar.read_text())
        tags = data.get("tags", []) if isinstance(data, dict) else []
        return [sanitize_string(t) for t in tags if isinstance(t, str)]
    except Exception as ex:  # noqa: BLE001
        logger.warning("Ignoring unreadable sidecar %s: %s", sidecar.name, ex)
        return []


@router.post(
    "/videos/ingest-dir",
    summary="Ingest all supported videos from a mounted directory (async batch job).",
    operation_id="ingestDirectory",
    status_code=HTTPStatus.ACCEPTED,
    response_model=BatchSubmitResponse,
    response_model_exclude_none=True,
)
async def ingest_directory(
    request: Annotated[DirectoryIngestRequest, Body(description="Directory ingest parameters")],
) -> BatchSubmitResponse:
    """Walk a mounted directory, stash each MP4 into storage, and submit one async job."""
    try:
        target = _resolve_ingest_dir(request.dir_path)
        fi, od, dc = _resolve_defaults(
            request.frame_interval, request.enable_object_detection, request.detection_confidence
        )
        bucket = (
            sanitize_bucket_name(request.bucket_name)
            if request.bucket_name
            else settings.DEFAULT_BUCKET_NAME
        )
        req_tags = [sanitize_string(t) for t in (request.tags or []) if isinstance(t, str)]

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
        for index, media_file in enumerate(media_files):
            filename = media_file.name
            video_id = _new_video_id(index)
            _stash_bytes(bucket, video_id, filename, media_file.read_bytes())
            tags = (_read_sidecar_tags(media_file) or []) + req_tags
            items.append(
                BatchItem(
                    identifier=str(media_file.relative_to(target)),
                    bucket_name=bucket,
                    video_id=video_id,
                    frame_interval=fi,
                    enable_object_detection=od,
                    detection_confidence=dc,
                    tags=tags,
                )
            )

        job = submit_job("directory", items, process_stored_video)
        return BatchSubmitResponse(
            message=Strings.batch_accepted, job_id=job.job_id, accepted=len(items)
        )
    except DataPrepException as ex:
        logger.error(ex)
        raise HTTPException(status_code=ex.status_code, detail=ex.message)
    except Exception as ex:  # noqa: BLE001
        logger.error(ex)
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=Strings.server_error)


@router.get(
    "/videos/batch/{job_id}",
    summary="Get the status and per-item results of a batch job.",
    operation_id="getBatchJobStatus",
    response_model=BatchJobStatus,
    response_model_exclude_none=True,
)
async def get_batch_job_status(job_id: str) -> BatchJobStatus:
    """Return the current state and per-item results of a batch job (404 if unknown)."""
    job = get_job(sanitize_string(job_id))
    if job is None:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=Strings.batch_job_not_found)
    return _job_to_status(job)


@router.delete(
    "/videos/batch/{job_id}",
    summary="Request cancellation of a pending/running batch job.",
    operation_id="cancelBatchJob",
    response_model=BatchJobStatus,
    response_model_exclude_none=True,
)
async def cancel_batch_job(job_id: str) -> BatchJobStatus:
    """Request cooperative cancellation of a batch job (404 if unknown)."""
    job = cancel_job(sanitize_string(job_id))
    if job is None:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=Strings.batch_job_not_found)
    return _job_to_status(job)
