# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""CRUD endpoints for live (RTSP) stream ingestion.

A live stream is a long-lived resource, not a request. Registering one returns
immediately with a ``stream_id``; ingestion then runs on a background worker
that reconnects on failure, records playback media, and keeps writing
embeddings until the stream is paused or deleted.

Because every live embedding is stored with ``bucket_name`` = the configured
live bucket and ``video_id`` = the ``stream_id``, the existing media endpoints
(``GET /media``, ``GET /media/download``, ``DELETE /media/{bucket}/{video_id}``)
work on live data as well.

.. note::
   Source URLs may embed credentials. They are accepted for connection but are
   **never** returned by these endpoints, written to the vector database, or
   logged: every response goes through the redaction in
   :mod:`src.core.live.urls`.
"""

from http import HTTPStatus
from typing import Annotated, List, Optional

from fastapi import APIRouter, Body, HTTPException, Path, Query

from src.common import logger, sanitize_for_log, settings
from src.common.api_responses import LIVE_STREAM_ERRORS, READ_ERRORS, error_responses
from src.common.schema import (
    BatchItemStatusEnum,
    LiveStreamBatchCreateRequest,
    LiveStreamBatchItemResult,
    LiveStreamBatchResponse,
    LiveStreamCreateRequest,
    LiveStreamDeleteRequest,
    LiveStreamDeleteResponse,
    LiveStreamInfo,
    LiveStreamListResponse,
    LiveStreamResponse,
    LiveStreamStateEnum,
    LiveStreamUpdateRequest,
)
from src.core.live import (
    InvalidStreamUrlError,
    LiveStreamLimitError,
    LiveStreamNotFoundError,
    get_live_stream_manager,
    redact_stream_url,
)

router = APIRouter(tags=["Live Stream APIs"])


def _require_enabled() -> None:
    """Reject live-stream calls when the subsystem is switched off."""
    if not settings.LIVE_STREAM_ENABLED:
        raise HTTPException(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            detail="Live-stream ingestion is disabled (MM_DATAPREP_LIVE_STREAM_ENABLED=false).",
        )


def _create_one(request: LiveStreamCreateRequest) -> LiveStreamInfo:
    """Register a single stream, translating core errors to HTTP errors."""
    manager = get_live_stream_manager()
    try:
        stream = manager.create(
            stream_url=request.stream_url,
            stream_name=request.stream_name,
            description=request.description,
            sensor_id=request.sensor_id,
            frame_interval=request.frame_interval,
            enable_object_detection=request.enable_object_detection,
            detection_confidence=request.detection_confidence,
            tags=request.tags,
            start=request.start,
        )
    except InvalidStreamUrlError as exc:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=str(exc)) from exc
    except LiveStreamLimitError as exc:
        raise HTTPException(status_code=HTTPStatus.SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return stream.to_info()


@router.post(
    "/media/streams",
    summary="Register an RTSP stream and start ingesting it.",
    operation_id="createLiveStream",
    status_code=HTTPStatus.ACCEPTED,
    response_model=LiveStreamResponse,
    response_model_exclude_none=True,
    responses=error_responses(*LIVE_STREAM_ERRORS),
)
async def create_live_stream(
    request: Annotated[LiveStreamCreateRequest, Body(...)],
) -> LiveStreamResponse:
    """
    ### Register a live RTSP stream and begin continuous ingestion.

    The call returns as soon as the stream is registered; frames are decoded,
    embedded, and stored by a background worker that keeps running until the
    stream is paused or deleted. The worker also records N-second video segments
    and sampled frames so retrieval hits are playable.

    #### Request Body:
    - **stream_url (str, required) :** RTSP source URL. Credentials embedded in
      the URL are used to connect but are never returned or persisted to the
      vector database.
    - **stream_name (str, optional) :** Friendly label; defaults to the redacted URL.
    - **description (str, optional) :** Free-text description.
    - **sensor_id (str, optional) :** Stable logical identity of the physical
      source, recorded on every embedding so externally stored media for the
      same source can be correlated back to it. Defaults to the stream_id.
    - **frame_interval (int, optional) :** Sample every Nth frame (1-60).
    - **enable_object_detection (bool, optional) :** Enable crop extraction.
    - **detection_confidence (float, optional) :** Detection threshold (0.1-1.0).
    - **tags (list(str), optional) :** Tags applied to every embedding.
    - **start (bool, optional) :** Register without starting when false.

    #### Raises:
    - **400 Bad Request :** The URL is not a valid RTSP URL.
    - **503 Service Unavailable :** The concurrency limit is reached, or live
      ingestion is disabled.
    - **500 Internal Server Error :** Unexpected failure while registering.

    Returns:
    - **response (json) :** The registered stream, with its credentials redacted.
    """
    _require_enabled()
    info = _create_one(request)
    return LiveStreamResponse(
        message=f"Live stream registered with id {info.stream_id}.", stream=info
    )


@router.post(
    "/media/streams/batch",
    summary="Register several RTSP streams in one call.",
    operation_id="createLiveStreamsBatch",
    status_code=HTTPStatus.ACCEPTED,
    response_model=LiveStreamBatchResponse,
    response_model_exclude_none=True,
    responses=error_responses(*LIVE_STREAM_ERRORS),
)
async def create_live_streams_batch(
    request: Annotated[LiveStreamBatchCreateRequest, Body(...)],
) -> LiveStreamBatchResponse:
    """
    ### Register a batch of live RTSP streams.

    Items are processed independently: one rejected URL (or a stream that would
    exceed the concurrency limit) does not prevent the rest from being
    registered. The response reports the outcome per item.

    #### Request Body:
    - **items (list, required) :** Live stream definitions, each matching the
      body of `POST /media/streams`.

    #### Raises:
    - **400 Bad Request :** The batch body is malformed or empty.
    - **503 Service Unavailable :** Live ingestion is disabled.

    Returns:
    - **response (json) :** Accepted/rejected counts and a per-item result list.
    """
    _require_enabled()

    results: List[LiveStreamBatchItemResult] = []
    accepted = 0
    for item in request.items:
        identifier = redact_stream_url(item.stream_url)
        try:
            info = _create_one(item)
        except HTTPException as exc:
            results.append(
                LiveStreamBatchItemResult(
                    identifier=identifier,
                    status=BatchItemStatusEnum.error,
                    message=str(exc.detail),
                )
            )
            continue
        accepted += 1
        results.append(
            LiveStreamBatchItemResult(
                identifier=identifier,
                stream_id=info.stream_id,
                status=BatchItemStatusEnum.success,
                message="Registered.",
            )
        )

    rejected = len(results) - accepted
    return LiveStreamBatchResponse(
        message=f"{accepted} live stream(s) registered, {rejected} rejected.",
        accepted=accepted,
        rejected=rejected,
        items=results,
    )


@router.get(
    "/media/streams",
    summary="List registered live streams.",
    operation_id="listLiveStreams",
    status_code=HTTPStatus.OK,
    response_model=LiveStreamListResponse,
    response_model_exclude_none=True,
    responses=error_responses(*READ_ERRORS),
)
async def list_live_streams(
    state: Annotated[
        Optional[LiveStreamStateEnum],
        Query(description="Only return streams in this state."),
    ] = None,
    tags: Annotated[
        Optional[List[str]],
        Query(description="Only return streams carrying all of these tags."),
    ] = None,
) -> LiveStreamListResponse:
    """
    ### List every registered live stream and its current state.

    #### Query Params:
    - **state (str, optional) :** Filter by lifecycle state (`running`,
      `paused`, `reconnecting`, `error`, ...).
    - **tags (list(str), optional) :** Only streams carrying all given tags.

    Returns:
    - **response (json) :** Count and the list of streams (URLs redacted).
    """
    _require_enabled()
    streams = get_live_stream_manager().list(state=state, tags=tags)
    infos = [stream.to_info() for stream in streams]
    return LiveStreamListResponse(
        message=f"{len(infos)} live stream(s) registered.",
        count=len(infos),
        streams=infos,
    )


@router.get(
    "/media/streams/{stream_id}",
    summary="Get one live stream's configuration, state, and statistics.",
    operation_id="getLiveStream",
    status_code=HTTPStatus.OK,
    response_model=LiveStreamResponse,
    response_model_exclude_none=True,
    responses=error_responses(*READ_ERRORS),
)
async def get_live_stream(
    stream_id: Annotated[str, Path(description="Identifier returned at registration.")],
) -> LiveStreamResponse:
    """
    ### Return a single live stream.

    #### Path Params:
    - **stream_id (str, required) :** Identifier returned at registration.

    #### Raises:
    - **404 Not Found :** No stream is registered with this id.

    Returns:
    - **response (json) :** The stream, including ingestion counters and the
      last error observed by its worker.
    """
    _require_enabled()
    try:
        stream = get_live_stream_manager().get(stream_id)
    except LiveStreamNotFoundError as exc:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f"No live stream registered with id {sanitize_for_log(stream_id, max_length=64)}.",
        ) from exc
    return LiveStreamResponse(message="Live stream found.", stream=stream.to_info())


@router.patch(
    "/media/streams/{stream_id}",
    summary="Update a live stream, or pause/resume its ingestion.",
    operation_id="updateLiveStream",
    status_code=HTTPStatus.OK,
    response_model=LiveStreamResponse,
    response_model_exclude_none=True,
    responses=error_responses(*LIVE_STREAM_ERRORS),
)
async def update_live_stream(
    stream_id: Annotated[str, Path(description="Identifier returned at registration.")],
    request: Annotated[LiveStreamUpdateRequest, Body(...)],
) -> LiveStreamResponse:
    """
    ### Update a registered live stream.

    Only the supplied fields change. Setting `state` to `paused` stops ingestion
    while keeping the registration; setting it to `running` resumes. Changing a
    processing parameter on a running stream restarts its ingestion session so
    the new value takes effect immediately.

    #### Path Params:
    - **stream_id (str, required) :** Identifier returned at registration.

    #### Request Body:
    - **stream_name / description (str, optional) :** Descriptive fields.
    - **frame_interval / enable_object_detection / detection_confidence (optional) :**
      Processing parameters.
    - **tags (list(str), optional) :** Replaces the existing tag list.
    - **state (str, optional) :** `paused` or `running`.

    #### Raises:
    - **400 Bad Request :** An unsupported state transition was requested.
    - **404 Not Found :** No stream is registered with this id.
    - **503 Service Unavailable :** Resuming would exceed the concurrency limit.

    Returns:
    - **response (json) :** The updated stream.
    """
    _require_enabled()
    manager = get_live_stream_manager()
    try:
        stream = manager.update(
            stream_id,
            stream_name=request.stream_name,
            description=request.description,
            frame_interval=request.frame_interval,
            enable_object_detection=request.enable_object_detection,
            detection_confidence=request.detection_confidence,
            tags=request.tags,
            state=request.state,
        )
    except LiveStreamNotFoundError as exc:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f"No live stream registered with id {sanitize_for_log(stream_id, max_length=64)}.",
        ) from exc
    except LiveStreamLimitError as exc:
        raise HTTPException(status_code=HTTPStatus.SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return LiveStreamResponse(message="Live stream updated.", stream=stream.to_info())


@router.delete(
    "/media/streams/{stream_id}",
    summary="Stop a live stream and deregister it.",
    operation_id="deleteLiveStream",
    status_code=HTTPStatus.OK,
    response_model=LiveStreamDeleteResponse,
    response_model_exclude_none=True,
    responses=error_responses(*LIVE_STREAM_ERRORS),
)
async def delete_live_stream(
    stream_id: Annotated[str, Path(description="Identifier returned at registration.")],
    purge_embeddings: Annotated[
        bool,
        Query(description="Also delete every embedding generated from this stream."),
    ] = False,
    purge_media: Annotated[
        bool,
        Query(description="Also delete the stream's recorded segments and frames."),
    ] = False,
) -> LiveStreamDeleteResponse:
    """
    ### Stop ingesting a live stream and remove its registration.

    Stored embeddings and recorded media are kept by default so that historical
    search results keep working after a camera is decommissioned. Set the purge
    flags to remove them.

    #### Path Params:
    - **stream_id (str, required) :** Identifier returned at registration.

    #### Query Params:
    - **purge_embeddings (bool, optional) :** Delete this stream's vectors.
    - **purge_media (bool, optional) :** Delete this stream's recorded media.

    #### Raises:
    - **404 Not Found :** No stream is registered with this id.
    - **502 Bad Gateway :** The vector database or storage backend failed during purge.

    Returns:
    - **response (json) :** The stream id and, when purging, how much was removed.
    """
    _require_enabled()
    manager = get_live_stream_manager()
    try:
        _, embeddings_purged, media_purged = manager.delete(
            stream_id,
            purge_embeddings=purge_embeddings,
            purge_media=purge_media,
        )
    except LiveStreamNotFoundError as exc:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f"No live stream registered with id {sanitize_for_log(stream_id, max_length=64)}.",
        ) from exc
    return LiveStreamDeleteResponse(
        message="Live stream stopped and deregistered.",
        stream_id=stream_id,
        embeddings_purged=embeddings_purged,
        media_purged=media_purged,
    )


@router.delete(
    "/media/streams",
    summary="Stop and deregister several live streams.",
    operation_id="deleteLiveStreamsBatch",
    status_code=HTTPStatus.OK,
    response_model=LiveStreamBatchResponse,
    response_model_exclude_none=True,
    responses=error_responses(*LIVE_STREAM_ERRORS),
)
async def delete_live_streams_batch(
    request: Annotated[LiveStreamDeleteRequest, Body(...)],
    purge_embeddings: Annotated[
        bool, Query(description="Also delete embeddings generated from these streams.")
    ] = False,
    purge_media: Annotated[
        bool, Query(description="Also delete the streams' recorded media.")
    ] = False,
) -> LiveStreamBatchResponse:
    """
    ### Stop and deregister a batch of live streams.

    Streams are processed independently; an unknown id is reported on its own
    item rather than failing the whole call.

    #### Request Body:
    - **stream_ids (list(str), required) :** Streams to stop and deregister.

    #### Query Params:
    - **purge_embeddings (bool, optional) :** Delete the streams' vectors.
    - **purge_media (bool, optional) :** Delete the streams' recorded media.

    Returns:
    - **response (json) :** Accepted/rejected counts and a per-item result list.
    """
    _require_enabled()
    manager = get_live_stream_manager()

    results: List[LiveStreamBatchItemResult] = []
    accepted = 0
    for stream_id in request.stream_ids:
        try:
            manager.delete(
                stream_id,
                purge_embeddings=purge_embeddings,
                purge_media=purge_media,
            )
        except LiveStreamNotFoundError:
            results.append(
                LiveStreamBatchItemResult(
                    identifier=stream_id,
                    stream_id=stream_id,
                    status=BatchItemStatusEnum.error,
                    message="No live stream registered with this id.",
                )
            )
            continue
        except Exception as exc:  # noqa: BLE001 - isolate per-item failures
            logger.error(
                "Failed to delete live stream %s: %s",
                sanitize_for_log(stream_id, max_length=64),
                sanitize_for_log(str(exc), max_length=256),
            )
            results.append(
                LiveStreamBatchItemResult(
                    identifier=stream_id,
                    stream_id=stream_id,
                    status=BatchItemStatusEnum.error,
                    message=sanitize_for_log(str(exc), max_length=256),
                )
            )
            continue
        accepted += 1
        results.append(
            LiveStreamBatchItemResult(
                identifier=stream_id,
                stream_id=stream_id,
                status=BatchItemStatusEnum.success,
                message="Stopped and deregistered.",
            )
        )

    rejected = len(results) - accepted
    return LiveStreamBatchResponse(
        message=f"{accepted} live stream(s) deleted, {rejected} failed.",
        accepted=accepted,
        rejected=rejected,
        items=results,
    )
