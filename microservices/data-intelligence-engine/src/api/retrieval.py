# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Combined retrieval and optional postprocessing endpoint.

Stateless by design: the caller (its retrieval pipeline) owns the stage
configuration and sends all of it on every request. The engine holds asset
libraries and models, never pipelines or a "current" asset library.
"""

import logging
from collections import OrderedDict
from itertools import zip_longest
from typing import Optional

import config
from assetlib.content import BLOB_PREFIX
from core.content import (
    ROLE_AUDIO, ROLE_DOC_IMAGE, ROLE_IMAGE, ROLE_L1_SEGMENT,
    ROLE_L2_CAPTION, ROLE_L2_TRANSCRIPT, ROLE_L3_WIKI,
    ROLE_LONG_VIDEO, ROLE_SHORT_VIDEO, is_file_uri,
)
from core.indexer import MultimodalIndexer
from core.multimodal.retrieval import _TARGET_ROLES, _projection_target, media_nodes_to_chunks, targeted_projections
from core.file_asset_library import nodes_to_chunks, postprocess_chunks
from core.manager import registry
from core.retrievers import RETRIEVER_TYPES, build_pool_retriever, graph_search_of
from schemas import GraphTrace, RerankerModelIn, RetrieveRequest, RetrieveResult
from fastapi import APIRouter, HTTPException, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from llama_index.core.vector_stores.types import (
    FilterOperator, MetadataFilter, MetadataFilters,
)

router = APIRouter(tags=["retrieval"])
logger = logging.getLogger(__name__)


@router.post("/v1/retrieve", response_model=RetrieveResult)
async def retrieve(body: RetrieveRequest):
    """Retrieve across libraries, then optionally postprocess the merged set."""
    if not body.query.strip() or not 1 <= body.top_k <= 100:
        raise HTTPException(status_code=400, detail="nonempty query and top_k between 1 and 100 are required")
    if (body.postprocess is not None and body.postprocess.processor_type == "reranker"
            and (body.postprocess.top_n is None or body.postprocess.top_n < 1)):
        raise HTTPException(status_code=400, detail="postprocess.top_n must be positive")
    if body.retriever_type and body.retriever_type not in RETRIEVER_TYPES:
        raise HTTPException(status_code=400, detail=f"unsupported retriever type {body.retriever_type!r}")
    library_refs = list(dict.fromkeys(body.libraries))
    try:
        asset_libraries = [registry.require(reference) for reference in library_refs]
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    if body.asset_pool_ids:
        available_pool_ids = {
            pool.asset_pool_id
            for library in asset_libraries
            for pool in library._select_asset_pools([])
        }
        unknown = set(body.asset_pool_ids) - available_pool_ids
        if unknown:
            raise HTTPException(status_code=404, detail=f"asset pool not found: {', '.join(sorted(unknown))}")
    try:
        if body.target_media:
            _check_targets(asset_libraries, body)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    traces = []
    try:
        # Embedding, backend search and native inference are synchronous.
        recalled = await run_in_threadpool(
            lambda: [
                chunk
                for asset_library in asset_libraries
                for chunk in _retrieve_chunks(asset_library, body, traces)
            ]
        )
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    excluded = set(body.exclude_chunk_ids)
    recalled = [chunk for chunk in recalled if chunk.id not in excluded]
    retrieved_chunks = _merge_candidates(recalled)
    for rank, chunk in enumerate(retrieved_chunks, 1):
        chunk.metadata["rank"] = rank
    chunks = [chunk.model_copy(deep=True) for chunk in retrieved_chunks]
    postprocess_error = None
    if body.postprocess is not None:
        options = body.postprocess
        if options.processor_type == "reranker":
            requested_media = bool(set(body.target_media) & {"image", "video", "audio"})
            recalled_media = any(
                chunk.metadata.get("target_media") not in (None, "document")
                and chunk.metadata.get("role") != ROLE_DOC_IMAGE
                for chunk in chunks
            )
            if options.reranker_model is None and (requested_media or recalled_media):
                options = options.model_copy(update={
                    "reranker_model": RerankerModelIn(backend="openvino_vl"),
                })
            backend = options.reranker_model.backend if options.reranker_model else None
            if backend != "openvino_vl":
                for chunk in chunks:
                    text = chunk.text.strip() or str(chunk.metadata.get("surrounding_text") or "").strip()
                    if not text or text in (chunk.metadata.get("media_key"), chunk.metadata.get("file_name")):
                        raise HTTPException(status_code=400, detail="text reranker requires meaningful candidate text")
                    chunk.text = text
        else:
            backend = None
        try:
            if backend == "openvino_vl":
                chunks = await run_in_threadpool(
                    postprocess_chunks,
                    options.query or body.query, chunks, options.processor_type,
                    options.top_n, options.reranker_model,
                    media_libraries={library.name: library for library in asset_libraries},
                    options=options,
                )
            else:
                chunks = await run_in_threadpool(
                    postprocess_chunks,
                    options.query or body.query, chunks, options.processor_type,
                    options.top_n, options.reranker_model,
                )
        except ValueError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except Exception as error:
            logger.exception("retrieval postprocessing failed; returning recall order")
            chunks = None
            postprocess_error = f"{type(error).__name__}: {error}"
        if chunks is None:
            chunks = [chunk.model_copy(deep=True) for chunk in retrieved_chunks]
    for rank, chunk in enumerate(chunks, 1):
        chunk.metadata["rank"] = rank
    retrieved_ids_by_scope = {}
    for chunk in retrieved_chunks:
        metadata = chunk.metadata
        key = (metadata.get("library"), metadata.get("pool_id"))
        retrieved_ids_by_scope.setdefault(key, set()).add(chunk.id)
    return RetrieveResult(
        query=body.query,
        libraries=[asset_library.name for asset_library in asset_libraries],
        retrieved_chunks=retrieved_chunks,
        chunks=chunks,
        postprocess_error=postprocess_error,
        graph_traces=[
            _graph_trace(
                trace,
                retrieved_ids_by_scope.get((trace["library"], trace["asset_pool_id"]), set()),
            )
            for trace in traces
        ],
    )


def _graph_trace(trace, retrieved_ids) -> GraphTrace:
    """A walk as reported: each concept keeps only the chunks it got into the result."""
    return GraphTrace(
        library=trace["library"],
        asset_pool_id=trace["asset_pool_id"],
        seeds=trace["seeds"],
        concepts=[
            {
                "id": concept["id"],
                "hop": concept["hop"],
                "weight": concept["weight"],
                "hit_chunk_ids": [cid for cid in concept["chunk_ids"] if cid in retrieved_ids],
            }
            for concept in trace["concepts"]
        ],
        edges=trace["edges"],
    )


def _is_media_projection(projection) -> bool:
    return isinstance(projection, MultimodalIndexer) or (
        (getattr(projection.source, "profile", None) or {}).get("encoder_kind") == "multimodal"
    )


def _chunk_targets(chunk, fallback: str) -> set[str]:
    metadata = chunk.metadata
    role = metadata.get("role")
    kind = metadata.get("kind")
    if role == ROLE_DOC_IMAGE:
        return {"document", "image"}
    if role == ROLE_L2_TRANSCRIPT:
        return {"audio"}
    if role in (ROLE_L1_SEGMENT, ROLE_SHORT_VIDEO, ROLE_LONG_VIDEO) or kind == "video":
        return {"video"}
    if role == ROLE_IMAGE or kind == "image":
        return {"image"}
    if role == ROLE_AUDIO or kind == "audio":
        return {"audio"}
    if role in (ROLE_L2_CAPTION, ROLE_L3_WIKI):
        return {fallback} if fallback in ("image", "audio", "video") else set()
    if kind in ("text", "table"):
        return {"document"}
    return {fallback} if fallback else set()


def _accept_chunk(chunk, body: RetrieveRequest, fallback: str) -> bool:
    targets = _chunk_targets(chunk, fallback)
    if not body.target_media:
        return True
    if not targets.intersection(body.target_media):
        return False
    # Document targets text only; images come along only when image is selected.
    if "image" not in body.target_media and "image" in targets:
        return False
    return True


def _tag_chunk(chunk, fallback: str) -> None:
    targets = _chunk_targets(chunk, fallback)
    chunk.metadata["target_media"] = (
        "image" if "image" in targets else
        "video" if "video" in targets else
        "audio" if "audio" in targets else "document"
    )


def _text_vector_filters(body: RetrieveRequest):
    """Push the selected document/image kinds into vector search."""
    requested = set(body.target_media)
    if not requested:
        return None
    if "image" in requested and "document" not in requested:
        return MetadataFilters(filters=[MetadataFilter(key="kind", value="image")])
    text_kinds = MetadataFilter(
        key="kind", value=["text", "table"], operator=FilterOperator.IN,
    )
    if "image" in requested:
        return MetadataFilters(filters=[MetadataFilter(
            key="kind", value=["text", "table", "image"], operator=FilterOperator.IN,
        )])
    return MetadataFilters(filters=[text_kinds])


def _selected_pools(asset_library, body: RetrieveRequest):
    pools = asset_library._select_asset_pools([])
    if not body.asset_pool_ids:
        return pools
    wanted = set(body.asset_pool_ids)
    return [pool for pool in pools if pool.asset_pool_id in wanted]


def _check_targets(asset_libraries, body: RetrieveRequest) -> None:
    available = set()
    for asset_library in asset_libraries:
        pools = _selected_pools(asset_library, body)
        text_sources = [
            projection for pool in pools for projection in pool.serving
            if getattr(projection, "kind", None) == "vector"
            and getattr(projection.source, "enabled", True)
            and not _is_media_projection(projection)
        ]
        if text_sources:
            available.update(("document", "image"))
        for target in ("image", "video", "audio"):
            if targeted_projections(asset_library, target, pools=pools):
                available.add(target)
        for _, projection in targeted_projections(asset_library, "image", pools=pools):
            profile_roles = set((projection.source.profile or {}).get("supported_roles") or ())
            configured_roles = set(projection.source.configuration.get("block_roles") or profile_roles)
            if ROLE_DOC_IMAGE in profile_roles.intersection(configured_roles):
                available.add("document")
    targets = set(body.target_media)
    missing = targets - available
    if missing and (not body.allow_missing_targets or missing == targets):
        raise HTTPException(status_code=503, detail=f"search unavailable for: {', '.join(sorted(missing))}")


def _merge_candidates(chunks):
    groups = OrderedDict()
    for chunk in chunks:
        metadata = chunk.metadata
        source = metadata.get("vector_source_id") or metadata.get("source_id") or ""
        key = (metadata.get("library"), metadata.get("pool_id"), source)
        groups.setdefault(key, []).append(chunk)
    merged = []
    seen = set()
    for row in zip_longest(*groups.values()):
        for chunk in row:
            if chunk is None:
                continue
            metadata = chunk.metadata
            identity = (metadata.get("library"), metadata.get("pool_id"), metadata.get("asset_id"), chunk.id)
            if identity in seen:
                continue
            seen.add(identity)
            merged.append(chunk)
    return merged


def _retrieve_chunks(asset_library, body: RetrieveRequest, traces: list):
    top_k = body.top_k or config.RETRIEVE_TOP_K
    retriever_type = body.retriever_type or "rrf"
    chunks = []
    requested = set(body.target_media)
    excluded = set(body.exclude_chunk_ids)
    depth = min(top_k + len(excluded), 100)
    pools = _selected_pools(asset_library, body)
    eligible_media = {
        target: {id(projection) for _, projection in targeted_projections(
            asset_library, target, pools=pools,
        )}
        for target in ("image", "video", "audio")
    }
    for asset_pool in pools:
        vectors = [
            projection for projection in asset_pool.serving
            if getattr(projection, "kind", None) == "vector"
            and getattr(projection.source, "enabled", True)
        ]
        text_vectors = [projection for projection in vectors if not _is_media_projection(projection)]
        if text_vectors and (not requested or requested.intersection(("document", "image"))):
            scoped = bool(requested) or bool(excluded)
            retriever = build_pool_retriever(
                asset_library, asset_pool, retriever_type, depth, selected_vectors=text_vectors,
                vector_filters=_text_vector_filters(body),
                node_filter=(lambda node: _accept_chunk(node, body, "document")) if scoped else None,
                filter_key=tuple(sorted(requested)) if scoped else None,
            )
            if retriever is not None:
                nodes = retriever.retrieve(body.query)
                for scored in nodes:
                    asset_library._show_description(scored.node)
                per_source = {}
                for chunk in nodes_to_chunks(nodes, library=asset_library.name, pool_id=asset_pool.asset_pool_id):
                    if chunk.id in excluded or not _accept_chunk(chunk, body, "document"):
                        continue
                    source = chunk.metadata.get("source_id") or ""
                    rank = per_source.get(source, 0) + 1
                    if rank > top_k:
                        continue
                    per_source[source] = rank
                    chunk.metadata["source_rank"] = rank
                    _tag_chunk(chunk, "document")
                    chunks.append(chunk)
                search = graph_search_of(retriever) if body.include_graph_trace else None
                if search is not None and search.last_trace is not None:
                    traces.append({
                        **search.last_trace,
                        "library": asset_library.name,
                        "asset_pool_id": asset_pool.asset_pool_id,
                    })
        for projection in vectors:
            if not _is_media_projection(projection):
                continue
            supported = [target for target, ids in eligible_media.items() if id(projection) in ids]
            if requested and not requested.intersection(supported):
                continue
            fallback = _projection_target(projection) or (supported[0] if supported else "image")
            needs_filter = bool(
                requested and (fallback not in requested or len(supported) > 1)
            )
            accept = (
                (lambda chunk, target=fallback: _accept_chunk(chunk, body, target))
                if needs_filter else None
            )
            filters = None
            if needs_filter:
                roles = {ROLE_DOC_IMAGE} if "image" in requested else set()
                for target in requested.intersection(("image", "video", "audio")):
                    roles.update(_TARGET_ROLES[target])
                if not roles:
                    continue
                filters = MetadataFilters(filters=[MetadataFilter(
                    key="role", value=sorted(roles), operator=FilterOperator.IN,
                )])
            retriever = build_pool_retriever(
                asset_library, asset_pool, "vectorsimilarity", depth,
                selected_vectors=[projection], vector_filters=filters,
            )
            if retriever is None:
                raise RuntimeError(
                    f"Media retrieval source {projection.source.source_id!r} is no longer serving"
                )
            hits = media_nodes_to_chunks(
                retriever.retrieve(body.query), asset_library, asset_pool, projection,
                fallback, top_k, excluded, accept=accept,
            )
            for chunk in hits:
                _tag_chunk(chunk, fallback)
            chunks.extend(hits)
    return chunks


# Magic-byte prefixes, because the content store keeps only bytes -- not the
# content type they were written with -- so the media type is sniffed here.
_MEDIA_SIGNATURES = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"RIFF", "image/webp"),  # RIFF....WEBP; the WEBP tag is checked below
)


def _sniff_media_type(data: bytes) -> str:
    for signature, media_type in _MEDIA_SIGNATURES:
        if data.startswith(signature):
            if signature == b"RIFF" and data[8:12] != b"WEBP":
                continue
            return media_type
    return "application/octet-stream"


@router.get("/v1/blob")
async def get_blob(library: str, media_key: str, source_id: Optional[str] = None):
    """Serve a content-store blob or a registered asset's local media file.

    `library`, `media_key` and `source_id` are exactly the fields a retrieved
    chunk carries in its metadata, so a client renders an image node by handing
    them back here. Object keys stay restricted to `blobs/`. A `file://` key
    must exactly match a registered asset's binary block within the requested
    source; the library's reader verifies this before opening any local file.
    """
    if not (media_key.startswith(f"{BLOB_PREFIX}/") or is_file_uri(media_key)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"media_key must be a blob key under {BLOB_PREFIX}/ or a registered file:// key",
        )
    try:
        asset_library = registry.require(library)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    try:
        if is_file_uri(media_key):
            # Content records may require synchronous I/O to authorize. Resolve
            # the registered reference off-loop, never the caller's URI alone.
            path = await run_in_threadpool(
                asset_library.blob_file_path, media_key, source_id
            )
            return FileResponse(path)
        data = await run_in_threadpool(
            lambda: asset_library.blob_reader()(media_key, source_id)
        )
    except (KeyError, OSError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="blob not found"
        )
    return Response(content=data, media_type=_sniff_media_type(data))
