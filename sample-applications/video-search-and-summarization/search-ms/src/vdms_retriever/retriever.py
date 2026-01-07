# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import math
import time
from typing import List, Dict, Any, Tuple, Optional
from langchain_vdms.vectorstores import VDMS, VDMS_Client

from src.utils.common import settings, logger
from src.vdms_retriever.embedding_wrapper import EmbeddingAPI

DEBUG = False
client = VDMS_Client(settings.VDMS_VDB_HOST, settings.VDMS_VDB_PORT)


# Frame-to-Video Aggregation Configuration
def get_aggregation_config():
    """Get aggregation configuration from settings with fallback defaults."""
    return {
        "strategy": "temporal_segment_clustering",
        "segment_duration_seconds": getattr(settings, 'AGGREGATION_SEGMENT_DURATION', 8),
        "min_temporal_gap_seconds": getattr(settings, 'AGGREGATION_MIN_GAP', 0),
        "final_max_results": getattr(settings, 'AGGREGATION_MAX_RESULTS', 20),
        # Baseline duration is retained for metadata fallbacks only (no length bonus applied)
        "length_normalization": {
            "baseline_duration_seconds": 30,
        },
        "scoring": {
            "qualitative_weights": {
                "max_component": getattr(settings, 'AGGREGATION_QUAL_MAX_WEIGHT', 0.65),
                "top_component": getattr(settings, 'AGGREGATION_QUAL_TOP_WEIGHT', 0.35),
                "top_ratio": getattr(settings, 'AGGREGATION_QUAL_TOP_RATIO', 0.35),
                "top_min_count": getattr(settings, 'AGGREGATION_QUAL_TOP_MIN_COUNT', 2),
                "top_max_count": getattr(settings, 'AGGREGATION_QUAL_TOP_MAX_COUNT', 6),
            },
            "contextual": {
                "sigma_seconds": getattr(settings, 'AGGREGATION_CONTEXT_SIGMA_SECONDS', 40.0),
                "boost_strength": getattr(settings, 'AGGREGATION_CONTEXT_BOOST_STRENGTH', 0.5),
            },
            "context_seek_offset_seconds": getattr(
                settings, 'AGGREGATION_CONTEXT_SEEK_OFFSET_SECONDS', 0.0
            ),
        },
        "filtering": {
            "overlap_filter_enabled": True,
            "min_frame_score_threshold": 0.5
        }
    }


