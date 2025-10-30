# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import time
from typing import List, Dict, Any, Tuple, Optional
from langchain_community.vectorstores.vdms import VDMS, VDMS_Client

from src.utils.common import settings, logger
from src.vdms_retriever.embedding_wrapper import vCLIPEmbeddingsWrapper

DEBUG = False
client = VDMS_Client(settings.VDMS_VDB_HOST, settings.VDMS_VDB_PORT)


# Frame-to-Video Aggregation Configuration
def get_aggregation_config():
    """Get aggregation configuration from settings with fallback defaults."""
    return {
        "strategy": "temporal_segment_clustering",
        "segment_duration_seconds": getattr(settings, 'AGGREGATION_SEGMENT_DURATION', 8),
        "min_temporal_gap_seconds": getattr(settings, 'AGGREGATION_MIN_GAP', 5),
        "final_max_results": getattr(settings, 'AGGREGATION_MAX_RESULTS', 20),
        "length_normalization": {
            "enabled": True,
            "baseline_duration_seconds": 30,
            "slowdown_duration_seconds": 120,
            "short_video_bonus_scale": 0.1,
            "min_factor": 0.75,
            "max_factor": 1.1,
        },
        "scoring": {
            "density_bonus_cap": getattr(settings, 'AGGREGATION_DENSITY_BONUS_CAP', 1.0),
            "density_bonus_per_frame": getattr(settings, 'AGGREGATION_DENSITY_BONUS_PER_FRAME', 0.05),
            "context_seek_offset_seconds": 1.5,
            "frame_count_bonus": {
                "enabled": getattr(settings, 'AGGREGATION_FRAME_COUNT_BONUS_ENABLED', True),
                "per_frame": getattr(settings, 'AGGREGATION_FRAME_COUNT_BONUS_PER_FRAME', 0.0),
                "cap": getattr(settings, 'AGGREGATION_FRAME_COUNT_BONUS_CAP', 0.5),
                "reference_count": getattr(settings, 'AGGREGATION_FRAME_COUNT_REFERENCE', 10)
            }
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
    
    for frame in frame_matches:
        metadata = frame.metadata if hasattr(frame, 'metadata') else frame
        video_id = metadata.get("video_id", "unknown")
        timestamp = metadata.get("timestamp", 0)

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
        
        if key not in segments:
            segments[key] = {
                "video_id": video_id,
                "segment_start": segment_id * segment_duration,
                "segment_end": (segment_id + 1) * segment_duration,
                "frames": [],
                "video_duration": raw_duration,
            }
        
        segments[key]["frames"].append(frame)
    
    return list(segments.values())


def calculate_segment_score(segment: Dict, global_max_score: float) -> Dict:
    """
    Calculate length-normalized segment score.
    
    Addresses length bias problem:
    - Long videos (5 min) vs short videos (30s) fair comparison
    - Density-based scoring rewards concentrated relevance
    
    Args:
        segment: Segment dictionary with frames and metadata
        global_max_score: Highest relevance score observed across all frame results
        
    Returns:
        Dictionary with detailed scoring breakdown
    """
    config = get_aggregation_config()
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
    
    score_config = config["scoring"]

    # Primary score: Best frame in segment
    segment_max_score = max(relevance_scores)

    # Global max score across all frame results (fallback to segment max if unavailable)
    max_score = global_max_score if global_max_score else segment_max_score
    
    # Density bonus: Multiple high-scoring frames in segment
    high_confidence_frames = [score for score in relevance_scores if score > 0.8*max_score]
    density_bonus_cap = score_config.get("density_bonus_cap", 1.0)
    density_bonus_per_frame = score_config.get("density_bonus_per_frame", 0.05)

    if density_bonus_per_frame < 0:
        density_bonus_per_frame = 0.0

    high_confidence_frames = [score for score in relevance_scores if score > 0.8 * max_score]
    density_bonus_ratio = len(high_confidence_frames) * density_bonus_per_frame

    if density_bonus_cap > 0:
        density_bonus_ratio = min(density_bonus_ratio, density_bonus_cap)

    density_bonus = segment_max_score * density_bonus_ratio

    # Experimental frame-count bonus: reward densely populated segments for testing
    frame_count = len(frames)
    frame_count_bonus_ratio = 0.0
    frame_count_bonus = 0.0

    if frame_count > 0:
        baseline_frame_count = max(config["segment_duration_seconds"], 1)
        # Treat frame density beyond baseline as signal; each extra baseline multiple adds 5%
        frame_density_multiple = max(frame_count / baseline_frame_count - 1.0, 0.0)
        frame_count_bonus_ratio = frame_density_multiple * 0.05
        frame_count_bonus_ratio = min(frame_count_bonus_ratio, 0.35)
        frame_count_bonus = segment_max_score * frame_count_bonus_ratio
    
    # Length normalization (logarithmic to avoid over-penalizing)
    length_cfg = config.get("length_normalization", {})
    baseline_duration = float(length_cfg.get("baseline_duration_seconds", 30) or 30)
    slowdown_duration = float(length_cfg.get("slowdown_duration_seconds", 120) or 120)
    min_factor = float(length_cfg.get("min_factor", 0.75))
    max_factor = float(length_cfg.get("max_factor", 1.1))
    short_bonus_scale = float(length_cfg.get("short_video_bonus_scale", 0.1))

    try:
        duration_value = float(video_duration)
    except (TypeError, ValueError):
        duration_value = baseline_duration

    if duration_value <= 0:
        duration_value = baseline_duration

    if duration_value <= baseline_duration:
        bonus_ratio = (baseline_duration - duration_value) / baseline_duration
        length_factor = 1.0 + bonus_ratio * short_bonus_scale
    else:
        excess = duration_value - baseline_duration
        slowdown = max(slowdown_duration, 1.0)
        length_factor = baseline_duration / (baseline_duration + excess / slowdown)

    length_factor = max(min_factor, min(max_factor, length_factor))
    
    final_score = (segment_max_score + density_bonus + frame_count_bonus) * length_factor
    
    return {
        "score": final_score,
        "max_frame_score": segment_max_score,
        "density_bonus": density_bonus,
        "density_bonus_ratio": density_bonus_ratio,
        "frame_count_bonus": frame_count_bonus,
        "frame_count_bonus_ratio": frame_count_bonus_ratio,
        "length_factor": length_factor,
        "frame_count": len(frames)
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

    # Calculate global maximum relevance score across all frames for density thresholds
    global_scores: List[float] = []
    for frame in frame_results:
        frame_metadata = frame.metadata if hasattr(frame, 'metadata') else frame
        score = frame_metadata.get('relevance_score') if isinstance(frame_metadata, dict) else None
        if score is not None:
            global_scores.append(score)

    global_max_score = max(global_scores) if global_scores else 0.1
    
    # Step 1: Create temporal segments
    segment_duration = config["segment_duration_seconds"]
    segmentation_start = time.perf_counter()
    segments = create_temporal_segments(frame_results, segment_duration, config)
    segmentation_time_ms = (time.perf_counter() - segmentation_start) * 1000
    logger.debug(f"Created {len(segments)} temporal segments")
    
    # Step 2: Score all segments with length normalization
    scoring_start = time.perf_counter()
    scored_segments = []
    for segment in segments:
        score_data = calculate_segment_score(segment, global_max_score)
        seek_data = determine_seek_point(segment)
        
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
        
        scored_segments.append({
            **segment,
            "score_breakdown": score_data,
            "seek_info": seek_data,
            "final_score": score_data["score"],
            "best_frame_metadata": best_frame_metadata
        })
    
    scoring_time_ms = (time.perf_counter() - scoring_start) * 1000
    logger.debug(f"Scored {len(scored_segments)} segments")
    
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
                "upload_timestamp": best_frame_meta.get("date_time", {}).get("_date", ""),
                "bucket_name": best_frame_meta.get("bucket_name", "")
            }
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

    embeddings = vCLIPEmbeddingsWrapper(
        api_url=settings.VCLIP_EMBEDDINGS_ENDPOINT,
        model_name=settings.VCLIP_EMBEDDINGS_MODEL_NAME,
        num_frames=settings.VCLIP_EMBEDDINGS_NUM_FRAMES,
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
