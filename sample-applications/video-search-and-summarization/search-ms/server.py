# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime
import asyncio
import json
import time
from typing import Optional, List, Tuple, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.utils.common import logger, settings
from src.utils.retriever_delegate import retrieve_frames_via_service
from src.utils.time_filters import parse_time_range
from src.utils.directory_watcher import (
    get_initial_upload_status,
    get_last_updated,
    start_watcher,
)
from pydantic import BaseModel, Field, AliasChoices, ConfigDict

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    import threading

    watcher_thread = threading.Thread(target=start_watcher)
    watcher_thread.daemon = True
    watcher_thread.start()


class TimeRange(BaseModel):
    start: str
    end: str


class QueryRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    query_id: str = Field(
        validation_alias=AliasChoices("query_id", "queryId")
    )
    query: str
    tags: Optional[list[str] | str] = None
    time_filter: Optional[TimeRange] = Field(
        default=None,
        validation_alias=AliasChoices("time_filter", "timeFilter"),
    )


def _normalize_tags(tags: Optional[list[str] | str]) -> list[str]:
    """Normalize tags from list/string input and trim whitespace."""
    if not tags:
        return []

    raw_tags = tags.split(",") if isinstance(tags, str) else tags
    return [tag.strip() for tag in raw_tags if isinstance(tag, str) and tag.strip()]


def resolve_time_range(query_request: "QueryRequest") -> Optional[Tuple[str, str]]:
    """Resolve an (start, end) ISO time range for the query, backend-agnostic.

    Uses the explicit ``time_filter`` when provided, otherwise falls back to
    natural-language time parsing of the query text. The range is pushed down to
    the vector-retriever microservice, which applies it against the stored
    ``created_at`` metadata.
    """
    explicit = query_request.time_filter
    if explicit and explicit.start and explicit.end:
        return explicit.start, explicit.end

    start, end = parse_time_range(query_request.query)
    if start and end:
        return start.isoformat(), end.isoformat()
    return None


def format_aggregated_results(aggregated_videos: list[dict]) -> list[dict]:
    """Convert aggregated video search results into API response documents."""

    formatted_results: list[dict] = []

    for rank, video_result in enumerate(aggregated_videos, 1):
        raw_video_metadata = video_result.get("video_metadata") or {}
        video_metadata = dict(raw_video_metadata)
        duration = video_result.get("video_duration")

        if duration is not None and "duration" not in video_metadata:
            video_metadata["duration"] = duration

        tags_value = video_metadata.get("tags", [])
        if isinstance(tags_value, str):
            tags_list = [tag.strip() for tag in tags_value.split(",") if tag.strip()]
            video_metadata["tags"] = tags_list
        else:
            tags_list = tags_value or []

        fps_value = video_metadata.get("fps", video_result.get("fps"))
        video_metadata["fps"] = fps_value

        best_frame_info = video_result.get("best_frame_info") or {}
        created_at_value = video_metadata.get("created_at") or video_metadata.get("upload_timestamp", "")

        metadata = {
            "video_id": video_result.get("video_id"),
            "video_url": video_result.get("video_url", ""),
            "video_rel_url": video_result.get("video_rel_url", ""),
            "timestamp": video_result.get("seek_timestamp"),
            "relevance_score": video_result.get("relevance_score"),
            "tags": ",".join(tags_list) if tags_list else "",
            "bucket_name": video_metadata.get("bucket_name", ""),
            "date_time": video_metadata.get("upload_timestamp", ""),
            "segment_start": video_result.get("segment_start"),
            "segment_end": video_result.get("segment_end"),
            "seek_timestamp": video_result.get("seek_timestamp"),
            "score_breakdown": video_result.get("score_breakdown"),
            "best_frame_info": best_frame_info,
            "created_at": created_at_value,
            "aggregated": True,
            "video_metadata": video_metadata,
            "rank": rank,
        }

        formatted_results.append(
            {
                "id": None,
                "metadata": metadata,
                "page_content": (
                    f"Video segment from {video_result.get('segment_start')}s to {video_result.get('segment_end')}s, "
                    f"seeking to {video_result.get('seek_timestamp')}s"
                ),
                "type": "Document",
                "frame_scores": video_result.get("frame_scores", [])
            }
        )

    return formatted_results


