# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Asset library management endpoints.

An asset library owns assets, sources, and the pools that pair the two. There is
no activation: every path names the library it operates on, and ``{library}``
accepts a name or an id.
"""

import hashlib
import os
from typing import List

import config
from assetlib.sources.updates import SourceRuleError
from core import materialize
from core.extractor import is_supported
from core.file_asset_library import asset_id_for, file_origin, inline_origin
from core.manager import registry
from core.knowledge.okf import is_okf
from core.multimodal import captioning, coverage, transcription
from schemas import (
    AssetCreateRequest,
    AssetCreateResult,
    AssetDeleteRequest,
    AssetDeleteResult,
    AssetEnrichmentOut,
    AssetLibraryIn,
    AssetLibraryOut,
    AssetLibraryUpdate,
    AssetPage,
    AssetPoolAssetsIn,
    AssetPoolIn,
    AssetPoolOut,
    AssetPoolSourcesIn,
    ExtractionOut,
    ExtractionRequest,
    PoolGraph,
    PoolRoutingOut,
    SourceIn,
    SourceOut,
    SourceServingStateUpdate,
    SourceUpdate,
    UploadResult,
)
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool

LIBRARY_API_PREFIX = "/v1/libraries"

router = APIRouter(prefix=LIBRARY_API_PREFIX, tags=["libraries"])

# A request the multi-source rules refuse (assetlib/sources/updates.py). Written
# out because Starlette renamed the constant between versions.
_UNPROCESSABLE = 422


def _text_reference(text: str) -> str:
    """A stable handle for inline text, so posting it twice updates one asset."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _folder_files(path: str) -> List[str]:
    """The ingestible files under a plain (non-OKF) folder, in a stable order.

    Hidden entries are skipped (``.DS_Store``, ``.git``), as are files the
    extractor cannot read: a dropped folder routinely holds a few, and refusing
    the whole folder for them would make folder upload useless.
    """
    found = []
    for root, dirs, files in os.walk(path):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        found.extend(
            os.path.join(root, name)
            for name in sorted(files)
            if not name.startswith(".") and is_supported(os.path.join(root, name))
        )
    return found


def _resolve_uploads(file_paths: List[str]) -> List[str]:
    """Resolve bare file names in the shared upload directory.

    An OKF bundle directory is one asset; any other directory stands for the
    supported files inside it.
    """
    resolved = []
    for requested in file_paths:
        path = (
            requested
            if os.path.isabs(requested) or os.path.exists(requested)
            else os.path.join(config.UPLOAD_DIR, requested)
        )
        path = os.path.abspath(path)
        if not os.path.exists(path):
            raise ValueError(
                f"Asset file not found: {requested!r} (resolved to {path!r})"
            )
        if os.path.isdir(path):
            if not is_okf(path):
                files = _folder_files(path)
                if not files:
                    raise ValueError(
                        f"Asset folder holds no supported files: {requested!r}"
                    )
                resolved.extend(files)
                continue
        elif not os.path.isfile(path):
            raise ValueError(f"Asset path is not a file: {requested!r}")
        elif not is_supported(path):
            raise ValueError(f"Unsupported asset file type: {requested!r}")
        resolved.append(path)
    return resolved


def _require(library: str):
    """The asset library named (or identified) by `library`, or a 404."""
    found = registry.get(library)
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset library '{library}' not found",
        )
    return found


@router.get("", response_model=list[AssetLibraryOut])
async def list_asset_libraries():
    return [library.to_out() for library in registry.list()]


@router.get("/{library}", response_model=AssetLibraryOut)
async def get_asset_library(library: str):
    return _require(library).to_out()


@router.post("", response_model=AssetLibraryOut, status_code=status.HTTP_201_CREATED)
async def create_asset_library(body: AssetLibraryIn):
    try:
        # `exclude_none` so an omitted content_database means "resolve one on
        # first ingest" rather than arriving as an explicit None.
        return registry.create(**body.model_dump(exclude_none=True)).to_out()
    except ValueError as e:
        # "already exists" is a conflict; an unsupported parser/indexer is a 400.
        code = status.HTTP_409_CONFLICT if "already exists" in str(e) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(e))


