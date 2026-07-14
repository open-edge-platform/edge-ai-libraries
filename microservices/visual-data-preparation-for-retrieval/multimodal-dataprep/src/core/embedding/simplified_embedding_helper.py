# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pathlib
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from src.common import logger, sanitize_for_log, settings
from src.core.telemetry.recorder import record_video_telemetry
from src.common.schema import TelemetryRecord

# Import embedding helper for optimized processing
from .embedding_helper import (
    generate_rtsp_video_embedding_pipeline,
    generate_video_embedding_pipeline,
    get_embedding_client,
)


def _normalize_tags(tags: Optional[List[str]]) -> List[str]:
    return [str(tag) for tag in tags or []]


def _ensure_telemetry_context(context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    normalized = dict(context or {})
    normalized.setdefault("request_id", str(uuid.uuid4()))
    normalized.setdefault("source", "unknown")
    normalized.setdefault("requested_at", time.time())
    return normalized


def _prepare_video_metadata_payload(
    *,
    bucket_name: str,
    video_id: str,
    filename: str,
    frame_interval: int,
    tags: Optional[List[str]],
    video_url: Optional[str],
    video_rel_url: Optional[str],
    fps: Optional[float],
    total_frames: Optional[int],
    video_duration_seconds: Optional[float],
) -> Dict[str, Any]:
    return {
        "bucket_name": bucket_name,
        "video_id": video_id,
        "filename": filename,
        "frame_interval": frame_interval,
        "tags": _normalize_tags(tags),
        "video_url": video_url,
        "video_rel_url": video_rel_url,
        "fps": fps,
        "total_frames": total_frames,
        "video_duration_seconds": video_duration_seconds,
    }


def _log_telemetry_record(record: TelemetryRecord | None) -> None:
    """Emit a structured log that mirrors the stored telemetry entry."""
    if record is None:
        return

    try:

        if record.batches:
            total_batches = len(record.batches)
            total_seconds = sum(batch.total_seconds for batch in record.batches)
            avg_batch = total_seconds / total_batches if total_batches else 0.0
            max_batch = max(batch.total_seconds for batch in record.batches)
            batch_summary = f"{total_batches} batches (avg {avg_batch:.3f}s, max {max_batch:.3f}s)"
        else:
            batch_summary = "no batch telemetry"

        logger.info(
            "Telemetry captured [request_id=%s, source=%s, video=%s]: batches: %s",
            record.request_id or "<unknown>",
            record.source or "<unknown>",
            record.video.video_id if record.video else "<unknown>",
            batch_summary,
        )

        logger.info(
            "Pipeline Summary | "
            "stream_id=%s | frames=%d | detections=%d | embeddings=%d | "
            "total_time=%.2fs | fps=%.2f | concurrency=%.2f | efficiency=%.1f%%",
            record.counts.frames_extracted,
            record.counts.frames_extracted,
            record.counts.items_after_detection,
            record.counts.embeddings_stored,
            record.stage_duration["total_wall_seconds"],
            record.pipeline_stats["pipeline_throughput_fps"],
            record.pipeline_stats["pipeline_concurrency_factor"],
            record.pipeline_stats["pipeline_efficiency_pct"],
        )

        logger.info(
            "Stage Timing | decode=%.2fs | detect=%.2fs | embed=%.2fs | store=%.2fs",
            record.stage_duration["frame_extraction_seconds"],
            record.stage_duration["detection_seconds"],
            record.stage_duration["embedding_seconds_total"],
            record.stage_duration["storage_seconds_total"],
        )

        logger.info(
            "Throughput | pipeline=%.2f fps | detect=%.2f | embed=%.2f | store=%.2f",
            record.stage_throughput["pipeline_throughput"],
            record.stage_throughput["detect_throughput"],
            record.stage_throughput["embeddings_throughput"],
            record.stage_throughput["store_throughput"],
        )

    except Exception as exc:  # pragma: no cover - logging should not fail pipeline
        logger.debug("Unable to summarize telemetry record %s: %s", record.request_id, exc)


def _record_pipeline(
    *,
    context: Dict[str, Any],
    bucket_name: str,
    video_id: str,
    filename: str,
    frame_interval: int,
    tags: Optional[List[str]],
    enable_object_detection: bool,
    detection_confidence: float,
    metadata_dict: Dict[str, Any],
    pipeline_result: Dict[str, Any],
) -> None:
    try:
        video_props = pipeline_result.get("video_metadata", {})

        pipeline_stats = {
            "properties": {
                "stream_id": pipeline_result.get("stream_id", -1),
                "frames_extracted": pipeline_result.get("total_frames_processed", 0),
                "items_after_detection": pipeline_result.get("total_detected_crops", 0),
                "embeddings_stored": pipeline_result.get("total_stored_ids", 0),
            },
            "stage_duration": {
                "frame_extraction_seconds": pipeline_result.get("metrics", {})
                .get("decode", {})
                .get("total", 0.0),
                "detection_seconds": pipeline_result.get("metrics", {})
                .get("detect", {})
                .get("total", 0.0),
                "embedding_seconds_total": pipeline_result.get("metrics", {})
                .get("embed", {})
                .get("total", 0.0),
                "embed_inference_time": pipeline_result.get("metrics", {})
                .get("embed_inference_time", {})
                .get("total", 0.0),
                "storage_seconds_total": pipeline_result.get("metrics", {})
                .get("store", {})
                .get("total", 0.0),
                "total_wall_seconds": pipeline_result.get("pipeline_wall_duration_s", 0.0),
            },
            "batches": pipeline_result.get("batch_details", []),
            "pipeline_metrics": {
                "pipeline_wall_duration": pipeline_result.get("pipeline_wall_duration_s", -1),
                # "pipeline_throughput_fps": pipeline_result.get("pipeline_throughput_fps", -1),
                "pipeline_throughput_fps": pipeline_result.get("pipeline_throughput_fps_with_OD", -1),
                "pipeline_concurrency_factor": pipeline_result.get("pipeline_concurrency_factor", -1),
                "pipeline_efficiency_pct": pipeline_result.get("pipeline_efficiency_pct", -1),
                "parallel_efficiency_pct": pipeline_result.get("parallel_efficiency_pct", -1),
                "decode_pipeline_efficiency_pct": pipeline_result.get(
                    "decode_pipeline_efficiency_pct", -1
                ),
                "detect_pipeline_efficiency_pct": pipeline_result.get(
                    "detect_pipeline_efficiency_pct", -1
                ),
                "embed_store_pipeline_efficiency_pct": pipeline_result.get(
                    "embed_store_pipeline_efficiency_pct", -1
                ),
            },
            "stage_throughput": {
                "decode_throughput": pipeline_result.get("metrics", {})
                .get("decode", {})
                .get("throughput", 0.0),
                "embedding_infer_throughput": pipeline_result.get("metrics", {})
                .get("embed_inference_time", {})
                .get("throughput", 0.0),
                "embeddings_throughput": pipeline_result.get("metrics", {})
                .get("embed", {})
                .get("throughput", 0.0),
                # "pipeline_throughput": pipeline_result.get("pipeline_throughput_fps", 0.0),
                "pipeline_throughput": pipeline_result.get("pipeline_throughput_fps_with_OD", 0.0),
                "store_throughput": pipeline_result.get("metrics", {})
                .get("store", {})
                .get("throughput", 0.0),
                "detect_throughput": pipeline_result.get("metrics", {})
                .get("detect", {})
                .get("throughput", 0.0),
            },
        }

        video_metadata = _prepare_video_metadata_payload(
            bucket_name=bucket_name,
            video_id=video_id,
            filename=filename,
            frame_interval=frame_interval,
            tags=tags,
            video_url=metadata_dict.get("video_url"),
            video_rel_url=metadata_dict.get("video_rel_url"),
            fps=video_props.get("fps"),
            total_frames=video_props.get("total_frames"),
            video_duration_seconds=video_props.get(
                "video_duration_seconds",
                (
                    video_props.get("total_frames") / video_props.get("fps")
                    if video_props.get("fps")
                    else 0.0
                ),
            ),
        )

        pipeline_config = pipeline_result.get("pipeline_config", {})
        config = {
            "object_detection_enabled": enable_object_detection,
            "detection_confidence": detection_confidence,
            "parallel_workers": pipeline_config.get("pipeline_count"),
            "batch_size": pipeline_config.get("batch_size"),
        }

        context["completed_at"] = time.time()
        record = record_video_telemetry(
            context=context,
            video_metadata=video_metadata,
            pipeline_stats=pipeline_stats,
            config=config,
        )
        _log_telemetry_record(record)
    except Exception as exc:
        logger.warning("Unable to record telemetry: %s", exc)


async def generate_video_embedding(
    bucket_name: str,
    video_id: str,
    filename: str,
    temp_video_path: pathlib.Path,
    metadata_temp_path: pathlib.Path,
    frame_interval: int = 15,
    enable_object_detection: bool = True,
    detection_confidence: float = 0.85,
    tags: List[str] = None,
    telemetry_context: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    Generate video embeddings using the in-process embedding pipeline.

    Args:
        bucket_name: Bucket name where the video is stored
        video_id: Directory containing the video
        filename: Video filename
        temp_video_path: Temporary path to the video file
        metadata_temp_path: Path to store metadata
        frame_interval: Number of frames between extractions
        enable_object_detection: Whether to enable object detection
        detection_confidence: Confidence threshold for object detection
        tags: Tags for the video

    Returns:
        List of IDs of the created embeddings
    """
    try:
        telemetry_context = _ensure_telemetry_context(telemetry_context)

        logger.info(f"Starting video embedding for {video_id}/{filename}")

        return await _generate_video_embedding(
            bucket_name=bucket_name,
            video_id=video_id,
            filename=filename,
            temp_video_path=temp_video_path,
            metadata_temp_path=metadata_temp_path,
            frame_interval=frame_interval,
            enable_object_detection=enable_object_detection,
            detection_confidence=detection_confidence,
            tags=tags,
            telemetry_context=telemetry_context,
        )

    except Exception as ex:
        logger.error(f"Error in video embedding generation: {ex}")
        raise


async def generate_video_embedding_from_content(
    video_content: bytes,
    bucket_name: str,
    video_id: str,
    filename: str,
    metadata_temp_path: pathlib.Path,
    frame_interval: int = 15,
    enable_object_detection: bool = True,
    detection_confidence: float = 0.85,
    tags: List[str] = None,
    telemetry_context: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    Generate video embeddings directly from video content bytes.

    This function processes video content directly
    from memory without writing to disk first, providing maximum performance.

    Args:
        video_content: Video content as bytes (in memory)
        bucket_name: Bucket name where the video is stored
        video_id: Directory containing the video
        filename: Video filename
        metadata_temp_path: Path to store metadata
        frame_interval: Number of frames between extractions
        enable_object_detection: Whether to enable object detection
        detection_confidence: Confidence threshold for object detection
        tags: Tags for the video

    Returns:
        List of IDs of the created embeddings
    """
    try:
        telemetry_context = _ensure_telemetry_context(telemetry_context)

        logger.info(
            "Starting video embedding from content for %s/%s",
            sanitize_for_log(video_id, max_length=128),
            sanitize_for_log(filename, max_length=256),
        )
        logger.info(
            "Video content size: %s bytes",
            sanitize_for_log(len(video_content), max_length=32),
        )

        # Create metadata for video (including video URLs for search-ms compatibility)
        video_rel_url = (
            f"/v1/dataprep/videos/download?video_id={video_id}&bucket_name={bucket_name}"
        )
        video_url = f"http://{settings.APP_HOST}:{settings.APP_PORT}{video_rel_url}"

        # Create metadata dictionary for processing
        metadata_dict = {
            "bucket_name": bucket_name,
            "video_id": video_id,
            "filename": filename,
            "tags": tags or [],
            "video_url": video_url,
            "video_rel_url": video_rel_url,
        }

        # DEBUG: Print metadata dictionary to verify video URLs are created
        logger.info(
            "DEBUG: metadata_dict created in simplified_embedding_helper: %s",
            sanitize_for_log(metadata_dict, max_length=1024),
        )
        logger.info(
            "DEBUG: video_url value: '%s', video_rel_url value: '%s'",
            sanitize_for_log(video_url, max_length=512),
            sanitize_for_log(video_rel_url, max_length=512),
        )

        # Process video directly from memory
        results = generate_video_embedding_pipeline(
            video_content=video_content,
            metadata_dict=metadata_dict,
            frame_interval=frame_interval,
            enable_object_detection=enable_object_detection,
            detection_confidence=detection_confidence,
        )

        stored_ids = []
        for stream_id, stream_result in results.items():

            bucket_name = stream_result["video_metadata"]["_bucket_name"]
            video_id = stream_result["video_metadata"]["_video_id"]
            filename = stream_result["video_metadata"]["_filename"]

            _record_pipeline(
                context=telemetry_context,
                bucket_name=bucket_name,
                video_id=video_id,
                filename=filename,
                frame_interval=frame_interval,
                tags=tags,
                enable_object_detection=enable_object_detection,
                detection_confidence=detection_confidence,
                metadata_dict=metadata_dict,
                pipeline_result=stream_result,
            )

            logger.info(
                f"Processing from content | Stream ID: {stream_id} completed. {sanitize_for_log(stream_result['total_frames_processed'], max_length=32)} frames processed",
            )

            stored_ids.extend(stream_result["stored_ids"])

        return stored_ids

    except Exception as ex:
        logger.error(f"Error in video embedding from content: {ex}")
        raise


async def generate_video_embedding_from_uri(
    video_uris: list[str],
    bucket_name: str,
    video_id: str,
    filename: str,
    metadata_temp_path: pathlib.Path,
    frame_interval: int = 15,
    enable_object_detection: bool = True,
    detection_confidence: float = 0.85,
    tags: List[str] = None,
    telemetry_context: Optional[Dict[str, Any]] = None,
    shutdown_event: Optional[threading.Event] = None,
) -> List[str]:
    """
    Generate video embeddings directly from video URI.

    This function processes video content directly
    from the provided URI, allowing for maximum performance without intermediate storage.

    Args:
        video_uri: List of video URIs to process
        bucket_name: Bucket name where the video is stored
        video_id: Directory containing the video
        filename: Video filename
        metadata_temp_path: Path to store metadata
        frame_interval: Number of frames between extractions
        enable_object_detection: Whether to enable object detection
        detection_confidence: Confidence threshold for object detection
        tags: Tags for the video

    Returns:
        List of IDs of the created embeddings

    """

    logger.info(f"Starting video embedding from URI for {video_id}/{filename}")
    logger.info(f"Video URI: {video_uris}")
    logger.info("ID of shutdown_event in generate_video_embedding_from_uri: %s", id(shutdown_event))

    # Create metadata for video (including video URLs for search-ms compatibility)

    result = generate_rtsp_video_embedding_pipeline(
        video_uris=video_uris,
        metadata_dict={
            "bucket_name": "RTSP_BUCKET",
            "video_id": -1,
            "filename": "filename",
            "tags": tags or [],
        },
        frame_interval=frame_interval,
        enable_object_detection=enable_object_detection,
        detection_confidence=detection_confidence,
        shutdown_event=shutdown_event,
    )

    return (result or {}).get("stored_ids", [])


async def _generate_video_embedding(
    bucket_name: str,
    video_id: str,
    filename: str,
    temp_video_path: pathlib.Path,
    metadata_temp_path: pathlib.Path,
    frame_interval: int = 15,
    enable_object_detection: bool = True,
    detection_confidence: float = 0.85,
    tags: List[str] = None,
    telemetry_context: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    Video embedding generation from a temp file (optimized approach).

    This function reads from the temp file.
    For maximum optimization, use generate_video_embedding_from_content().
    """
    logger.info("Processing video (direct calls)")

    # Read video content from temp file
    with open(temp_video_path, "rb") as f:
        video_content = f.read()

    logger.info(f"Loaded video content: {len(video_content)} bytes")

    # Create video URL paths for search-ms compatibility
    video_rel_url = f"/v1/dataprep/videos/download?video_id={video_id}&bucket_name={bucket_name}"
    app_host = settings.APP_HOST or "localhost"
    video_url = f"http://{app_host}:{settings.APP_PORT}{video_rel_url}"

    # Create metadata for video
    metadata_dict = {
        "bucket_name": bucket_name,
        "video_id": video_id,
        "filename": filename,
        "tags": tags or [],
        "video_url": video_url,
        "video_rel_url": video_rel_url,
    }

    # DEBUG: Print metadata dictionary to verify video URLs are created
    logger.info(
        "DEBUG: metadata_dict created in _generate_video_embedding: %s",
        sanitize_for_log(metadata_dict, max_length=1024),
    )

    # Process video
    results = generate_video_embedding_pipeline(
        video_content=video_content,
        metadata_dict=metadata_dict,
        frame_interval=frame_interval,
        enable_object_detection=enable_object_detection,
        detection_confidence=detection_confidence,
    )

    stored_ids = []
    for stream_id, stream_result in results.items():

        bucket_name = stream_result["video_metadata"]["_bucket_name"]
        video_id = stream_result["video_metadata"]["_video_id"]
        filename = stream_result["video_metadata"]["_filename"]

        _record_pipeline(
            context=telemetry_context or {},
            bucket_name=bucket_name,
            video_id=video_id,
            filename=filename,
            frame_interval=frame_interval,
            tags=tags,
            enable_object_detection=enable_object_detection,
            detection_confidence=detection_confidence,
            metadata_dict=metadata_dict,
            pipeline_result=stream_result,
        )

        logger.info(
            f"Processing | Stream ID: {stream_id} completed. {sanitize_for_log(stream_result['total_frames_processed'], max_length=32)} frames processed",
        )

        stored_ids.extend(stream_result["stored_ids"])

    return stored_ids


async def generate_text_embedding(
    text: str,
    text_metadata: dict = {},
    use_qwen_for_long_text: bool = True,
    qwen_threshold: int = 500,
) -> List[str]:
    """
    Generate and persist text embeddings using the in-process embedding pipeline.

    Args:
        text: The text content to embed
        text_metadata: Metadata associated with the text
        use_qwen_for_long_text: Whether to use Qwen for long texts
        qwen_threshold: Character threshold to switch to Qwen (default: 500)

    Returns:
        List of IDs of the created embeddings
    """
    try:
        text_length = len(text)
        use_qwen_hint = use_qwen_for_long_text and text_length >= qwen_threshold
        model_name = (settings.MULTIMODAL_EMBEDDING_MODEL_NAME or "").strip() or "<unspecified>"

        logger.info(
            f"Processing text embedding (length: {text_length}, use_qwen_hint={use_qwen_hint}, model: {model_name})"
        )

        embedding_client = get_embedding_client()
        if not embedding_client.supports_text:
            raise ValueError(
                f"Configured model '{model_name}' does not support text embeddings. "
                "Please verify your EMBEDDING_MODEL_NAME setting and ensure the selected model supports text embedding."
            )

        ids = embedding_client.store_text_embedding(text=text, metadata=text_metadata)
        logger.info(
            "Stored text embedding, ID: %s",
            ids[0] if ids else "<none>",
        )
        return ids

    except Exception as ex:
        logger.error(f"Error in smart text embedding generation: {ex}")
        raise