@app.post("/query")
async def query_endpoint(request: list[QueryRequest]):
    try:
        from src.vdms_retriever.retriever import aggregate_frame_results_to_videos

        api_start = time.perf_counter()
        logger.info(f"=== SEARCH API CALLED ===")
        logger.info(
            f"Received request: {json.dumps([req.dict() for req in request], indent=2)}"
        )

        # All vector similarity search is delegated to the vector-retriever
        # microservice (vector-DB agnostic: VDMS, Milvus, ...). This service owns
        # only query orchestration and frame-to-video aggregation.
        if not settings.RETRIEVER_ENDPOINT:
            logger.error(
                "RETRIEVER_ENDPOINT is not configured; the vector-retriever "
                "microservice is required for search."
            )
            raise HTTPException(
                status_code=500,
                detail="Search backend is not configured (RETRIEVER_ENDPOINT missing).",
            )
        logger.info(
            f"Delegating similarity search to vector-retriever at {settings.RETRIEVER_ENDPOINT}"
        )

        async def process_query(query_request):
            """Process a single query request with frame-to-video aggregation."""

            query_start = time.perf_counter()
            query_tags = _normalize_tags(query_request.tags)
            query_tags_set = set(query_tags)
            logger.info(
                f"Processing query: {query_request.query} (ID: {query_request.query_id})"
            )
            logger.debug(f"Query tags: {query_tags}")

            # Resolve an explicit/NLP-derived time range to push to the retriever.
            time_range = resolve_time_range(query_request)
            if time_range:
                logger.info(f"Applying time filter to search: {time_range}")
            else:
                logger.debug("No explicit or derived time filter applied")
            if query_tags_set:
                logger.info(f"Applying tag filter to search results: {query_tags}")

            # Get more initial results for aggregation (before filtering)
            initial_k = getattr(
                settings, "AGGREGATION_INITIAL_K", 1000
            )  # Get more frame results before aggregation
            logger.debug(f"Searching with initial_k={initial_k}")

            retrieval_start = time.perf_counter()
            try:
                docs_with_score: List[Tuple[Any, float]] = (
                    await retrieve_frames_via_service(
                        query_request,
                        initial_k=initial_k,
                        time_range=time_range,
                    )
                )
            except Exception as retriever_error:
                logger.error(
                    f"vector-retriever delegation failed for query {query_request.query_id}: {retriever_error}"
                )
                raise HTTPException(
                    status_code=502,
                    detail="Failed to retrieve results from the vector-retriever service.",
                )
            retrieval_duration_ms = (time.perf_counter() - retrieval_start) * 1000
            logger.info(
                f"vector-retriever search (embedding + retrieval) completed in {retrieval_duration_ms:.2f} ms with {len(docs_with_score)} results"
            )

            logger.info(f"Raw search returned {len(docs_with_score)} results")

            # Add relevance scores to metadata
            filter_start = time.perf_counter()
            frame_results = []
            for res, score in docs_with_score:
                res.metadata["relevance_score"] = score

                # Filter by tags if specified
                if query_tags_set:
                    result_tags = _normalize_tags(res.metadata.get("tags"))

                    # Keep results when they match any requested tag (subset semantics).
                    if not query_tags_set.intersection(set(result_tags)):
                        logger.debug(
                            f"Filtering out result due to tags: query_tags={query_tags}, result_tags={result_tags}"
                        )
                        continue

                frame_results.append(res)

            filtering_duration_ms = (time.perf_counter() - filter_start) * 1000
            logger.info(
                f"Filtering and metadata enrichment finished in {filtering_duration_ms:.2f} ms. Remaining results: {len(frame_results)}"
            )

            logger.info(f"After tag filtering: {len(frame_results)} results")

            # Apply frame-to-video aggregation if enabled
            if getattr(settings, "AGGREGATION_ENABLED", True) and frame_results:
                try:
                    logger.debug("Starting aggregation process")
                    max_results = getattr(settings, "AGGREGATION_MAX_RESULTS", 20)
                    aggregation_start = time.perf_counter()
                    aggregated_videos, aggregation_stats = (
                        aggregate_frame_results_to_videos(
                            frame_results, max_results=max_results
                        )
                    )
                    aggregation_duration_ms = (
                        time.perf_counter() - aggregation_start
                    ) * 1000
                    logger.info(
                        f"Aggregation pipeline completed in {aggregation_duration_ms:.2f} ms (reported {aggregation_stats.get('processing_time_ms', 0):.2f} ms)"
                    )

                    logger.info(
                        f"Aggregation completed: {len(aggregated_videos)} videos"
                    )
                    logger.debug(f"Aggregation stats: {aggregation_stats}")

                    # Convert aggregated results back to langchain document format for API compatibility
                    converted_results = format_aggregated_results(aggregated_videos)

                    result = {
                        "query_id": query_request.query_id,
                        "results": converted_results,
                        "aggregation_stats": aggregation_stats,
                    }

                    logger.info(
                        f"Returning {len(converted_results)} aggregated results for query {query_request.query_id}"
                    )
                    total_query_duration_ms = (time.perf_counter() - query_start) * 1000
                    logger.info(
                        f"Total processing time for query {query_request.query_id}: {total_query_duration_ms:.2f} ms"
                    )
                    return result
                except Exception as e:
                    aggregation_duration_ms = (
                        (time.perf_counter() - aggregation_start) * 1000
                        if "aggregation_start" in locals()
                        else 0
                    )
                    logger.error(
                        f"Error in aggregation for query {query_request.query_id}: {str(e)}"
                    )
                    logger.info(
                        f"Aggregation failed after {aggregation_duration_ms:.2f} ms; falling back to frame results"
                    )
                    import traceback

                    traceback.print_exc()
                    # Fallback to original frame results if aggregation fails
                    fallback_results = []
                    for res in frame_results[:20]:
                        fallback_result = {
                            "id": None,
                            "metadata": dict(res.metadata),
                            "page_content": res.page_content,
                            "type": res.type if hasattr(res, "type") else "Document",
                        }
                        fallback_results.append(fallback_result)

                    result = {
                        "query_id": query_request.query_id,
                        "results": fallback_results,
                        "aggregation_stats": {
                            "aggregation_failed": True,
                            "error": str(e),
                            "fallback_frame_count": len(fallback_results),
                        },
                    }
                    logger.info(
                        f"Returning {len(fallback_results)} fallback results for query {query_request.query_id}"
                    )
                    total_query_duration_ms = (time.perf_counter() - query_start) * 1000
                    logger.info(
                        f"Total processing time for query {query_request.query_id}: {total_query_duration_ms:.2f} ms"
                    )
                    return result
            else:
                # Return original frame results if aggregation is disabled
                converted_results = []
                for res in frame_results[:20]:
                    converted_result = {
                        "id": None,
                        "metadata": dict(res.metadata),
                        "page_content": res.page_content,
                        "type": res.type if hasattr(res, "type") else "Document",
                    }
                    converted_results.append(converted_result)

                result = {
                    "query_id": query_request.query_id,
                    "results": converted_results,
                    "aggregation_stats": {
                        "aggregation_enabled": False,
                        "frame_count": len(converted_results),
                    },
                }
                logger.info(
                    f"Returning {len(converted_results)} frame results for query {query_request.query_id} (aggregation disabled)"
                )
                total_query_duration_ms = (time.perf_counter() - query_start) * 1000
                logger.info(
                    f"Total processing time for query {query_request.query_id}: {total_query_duration_ms:.2f} ms"
                )
                return result

        async def process_batch(batch):
            tasks = [process_query(query_request) for query_request in batch]
            return await asyncio.gather(*tasks)

        async def process_requests(requests):
            batch_size = 20
            results = []
            for i in range(0, len(requests), batch_size):
                batch = requests[i : i + batch_size]
                batch_results = await process_batch(batch)
                results.extend(batch_results)
            return results

        results = await process_requests(request)

        logger.info(f"=== FINAL API RESPONSE ===")
        logger.info(f"Total result groups: {len(results)}")
        for i, result in enumerate(results):
            logger.info(
                f"Result group {i}: query_id={result.get('query_id')}, results_count={len(result.get('results', []))}"
            )

        final_response = {"results": results}
        logger.info(
            f"Response structure: {json.dumps(final_response, indent=2, default=str)}"
        )
        total_api_duration_ms = (time.perf_counter() - api_start) * 1000
        logger.info(
            f"Total /query processing time: {total_api_duration_ms:.2f} ms across {len(request)} queries"
        )

        return final_response

    except HTTPException:
        raise

    except KeyError as e:
        if str(e) == "'entities'":
            logger.error(f"KeyError in query_endpoint: {str(e)}")
            logger.error(
                f"No entities were found. Perhaps, no index is created or no \
                         embeddings have been generated yet in the index: {settings.INDEX_NAME}"
            )
            raise HTTPException(status_code=404, detail=f"No entities were found.")
        else:
            logger.error(f"KeyError in query_endpoint: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="Some error ocurred while running the search query.",
            )

    except Exception as e:
        import traceback

        traceback.print_exc()
        logger.error(f"Error in query_endpoint: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Some error ocurred at the DataPrep Service."
        )


@app.get("/watcher-last-updated")
async def watcher_last_updated():
    try:
        last_updated = get_last_updated()
        return {"last_updated": last_updated}
    except Exception as e:
        logger.error(f"Error in watcher_last_updated: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Simple health check endpoint to verify the service is running."""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.get("/initial-upload-status")
async def initial_upload_status():
    try:
        logger.debug("Querying initial upload status")
        status = get_initial_upload_status()
        logger.debug(f"Initial upload status: {status}")
        return {"status": status}
    except Exception as e:
        logger.error(f"Error in initial_upload_status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
