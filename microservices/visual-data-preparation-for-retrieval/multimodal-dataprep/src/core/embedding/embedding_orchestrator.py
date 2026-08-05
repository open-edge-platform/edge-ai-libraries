# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Embedding orchestration layer.

Thin, async, endpoint-facing facade that prepares metadata and telemetry,
then delegates the heavy video-embedding work to the synchronous pipeline
engine in ``embedding_helper``. The API endpoints call the ``async``
functions exposed here (via ``src.core.embedding``); they should not call the
pipeline engine directly.
"""

import asyncio
import datetime
import io
import pathlib
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from src.common import logger, sanitize_for_log, settings
from src.common.schema import TelemetryRecord
from src.core.metrics_manager import publish_embeddings_throughput
from src.core.telemetry.recorder import record_video_telemetry

# Import embedding helper for optimized processing
from .embedding_helper import (
    generate_rtsp_video_embedding_pipeline,
    generate_video_embedding_pipeline,
    get_embedding_client,
    get_global_detector,
)


def _normalize_tags(tags: Optional[List[str]]) -> List[str]:
    """Coerce an optional tag list into a list of strings, mapping ``None`` to ``[]``."""
    return [str(tag) for tag in tags or []]


def _ensure_telemetry_context(context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return a telemetry context with ``request_id``, ``source`` and ``requested_at`` defaults filled in.

    A shallow copy of ``context`` (or a new dict) is returned so the caller's
    input is never mutated; only missing keys are populated.
    """
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
    """Assemble the normalized video-metadata payload passed to the telemetry recorder.

    Bundles identifying fields (bucket/video/filename), processing settings
    (frame interval, tags) and probed video properties (URLs, fps, frame count,
    duration) into a single flat dict, normalizing ``tags`` via
    :func:`_normalize_tags`.
    """
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
    """Transform a raw pipeline result into telemetry and record + log it.

    Extracts per-stage durations, throughput and pipeline efficiency metrics
    from ``pipeline_result``, builds the video-metadata payload, persists the
    record via :func:`record_video_telemetry`, and emits a structured summary
    log. Failures are swallowed with a warning so telemetry never breaks the
    embedding request.
    """
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

        completed_at = time.time()
        context["completed_at"] = completed_at
        record = record_video_telemetry(
            context=context,
            video_metadata=video_metadata,
            pipeline_stats=pipeline_stats,
            config=config,
        )
        _log_telemetry_record(record)
        if record is not None:
            publish_embeddings_throughput(
                record.stage_throughput["embeddings_throughput"],
                completed_at,
            )
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
    video_name: Optional[str] = None,
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
            video_name=video_name,
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
    video_name: Optional[str] = None,
    tags: List[str] = None,
    source_path: Optional[str] = None,
    custom_metadata: Optional[Dict[str, Any]] = None,
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
        source_path: Origin path of the media as seen outside the container,
            recorded so consumers sharing the ingest mount can read it in place
        custom_metadata: Caller-supplied metadata persisted as filterable fields

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
            f"/v1/dataprep/media/download?video_id={video_id}&bucket_name={bucket_name}"
        )
        video_url = f"http://{settings.APP_HOST}:{settings.APP_PORT}{video_rel_url}"

        # Create metadata dictionary for processing
        metadata_dict = {
            "bucket_name": bucket_name,
            "video_id": video_id,
            "filename": filename,
            "video_name": video_name or filename,
            "tags": tags or [],
            "video_url": video_url,
            "video_rel_url": video_rel_url,
            "source_path": source_path or "",
            "custom_metadata": custom_metadata or {},
        }

        # DEBUG: Print metadata dictionary to verify video URLs are created
        logger.info(
            "DEBUG: metadata_dict created in embedding_orchestrator: %s",
            sanitize_for_log(metadata_dict, max_length=1024),
        )
        logger.info(
            "DEBUG: video_url value: '%s', video_rel_url value: '%s'",
            sanitize_for_log(video_url, max_length=512),
            sanitize_for_log(video_rel_url, max_length=512),
        )

        # Process video directly from memory. Offload the synchronous pipeline
        # engine to a worker thread so the single uvicorn worker's event loop
        # stays responsive and concurrent requests are not serialized.
        results = await asyncio.to_thread(
            generate_video_embedding_pipeline,
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

    # Offload the blocking RTSP pipeline engine to a worker thread so the event
    # loop stays responsive (the engine skips SIGINT registration off the main
    # thread; graceful shutdown is driven by shutdown_event).
    result = await asyncio.to_thread(
        generate_rtsp_video_embedding_pipeline,
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
    video_name: Optional[str] = None,
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
    video_rel_url = f"/v1/dataprep/media/download?video_id={video_id}&bucket_name={bucket_name}"
    app_host = settings.APP_HOST or "localhost"
    video_url = f"http://{app_host}:{settings.APP_PORT}{video_rel_url}"

    # Create metadata for video
    metadata_dict = {
        "bucket_name": bucket_name,
        "video_id": video_id,
        "filename": filename,
        "video_name": video_name or filename,
        "tags": tags or [],
        "video_url": video_url,
        "video_rel_url": video_rel_url,
    }

    # DEBUG: Print metadata dictionary to verify video URLs are created
    logger.info(
        "DEBUG: metadata_dict created in _generate_video_embedding: %s",
        sanitize_for_log(metadata_dict, max_length=1024),
    )

    # Process video. Offload the synchronous pipeline engine to a worker thread
    # so the event loop stays responsive under concurrent requests.
    results = await asyncio.to_thread(
        generate_video_embedding_pipeline,
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
) -> List[str]:
    """
    Generate and persist text embeddings using the in-process embedding pipeline.

    Args:
        text: The text content to embed
        text_metadata: Metadata associated with the text

    Returns:
        List of IDs of the created embeddings
    """
    try:
        text_length = len(text)
        model_name = (settings.EMBEDDING_MODEL_NAME or "").strip() or "<unspecified>"

        logger.info(
            f"Processing text embedding (length: {text_length}, model: {model_name})"
        )

        embedding_client = get_embedding_client()
        if not embedding_client.supports_text:
            raise ValueError(
                f"Configured model '{model_name}' does not support text embeddings. "
                "Please verify your MM_DATAPREP_EMBEDDING_MODEL_NAME setting and ensure the selected model supports text embedding."
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


def _build_image_base_metadata(
    *,
    bucket_name: str,
    video_id: str,
    filename: str,
    video_name: Optional[str] = None,
    tags: List[str],
    source_path: Optional[str] = None,
    custom_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Assemble the canonical metadata shared by an image and all its crops.

    Mirrors the video full-frame metadata contract so image embeddings are
    indistinguishable to a retriever except for ``content_type="image"``. The
    generic media id (``video_id``) and ``video_name``/``filename`` fields are
    reused verbatim for backward compatibility with existing retrievers.
    """
    video_rel_url = (
        f"/v1/dataprep/media/download?video_id={video_id}&bucket_name={bucket_name}"
    )
    video_url = f"http://{settings.APP_HOST}:{settings.APP_PORT}{video_rel_url}"
    return {
        "video_id": video_id,
        "bucket_name": bucket_name,
        "filename": filename,
        "video_name": video_name or filename,
        "video_index": 0,
        "frame_number": 0,
        "timestamp": 0.0,
        "content_type": "image",
        "tags": _normalize_tags(tags),
        "video_url": video_url,
        "video_rel_url": video_rel_url,
        "source_path": source_path or "",
        "custom_metadata": custom_metadata or {},
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def _decode_image(image_content: bytes) -> "Any":
    """Decode raw image bytes into an RGB PIL image, raising on invalid input.

    The bytes are the trust boundary: Pillow parses untrusted content, so any
    decode failure is surfaced as a ``ValueError`` for the caller to map to a
    400. Conversion to RGB normalizes palette/alpha/grayscale inputs so the CLIP
    image encoder receives a consistent 3-channel array.
    """
    from PIL import Image, UnidentifiedImageError

    try:
        image = Image.open(io.BytesIO(image_content))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(f"Provided bytes are not a valid/decodable image: {exc}")
    return image.convert("RGB")


def _embed_image_from_content_sync(
    *,
    image_content: bytes,
    bucket_name: str,
    video_id: str,
    filename: str,
    video_name: Optional[str] = None,
    enable_object_detection: bool,
    detection_confidence: float,
    tags: List[str],
    source_path: Optional[str] = None,
    custom_metadata: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Synchronous image embedding core (runs off the event loop via a thread).

    Pipeline: decode PIL once -> optionally run YOLOX detection and crop each
    detected object -> batched CLIP ``encode_image`` in sub-batches of
    ``EMBEDDING_BATCH_SIZE`` -> ``store_frame_embeddings`` into the active vector
    store. The full image is always embedded (``frame_type="full_frame"``); crops
    add ``frame_type="detected_crop"`` entries with the same crop-metadata
    contract as the video pipeline.
    """
    image = _decode_image(image_content)

    embedding_client = get_embedding_client()
    if not embedding_client.supports_image:
        model_name = (settings.EMBEDDING_MODEL_NAME or "").strip() or "<unspecified>"
        raise ValueError(
            f"Configured model '{model_name}' does not support image embeddings. "
            "Please verify your MM_DATAPREP_EMBEDDING_MODEL_NAME setting and ensure "
            "the selected model supports image embedding."
        )

    base_metadata = _build_image_base_metadata(
        bucket_name=bucket_name,
        video_id=video_id,
        filename=filename,
        video_name=video_name,
        tags=tags,
        source_path=source_path,
        custom_metadata=custom_metadata,
    )

    # The full image is always the first item.
    images: List[Any] = [image]
    metadatas: List[Dict[str, Any]] = [{**base_metadata, "frame_type": "full_frame"}]

    # Optional object detection -> one crop embedding per detected object.
    if enable_object_detection:
        detector = get_global_detector(True, detection_confidence)
        if detector is not None:
            try:
                detections = detector.detect(image, return_metadata=True)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Image object detection failed; embedding full image only: %s", exc)
                detections = []

            width, height = image.size
            crop_idx = 0
            for det in detections:
                bbox = det.get("bbox") or []
                if len(bbox) != 4:
                    continue
                x1, y1, x2, y2 = bbox
                x1 = max(0, min(int(x1), width - 1))
                y1 = max(0, min(int(y1), height - 1))
                x2 = max(x1 + 1, min(int(x2), width))
                y2 = max(y1 + 1, min(int(y2), height))
                if (x2 - x1) < 10 or (y2 - y1) < 10:
                    continue

                crop = image.crop((x1, y1, x2, y2))
                crop_metadata = {
                    **base_metadata,
                    "frame_type": "detected_crop",
                    "is_detected_crop": True,
                    "crop_index": crop_idx,
                    "detection_confidence": float(det.get("confidence", 0.0)),
                    "crop_bbox": [x1, y1, x2, y2],
                    "detected_class_id": int(det.get("class_id", -1)),
                    "detected_label": det.get("class_name", "unknown"),
                    "merged_boxes_count": det.get("merged_boxes_count"),
                    "context_expansion_applied": det.get("context_expansion_applied"),
                }
                images.append(crop)
                metadatas.append(crop_metadata)
                crop_idx += 1

    # Batched embedding + storage. Sub-batching bounds peak GPU/host memory while
    # letting the CLIP image encoder amortize per-call overhead.
    batch_size = max(1, int(settings.EMBEDDING_BATCH_SIZE or 32))
    all_ids: List[str] = []
    for start in range(0, len(images), batch_size):
        sub_images = images[start : start + batch_size]
        sub_metadatas = metadatas[start : start + batch_size]
        embeddings = embedding_client.generate_embeddings_for_images(sub_images)

        good_embeddings: List[List[float]] = []
        good_metadatas: List[Dict[str, Any]] = []
        for embedding, metadata in zip(embeddings, sub_metadatas):
            if embedding is not None:
                good_embeddings.append(embedding)
                good_metadatas.append(metadata)

        if good_embeddings:
            all_ids.extend(
                embedding_client.store_frame_embeddings(good_embeddings, good_metadatas)
            )

    logger.info(
        "Stored %d image embeddings for %s/%s (%d crops)",
        len(all_ids),
        sanitize_for_log(bucket_name, max_length=128),
        sanitize_for_log(video_id, max_length=128),
        len(images) - 1,
    )
    return all_ids


async def generate_image_embedding_from_content(
    *,
    image_content: bytes,
    bucket_name: str,
    video_id: str,
    filename: str,
    enable_object_detection: bool = True,
    detection_confidence: float = 0.85,
    video_name: Optional[str] = None,
    tags: Optional[List[str]] = None,
    source_path: Optional[str] = None,
    custom_metadata: Optional[Dict[str, Any]] = None,
    telemetry_context: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Generate and persist embeddings for a single image.

    Async, endpoint-facing facade mirroring
    :func:`generate_video_embedding_from_content`. The blocking decode/detect/
    encode/store work runs in a worker thread so the single uvicorn worker stays
    responsive. ``telemetry_context`` is accepted for signature parity with the
    video path (image ingestion has no frame-pipeline telemetry to record).

    Returns the list of stored embedding IDs (one for the full image plus one per
    detected crop when object detection is enabled).
    """
    tags = _normalize_tags(tags)
    logger.info(
        "Processing image embedding for %s/%s (object_detection=%s)",
        sanitize_for_log(bucket_name, max_length=128),
        sanitize_for_log(video_id, max_length=128),
        enable_object_detection,
    )
    return await asyncio.to_thread(
        _embed_image_from_content_sync,
        image_content=image_content,
        bucket_name=bucket_name,
        video_id=video_id,
        filename=filename,
        video_name=video_name,
        enable_object_detection=enable_object_detection,
        detection_confidence=detection_confidence,
        tags=tags,
        source_path=source_path,
        custom_metadata=custom_metadata,
    )