@router.patch("/{library}", response_model=AssetLibraryOut)
async def update_asset_library(library: str, body: AssetLibraryUpdate):
    asset_library = _require(library)
    asset_library.update(**body.model_dump(exclude_unset=True))
    registry.save()
    return asset_library.to_out()


@router.delete("/{library}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset_library(library: str):
    if not registry.delete(library):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Asset library '{library}' not found")


@router.post(
    "/{library}/assets",
    response_model=AssetCreateResult,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_assets(
    library: str,
    body: AssetCreateRequest,
    background_tasks: BackgroundTasks,
):
    """Accept assets for a library and index them through selected pools.

    Returns 202 at once: extraction (render/detect/OCR) and embedding are slow, so
    they run in a background task (`materialize.ingest`) rather than on the request
    thread. The response names the assets straight away because an
    asset's id comes from where it was read from, not from its content
    (`asset_id_for`), so it is known before anything is extracted.
    """
    asset_library = _require(library)
    if not body.file_paths and not body.text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one file path or text value is required",
        )

    asset_pool_ids = list(dict.fromkeys(body.asset_pool_ids))
    missing_pool_ids = [
        asset_pool_id
        for asset_pool_id in asset_pool_ids
        if asset_pool_id not in asset_library.asset_pools
    ]
    if missing_pool_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset pool(s) not found: {', '.join(missing_pool_ids)}",
        )

    # Resolved before the task is scheduled: an unknown source or a missing file
    # is a bad request, and reporting it from a background task would lose it.
    # Resolving the source also adopts the library's default on a first ingest --
    # a mutation of the library, hence the lock, and a cheap one: registering a
    # source stores a locator and dials nothing.
    try:
        with registry.lock:
            content_source = asset_library.content_source(body.content_source_id)
        resolved_paths = _resolve_uploads(body.file_paths)
    except ValueError as error:
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in str(error).lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=str(error)) from error

    source_id = content_source.source_id
    asset_ids = [asset_id_for(file_origin(path)) for path in resolved_paths]
    text_reference = ""
    if body.text:
        text_reference = _text_reference(body.text)
        asset_ids.append(asset_id_for(inline_origin(text_reference)))

    # Mark them materializing now, so a client polling GET /assets sees progress
    # the instant this 202 returns rather than only once the background task runs.
    materialize.begin_materialization(asset_ids)
    background_tasks.add_task(
        materialize.ingest,
        asset_library,
        resolved_paths,
        body.text or "",
        text_reference,
        asset_pool_ids,
        source_id,
    )
    return AssetCreateResult(
        library=asset_library.name,
        asset_ids=asset_ids,
        asset_pool_ids=asset_pool_ids,
        file_paths=resolved_paths,
        content_source_id=source_id,
        status="materializing",
    )


def _upload_target(library_id: str, relative_path: str) -> str:
    """Where an upload lands: under the library's own upload folder, never above it."""
    root = os.path.abspath(os.path.join(config.UPLOAD_DIR, library_id))
    parts = relative_path.replace("\\", "/").split("/")
    if (
        not relative_path
        or os.path.isabs(relative_path)
        or any(part in ("", ".", "..") for part in parts)
    ):
        raise ValueError(f"Invalid upload path: {relative_path!r}")
    target = os.path.abspath(os.path.join(root, *parts))
    if not target.startswith(root + os.sep):
        raise ValueError(f"Invalid upload path: {relative_path!r}")
    return target


@router.put(
    "/{library}/uploads/{file_path:path}",
    response_model=UploadResult,
    status_code=status.HTTP_201_CREATED,
)
async def upload_file(library: str, file_path: str, request: Request):
    """Stage a file from a browser so `POST /assets` can name it.

    The request body is the file's bytes, not a multipart form: a browser can
    send a `File` as-is, nothing has to buffer the whole thing to parse it, and
    the engine needs no form parser. `file_path` is relative and may contain
    folders, which is how a folder upload keeps its shape (an OKF bundle needs
    it). Files go under the library's id, so the same name in two libraries
    does not collide, and uploading a name again replaces it -- an asset's id
    comes from its path, so re-ingesting it updates that asset.
    """
    asset_library = _require(library)
    try:
        target = _upload_target(asset_library.library_id, file_path)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    partial = target + ".part"
    size = 0
    try:
        with open(partial, "wb") as out:
            async for chunk in request.stream():
                out.write(chunk)
                size += len(chunk)
        os.replace(partial, target)
    except OSError as error:
        if os.path.exists(partial):
            os.remove(partial)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not store the upload: {error}",
        ) from error
    return UploadResult(
        library=asset_library.name,
        name=os.path.relpath(target, config.UPLOAD_DIR),
        file_path=target,
        size=size,
        supported=is_supported(target) or is_okf(target),
    )


