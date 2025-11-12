# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pathlib
import time
from typing import List

from src.common import logger, settings
from src.core.embedding.simple_client import SimpleVDMSClient
from src.core.utils.metadata_utils import store_enhanced_video_metadata

# Import SDK-based embedding helper for optimized processing
from .sdk_embedding_helper import generate_video_embedding_sdk, get_sdk_client

# Cache to store VDMS client instances for different use cases
_client_cache: dict[str, SimpleVDMSClient] = {}


def _get_client_key(endpoint: str | None = None, use_case: str = "default") -> str:
    """
    Generate a unique key for caching VDMS clients based on endpoint and use case.
    
    Args:
        endpoint: Multimodal embedding service endpoint URL
        use_case: Type of processing ("video", "text", or "default")
    
    Returns:
        A unique string key for the VDMS client cache
    """
    base_key = f"{settings.VDMS_VDB_HOST}:{settings.VDMS_VDB_PORT}:{settings.DB_COLLECTION}"
    
    if endpoint:
        # Include endpoint in cache key since different endpoints may have different configs
        base_key += f":{endpoint}"
    
    # Different use cases might need different client configurations
    return f"{base_key}:{use_case}"


def _get_cached_vdms_client(use_case: str = "default") -> SimpleVDMSClient:
    """
    Get or create a cached VDMS client for the specified use case.
    
    Args:
        use_case: Type of processing ("video", "text", or "default")
        
    Returns:
        A SimpleVDMSClient instance
    """
    cache_key = _get_client_key(
        endpoint=settings.MULTIMODAL_EMBEDDING_ENDPOINT,
        use_case=use_case
    )
    
    if cache_key not in _client_cache:
        logger.info(f"Creating new VDMS client for use case: {use_case}")
        
        # Validate that model name is provided when using API mode
        if not settings.MULTIMODAL_EMBEDDING_MODEL_NAME:
            raise ValueError("MULTIMODAL_EMBEDDING_MODEL_NAME must be explicitly provided when using API embedding mode - no default model is allowed")
        
        client = SimpleVDMSClient(
            host=settings.VDMS_VDB_HOST,
            port=settings.VDMS_VDB_PORT,
            collection_name=settings.DB_COLLECTION,
            embedding_dimensions=None,  # Auto-detect from multimodal API
            multimodal_api_url=settings.MULTIMODAL_EMBEDDING_ENDPOINT,
            model_name=settings.MULTIMODAL_EMBEDDING_MODEL_NAME  # Must be explicitly set - no default
        )
        _client_cache[cache_key] = client
        logger.debug(f"VDMS client cached with key: {cache_key}")
    else:
        logger.debug(f"Using cached VDMS client for: {cache_key}")
    
    return _client_cache[cache_key]


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
) -> List[str]:
    """
    Video embedding generation with flag-based routing between API and SDK modes.
    
    This function routes to either:
    - API mode: Traditional HTTP API calls to multimodal embedding service  
    - SDK mode: Direct SDK calls for optimized performance
    
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
        logger.info(f"Starting video embedding for {video_id}/{filename}")
        logger.info(f"Processing mode: {settings.EMBEDDING_PROCESSING_MODE}")
        
        # Route based on processing mode flag
        if settings.EMBEDDING_PROCESSING_MODE.lower() == "sdk":
            logger.info("Using SDK mode for optimized performance")
            return await _generate_video_embedding_sdk_mode(
                bucket_name=bucket_name,
                video_id=video_id,
                filename=filename,
                temp_video_path=temp_video_path,
                metadata_temp_path=metadata_temp_path,
                frame_interval=frame_interval,
                enable_object_detection=enable_object_detection,
                detection_confidence=detection_confidence,
                tags=tags
            )
        else:
            logger.info("Using API mode (traditional HTTP calls)")
            return await _generate_video_embedding_api_mode(
                bucket_name=bucket_name,
                video_id=video_id,
                filename=filename,
                temp_video_path=temp_video_path,
                metadata_temp_path=metadata_temp_path,
                frame_interval=frame_interval,
                enable_object_detection=enable_object_detection,
                detection_confidence=detection_confidence,
                tags=tags
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
) -> List[str]:
    """
    Generate video embeddings directly from video content bytes (SDK mode only).
    
    This function is optimized for SDK mode and processes video content directly
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
        logger.info(f"Starting SDK video embedding from content for {video_id}/{filename}")
        logger.info(f"Video content size: {len(video_content)} bytes")
        
        if settings.EMBEDDING_PROCESSING_MODE.lower() != "sdk":
            logger.warning("generate_video_embedding_from_content called but SDK mode not enabled")
            logger.warning("This function is optimized for SDK mode only")
        
        # Create metadata for video (including video URLs for search-ms compatibility)
        video_rel_url = f"/v1/dataprep/videos/download?video_id={video_id}&bucket_name={bucket_name}"
        video_url = f"http://{settings.APP_HOST}:{settings.APP_PORT}{video_rel_url}"
        
        # Create metadata dictionary for SDK processing
        metadata_dict = {
            'bucket_name': bucket_name,
            'video_id': video_id,
            'filename': filename,
            'tags': tags or [],
            'processing_mode': 'sdk',
            'video_url': video_url,
            'video_rel_url': video_rel_url
        }
        
        # DEBUG: Print metadata dictionary to verify video URLs are created
        logger.info(f"DEBUG: metadata_dict created in simplified_embedding_helper: {metadata_dict}")
        logger.info(f"DEBUG: video_url value: '{video_url}', video_rel_url value: '{video_rel_url}'")
        
        # Process video using SDK mode directly from memory
        results = generate_video_embedding_sdk(
            video_content=video_content,
            metadata_dict=metadata_dict,
            frame_interval=frame_interval,
            enable_object_detection=enable_object_detection,
            detection_confidence=detection_confidence
        )
        
        logger.info(f"SDK processing completed: {results['total_frames_processed']} frames processed")
        return results['stored_ids']

    except Exception as ex:
        logger.error(f"Error in SDK video embedding from content: {ex}")
        raise


