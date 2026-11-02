# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Delegation client for the standalone vector-retriever microservice.

The search service delegates ALL vector similarity search to the vector-retriever
microservice (which is vector-DB agnostic and supports Milvus, VDMS, pgvector, ...)
for every backend; search-ms holds no vector DB client of its own. The retriever
returns frame-level scored documents that are then fed into the frame-to-video
aggregation pipeline, so downstream behavior is identical regardless of the
active vector database.
"""

from typing import Any, List, Optional, Tuple

import aiohttp

from src.utils.common import logger, settings


class RetrievedDocument:
    """Lightweight stand-in for a LangChain ``Document``.

    The aggregation pipeline only relies on ``metadata`` (a dict), ``page_content``
    and ``type``, so this minimal object is a drop-in replacement for the documents
    the vector-retriever microservice returns.
    """

    def __init__(self, page_content: str, metadata: dict, doc_type: str = "Document"):
        self.page_content = page_content
        self.metadata = metadata
        self.type = doc_type


def _build_retriever_payload(
    query_request: Any,
    initial_k: int,
    time_range: Optional[Tuple[str, str]],
) -> list[dict]:
    """Build the vector-retriever ``/query`` request body for a single query.

    Supports both text queries (``query``) and image queries (``image_base64``);
    exactly one of the two is expected to be set on ``query_request``. Image
    embedding is performed by the vector-retriever microservice itself, which
    natively accepts a discriminated ``image`` input (``image_base64``/``image_url``).

    Tags are intentionally NOT pushed down; the caller keeps its own tag
    post-filtering to preserve exact "match any" subset semantics across backends.
    """
    item: dict[str, Any] = {
        "query_id": query_request.query_id,
        "top_k": initial_k,
    }

    image_base64 = getattr(query_request, "image_base64", None)
    if image_base64 and image_base64.strip():
        # Accept either a raw base64 string or a full ``data:image/...;base64,``
        # data URL; strip the prefix so any caller can be tolerant.
        raw_image = image_base64.strip()
        if "," in raw_image and raw_image.lower().startswith("data:"):
            raw_image = raw_image.split(",", 1)[1]
        item["image"] = {"type": "image_base64", "image_base64": raw_image}
    else:
        item["query"] = query_request.query

    if time_range is not None:
        start, end = time_range
        item["time_filter"] = {"start": start, "end": end}
    return [item]


async def retrieve_frames_via_service(
    query_request: Any,
    initial_k: int,
    time_range: Optional[Tuple[str, str]] = None,
) -> List[Tuple[RetrievedDocument, float]]:
    """Delegate similarity search to the vector-retriever microservice.

    Args:
        query_request: The incoming query (must expose ``query_id`` and ``query``).
        initial_k: Number of frame candidates to request (maps to retriever ``top_k``).
        time_range: Optional ``(start, end)`` ISO strings to push down as a time filter.

    Returns:
        A list of ``(RetrievedDocument, score)`` tuples ordered by relevance.

    Raises:
        RuntimeError: If the retriever call fails or returns an error payload.
    """
    endpoint = settings.RETRIEVER_ENDPOINT.rstrip("/")
    payload = _build_retriever_payload(query_request, initial_k, time_range)

    timeout = aiohttp.ClientTimeout(total=settings.RETRIEVER_TIMEOUT_SECONDS)
    # trust_env=False so internal service-to-service calls never route through a
    # corporate HTTP proxy.
    async with aiohttp.ClientSession(timeout=timeout, trust_env=False) as session:
        try:
            async with session.post(endpoint, json=payload) as resp:
                body = await resp.json()
                if resp.status != 200:
                    raise RuntimeError(
                        f"vector-retriever returned HTTP {resp.status}: {body}"
                    )
        except aiohttp.ClientError as exc:
            raise RuntimeError(
                f"Failed to reach vector-retriever at {endpoint}: {exc}"
            ) from exc

    errors = body.get("errors") or []
    if errors:
        logger.warning(f"vector-retriever reported per-query errors: {errors}")

    results = body.get("results") or []
    if not results:
        return []

    # Single query in, single result block out.
    items = results[0].get("items") or []
    frames: List[Tuple[RetrievedDocument, float]] = []
    for item in items:
        metadata = dict(item.get("metadata") or {})
        score = float(item.get("score", 0.0))
        page_content = item.get("page_content", "")
        frames.append((RetrievedDocument(page_content, metadata), score))

    logger.info(
        f"vector-retriever returned {len(frames)} frames for query "
        f"{query_request.query_id}"
    )
    return frames