def _uncovered_media_warnings(asset_library, media_streams) -> List[str]:
    """Legacy coverage formatting, not part of the asynchronous ingest response.

    Kept for callers of the old private helper. The request has no stream yet;
    clients now read the authoritative coverage from `/enrichment` after ingest.
    """
    warnings = []
    for asset_id, (path, stream) in media_streams.items():
        found = coverage.embedding_coverage(asset_library, asset_id, stream)
        if found.status == coverage.NO_SOURCE:
            warnings.append(
                f"{os.path.basename(path)} is stored but will not be embedded: "
                f"{found.reason}"
            )
    return warnings


@router.get("/{library}/sources", response_model=list[SourceOut])
async def list_sources(library: str):
    return _require(library).to_out().sources


@router.post(
    "/{library}/sources", response_model=SourceOut, status_code=status.HTTP_201_CREATED
)
async def add_source(library: str, body: SourceIn):
    asset_library = _require(library)
    try:
        source = asset_library.create_source(
            name=body.name,
            database_id=body.database_id,
            collection_name=body.collection_name or "",
            configuration=body.operator_options,
            enabled=body.enabled,
            labels=body.labels,
        )
    except (TypeError, ValueError) as error:
        code = status.HTTP_409_CONFLICT if "already exists" in str(error) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(error))
    registry.save()
    return next(
        output
        for output in asset_library.to_out().sources
        if output.id == source.source_id
    )


@router.patch("/{library}/sources/{source_id}", response_model=SourceOut)
async def update_source(
    library: str,
    source_id: str,
    body: SourceUpdate,
    background_tasks: BackgroundTasks,
):
    """Rename, relabel, or switch a source on or off.

    Nothing that decides its vectors can change: a different model or different
    parameters is a new source, attached with `replaces`. Switching a source
    off freezes it in every pool (its data stays); switching it back on rebuilds
    its projections and catches it up before it serves again.
    """
    asset_library = _require(library)
    if source_id not in asset_library.sources:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Source '{source_id}' not found")
    try:
        resync = asset_library.update_source(
            source_id, **body.model_dump(exclude_unset=True)
        )
    except SourceRuleError as error:
        raise HTTPException(status_code=_UNPROCESSABLE, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
    except Exception as error:  # a projection could not be rebuilt
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not enable the source: {type(error).__name__}: {error}",
        )
    registry.save()
    if resync:
        background_tasks.add_task(_sync_and_save, asset_library, resync)
    return next(
        output
        for output in asset_library.to_out().sources
        if output.id == source_id
    )


@router.delete("/{library}/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_source(library: str, source_id: str):
    """Detach a source and its pool bindings; leave external collections intact.

    Refused while it holds live asset content or has an in-flight extraction.
    Queued extraction jobs are cancelled before their bindings are removed.
    """
    asset_library = _require(library)
    try:
        detached = asset_library.detach_source(source_id)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error
    if not detached:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Source '{source_id}' not found")
    registry.save()


@router.get("/{library}/asset_pools", response_model=list[AssetPoolOut])
async def list_asset_pools(library: str):
    return _require(library).to_out().asset_pools


@router.post(
    "/{library}/asset_pools",
    response_model=AssetPoolOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_asset_pool(library: str, body: AssetPoolIn):
    asset_library = _require(library)
    try:
        asset_library.create_asset_pool(
            asset_pool_id=body.id,
            name=body.name,
            source_configurations=[
                {"source_id": source_id} for source_id in body.sources or []
            ],
            metadata=body.metadata,
        )
    except (TypeError, ValueError) as error:
        code = status.HTTP_409_CONFLICT if "already exists" in str(error) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(error))
    except Exception as error:  # backend or model dependency is unavailable
        # Attaching a source builds its projection, which dials. Registering a
        # database deliberately does not, so "registered but unreachable" is an
        # ordinary state and this is where an operator first meets it -- as a
        # 503 naming the backend, not a 500 that reads like a bad request.
        # `set_asset_pool_sources` below answers the same way.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not create the asset pool: {type(error).__name__}: {error}",
        )
    registry.save()
    return next(
        asset_pool
        for asset_pool in asset_library.to_out().asset_pools
        if asset_pool.id == body.id
    )