async def _generate_video_embedding_api_mode(
    bucket_name: str,
    video_id: str,
    filename: str,
    temp_video_path: pathlib.Path,
    metadata_temp_path: pathlib.Path,
    frame_interval: int = 15,
    enable_object_detection: bool = True,
    detection_confidence: float = 0.85,
    tags: List[str] = None,
) -> List[str]:
    """
    Original API-based video embedding generation (for comparison).
    
    This function preserves the original HTTP API-based approach for
    performance comparison with the new SDK approach.
    """
    logger.info("Processing video using API mode (HTTP calls)")

    total_start = time.time()

    extraction_start = time.time()
    metadata_file_path = store_enhanced_video_metadata(
        bucket_name=bucket_name,
        video_id=video_id,
        video_filename=filename,
        temp_video_path=temp_video_path,
        metadata_temp_path=str(metadata_temp_path),
        frame_interval=frame_interval,
        enable_object_detection=enable_object_detection,
        detection_confidence=detection_confidence,
        tags=tags or [],
    )
    extraction_time = time.time() - extraction_start
    logger.info("Video metadata created at %s", metadata_file_path)

    client_setup_start = time.time()
    vdms_client = _get_cached_vdms_client(use_case="video")
    client_setup_time = time.time() - client_setup_start
    logger.debug("VDMS client ready in %.3fs", client_setup_time)

    storage_start = time.time()
    storage_result = vdms_client.store_embeddings_from_manifest(metadata_file_path)
    embedding_storage_time = time.time() - storage_start

    ids = storage_result.get("ids", [])
    post_detection_items = storage_result.get("post_detection_items", len(ids))
    extracted_frames = storage_result.get("extracted_frames", post_detection_items)
    embedding_time = storage_result.get("embedding_time", embedding_storage_time)
    storage_time = storage_result.get("storage_time", 0.0)

    total_time = time.time() - total_start

    logger.info(
        "Frame flow summary: extracted=%d -> after_detection=%d -> stored=%d",
        extracted_frames,
        post_detection_items,
        len(ids),
    )

    detection_time = 0.0
    if enable_object_detection:
        logger.debug("Object detection time reported as part of extraction stage")

    logger.info(
        "Stage timing summary (s): extraction=%.3f | detection=%.3f | embedding=%.3f | storage=%.3f | total=%.3f",
        extraction_time,
        detection_time,
        embedding_time,
        storage_time,
        total_time,
    )

    return ids