def create_temporal_segments(
    frame_matches: List[Dict],
    segment_duration: int = 8,
    aggregation_config: Optional[Dict[str, Any]] = None,
) -> List[Dict]:
    """
    Create temporal segments from frame matches.
    
    Rationale:
    - 8-second segments provide meaningful context without excessive granularity
    - Addresses the "same video multiple matches" problem
    - Each segment can contain multiple high-scoring frames
    
    Args:
        frame_matches: List of frame match results with metadata
        segment_duration: Duration in seconds for each segment
        
    Returns:
        List of segment dictionaries with grouped frames
    """
    segments = {}
    config = aggregation_config or get_aggregation_config()
    length_cfg = config.get("length_normalization", {})
    baseline_duration = float(length_cfg.get("baseline_duration_seconds", 30) or 30)
    
    logger.debug(f"=== SEGMENTATION DEBUG: Processing {len(frame_matches)} frames ===")
    
    for frame in frame_matches:
        metadata = frame.metadata if hasattr(frame, 'metadata') else frame
        video_id = metadata.get("video_id", "unknown")
        timestamp = metadata.get("timestamp", 0)
        relevance_score = metadata.get("relevance_score", 0)

        raw_duration = metadata.get("video_duration") or metadata.get("video_duration_seconds")
        if raw_duration is not None:
            try:
                raw_duration = float(raw_duration)
            except (TypeError, ValueError):
                raw_duration = None
        if raw_duration is None:
            fps_value = metadata.get("fps")
            total_frames_value = metadata.get("total_frames")
            try:
                if fps_value and total_frames_value:
                    raw_duration = float(total_frames_value) / float(fps_value)
            except (TypeError, ValueError, ZeroDivisionError):
                raw_duration = None
        if raw_duration is None or raw_duration <= 0:
            raw_duration = baseline_duration
        
        segment_id = int(timestamp // segment_duration)
        key = f"{video_id}_seg_{segment_id}"
        segment_start = segment_id * segment_duration
        segment_end = (segment_id + 1) * segment_duration
        
        logger.debug(f"Frame at {timestamp}s (score={relevance_score:.4f}) → Segment [{segment_start}-{segment_end}s] in video {video_id[:8]}...")
        
        if key not in segments:
            segments[key] = {
                "video_id": video_id,
                "segment_start": segment_start,
                "segment_end": segment_end,
                "frames": [],
                "video_duration": raw_duration,
            }
        
        segments[key]["frames"].append(frame)
    
    # Log segment summaries
    for key, segment in segments.items():
        frame_scores = []
        for frame in segment["frames"]:
            frame_metadata = frame.metadata if hasattr(frame, 'metadata') else frame
            frame_scores.append(frame_metadata.get('relevance_score', 0))
        
        logger.debug(f"Segment {key}: {len(segment['frames'])} frames, scores: {[f'{s:.4f}' for s in sorted(frame_scores, reverse=True)]}")
    
    return list(segments.values())


def calculate_segment_score(
    segment: Dict,
    global_max_score: float,
    global_best_frame: Optional[Dict[str, Any]] = None,
    aggregation_config: Optional[Dict[str, Any]] = None
) -> Dict:
    """
    Calculate segment score with extreme quality focus.
    
    Simple algorithm that prioritizes the highest individual frame scores
    over quantity of frames. Uses a pure quality-first approach.
    
    Args:
        segment: Segment dictionary with frames and metadata
        global_max_score: Highest relevance score observed across all frame results
        
    Returns:
        Dictionary with detailed scoring breakdown
    """
    config = aggregation_config or get_aggregation_config()
    frames = segment["frames"]
    video_duration = segment["video_duration"]
    
    # Extract relevance scores
    relevance_scores = []
    for frame in frames:
        if hasattr(frame, 'metadata') and 'relevance_score' in frame.metadata:
            relevance_scores.append(frame.metadata['relevance_score'])
        elif isinstance(frame, dict) and 'relevance_score' in frame:
            relevance_scores.append(frame['relevance_score'])
        else:
            relevance_scores.append(0.1)  # Default score

    if not relevance_scores:
        relevance_scores = [0.1]
    
    # Primary score: Best frame in segment  
    segment_max_score = max(relevance_scores)

    # Calculate average for reference
    segment_avg_score = sum(relevance_scores) / len(relevance_scores) if relevance_scores else 0.0

    # Determine top-N average for sustained quality component
    scoring_config = config.get("scoring", {})
    qualitative_cfg = scoring_config.get("qualitative_weights", {})
    top_ratio = float(qualitative_cfg.get("top_ratio", 0.35) or 0.35)
    top_min_count = int(qualitative_cfg.get("top_min_count", 2) or 2)
    top_max_count = int(qualitative_cfg.get("top_max_count", 6) or 6)
    max_weight = float(qualitative_cfg.get("max_component", 0.65))
    top_weight = float(qualitative_cfg.get("top_component", 0.35))

    weight_total = max(max_weight + top_weight, 1e-6)
    max_weight /= weight_total
    top_weight /= weight_total

    sorted_scores = sorted(relevance_scores, reverse=True)
    dynamic_top_count = max(top_min_count, int(math.ceil(len(sorted_scores) * top_ratio)))
    if top_max_count > 0:
        dynamic_top_count = min(dynamic_top_count, top_max_count)
    dynamic_top_count = min(dynamic_top_count, len(sorted_scores)) if sorted_scores else 0

    if dynamic_top_count > 0:
        top_n_avg = sum(sorted_scores[:dynamic_top_count]) / dynamic_top_count
    else:
        top_n_avg = segment_max_score

    base_quality = (segment_max_score * max_weight) + (top_n_avg * top_weight)

    # Determine best frame timestamp for contextual proximity
    segment_best_timestamp: Optional[float] = None
    best_frame_score = -1.0
    for frame in frames:
        frame_metadata = frame.metadata if hasattr(frame, 'metadata') else frame
        timestamp = frame_metadata.get("timestamp")
        score = frame_metadata.get('relevance_score', 0.0)
        if score > best_frame_score:
            best_frame_score = score
            segment_best_timestamp = timestamp

    contextual_cfg = scoring_config.get("contextual", {})
    sigma_seconds = float(contextual_cfg.get("sigma_seconds", 40.0) or 40.0)
    boost_strength = float(contextual_cfg.get("boost_strength", 0.5))

    context_weight = 0.0
    global_peak_timestamp = None
    if isinstance(global_best_frame, dict):
        global_peak_timestamp = global_best_frame.get("timestamp")

    if (
        segment_best_timestamp is not None
        and global_peak_timestamp is not None
        and sigma_seconds > 0
    ):
        distance = abs(float(segment_best_timestamp) - float(global_peak_timestamp))
        context_weight = math.exp(-((distance / sigma_seconds) ** 2))

    final_score = base_quality * (1.0 + boost_strength * context_weight)

    return {
        "score": final_score,
        "max_frame_score": segment_max_score,
        "top_n_avg_score": top_n_avg,
        "top_n_frame_count": dynamic_top_count,
        "avg_frame_score": segment_avg_score,
        "quality_score": base_quality,
        "frame_count": len(frames),
        "contextual_weight": context_weight,
        "contextual_boost_factor": boost_strength,
        "contextual_sigma_seconds": sigma_seconds,
        "segment_best_timestamp": segment_best_timestamp,
        "global_peak_timestamp": global_peak_timestamp,
    }


def determine_seek_point(segment: Dict, context_offset: float = 1.5) -> Dict:
    """
    Determine optimal video seek point for UI playback.
    
    Strategy: Find best frame, then seek slightly before for context
    
    Args:
        segment: Segment dictionary with frames
        context_offset: Seconds to seek before best frame for context
        
    Returns:
        Dictionary with seek point information
    """
    frames = segment["frames"]
    
    # Find highest scoring frame
    best_frame = None
    best_score = -1
    
    for frame in frames:
        frame_metadata = frame.metadata if hasattr(frame, 'metadata') else frame
        score = frame_metadata.get('relevance_score', 0)
        if score > best_score:
            best_score = score
            best_frame = frame
    
    if not best_frame:
        best_frame = frames[0] if frames else None
    
    if best_frame:
        best_frame_metadata = best_frame.metadata if hasattr(best_frame, 'metadata') else best_frame
        best_timestamp = best_frame_metadata.get("timestamp", segment["segment_start"])
    else:
        best_timestamp = segment["segment_start"]
    
    # Seek point: context_offset seconds before best frame for context
    seek_timestamp = max(0, best_timestamp - context_offset)
    
    # Ensure seek point is within segment bounds
    seek_timestamp = max(segment["segment_start"], seek_timestamp)
    
    return {
        "seek_timestamp": seek_timestamp,
        "best_frame_timestamp": best_timestamp,
        "segment_start": segment["segment_start"],
        "segment_end": segment["segment_end"]
    }


def apply_temporal_overlap_filtering(segments: List[Dict], min_gap_seconds: int = 5) -> List[Dict]:
    """
    Filter temporally overlapping segments from same video.
    
    Inspired by Metro AI Suite overlap_filter_thresh_sec.
    Addresses: "matches very close together don't make sense"
    
    Args:
        segments: List of scored segments
        min_gap_seconds: Minimum gap in seconds between segments from same video
        
    Returns:
        Filtered list of segments
    """
    # Sort by score (highest first)
    sorted_segments = sorted(segments, key=lambda x: x.get("final_score", 0), reverse=True)
    
    filtered_segments = []
    
    for segment in sorted_segments:
        should_keep = True

        for kept_segment in filtered_segments:
            if segment["video_id"] != kept_segment["video_id"]:
                continue

            segment_start = segment["segment_start"]
            segment_end = segment["segment_end"]
            kept_start = kept_segment["segment_start"]
            kept_end = kept_segment["segment_end"]

            segments_are_separated = (
                segment_end + min_gap_seconds <= kept_start
                or kept_end + min_gap_seconds <= segment_start
            )

            if not segments_are_separated:
                should_keep = False
                break

        if should_keep:
            filtered_segments.append(segment)
    
    return filtered_segments


def aggregate_frame_results_to_videos(frame_results: List[Any], max_results: int = 20) -> Tuple[List[Dict], Dict[str, float]]:
    """
    Complete aggregation pipeline for frame-to-video conversion.
    
    This is the main function that implements the temporal segment clustering strategy
    to convert individual frame search results into meaningful video segment results.
    
    Args:
        frame_results: List of frame-level search results from VDMS
        max_results: Maximum number of video results to return
        
    Returns:
        List of aggregated video segment results with seek points and metadata
    """
    start_time = time.perf_counter()
    config = get_aggregation_config()
    
    if not frame_results:
        return [], {
            "total_frame_matches": 0,
            "segments_created": 0,
            "segments_after_filtering": 0,
            "final_results": 0,
            "processing_time_ms": 0.0,
            "segmentation_time_ms": 0.0,
            "scoring_time_ms": 0.0,
            "filtering_time_ms": 0.0,
            "formatting_time_ms": 0.0,
        }
    
    logger.debug(f"Starting aggregation of {len(frame_results)} frame results")

    # Calculate global maximum relevance score across all frames for contextual comparisons
    global_scores: List[float] = []
    frame_info_for_debug = []
    global_best_frame_metadata: Optional[Dict[str, Any]] = None
    for frame in frame_results:
        frame_metadata = frame.metadata if hasattr(frame, 'metadata') else frame
        score = frame_metadata.get('relevance_score') if isinstance(frame_metadata, dict) else None
        if score is not None:
            global_scores.append(score)
            # Collect debug info
            video_id = frame_metadata.get('video_id', 'unknown')
            timestamp = frame_metadata.get('timestamp', 0)
            frame_info_for_debug.append((video_id[:8] + "...", timestamp, score))

            if (
                global_best_frame_metadata is None
                or score > global_best_frame_metadata.get('relevance_score', float('-inf'))
            ):
                global_best_frame_metadata = {
                    "video_id": frame_metadata.get('video_id'),
                    "timestamp": timestamp,
                    "relevance_score": score,
                }

    if global_best_frame_metadata is not None:
        global_max_score = global_best_frame_metadata.get('relevance_score', 0.1)
    else:
        global_max_score = max(global_scores) if global_scores else 0.1
    
    # Debug log initial frame distribution
    logger.debug(f"=== FRAME DISTRIBUTION DEBUG ===")
    logger.debug(f"Global max score: {global_max_score:.4f}")
    logger.debug(f"Top 10 frame scores: {sorted(global_scores, reverse=True)[:10]}")
    
    # Group frames by video for debug
    video_frame_counts = {}
    for video_id, timestamp, score in frame_info_for_debug:
        if video_id not in video_frame_counts:
            video_frame_counts[video_id] = []
        video_frame_counts[video_id].append((timestamp, score))
    
    for video_id, frames in video_frame_counts.items():
        logger.debug(f"Video {video_id}: {len(frames)} frames, timestamps: {[f'{t}s' for t, _ in sorted(frames)[:5]]}{'...' if len(frames) > 5 else ''}")
    
    # Step 1: Create temporal segments
    segment_duration = config["segment_duration_seconds"]
    segmentation_start = time.perf_counter()
    segments = create_temporal_segments(frame_results, segment_duration, config)
    segmentation_time_ms = (time.perf_counter() - segmentation_start) * 1000
    logger.debug(f"Created {len(segments)} temporal segments")
    
    # Step 2: Score all segments with length normalization
    scoring_start = time.perf_counter()
    scored_segments = []
    seek_offset = float(config["scoring"].get("context_seek_offset_seconds", 0.0))

    logger.debug(f"=== SCORING DEBUG: Scoring {len(segments)} segments ===")
    
    for segment in segments:
        # Extract frame scores for logging
        frame_scores = []
        for frame in segment["frames"]:
            frame_metadata = frame.metadata if hasattr(frame, 'metadata') else frame
            timestamp = frame_metadata.get("timestamp", 0)
            score = frame_metadata.get('relevance_score', 0)
            frame_scores.append((timestamp, score))
        
        score_data = calculate_segment_score(
            segment,
            global_max_score,
            global_best_frame_metadata,
            config,
        )
        seek_data = determine_seek_point(segment, context_offset=seek_offset)
        
        # Get best frame for metadata
        best_frame = None
        best_score = -1
        for frame in segment["frames"]:
            frame_metadata = frame.metadata if hasattr(frame, 'metadata') else frame
            score = frame_metadata.get('relevance_score', 0)
            if score > best_score:
                best_score = score
                best_frame = frame
        
        best_frame_metadata = best_frame.metadata if (best_frame and hasattr(best_frame, 'metadata')) else best_frame
        if not best_frame_metadata:
            best_frame_metadata = {}
        
        # Debug log for this segment
        segment_key = f"{segment['video_id'][:8]}..._[{segment['segment_start']}-{segment['segment_end']}s]"
        logger.debug(f"Segment {segment_key}:")
        logger.debug(f"  Frame scores: {[(f'{ts}s', f'{sc:.4f}') for ts, sc in sorted(frame_scores)]}")
        logger.debug(
            "  Score breakdown: max=%.4f, top_n_avg=%.4f (count=%d), "
            "base_quality=%.4f, context_weight=%.3f, final=%.4f",
            score_data['max_frame_score'],
            score_data['top_n_avg_score'],
            score_data['top_n_frame_count'],
            score_data['quality_score'],
            score_data['contextual_weight'],
            score_data['score'],
        )
        contextual_weight = score_data.get('contextual_weight')
        boost_factor = score_data.get('contextual_boost_factor')
        logger.debug(
            "  Final score: %.4f (context_weight=%s, boost=%.2f)",
            score_data['score'],
            f"{contextual_weight:.3f}" if contextual_weight is not None else "N/A",
            boost_factor if boost_factor is not None else 0.0,
        )
        
        # Store frame scores for API response
        formatted_frame_scores = [(f'{ts}s', f'{sc:.4f}') for ts, sc in sorted(frame_scores)]
        
        scored_segments.append({
            **segment,
            "score_breakdown": score_data,
            "seek_info": seek_data,
            "final_score": score_data["score"],
            "best_frame_metadata": best_frame_metadata,
            "frame_scores": formatted_frame_scores
        })
    
    scoring_time_ms = (time.perf_counter() - scoring_start) * 1000
    logger.debug(f"Scored {len(scored_segments)} segments")
    
    # Step 2.5: Normalize scores to [0, 1] range
    if scored_segments:
        raw_scores = [seg["final_score"] for seg in scored_segments]
        min_score = min(raw_scores)
        max_score = max(raw_scores)
        score_range = max_score - min_score
        
        if score_range > 0:
            for seg in scored_segments:
                raw_score = seg["final_score"]
                normalized_score = (raw_score - min_score) / score_range
                seg["score_breakdown"]["raw_score"] = raw_score
                seg["score_breakdown"]["score"] = normalized_score
                seg["final_score"] = normalized_score
            logger.debug(f"Normalized scores: range [{min_score:.4f}, {max_score:.4f}] → [0.0, 1.0]")
        else:
            # All scores identical, set to 1.0
            for seg in scored_segments:
                seg["score_breakdown"]["raw_score"] = seg["final_score"]
                seg["score_breakdown"]["score"] = 1.0
                seg["final_score"] = 1.0
            logger.debug(f"All scores identical ({max_score:.4f}), normalized to 1.0")
    
    # Step 3: Apply temporal overlap filtering
    filtering_start = time.perf_counter()
    if config["filtering"]["overlap_filter_enabled"]:
        min_gap = config["min_temporal_gap_seconds"]
        filtered_segments = apply_temporal_overlap_filtering(scored_segments, min_gap)
        logger.debug(f"After temporal filtering: {len(filtered_segments)} segments")
    else:
        filtered_segments = scored_segments
    filtering_time_ms = (time.perf_counter() - filtering_start) * 1000
    
    # Step 4: Final ranking and top-K selection
    final_results = sorted(
        filtered_segments, 
        key=lambda x: x["final_score"], 
        reverse=True
    )[:max_results]
    
    # Debug log final ranking
    logger.debug(f"=== FINAL RANKING DEBUG: Top {len(final_results)} results ===")
    for i, result in enumerate(final_results[:10]):  # Show top 10
        segment_key = f"{result['video_id'][:8]}..._[{result['segment_start']}-{result['segment_end']}s]"
        logger.debug(f"Rank #{i+1}: {segment_key} → Final Score: {result['final_score']:.4f}")
    
    if len(final_results) > 10:
        logger.debug(f"... and {len(final_results) - 10} more results")
    
    # Step 5: Format results for API response
    formatting_start = time.perf_counter()
    formatted_results = []
    for result in final_results:
        best_frame_meta = result.get("best_frame_metadata", {})
        
        # Extract video URLs from any frame metadata (all frames in same video have same URLs)
        video_url = ""
        video_rel_url = ""
        
        # Try to get URLs from best frame first
        if best_frame_meta.get("video_url"):
            video_url = best_frame_meta.get("video_url", "")
            video_rel_url = best_frame_meta.get("video_rel_url", "")
        else:
            # Fallback: get URLs from any frame in the segment
            frames = result.get("frames", [])
            for frame in frames:
                frame_metadata = frame.metadata if hasattr(frame, 'metadata') else frame
                if frame_metadata.get("video_url"):
                    video_url = frame_metadata.get("video_url", "")
                    video_rel_url = frame_metadata.get("video_rel_url", "")
                    break
        
        created_at = best_frame_meta.get("created_at")
        if not created_at:
            # VDMS can store datetime as an object with the actual value in _date
            created_at = best_frame_meta.get("date_time", {}).get("_date", "")

        formatted_result = {
            "video_id": result["video_id"],
            "video_url": video_url,
            "video_rel_url": video_rel_url,
            "video_duration": result.get("video_duration"),
            "seek_timestamp": result["seek_info"]["seek_timestamp"],
            "segment_start": result["segment_start"],
            "segment_end": result["segment_end"],
            "relevance_score": result["final_score"],
            "score_breakdown": result["score_breakdown"],
            "best_frame_info": {
                "timestamp": result["seek_info"]["best_frame_timestamp"],
                "frame_number": best_frame_meta.get("frame_number", 0),
                "frame_type": best_frame_meta.get("frame_type", "full_frame"),
                "detection_confidence": best_frame_meta.get("detection_confidence"),
                "detected_label": best_frame_meta.get("detected_label")
            },
            "video_metadata": {
                "duration": result["video_duration"],
                "fps": best_frame_meta.get("fps", 30),
                "tags": best_frame_meta.get("tags", "").split(",") if best_frame_meta.get("tags") else [],
                "created_at": created_at,
                "upload_timestamp": best_frame_meta.get("date_time", {}).get("_date", ""),
                "bucket_name": best_frame_meta.get("bucket_name", "")
            },
            "frame_scores": result.get("frame_scores", [])
        }
        formatted_results.append(formatted_result)
    
    formatting_time_ms = (time.perf_counter() - formatting_start) * 1000
    processing_time = (time.perf_counter() - start_time) * 1000  # Convert to milliseconds

    logger.info(
        "Aggregation complete: %d frames -> %d video segments in %.1fms (segmentation=%.2fms, scoring=%.2fms, filtering=%.2fms, formatting=%.2fms)",
        len(frame_results),
        len(final_results),
        processing_time,
        segmentation_time_ms,
        scoring_time_ms,
        filtering_time_ms,
        formatting_time_ms,
    )
    
    return formatted_results, {
        "total_frame_matches": len(frame_results),
        "segments_created": len(segments),
        "segments_after_filtering": len(filtered_segments),
        "final_results": len(final_results),
        "processing_time_ms": processing_time,
        "segmentation_time_ms": segmentation_time_ms,
        "scoring_time_ms": scoring_time_ms,
        "filtering_time_ms": filtering_time_ms,
        "formatting_time_ms": formatting_time_ms,
    }


def get_vectordb() -> VDMS:
    """
    Initializes and returns a vector database based on the specified configuration.
    Depending on the configuration, it uses either CLIP embeddings, a HuggingFace endpoint for embeddings,
    or a default HuggingFace BGE embeddings model.
    Returns:
        tuple: The vector database instance
    """

    embeddings = EmbeddingAPI(
        api_url=settings.EMBEDDINGS_ENDPOINT,
        model_name=settings.EMBEDDINGS_MODEL_NAME,
    )

    vector_dimensions = embeddings.get_embedding_length()

    vector_db = VDMS(
        client=client,
        embedding=embeddings,
        collection_name=settings.INDEX_NAME,
        distance_strategy=settings.DISTANCE_STRATEGY,
        embedding_dimensions=vector_dimensions,
        engine=settings.SEARCH_ENGINE,
    )

    return vector_db