@router.delete("/{library}/asset_pools/{asset_pool_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_asset_pool(library: str, asset_pool_id: str):
    asset_library = _require(library)
    if not asset_library.remove_asset_pool(asset_pool_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset pool '{asset_pool_id}' not found",
        )
    registry.save()


@router.get("/{library}/asset_pools/{asset_pool_id}", response_model=AssetPoolOut)
async def get_asset_pool(library: str, asset_pool_id: str):
    asset_library = _require(library)
    asset_library._require_asset_pool(asset_pool_id)
    return next(
        pool for pool in asset_library.to_out().asset_pools
        if pool.id == asset_pool_id
    )


@router.get(
    "/{library}/asset_pools/{asset_pool_id}/sources",
    response_model=list[SourceOut],
)
async def list_asset_pool_sources(library: str, asset_pool_id: str):
    asset_library = _require(library)
    asset_pool = asset_library._require_asset_pool(asset_pool_id)
    source_ids = set(asset_pool.source_statuses)
    return [
        source
        for source in asset_library.to_out().sources
        if source.id in source_ids
    ]


@router.get(
    "/{library}/asset_pools/{asset_pool_id}/routing",
    response_model=PoolRoutingOut,
)
async def get_asset_pool_routing(library: str, asset_pool_id: str):
    """Which source takes each kind of content in this pool, and in what state.

    Routing is the sum of every source's filters and model; this is where it
    can be read as one table, including the kinds nothing serving takes.
    """
    asset_library = _require(library)
    try:
        return asset_library.routing(asset_pool_id)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))


@router.get(
    "/{library}/asset_pools/{asset_pool_id}/assets",
    response_model=list[str],
)
async def list_asset_pool_assets(library: str, asset_pool_id: str):
    asset_library = _require(library)
    return list(asset_library._require_asset_pool(asset_pool_id).asset_ids)


@router.get("/{library}/asset_pools/{asset_pool_id}/graph", response_model=PoolGraph)
async def get_asset_pool_graph(
    library: str,
    asset_pool_id: str,
    limit: int = Query(config.GRAPH_VIEW_LIMIT, ge=1, le=20000),
):
    """The pool's concept graph -- what `graph` retrieval walks -- for drawing.

    Read from the graph source as persisted. 404 when the pool has no graph
    source; 503 when its database cannot be reached.
    """
    from core.retrievers import pool_concept_graph

    asset_library = _require(library)
    try:
        asset_pool = asset_library._require_asset_pool(asset_pool_id)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    scope = await run_in_threadpool(asset_library.pool_concept_scope, asset_pool_id)
    origins = await run_in_threadpool(asset_library.concept_origins, asset_pool_id)
    try:
        # Only this pool's concepts when its graph source serves other pools too.
        view = await run_in_threadpool(pool_concept_graph, asset_pool, limit, scope)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    except Exception as error:  # the graph database is unavailable
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not read the graph: {type(error).__name__}: {error}",
        )
    for node in view["nodes"]:
        node["origin"] = origins.get(node["id"], "")
    return PoolGraph(library=asset_library.name, asset_pool_id=asset_pool_id, **view)