async def _generate_video_embedding_sdk_mode(
    bucket_name: str,
    video_id: str,
    filename: str,
    temp_video_path: pathlib.Path,
    metadata_temp_path: pathlib.Path,
    frame_interval: int = 15,
    enable_object_detection: bool = True,
    detection_confidence: float = 0.85,
    tags: List[str] = None,
) -> List[str]:
    """
    SDK-based video embedding generation (optimized approach).
    
    This function uses the SDK approach but still reads from the temp file.
    For maximum optimization, use generate_video_embedding_from_content().
    """
    logger.info("Processing video using SDK mode (direct calls)")
    
    # Read video content from temp file
    with open(temp_video_path, 'rb') as f:
        video_content = f.read()
    
    logger.info(f"Loaded video content: {len(video_content)} bytes")
    
    # Create video URL paths for search-ms compatibility
    video_rel_url = (
        f"/v1/dataprep/videos/download?video_id={video_id}&bucket_name={bucket_name}"
    )
    app_host = settings.APP_HOST or "localhost"
    video_url = f"http://{app_host}:{settings.APP_PORT}{video_rel_url}"
    
    # Create metadata for video
    metadata_dict = {
        'bucket_name': bucket_name,
        'video_id': video_id,
        'filename': filename,
        'tags': tags or [],
        'processing_mode': 'sdk',
        'video_url': video_url,
        'video_rel_url': video_rel_url
    }
    
    # DEBUG: Print metadata dictionary to verify video URLs are created
    logger.info(
        "DEBUG: metadata_dict created in _generate_video_embedding_sdk_mode: %s",
        metadata_dict,
    )
    
    # Process video using SDK mode
    results = generate_video_embedding_sdk(
        video_content=video_content,
        metadata_dict=metadata_dict,
        frame_interval=frame_interval,
        enable_object_detection=enable_object_detection,
        detection_confidence=detection_confidence
    )
    
    logger.info(f"SDK processing completed: {results['total_frames_processed']} frames processed")
    return results['stored_ids']
async def generate_text_embedding(
    text: str, 
    text_metadata: dict = {}, 
    use_qwen_for_long_text: bool = True,
    qwen_threshold: int = 500
) -> List[str]:
    """
    Generate and persist text embeddings using either SDK or API mode.
    
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
        processing_mode = (settings.EMBEDDING_PROCESSING_MODE or "sdk").lower()
        use_sdk_mode = processing_mode == "sdk"
        model_name = (settings.MULTIMODAL_EMBEDDING_MODEL_NAME or "").strip() or "<unspecified>"
        
        logger.info(
            f"Processing text embedding (length: {text_length}, use_qwen_hint={use_qwen_hint}, mode: {processing_mode}, model: {model_name})"
        )

        if use_sdk_mode:
            sdk_client = get_sdk_client()
            if not sdk_client.supports_text:
                raise ValueError(
                    f"Configured SDK model '{model_name}' does not support text embeddings (processing mode: '{processing_mode}'). "
                    "Please verify your EMBEDDING_MODEL_NAME setting and ensure the selected model supports text embedding."
                )

            ids = sdk_client.store_text_embedding(text=text, metadata=text_metadata)
            logger.info(
                "Stored text embedding via SDK client, ID: %s",
                ids[0] if ids else "<none>",
            )
            return ids

        logger.info("Using multimodal embedding API for text")
        vdms_client = _get_cached_vdms_client(use_case="text")
        ids = vdms_client.store_text_embedding(text, metadata=text_metadata)
        logger.info(
            "Stored text embedding via multimodal API, ID: %s",
            ids[0] if ids else "<none>",
        )
        return ids

    except Exception as ex:
        logger.error(f"Error in smart text embedding generation: {ex}")
        raise
