# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime
import asyncio
import json
import time
from typing import Optional, List, Tuple, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langchain_community.vectorstores.vdms import VDMS

from src.utils.common import logger, settings
from src.utils.time_filters import build_vdms_time_filter
from src.utils.directory_watcher import (
    get_initial_upload_status,
    get_last_updated,
    start_watcher,
)
from pydantic import BaseModel

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
    query_id: str
    query: str
    tags: Optional[list[str]] = None
    time_filter: Optional[TimeRange] = None


def _build_explicit_time_filter(time_filter: Optional[TimeRange], property_name: str = "created_at") -> Optional[dict]:
    """Convert explicit start/end into VDMS constraint dict."""
    if not time_filter or not time_filter.start or not time_filter.end:
        return None
    return {property_name: [">=", time_filter.start, "<=", time_filter.end]}


def _build_tag_filter(tags: Optional[list[str]]) -> Optional[dict]:
    """Build VDMS tag filter using OR-array syntax for multiple tags."""
    if not tags:
        return None
    cleaned = [t.strip() for t in tags if t and t.strip()]
    if not cleaned:
        return None
    if len(cleaned) == 1:
        return {"tags": ["==", cleaned[0]]}

    return {"tags": ["==", cleaned]}


def build_combined_vdms_filter(query_request: QueryRequest) -> Tuple[Optional[dict], Optional[dict]]:
    """Return (vdms_filter, effective_time_filter) combining explicit + parsed time and tag filters."""
    explicit_time_filter = _build_explicit_time_filter(query_request.time_filter)
    parsed_time_filter = build_vdms_time_filter(query_request.query) if not explicit_time_filter else None
    effective_time_filter = explicit_time_filter or parsed_time_filter

    tag_filter = _build_tag_filter(query_request.tags)

    if not effective_time_filter and not tag_filter:
        return None, None

    if effective_time_filter and tag_filter:
        merged_filter = {**effective_time_filter, **tag_filter}
        return merged_filter, effective_time_filter

    return effective_time_filter or tag_filter, effective_time_filter


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
        from src.vdms_retriever.retriever import (
            get_vectordb,
            aggregate_frame_results_to_videos,
        )

        api_start = time.perf_counter()
        logger.info(f"=== SEARCH API CALLED ===")
        logger.info(
            f"Received request: {json.dumps([req.dict() for req in request], indent=2)}"
        )

        db: VDMS = get_vectordb()
        if not db:
            logger.error(
                "VectorDB could not be initialized. Please verify the connection."
            )
            raise HTTPException(
                status_code=500, detail="Some error ocurred at the DataPrep Service."
            )

        async def process_query(query_request):
            """Process a single query request with frame-to-video aggregation."""

            query_start = time.perf_counter()
            logger.info(
                f"Processing query: {query_request.query} (ID: {query_request.query_id})"
            )
            logger.debug(f"Query tags: {query_request.tags}")

            # Build combined VDMS filter from explicit time_filter + tags, with fallback to NLP time parsing
            vdms_filter, applied_time_filter = build_combined_vdms_filter(query_request)
            if applied_time_filter:
                logger.info(f"Applying time filter to VDMS query: {applied_time_filter}")
            else:
                logger.debug("No explicit or derived time filter applied")
            if query_request.tags:
                logger.info(f"Applying tag filter to VDMS query: {query_request.tags}")

            # Get more initial results for aggregation (before filtering)
            initial_k = getattr(
                settings, "AGGREGATION_INITIAL_K", 1000
            )  # Get more frame results before aggregation
            logger.debug(f"Searching with initial_k={initial_k}")

            vdms_start = time.perf_counter()
            docs_with_score: List[Tuple[Any, float]] = db.similarity_search_with_score(
                query_request.query,
                k=initial_k,
                fetch_k=initial_k + 1,  # ensure fetch_k > k for langchain_vdms
                filter=vdms_filter,
                # normalize_distance=True
            )
            vdms_duration_ms = (time.perf_counter() - vdms_start) * 1000
            logger.info(
                f"VDMS similarity search (embedding + retrieval) completed in {vdms_duration_ms:.2f} ms with {len(docs_with_score)} results"
            )

            logger.info(f"Raw search returned {len(docs_with_score)} results")

            # Add relevance scores to metadata
            filter_start = time.perf_counter()
            frame_results = []
            for res, score in docs_with_score:
                res.metadata["relevance_score"] = score

                # Filter by tags if specified
                if query_request.tags:
                    result_tags: list = []
                    if res.metadata.get("tags"):
                        # construct a list of tags from the tag string in results metadata
                        if isinstance(res.metadata["tags"], str):
                            result_tags = res.metadata["tags"].split(",")
                        else:
                            result_tags = res.metadata["tags"]

                    # check if any of the query tags are in the result tags
                    if not set(query_request.tags).intersection(set(result_tags)):
                        logger.debug(
                            f"Filtering out result due to tags: query_tags={query_request.tags}, result_tags={result_tags}"
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