@router.post(
    "/{library}/asset_pools/{asset_pool_id}/extractions",
    response_model=ExtractionOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_extraction(
    library: str, asset_pool_id: str, response: Response,
    body: ExtractionRequest = ExtractionRequest(),
):
    """Extract the pool's documents into OKF for a graph source, in the background.

    The whole current corpus is extracted, published as the source's generated
    `okf` bundle asset and built into the graph. 202 with a new job; 200 with
    the job already queued or running for that pool and source (a running one
    is followed by one more run, so documents added meanwhile are covered). A
    job finding nothing changed since the last extraction ends `up_to_date`
    unless `force`. Poll `GET .../extractions/{extraction_id}`.
    """
    asset_library = _require(library)
    try:
        asset_library._require_asset_pool(asset_pool_id)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    try:
        job, created = asset_library.request_extraction(asset_pool_id, body.source_id, body.force)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
    if not created:
        response.status_code = status.HTTP_200_OK
    return ExtractionOut(**job.to_out())


@router.get("/{library}/asset_pools/{asset_pool_id}/extractions", response_model=list[ExtractionOut])
async def list_extractions(library: str, asset_pool_id: str, source_id: str = Query(None)):
    """This engine run's extraction jobs for the pool, newest first."""
    asset_library = _require(library)
    try:
        asset_library._require_asset_pool(asset_pool_id)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    return [ExtractionOut(**job.to_out()) for job in asset_library.extraction_jobs.list(asset_pool_id, source_id)]


def _require_extraction(asset_library, asset_pool_id: str, extraction_id: str):
    job = asset_library.extraction_jobs.get(extraction_id)
    if job is None or job.asset_pool_id != asset_pool_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Extraction '{extraction_id}' not found",
        )
    return job


@router.get(
    "/{library}/asset_pools/{asset_pool_id}/extractions/{extraction_id}",
    response_model=ExtractionOut,
)
async def get_extraction(library: str, asset_pool_id: str, extraction_id: str):
    job = _require_extraction(_require(library), asset_pool_id, extraction_id)
    return ExtractionOut(**job.to_out())


@router.delete(
    "/{library}/asset_pools/{asset_pool_id}/extractions/{extraction_id}",
    response_model=ExtractionOut,
)
async def cancel_extraction(library: str, asset_pool_id: str, extraction_id: str):
    """Cancel a queued extraction. 409 for a running one: its request to the
    extractor is already in flight."""
    asset_library = _require(library)
    job = _require_extraction(asset_library, asset_pool_id, extraction_id)
    try:
        job = asset_library.extraction_jobs.cancel(job.extraction_id)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    return ExtractionOut(**job.to_out())


@router.post("/{library}/asset_pools/{asset_pool_id}/assets", response_model=AssetPoolOut)
async def add_asset_pool_assets(
    library: str,
    asset_pool_id: str,
    body: AssetPoolAssetsIn,
    background_tasks: BackgroundTasks,
):
    asset_library = _require(library)
    try:
        asset_library.add_assets_to_pool(asset_pool_id, body.asset_ids)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    registry.save()
    background_tasks.add_task(_sync_and_save, asset_library, [asset_pool_id])
    return await get_asset_pool(library, asset_pool_id)


@router.put("/{library}/asset_pools/{asset_pool_id}/sources", response_model=AssetPoolOut)
async def set_asset_pool_sources(
    library: str,
    asset_pool_id: str,
    body: AssetPoolSourcesIn,
    background_tasks: BackgroundTasks,
):
    asset_library = _require(library)
    try:
        asset_library.set_asset_pool_sources(
            asset_pool_id=asset_pool_id,
            source_configurations=[
                {"source_id": entry}
                if isinstance(entry, str)
                else entry.model_dump(exclude_none=True)
                for entry in body.sources
            ],
        )
    except SourceRuleError as error:
        raise HTTPException(status_code=_UNPROCESSABLE, detail=str(error))
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
    except Exception as error:  # backend or model dependency is unavailable
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not attach pool sources: {type(error).__name__}: {error}",
        )
    registry.save()
    background_tasks.add_task(_sync_and_save, asset_library, [asset_pool_id])
    return await get_asset_pool(library, asset_pool_id)


@router.patch(
    "/{library}/asset_pools/{asset_pool_id}/sources/{source_id}",
    response_model=AssetPoolOut,
)
async def set_source_serving_state(
    library: str,
    asset_pool_id: str,
    source_id: str,
    body: SourceServingStateUpdate,
    background_tasks: BackgroundTasks,
):
    """Stop/resume one binding without changing the pool's attachments.

    DEPRECATED stops reads and future writes, retaining indexed data. SERVING
    resumes this exact model, reporting PREPARING until caught up when needed.
    No other binding is replaced or deprecated.
    """
    asset_library = _require(library)
    pool = asset_library.asset_pools.get(asset_pool_id)
    if pool is None or source_id not in pool.source_statuses:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pool source binding not found")
    try:
        resync = await run_in_threadpool(
            asset_library.set_source_serving_state, asset_pool_id, source_id, body.serving_state
        )
    except SourceRuleError as error:
        raise HTTPException(status_code=_UNPROCESSABLE, detail=str(error))
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not resume the source: {type(error).__name__}: {error}",
        )
    registry.save()
    if resync:
        background_tasks.add_task(_sync_and_save, asset_library, resync)
    return await get_asset_pool(library, asset_pool_id)


def _sync_and_save(asset_library, asset_pool_ids: List[str]) -> None:
    for asset_pool_id in asset_pool_ids:
        asset_library.sync_asset_pool(asset_pool_id)
    registry.save()


def _caption_and_save(asset_library, asset_ids: List[str]) -> None:
    """Describe each clip, then re-materialize the pools that now have more text.

    The second sync is what gets the new description into the text collection;
    `caption_asset` has already marked the asset changed, so only the blocks
    that moved are rebuilt. A clip whose description failed is left alone --
    its own status says why, and its vector is untouched.
    """
    _enrich_and_save(asset_library, asset_ids, captioning.caption_asset)


def _transcribe_and_save(asset_library, asset_ids: List[str]) -> None:
    """Transcribe each recording, then re-materialize the pools that hold it.

    The sync is what gets the transcript into a source that embeds derived
    text (GME); a text source does not take it.
    """
    _enrich_and_save(asset_library, asset_ids, transcription.transcribe_asset)


def _enrich_and_save(asset_library, asset_ids: List[str], job) -> None:
    materialize._enrich_and_save(asset_library, asset_ids, job)


@router.get("/{library}/assets", response_model=AssetPage)
async def list_assets(
    library: str,
    page_num: int = Query(1, ge=1),
    page_size: int = Query(config.ASSET_PAGE_SIZE, ge=1),
):
    page = _require(library).list_assets(page_num, page_size)
    # Overlay the live ingest phase so a client can show "text searchable" before
    # "fully ready"; untracked assets (e.g. after a restart) report None.
    for asset in page.assets:
        asset.materialization = materialize.materialization_phase(asset.id)
    return page


@router.get(
    "/{library}/assets/{asset_id}/enrichment", response_model=AssetEnrichmentOut
)
async def get_asset_enrichment(library: str, asset_id: str):
    """How far this asset's background description and transcript have got.

    The first place to look when a media asset is not being found. Captioning
    and embedding are reported separately because they are separate pipelines:
    a clip can be fully embedded and still undescribed, or described and not
    embedded at all because no source in its pools can embed that kind of media.
    A pool's `ready` distinguishes none of these.
    """
    asset_library = _require(library)
    asset = asset_library.assets.get(asset_id)
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset '{asset_id}' not found",
        )
    stream = asset.content
    embedding = coverage.embedding_coverage(asset_library, asset_id, stream)
    return AssetEnrichmentOut(
        asset_id=asset_id,
        embedding_status=embedding.status,
        embedding_reason=embedding.reason,
        **captioning.caption_status(stream),
        **transcription.transcript_status(stream),
    )


@router.delete("/{library}/assets", response_model=AssetDeleteResult)
async def delete_assets(library: str, body: AssetDeleteRequest, background_tasks: BackgroundTasks):
    asset_library = _require(library)
    if not body.asset_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one asset ID is required",
        )
    try:
        result = asset_library.delete_assets(body.asset_ids)
    except ValueError as error:
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in str(error).lower()
            else status.HTTP_409_CONFLICT
        )
        raise HTTPException(status_code=code, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not delete assets: {type(error).__name__}: {error}",
        ) from error
    registry.save()
    # A deletion can leave work behind: a generated OKF bundle to rebuild
    # without the deleted documents, and an `auto` graph source to re-extract.
    pending = [
        pool_id for pool_id, pool in asset_library.asset_pools.items()
        if any(status.status == "pending" for status in pool.source_statuses.values())
    ]
    if pending:
        background_tasks.add_task(_sync_and_save, asset_library, pending)
    return AssetDeleteResult(library=asset_library.name, **result)


@router.delete("/{library}/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(library: str, asset_id: str, background_tasks: BackgroundTasks):
    await delete_assets(library, AssetDeleteRequest(asset_ids=[asset_id]), background_tasks)
