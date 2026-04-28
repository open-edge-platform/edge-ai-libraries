# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
SDK-based Embedding Helper for Optimized Video Processing

This module provides optimized video processing using the multimodal embedding service
as an SDK for direct function calls. Final implementation strategy:

1. **SDK-based Embedding Generation**: Direct function calls instead of HTTP API
2. **Parallel Processing**: Process embeddings in parallel using ThreadPoolExecutor
3. **Bulk Vector DB Storage**: Store all embeddings in VDMS in single bulk operation
4. **Memory-based Video Processing**: Process video directly from memory using PyAV

Performance Benefits:
- Eliminates network latency for embedding generation
- Parallel embedding generation for better CPU utilization
- Bulk storage reduces VDMS operation overhead
- Memory-only processing avoids disk I/O
"""

import datetime
import gc
import json
import multiprocessing
import os
import queue
import signal
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from multiprocessing import shared_memory
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

import numpy as np
from PIL import Image

from src.common import logger
from src.common import settings
from src.common import sanitize_for_log
from src.common import get_tracer
from src.common import shutdown_tracer
from src.common import init_tracer
from src.common import now_us
from src.common import Tracer

from src.core.embedding.decoder import SharedMemoryPool
from src.core.embedding.decoder import VideoFrameConfig
from src.core.embedding.decoder import VideoFrameExtractor
from src.core.embedding.sdk_client import SDKVDMSClient

# Global SDK client instance (initialized once per worker process)
_sdk_client: Optional[SDKVDMSClient] = None

# Global object detector instance (initialized once per worker process)
_global_detector = None
DONE = object()  # Sentinel value to signal completion


@dataclass
class FrameMetadata:
    video_id: str = "unknown"
    filename: str = "unknown"
    bucket_name: str = "unknown"
    extended_frame_id: str = ""
    frame_number: int = 0
    timestamp: float = 0.0
    frame_type: str = "FULL_FRAME"
    total_frames: Optional[int] = None
    fps: Optional[float] = None
    video_duration: Optional[float] = None
    video_duration_seconds: Optional[float] = None
    tags: List[str] = field(default_factory=list)
    video_url: str = ""
    video_rel_url: str = ""
    video_index: int = 0
    created_at: Optional[datetime.datetime] = None


    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def get_pipeline_config():
    """Get optimized pipeline configuration based on CPU cores."""
    from src.common import settings

    cpu_cores = multiprocessing.cpu_count()
    enable_pipelines = os.getenv("ENABLE_PARALLEL_PIPELINE", "true").lower() == "true"
    use_openvino = settings.SDK_USE_OPENVINO

    performance_mode = (
        (os.getenv("OV_PERFORMANCE_MODE") or os.getenv("OPENVINO_PERFORMANCE_MODE") or "")
        .strip()
        .upper()
    )

    max_workers_env = os.getenv("MAX_PARALLEL_WORKERS", None)
    if max_workers_env:
        try:
            max_workers = max(1, int(max_workers_env))
        except ValueError:
            logger.warning("Ignoring non-integer MAX_PARALLEL_WORKERS=%s", max_workers_env)
            max_workers = max(1, cpu_cores // 4)
    else:
        if use_openvino:
            base_worker_count = max(1, cpu_cores // 4)

            ov_parallel_limit: Optional[int] = None
            for env_key in (
                "OV_PERFORMANCE_HINT_NUM_REQUESTS",
                "PERFORMANCE_HINT_NUM_REQUESTS",
                "OV_NUM_STREAMS",
            ):
                env_value = os.getenv(env_key)
                if not env_value:
                    continue
                try:
                    resolved_value = max(1, int(env_value))
                except ValueError:
                    logger.warning(f"Ignoring non-integer value for {env_key}: {env_value}")
                    continue

                ov_parallel_limit = resolved_value
                logger.info(f"Resolved OpenVINO parallel limit from {env_key}={resolved_value}")
                break

            max_workers = (
                base_worker_count
                if ov_parallel_limit is None
                else min(base_worker_count, ov_parallel_limit)
            )
            logger.info(
                "Using optimized worker count: %s workers for %s CPU cores (OpenVINO limit: %s)",
                max_workers,
                cpu_cores,
                ov_parallel_limit if ov_parallel_limit is not None else "auto",
            )
        else:
            # PyTorch execution is more CPU-bound; keep the worker count conservative to avoid thrashing.
            base_worker_count = cpu_cores // 16
            if base_worker_count == 0:
                base_worker_count = 1
            base_worker_count = min(base_worker_count, 8)

            max_workers = base_worker_count
            logger.info(
                "Using PyTorch worker count: %s workers for %s CPU cores (OpenVINO disabled)",
                max_workers,
                cpu_cores,
            )

    config = {
        "pipeline_count": max_workers,
        "batch_size": max(1, settings.EMBEDDING_BATCH_SIZE),
        "enable_pipelines": enable_pipelines,
        "use_openvino": use_openvino,
    }

    if performance_mode:
        logger.info(
            "Pipeline config: %s pipelines, batch size %s, OpenVINO: %s (performance_mode=%s)",
            config["pipeline_count"],
            config["batch_size"],
            use_openvino,
            performance_mode,
        )
    else:
        logger.info(
            "Pipeline config: %s pipelines, batch size %s, OpenVINO: %s",
            config["pipeline_count"],
            config["batch_size"],
            use_openvino,
        )
    return config


def get_sdk_client() -> SDKVDMSClient:
    """
    Get or create a singleton SDK client instance.

    This ensures we reuse the same model instance across requests,
    avoiding the overhead of loading the model multiple times.

    Returns:
        SDKVDMSClient instance
    """
    global _sdk_client

    if _sdk_client is None:
        logger.info("Initializing SDK client for embedding generation")

        # Validate that MULTIMODAL_EMBEDDING_MODEL_NAME is provided when using SDK mode
        if not settings.MULTIMODAL_EMBEDDING_MODEL_NAME:
            raise ValueError(
                "MULTIMODAL_EMBEDDING_MODEL_NAME must be explicitly provided when using SDK embedding mode - no default model is allowed"
            )

        # Ensure OpenVINO models directory exists if using OpenVINO
        if settings.SDK_USE_OPENVINO:
            import os

            os.makedirs(settings.OV_MODELS_DIR, exist_ok=True)
            logger.info(
                f"Using OpenVINO optimization with models directory: {settings.OV_MODELS_DIR}"
            )
        else:
            logger.info("Using PyTorch native model (OpenVINO disabled)")

        _sdk_client = SDKVDMSClient(
            model_id=settings.MULTIMODAL_EMBEDDING_MODEL_NAME,
            device=settings.DEVICE,
            use_openvino=settings.SDK_USE_OPENVINO,
            ov_models_dir=settings.OV_MODELS_DIR,
        )
        logger.info("SDK client initialized successfully")

    return _sdk_client


def get_global_detector(enable_object_detection: bool = True, detection_confidence: float = 0.85):
    """
    Get or create a singleton global object detector instance.

    This ensures we reuse the same detector instance across requests,
    avoiding the overhead of loading the model multiple times.

    Args:
        enable_object_detection: Whether to enable object detection
        detection_confidence: Confidence threshold for detection

    Returns:
        Object detector instance or None if disabled/failed
    """
    global _global_detector

    if not enable_object_detection:
        return None

    if _global_detector is None:
        logger.info("Initializing global object detector...")

        try:
            from src.core.utils.common_utils import create_detector_instance

            # Create detector with specified confidence
            _global_detector = create_detector_instance(
                config=None,
                enable_object_detection=enable_object_detection,
                detection_confidence=detection_confidence,
            )

            if _global_detector is None:
                logger.warning("Global object detector initialization failed")
            else:
                logger.info(
                    "Global object detector initialized with confidence threshold: %s",
                    sanitize_for_log(detection_confidence, max_length=32),
                )
                
        except Exception as e:
            logger.error(f"Failed to initialize global object detector: {e}")
            _global_detector = None

    return _global_detector


def preload_object_detector(
    enable_object_detection: bool = True, detection_confidence: float = 0.85
) -> bool:
    """
    Preload the object detection model and perform warmup.

    This function should be called during app startup to avoid cold start delays
    on the first API request that uses object detection.

    Args:
        enable_object_detection: Whether to enable object detection
        detection_confidence: Confidence threshold for detection

    Returns:
        bool: True if preload successful, False otherwise
    """
    try:
        if not enable_object_detection:
            logger.info("Object detection disabled - skipping preload")
            return True

        logger.info("Preloading object detection model...")
        logger.info(
            f"Object Detection Configuration: enabled={enable_object_detection}, confidence={detection_confidence}, device={settings.DEVICE}"
        )

        # Initialize the global detector (this loads the model)
        detector = get_global_detector(enable_object_detection, detection_confidence)

        if detector is not None:
            # Perform model warmup with a small test image
            import numpy as np
            from PIL import Image

            # Create a small test image (640x640 for YOLOX optimal size)
            test_image = Image.fromarray(np.random.randint(0, 255, (640, 640, 3), dtype=np.uint8))

            # Run test detection to warm up the model
            try:
                test_detections = detector.detect(test_image)
                logger.info(
                    f"Object detection model preloaded successfully! Model cached and ready (warmup found {len(test_detections) if test_detections else 0} test objects)"
                )
                return True
            except Exception as e:
                logger.warning(f"Object detector initialized but test detection failed: {e}")
                return True  # Still consider success since model is loaded
        else:
            logger.warning("Object detector preload failed - model not loaded")
            return False

    except Exception as e:
        logger.error(f"Failed to preload object detection model: {e}")
        return False


def preload_sdk_client() -> bool:
    """
    Preload the SDK client and perform model warmup.

    This function should be called during app startup to avoid cold start delays
    on the first API request.

    Returns:
        bool: True if preload successful, False otherwise
    """
    try:
        logger.info("Preloading SDK client and warming up model...")
        logger.info(
            f"SDK Configuration: Model={settings.MULTIMODAL_EMBEDDING_MODEL_NAME}, Device={settings.DEVICE}, OpenVINO={settings.SDK_USE_OPENVINO}"
        )

        # Validate GPU setup if GPU device is requested
        if settings.DEVICE.upper() == "GPU":
            logger.info("GPU device requested - validating GPU setup...")

            # Check if running in OpenVINO mode (recommended for GPU)
            if not settings.SDK_USE_OPENVINO:
                logger.warning(
                    "GPU device specified but OpenVINO is disabled. For best GPU performance, enable OpenVINO with GPU device."
                )
            else:
                logger.info(
                    "GPU device with OpenVINO enabled - optimal configuration for GPU acceleration"
                )
        # Initialize the client (this loads the model)
        sdk_client = get_sdk_client()

        if sdk_client.supports_image:
            # Perform image warmup with a small test pattern
            import numpy as np

            test_image = Image.fromarray(np.random.randint(0, 255, (224, 224, 3), dtype=np.uint8))

            test_embedding = sdk_client.generate_embeddings_for_images([test_image])

            if test_embedding is not None:
                openvino_status = (
                    "OpenVINO optimized" if settings.SDK_USE_OPENVINO else "PyTorch native"
                )
                logger.info(
                    "SDK client preloaded successfully! %s model cached and ready (%d-dim embeddings)",
                    openvino_status,
                    len(test_embedding),
                )
                return True
            logger.warning("SDK client initialized but image warmup embedding failed")
            return False

        if sdk_client.supports_text:
            warmup_embedding = sdk_client.generate_embedding_for_text("sdk-warmup")
            if warmup_embedding is not None:
                openvino_status = (
                    "OpenVINO optimized" if settings.SDK_USE_OPENVINO else "PyTorch native"
                )
                logger.info(
                    "SDK client preloaded for text embeddings! %s model cached and ready (%d-dim embeddings)",
                    openvino_status,
                    len(warmup_embedding),
                )
                return True
            logger.warning("SDK client text warmup failed")
            return False

        logger.error(
            "SDK client model %s does not report support for text or image embeddings; warmup skipped",
            settings.MULTIMODAL_EMBEDDING_MODEL_NAME,
        )
        return False

    except Exception as e:
        logger.error(f"Failed to preload SDK client: {e}")
        return False


class SimplePipelineManager:
    """Simple pipeline manager for parallel frame processing with conditional thread safety and object detection."""

    def __init__(
        self,
        sdk_client: SDKVDMSClient,
        enable_object_detection: bool = False,
        detection_confidence: float = 0.85,
    ):
        self.master_sdk_client = sdk_client
        self.config = get_pipeline_config()
        self._thread_local = threading.local()
        self.supports_image_embeddings = sdk_client.supports_image

        # Object detection configuration
        self.enable_object_detection = enable_object_detection
        self.detection_confidence = detection_confidence
        self.detector = None

        # Initialize object detector if needed
        if self.enable_object_detection:
            self._initialize_object_detector()

        # Log device consistency across all components
        logger.info(
            f"Device consistency: Processing={settings.DEVICE}, "
            f"Embedding={sdk_client.device}, "
            f"Detection={'N/A' if not self.enable_object_detection else self.detector.device if self.detector else 'Failed'}, "
            f"ImageEmbeddingsSupported={self.supports_image_embeddings}"
        )

        # Remove inference locking - use thread-safe infer_new_request pattern
        self._inference_lock = None
        if self.config["use_openvino"]:
            logger.info(
                "OpenVINO parallel mode: Using thread-safe infer_new_request pattern (maximum performance)"
            )
        else:
            logger.info(
                "PyTorch mode: Using shared model instance across all threads (thread-safe)"
            )

    @staticmethod
    def _summarize_stage_times(samples: List[float]) -> Dict[str, float]:
        """Compute aggregate statistics for a collection of stage timings."""
        if not samples:
            return {
                "total": 0.0,
                "avg": 0.0,
                "max": 0.0,
                "min": 0.0,
                "count": 0,
            }

        total = float(sum(samples))
        return {
            "total": total,
            "avg": total / len(samples),
            "max": max(samples),
            "min": min(samples),
            "count": len(samples),
        }

    def _initialize_object_detector(self):
        """Initialize object detector for frame processing."""
        logger.info("Using global object detector for SDK mode...")

        # Use the global detector instance instead of creating a new one
        self.detector = get_global_detector(
            enable_object_detection=self.enable_object_detection,
            detection_confidence=self.detection_confidence,
        )

        if self.detector is None:
            logger.warning("Object detector not available - disabling object detection")
            self.enable_object_detection = False
        else:
            logger.info(
                "Using global object detector with confidence threshold: %s",
                sanitize_for_log(self.detection_confidence, max_length=32),
            )
        
    
    def _process_frame_with_detection(self, frame_numpy: np.ndarray, frame_metadata: Dict[str, Any]) -> List[Tuple[Image.Image, Dict[str, Any]]]:
        """
        Process a single frame and optionally detect objects to create crops.

        Args:
            frame_numpy: Frame as numpy array (H, W, C)
            frame_metadata: Metadata for the frame

        Returns:
            List of (image, metadata) tuples for processing
        """
        results = []

        # Always include the full frame
        frame_pil = Image.fromarray(frame_numpy)
        results.append((frame_pil, frame_metadata))

        # If object detection is enabled, detect objects and create crops
        if self.enable_object_detection and self.detector is not None:
            try:
                detections = self.detector.detect(frame_numpy, return_metadata=True)

                if detections:
                    logger.debug(
                        "Detected %d objects in frame %s",
                        len(detections),
                        frame_metadata.get("frame_id", "unknown"),
                    )

                    for crop_idx, det_meta in enumerate(detections):
                        try:
                            box = det_meta.get("bbox")
                            score = det_meta.get("confidence")
                            class_id = det_meta.get("class_id")
                            class_name = det_meta.get("class_name")

                            if not box or score is None or class_id is None:
                                logger.debug(
                                    "Skipping detection %d due to incomplete metadata", crop_idx
                                )
                                continue

                            x1, y1, x2, y2 = box

                            h, w = frame_numpy.shape[:2]
                            x1 = max(0, min(int(x1), w - 1))
                            y1 = max(0, min(int(y1), h - 1))
                            x2 = max(x1 + 1, min(int(x2), w))
                            y2 = max(y1 + 1, min(int(y2), h))

                            if (x2 - x1) < 10 or (y2 - y1) < 10:
                                continue

                            crop = frame_numpy[y1:y2, x1:x2]
                            crop_pil = Image.fromarray(crop)

                            crop_metadata = frame_metadata.copy()
                            crop_metadata.update(
                                {
                                    "frame_type": "detected_crop",
                                    "is_detected_crop": True,
                                    "crop_index": crop_idx,
                                    "detection_confidence": float(score),
                                    "crop_bbox": [int(x1), int(y1), int(x2), int(y2)],
                                    "detected_class_id": int(class_id),
                                    "detected_label": class_name,
                                    "merged_boxes_count": det_meta.get("merged_boxes_count"),
                                    "context_expansion_applied": det_meta.get(
                                        "context_expansion_applied"
                                    ),
                                    "frame_id": f"{frame_metadata.get('frame_id', 'unknown')}_crop_{crop_idx}",
                                }
                            )

                            results.append((crop_pil, crop_metadata))

                        except Exception as e:
                            logger.warning(
                                "Failed to create crop %d from frame %s: %s",
                                crop_idx,
                                frame_metadata.get("frame_id", "unknown"),
                                e,
                            )
                            continue

            except Exception as e:
                logger.warning(
                    "Object detection failed for frame %s: %s",
                    frame_metadata.get("frame_id", "unknown"),
                    e,
                )

        return results

    def _process_frames_with_parallel_detection(
        self, all_frames: List[np.ndarray], all_metadata: List[Dict[str, Any]]
    ) -> Tuple[List[Image.Image], List[Dict[str, Any]]]:
        """
        Process frames with parallel object detection.

        Args:
            all_frames: List of frame numpy arrays
            all_metadata: List of frame metadata

        Returns:
            Tuple of (images_list, metadata_list) including original frames and detected crops
        """
        logger.info(f"Starting parallel object detection on {len(all_frames)} frames")

        # Create batches for parallel detection processing
        detection_batch_size = max(1, len(all_frames) // self.config["pipeline_count"])
        detection_batches = []

        for i in range(0, len(all_frames), detection_batch_size):
            batch_frames = all_frames[i : i + detection_batch_size]
            batch_metadata = all_metadata[i : i + detection_batch_size]
            detection_batches.append((batch_frames, batch_metadata))

        logger.info(
            f"Created {len(detection_batches)} detection batches (batch_size={detection_batch_size})"
        )

        # Process detection batches in parallel
        all_images_for_embedding = []
        all_metadata_for_embedding = []

        with ThreadPoolExecutor(max_workers=self.config["pipeline_count"]) as executor:
            detection_futures = [
                executor.submit(self._process_detection_batch, batch_frames, batch_metadata)
                for batch_frames, batch_metadata in detection_batches
            ]

            # Process completed futures as they finish (true parallel processing)
            for future in as_completed(detection_futures):
                batch_images, batch_metadata = future.result()
                all_images_for_embedding.extend(batch_images)
                all_metadata_for_embedding.extend(batch_metadata)

        logger.info(
            f"Parallel object detection completed: {len(all_frames)} frames -> {len(all_images_for_embedding)} items"
        )
        return all_images_for_embedding, all_metadata_for_embedding

    def _process_detection_batch(
        self, batch_frames: List[np.ndarray], batch_metadata: List[Dict[str, Any]]
    ) -> Tuple[List[Image.Image], List[Dict[str, Any]]]:
        """
        Process a batch of frames for object detection.

        Args:
            batch_frames: Batch of frame numpy arrays
            batch_metadata: Batch of frame metadata

        Returns:
            Tuple of (images_list, metadata_list) for this batch
        """
        batch_images = []
        batch_metadata_results = []

        for frame_numpy, frame_metadata in zip(batch_frames, batch_metadata):
            # Process frame with detection (returns full frame + detected crops)
            frame_results = self._process_frame_with_detection(frame_numpy, frame_metadata)

            for image_pil, metadata in frame_results:
                batch_images.append(image_pil)
                batch_metadata_results.append(metadata)

        logger.debug(
            f"Detection batch processed: {len(batch_frames)} frames -> {len(batch_images)} items"
        )
        return batch_images, batch_metadata_results

    def process_frames_parallel(
        self, all_frames: List[np.ndarray], all_metadata: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Process frames in parallel for embedding generation with optional object detection and per-batch storage."""
        logger.info(
            "Processing %s frames with %s maximum parallel workers",
            sanitize_for_log(len(all_frames), max_length=32),
            sanitize_for_log(self.config['pipeline_count'], max_length=32),
        )
        
        if self.enable_object_detection:
            logger.info(
                "Object detection enabled with confidence threshold: %s",
                sanitize_for_log(self.detection_confidence, max_length=32),
            )
        
        try:
            # Create batches of frames for parallel processing
            logger.info(
                f"About to create batches from {len(all_frames)} frames with batch_size={self.config['batch_size']}"
            )
            batches = self.create_frame_batches(all_frames, all_metadata)
            detection_status = (
                "with object detection"
                if self.enable_object_detection
                else "without object detection"
            )
            logger.info(
                f"Created {len(batches)} batches for parallel processing ({detection_status})"
            )

            # Process batches in parallel - each batch will do optional object detection + embedding generation + immediate storage
            total_embeddings_stored = 0
            all_stored_ids = []
            batch_processing_times: List[float] = []
            detection_times: List[float] = []
            embedding_times: List[float] = []
            storage_times: List[float] = []
            total_items_after_detection = 0
            completed_batches: List[Dict[str, Any]] = []

            logger.info(
                f"Starting parallel execution of {len(batches)} batches with {self.config['pipeline_count']} maximum workers"
            )

            parallel_start_time = time.time()
            with ThreadPoolExecutor(max_workers=self.config["pipeline_count"]) as executor:
                total_batches = len(batches)
                future_to_index: Dict[Any, int] = {}
                batch_futures = []
                for batch_index, (batch_frames, batch_metadata) in enumerate(batches, start=1):
                    future = executor.submit(
                        self._process_single_batch,
                        batch_frames,
                        batch_metadata,
                        batch_index,
                        total_batches,
                    )
                    batch_futures.append(future)
                    future_to_index[future] = batch_index

                logger.info(f"Submitted {len(batch_futures)} batch jobs to thread pool")
                logger.info(
                    f"True parallel processing enabled - batches will complete in any order as they finish"
                )

                # Process completed batches as they finish (true parallel processing)
                batch_counter = 0
                timeout_per_batch = 300  # 5 minutes per batch maximum
                for future in as_completed(
                    batch_futures, timeout=timeout_per_batch * len(batch_futures)
                ):
                    batch_counter += 1
                    try:
                        batch_result = future.result()
                        embeddings_count = batch_result["embeddings_count"]
                        stored_ids = batch_result["stored_ids"]
                        processing_time = batch_result["processing_time"]
                        batch_index = future_to_index.get(future, batch_counter)
                        batch_detection_time = batch_result.get("detection_time", 0.0)
                        batch_embedding_time = batch_result.get("embedding_time", 0.0)
                        batch_storage_time = batch_result.get("storage_time", 0.0)
                        batch_items_after_detection = batch_result.get("items_after_detection", 0)

                        total_embeddings_stored += embeddings_count
                        all_stored_ids.extend(stored_ids)
                        batch_processing_times.append(processing_time)
                        detection_times.append(batch_detection_time)
                        embedding_times.append(batch_embedding_time)
                        storage_times.append(batch_storage_time)
                        total_items_after_detection += batch_items_after_detection
                        completed_batches.append(batch_result)

                        logger.info(
                            f"Batch {batch_index}/{len(batch_futures)} completed: {embeddings_count} embeddings stored"
                        )
                    except Exception as e:
                        failed_index = future_to_index.get(future, batch_counter)
                        logger.error(f"Batch {failed_index} failed: {e}")
                        # Continue processing other batches

            parallel_time = time.time() - parallel_start_time
            logger.info(
                f"Parallel processing completed: {total_embeddings_stored} embeddings generated and stored"
            )

            detection_stats = self._summarize_stage_times(detection_times)
            embedding_stats = self._summarize_stage_times(embedding_times)
            storage_stats = self._summarize_stage_times(storage_times)
            batch_time_stats = self._summarize_stage_times(batch_processing_times)

            avg_batch_time = batch_time_stats.get("avg", 0.0)
            max_batch_time = batch_time_stats.get("max", 0.0)

            def _build_stage_summary(stats: Dict[str, float]) -> Dict[str, float]:
                avg_time = stats.get("avg", 0.0)
                return {
                    "avg_s": avg_time,
                    "max_s": stats.get("max", 0.0),
                    "total_s": stats.get("total", 0.0),
                    "avg_pct_of_batch": (
                        (avg_time / avg_batch_time * 100.0) if avg_batch_time else 0.0
                    ),
                }

            stage_breakdown = {
                "detection": _build_stage_summary(detection_stats),
                "embedding": _build_stage_summary(embedding_stats),
                "storage": _build_stage_summary(storage_stats),
            }
            logger.info(
                "Performance: total parallel time %.3fs, avg batch time %.3fs, max batch time %.3fs",
                parallel_time,
                avg_batch_time,
                max_batch_time,
            )

            return {
                "total_embeddings": total_embeddings_stored,
                "stored_ids": all_stored_ids,
                "processing_time": parallel_time,
                "batches_processed": len(batches),
                "avg_batch_time": avg_batch_time,
                "max_batch_time": max_batch_time,
                "stage_breakdown": stage_breakdown,
                "batch_stats": {
                    "avg_s": avg_batch_time,
                    "max_s": max_batch_time,
                    "count": batch_time_stats.get("count", 0),
                },
                "batch_details": completed_batches,
                "pipeline_config": {
                    "pipeline_count": self.config.get("pipeline_count"),
                    "batch_size": self.config.get("batch_size"),
                    "use_openvino": self.config.get("use_openvino"),
                    "object_detection_enabled": self.enable_object_detection,
                    "detection_confidence": self.detection_confidence,
                },
                "post_detection_items": total_items_after_detection,
                "input_frames": len(all_frames),
            }

        except Exception as e:
            logger.error(f"Error in parallel processing: {e}")
            return {
                "total_embeddings": 0,
                "stored_ids": [],
                "processing_time": 0,
                "batches_processed": 0,
                "avg_batch_time": 0.0,
                "max_batch_time": 0.0,
                "stage_breakdown": {
                    "detection": {
                        "avg_s": 0.0,
                        "max_s": 0.0,
                        "total_s": 0.0,
                        "avg_pct_of_batch": 0.0,
                    },
                    "embedding": {
                        "avg_s": 0.0,
                        "max_s": 0.0,
                        "total_s": 0.0,
                        "avg_pct_of_batch": 0.0,
                    },
                    "storage": {
                        "avg_s": 0.0,
                        "max_s": 0.0,
                        "total_s": 0.0,
                        "avg_pct_of_batch": 0.0,
                    },
                },
                "batch_stats": {"avg_s": 0.0, "max_s": 0.0, "count": 0},
                "batch_details": completed_batches,
                "pipeline_config": {
                    "pipeline_count": self.config.get("pipeline_count"),
                    "batch_size": self.config.get("batch_size"),
                    "use_openvino": self.config.get("use_openvino"),
                    "object_detection_enabled": self.enable_object_detection,
                    "detection_confidence": self.detection_confidence,
                },
                "post_detection_items": 0,
                "input_frames": len(all_frames),
            }

    def create_frame_batches(
        self, frames: List[np.ndarray], metadata: List[Dict[str, Any]]
    ) -> List[tuple]:
        """Create batches of frames for parallel processing (including object detection)."""
        batch_size = self.config["batch_size"]
        total_frames = len(frames)

        logger.info(f"Creating frame batches: {total_frames} frames, batch_size={batch_size}")

        batches = []

        for i in range(0, total_frames, batch_size):
            batch_frames = frames[i : i + batch_size]
            batch_metadata = metadata[i : i + batch_size]
            batch_num = len(batches) + 1

            logger.debug(
                f"Batch {batch_num}: frames {i} to {min(i + batch_size - 1, total_frames - 1)} ({len(batch_frames)} frames)"
            )
            batches.append((batch_frames, batch_metadata))

        logger.info(
            f"Created {len(batches)} batches from {total_frames} frames (avg {total_frames/len(batches):.1f} frames/batch)"
        )
        return batches

    def _process_single_batch(
        self,
        batch_frames: List[np.ndarray],
        batch_metadata: List[Dict],
        batch_index: int,
        total_batches: int,
    ) -> Dict[str, Any]:
        """Process a single batch of frames: object detection + embedding generation + immediate storage."""
        batch_start_time = time.time()
        try:
            logger.info(
                f"[Batch {batch_index}/{total_batches}] Processing {len(batch_frames)} frames "
                f"(object detection: {self.enable_object_detection})"
            )

            if not self.supports_image_embeddings:
                logger.info(
                    "Embedding model %s does not support image/video embeddings; skipping batch %d",
                    self.master_sdk_client.model_id,
                    batch_index,
                )
                return {
                    "status": "skipped_no_image_support",
                    "embeddings_count": 0,
                    "stored_ids": [],
                    "processing_time": time.time() - batch_start_time,
                    "detection_time": 0.0,
                    "embedding_time": 0.0,
                    "storage_time": 0.0,
                    "items_after_detection": 0,
                    "input_frames": len(batch_frames),
                }

            # Step 1: Process frames with object detection to expand the batch
            logger.debug(f"Step 1: Starting object detection for {len(batch_frames)} frames")
            all_images_for_embedding = []
            all_metadata_for_embedding = []

            detection_start = time.time()
            for i, (frame_numpy, frame_metadata) in enumerate(zip(batch_frames, batch_metadata)):
                logger.debug(f"Processing frame {i+1}/{len(batch_frames)} for object detection")
                # Process frame with detection (returns full frame + detected crops)
                frame_results = self._process_frame_with_detection(frame_numpy, frame_metadata)

                for image_pil, metadata in frame_results:
                    all_images_for_embedding.append(image_pil)
                    all_metadata_for_embedding.append(metadata)
            detection_time = time.time() - detection_start

            expansion_info = (
                f"(including crops)" if self.enable_object_detection else "(frames only)"
            )
            logger.info(
                f"[Batch {batch_index}/{total_batches}] Expanded from {len(batch_frames)} frames "
                f"to {len(all_images_for_embedding)} items {expansion_info} in {detection_time:.3f}s"
            )
            items_after_detection = len(all_images_for_embedding)
            # Step 2: Generate embeddings for all images in the expanded batch
            logger.debug(
                f"Step 2: Starting embedding generation for {len(all_images_for_embedding)} images"
            )
            thread_sdk_client = self.master_sdk_client

            # Use parallel-safe embedding generation
            # The multimodal embedding service now uses thread-safe infer_new_request
            logger.debug(
                f"[Batch {batch_index}/{total_batches}] Using parallel mode - no locking needed with infer_new_request"
            )
            embedding_start = time.time()
            embeddings = thread_sdk_client.generate_embeddings_for_images(all_images_for_embedding)
            embedding_time = time.time() - embedding_start
            logger.debug(
                f"[Batch {batch_index}/{total_batches}] Step 2 completed: Generated {len(embeddings)} "
                f"embeddings in {embedding_time:.3f}s"
            )

            # Step 3: Prepare valid embeddings and metadata for storage
            logger.debug(f"Step 3: Validating embeddings")
            valid_embeddings = []
            valid_metadatas = []
            for i, (image, metadata, embedding) in enumerate(
                zip(all_images_for_embedding, all_metadata_for_embedding, embeddings)
            ):
                if embedding is not None:
                    valid_embeddings.append(embedding)
                    valid_metadatas.append(metadata)
                else:
                    if self.supports_image_embeddings:
                        logger.warning(
                            f"Failed to generate embedding for image {metadata['frame_id']}"
                        )
                    else:
                        logger.debug(
                            "Skipping embedding for %s because model does not support image modality",
                            metadata["frame_id"],
                        )
            logger.debug(
                f"[Batch {batch_index}/{total_batches}] Step 3 completed: {len(valid_embeddings)} valid "
                f"embeddings out of {len(embeddings)}"
            )

            # Step 4: Store embeddings immediately for this batch (prevents OutOfJournalSpace)
            logger.debug(f"Step 4: Starting storage for {len(valid_embeddings)} embeddings")
            storage_start = time.time()
            stored_ids = []
            if valid_embeddings:
                logger.debug(
                    f"[Batch {batch_index}/{total_batches}] Storing {len(valid_embeddings)} embeddings immediately"
                )
                stored_ids = thread_sdk_client.store_frame_embeddings(
                    valid_embeddings, valid_metadatas
                )
                logger.debug(
                    f"[Batch {batch_index}/{total_batches}] Successfully stored {len(stored_ids)} embeddings"
                )
            storage_time = time.time() - storage_start
            logger.debug(
                f"[Batch {batch_index}/{total_batches}] Step 4 completed: Storage took {storage_time:.3f}s"
            )

            batch_time = time.time() - batch_start_time
            logger.info(
                f"[Batch {batch_index}/{total_batches}] Completed: {len(valid_embeddings)} embeddings "
                f"(detection: {detection_time:.3f}s, embedding: {embedding_time:.3f}s, "
                f"storage: {storage_time:.3f}s, total: {batch_time:.3f}s)"
            )

            return {
                "batch_index": batch_index,
                "embeddings_count": len(valid_embeddings),
                "stored_ids": stored_ids,
                "processing_time": batch_time,
                "detection_time": detection_time,
                "embedding_time": embedding_time,
                "storage_time": storage_time,
                "items_after_detection": items_after_detection,
                "input_frames": len(batch_frames),
            }

        except Exception as e:
            logger.error(f"[Batch {batch_index}/{total_batches}] Error processing batch: {e}")
            return {
                "batch_index": batch_index,
                "embeddings_count": 0,
                "stored_ids": [],
                "processing_time": time.time() - batch_start_time,
                "detection_time": detection_time if "detection_time" in locals() else 0.0,
                "embedding_time": embedding_time if "embedding_time" in locals() else 0.0,
                "storage_time": storage_time if "storage_time" in locals() else 0.0,
                "items_after_detection": (
                    len(all_images_for_embedding) if "all_images_for_embedding" in locals() else 0
                ),
                "input_frames": len(batch_frames),
            }

    def _process_sequential_fallback(
        self, frames: List[np.ndarray], metadata: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Fallback to sequential processing with object detection support."""
        logger.warning("Using sequential fallback processing")
        embeddings = []

        # Get the appropriate SDK client based on mode
        thread_sdk_client = self.master_sdk_client

        for frame_numpy, frame_metadata in zip(frames, metadata):
            try:
                # Process frame with detection (returns full frame + detected crops)
                frame_results = self._process_frame_with_detection(frame_numpy, frame_metadata)

                for image_pil, metadata_item in frame_results:
                    try:
                        # Use parallel-safe embedding generation
                        embedding = thread_sdk_client.generate_embedding_for_image(image_pil)

                        if embedding:
                            embeddings.append({"embedding": embedding, "metadata": metadata_item})
                    except Exception as e:
                        logger.error(
                            f"Error generating embedding for {metadata_item.get('frame_id', 'unknown')}: {e}"
                        )
                        continue

            except Exception as e:
                logger.error(f"Error in sequential processing: {e}")
                continue

        return embeddings


def generate_video_embedding_sdk(
    video_content: bytes,
    metadata_dict: Dict[str, Any],
    frame_interval: int = 15,
    enable_object_detection: bool = False,
    detection_confidence: float = 0.85,
) -> Dict[str, Any]:
    """
    Generate video embeddings using SDK approach with parallel processing.

    Args:
        video_content: Video content as bytes
        metadata_dict: Video metadata dictionary
        frame_interval: Number of frames between extractions
        enable_object_detection: Whether to enable object detection (currently not implemented)
        detection_confidence: Confidence threshold (currently not used)

    Returns:
        Dictionary containing processing results and timing information
    """
    total_start_time = now_us()
    logger.info(
        "Starting SDK video processing with frame_interval=%s",
        sanitize_for_log(frame_interval, max_length=32),
    )
    
    try:
        # Get SDK client
        sdk_client = get_sdk_client()

        if not sdk_client.supports_image:
            logger.info(
                "Embedding model %s reports no image/video support; skipping video embedding pipeline",
                sdk_client.model_id,
            )
            total_time = (now_us() - total_start_time) / 1_000_000
            return {
                "status": "skipped_no_image_support",
                "stored_ids": [],
                "total_embeddings": 0,
                "total_frames_processed": 0,
                "frame_interval": frame_interval,
                "timing": {
                    "frame_extraction_time": 0.0,
                    "parallel_stage_time": 0.0,
                    "pipeline_wall_time": total_time,
                    "avg_batch_time": 0.0,
                    "max_batch_time": 0.0,
                    "stage_breakdown": {},
                },
                "frame_counts": {
                    "extracted_frames": 0,
                    "post_detection_items": 0,
                    "stored_embeddings": 0,
                },
                "processing_mode": "sdk_simple_pipeline_with_batch_storage",
            }
        # Process video using simple pipeline approach
        result = _process_video_from_memory_simple_pipeline(
            video_content=video_content,
            sdk_client=sdk_client,
            metadata_dict=metadata_dict,
            frame_interval=frame_interval,
            enable_object_detection=enable_object_detection,
            detection_confidence=detection_confidence,
        )

        total_time = (now_us() - total_start_time) / 1_000_000
        logger.info(f"SDK video processing completed in {total_time:.3f}s")
        return result

    except Exception as e:
        total_time = (now_us() - total_start_time) / 1_000_000
        logger.error(f"SDK video processing failed after {total_time:.3f}s: {e}")
        raise


def _process_video_from_memory_simple_pipeline(
    video_content: bytes,
    sdk_client: SDKVDMSClient,
    metadata_dict: Dict[str, Any],
    frame_interval: int,
    enable_object_detection: bool,
    detection_confidence: float,
    shutdown_event: Optional[threading.Event] = None,
) -> Dict[str, Any]:
    """
    Process video from memory using simple parallel pipeline approach.

    This is the main implementation that extracts frames from video in memory,
    generates embeddings in parallel, and stores them in bulk.
    """
    method_start_time = now_us()

    shutdown_event = shutdown_event or threading.Event()
    logger.info(settings.model_dump_json())
    logger.info("Processing video using simple parallel pipeline....")
    try:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        tracer = init_tracer(
            output_file=os.path.join(tempfile.gettempdir(), f"trace_{timestamp}.json"), 
            enabled=settings.SDK_ENABLE_TRACING
        )
        tracer.set_process_name("decode_detect_embed_store_pipeline")

        logger.info("Initializing shared memory pools for frames and detected crops...")
        _shm_pool = SharedMemoryPool(
            max_blocks=settings.SDK_VIDEO_SHM_MAX_BLOCKS,
            block_size=settings.SDK_VIDEO_SHM_BLOCK_SIZE,
        )
        _crop_pool = (
            SharedMemoryPool(max_blocks=_shm_pool.max_blocks, block_size=_shm_pool.block_size)
            if enable_object_detection
            else None
        )

        config = VideoFrameConfig(
            batch_size=settings.SDK_VIDEO_EXTRACTION_BATCH_SIZE,  # Large batch for efficient extraction
            frame_interval=frame_interval,
            keyframes_only=False,
        )

        # Create video input from bytes and extract frames
        logger.info("Initializing video frame extractor with in-memory video content...")

        extractor = VideoFrameExtractor(
            video_content,
            config,
            shm_pool=_shm_pool,
            shutdown_event=shutdown_event,
            tracer=tracer,
        )
        all_stream_metadata = extractor.get_metadata()
        logger.info(f"Extracted metadata for all streams: {all_stream_metadata}")

        detection_meta_queue: queue.Queue = queue.Queue(maxsize=settings.SDK_PIPELINE_QUEUE_MAXSIZE)
        embed_sink_queue: queue.Queue = queue.Queue(maxsize=settings.SDK_PIPELINE_QUEUE_MAXSIZE)
        store_queue: queue.Queue = queue.Queue(maxsize=settings.SDK_PIPELINE_QUEUE_MAXSIZE)
        result_queue: queue.Queue = queue.Queue(maxsize=settings.SDK_PIPELINE_QUEUE_MAXSIZE)
        completion_queue: queue.Queue = queue.Queue(
            maxsize=settings.SDK_PIPELINE_COMPLETION_QUEUE_MAXSIZE
        )

        def handle_sigint(sig, frame):
            logger.info("Shutdown signal received, stopping frame extraction...")
            shutdown_event.set()
            # Immediately inject DONE into the pipeline head so all workers unblock
            # without waiting for their queue.get() timeout to expire.
            try:
                detection_meta_queue.put_nowait(DONE)
            except queue.Full:
                logger.error(
                    "Failed to enqueue shutdown signal to detection_meta_queue, it is full. Workers may take up to 3 seconds to shut down."
                )
                raise  # Worker will see shutdown_event on its next iteration

        # Register after detection_meta_queue is defined — handle_sigint references it.
        signal.signal(signal.SIGINT, handle_sigint)

        detection_thread = threading.Thread(
            target=detection_worker,
            name="detection_worker",
            args=(
                detection_meta_queue,
                embed_sink_queue,
                _crop_pool,
                enable_object_detection,
                detection_confidence,
                shutdown_event,
                tracer,
            ),
        )

        embed_thread = threading.Thread(
            target=embed_worker,
            name="embed_thread",
            args=(embed_sink_queue, store_queue, _shm_pool, _crop_pool, shutdown_event, tracer),
        )

        store_thread = threading.Thread(
            target=store_worker,
            name="store_thread",
            args=(store_queue, result_queue, shutdown_event, tracer),
        )

        result_thread = threading.Thread(
            target=process_result_worker,
            name="result_worker",
            args=(result_queue, completion_queue, all_stream_metadata),
        )

        detection_thread.start()
        embed_thread.start()
        store_thread.start()
        result_thread.start()

        total_frames_processed = 0

        logger.info("Extracting frames from video in memory using decoder APIs...")
        # Common metadata fields for all frames
        video_id = metadata_dict.get("video_id", "unknown")
        filename = metadata_dict.get("filename", "unknown")
        bucket_name = metadata_dict.get("bucket_name", "unknown")
        tags = metadata_dict.get("tags", [])
        video_url = metadata_dict.get("video_url", "")
        video_rel_url = metadata_dict.get("video_rel_url", "")

        # Ensure created_at exists for downstream time filtering
        created_at_value = metadata_dict.get('created_at', None)
        if isinstance(created_at_value, dict) and '_date' in created_at_value:
            created_at_value = created_at_value.get('_date')
        if created_at_value is None:
            created_at_value = datetime.datetime.now(datetime.timezone.utc).isoformat()

        all_stream_metadata[0].update(
            {
                "_video_id": video_id,
                "_filename": filename,
                "_bucket_name": bucket_name,
                "_video_url": video_url,
                "_video_rel_url": video_rel_url,
            }
        )
        # Process batches in parallel - each batch will do optional object detection + embedding generation + immediate storage
        # total_embeddings_stored = 0
        total_stored_ids = 0

        total_wall_time_start = now_us()
        # Assuming single video input; can be extended for multiple videos
        frame_generator = extractor.decode_frames()
        try:
            for i, (batch_frame_metadata, batch_times) in enumerate(frame_generator):
                
                logger.info(f"Processing batch {i} of frames")
                logger.info(_shm_pool.stats())
                logger.info(_crop_pool.stats() if _crop_pool else "No crop pool configured")
                logger.info(
                    f"Detection queue size: {detection_meta_queue.qsize()}, Embed queue size: {embed_sink_queue.qsize()}, Result queue size: {result_queue.qsize()}"
                )
                stats = batch_frame_metadata.setdefault("stats", {})
                stats["decode"] = batch_times
                total_frames_processed += batch_frame_metadata["batch_size"]
                logger.info(
                    f"Extracted batch {i} with {batch_frame_metadata['batch_size']} frames. Total frames processed so far: {total_frames_processed}"
                )

                def extend_frame_metadata(frame_metadata):
                    stream_metadata = all_stream_metadata[frame_metadata["stream_id"]]
                    fm = FrameMetadata(
                        video_index=frame_metadata[
                            "stream_id"
                        ],  # Assuming single video; can be extended for multiple videos
                        video_id=video_id,
                        filename=filename,
                        bucket_name=bucket_name,
                        extended_frame_id=f"{video_id}_stream_{frame_metadata['frame_id']}",
                        frame_number=frame_metadata["frame_id"],
                        timestamp=(
                            frame_metadata["frame_id"] / float(stream_metadata["fps"])
                            if stream_metadata["fps"]
                            else None
                        ),
                        frame_type="FULL_FRAME",
                        tags=tags,
                        video_url=video_url,
                        video_rel_url=video_rel_url,
                        total_frames=(
                            int(stream_metadata["total_frames"])
                            if stream_metadata["total_frames"] is not None
                            else None
                        ),
                        fps=float(stream_metadata["fps"]) if stream_metadata["fps"] else None,
                        video_duration_seconds=(
                            float(stream_metadata["video_duration_seconds"])
                            if stream_metadata["video_duration_seconds"]
                            else None
                        ),
                        created_at=created_at_value,
                    ).to_dict()
                    frame_metadata.update(fm)
                    return frame_metadata

                extended_frame_metadata = list(
                    map(extend_frame_metadata, batch_frame_metadata["frames"])
                )
                batch_frame_metadata["frames"] = extended_frame_metadata

                # Non-blocking put with shutdown awareness — if queue is full and
                # workers have exited, shutdown_event will be set and we break out.

                if shutdown_event.is_set():
                    logger.info("Shutdown detected while enqueuing batch, exiting loop")
                    break

                detection_meta_queue.put(batch_frame_metadata)

                logger.info(f"detection_meta_queue - queued - {i}")
                logger.info(
                    f"Batch {i} processing results queued for detection and embedding workers"
                )

        except Exception as e:
            logger.error(f"Error processing frame {i}: {e.with_traceback(e.__traceback__)}")
            raise

        finally:
            frame_generator.close()

        total_wall_time_elapsed = now_us() - total_wall_time_start
        logger.info(
            "Total wall time for frame extraction (total_frames_processed=%d) + embedding generation + storage of (total_stored_ids=%d) frames: %.3fs",
            total_frames_processed,
            total_stored_ids,
            total_wall_time_elapsed,
        )

        try:
            detection_meta_queue.put(DONE)
        except queue.Full:
            logger.error(
                "Failed to enqueue shutdown signal to detection_meta_queue, it is full. Workers may take up to 3 seconds to shut down."
            )

        # wait for the result.
        processed_result = completion_queue.get()

        # Join threads BEFORE closing shm_pool; workers may still hold SHM references.
        detection_thread.join()
        embed_thread.join()
        store_thread.join()
        result_thread.join()

        logger.info("Worker threads have been joined successfully")

        _shm_pool.shutdown()
        if _crop_pool:
            _crop_pool.shutdown()

        logger.info("Shutdown Tracer!")
        shutdown_tracer()


        logger.info("Simple pipeline processing completed successfully")

        return processed_result

    except Exception as e:
        method_time = (now_us() - method_start_time) / 1_000_000
        shutdown_event.set()  # Ensure all workers are signaled to shut down on error
        logger.error(f"Simple pipeline processing failed after {method_time:.3f}s: {e}")
        raise


def process_frame_detection(
    frame_numpy: np.ndarray,
    frame_metadata: Dict[str, Any],
    detector: Optional[Any] = None,
    crop_pool: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """
    Process a single frame and optionally detect objects to create crops.
    """

    cropped_results: List[Dict[str, Any]] = []

    base_metadata = dict(frame_metadata)  # shallow copy, no shared ref

    try:
        detections = detector.detect(frame_numpy, return_metadata=True)
    except Exception:
        logger.warning(
            "Object detection failed for frame %s",
            base_metadata.get("frame_id", "unknown"),
        )
        return cropped_results

    if not detections:
        return cropped_results

    h, w = frame_numpy.shape[:2]

    for crop_idx, det_meta in enumerate(detections):
        try:
            box = det_meta.get("bbox")
            score = det_meta.get("confidence")
            class_id = det_meta.get("class_id")

            if not box or score is None or class_id is None:
                continue

            x1, y1, x2, y2 = box

            x1 = max(0, min(int(x1), w - 1))
            y1 = max(0, min(int(y1), h - 1))
            x2 = max(x1 + 1, min(int(x2), w))
            y2 = max(y1 + 1, min(int(y2), h))

            if (x2 - x1) < 10 or (y2 - y1) < 10:
                continue

            crop_view = frame_numpy[y1:y2, x1:x2]

            shm = shared_memory.SharedMemory(name=crop_pool.acquire())
            crop_arr = np.ndarray(crop_view.shape, dtype=crop_view.dtype, buffer=shm.buf)
            np.copyto(crop_arr, crop_view)
            del crop_view  # Release reference to the crop view to free memory

            crop_metadata = base_metadata.copy()  # shallow copy for isolation
            crop_metadata.update(
                {
                    "frame_type": "detected_crop",
                    "is_detected_crop": True,
                    "crop_index": crop_idx,
                    "detection_confidence": float(score),
                    "crop_bbox": [x1, y1, x2, y2],
                    "detected_class_id": int(class_id),
                    "detected_label": det_meta.get("class_name"),
                    "merged_boxes_count": det_meta.get("merged_boxes_count"),
                    "context_expansion_applied": det_meta.get("context_expansion_applied"),
                    "extended_frame_id": f"{base_metadata.get('frame_id', 'unknown')}_crop_{crop_idx}",
                    "shape": str(crop_arr.shape),  # Store shape as string for metadata
                    "dtype": crop_arr.dtype.name,
                    "shm": shm.name,
                }
            )

            shm.close()  # Close in this process, the consumer will open it when needed
            cropped_results.append(crop_metadata)

        except Exception:
            logger.warning(
                "Failed to create crop %d from frame %s",
                crop_idx,
                base_metadata.get("frame_id", "unknown"),
            )
            continue

    return cropped_results


def _map_shared_frame(d, to_pil=True):
    shm = shared_memory.SharedMemory(name=d["shm"])
    arr = np.ndarray(
        eval(d["shape"]),
        dtype=np.dtype(d["dtype"]),
        buffer=shm.buf,
    )

    # PIL from buffer
    # assert arr.dtype == np.uint8
    # assert arr.flags["C_CONTIGUOUS"]
    
    # if arr.ndim == 3 and arr.shape[2] == 3:
    #     mode = "RGB"
    #     h, w, _ = arr.shape
    # elif arr.ndim == 2:
    #     mode = "L"
    #     h, w = arr.shape
    # else:
    #     raise ValueError("Unsupported shape")
    if to_pil:
        h, w, _ = arr.shape
        arr = Image.frombuffer("RGB", (w, h), arr.data, "raw", "RGB", 0, 1)

    # PIL from array
    # img_arr = Image.fromarray(arr)
    # print(np.all(np.array(img) == np.array(img_arr)))

    return shm, arr, d


def allocate_detected_crops(
    batch: Dict[str, Any],
    thread_pool: ThreadPoolExecutor,
    detector,
    crop_pool=None,
) -> Tuple[List[np.ndarray], List[Dict[str, Any]]]:

    shm_handles = []
    detected_crops_metadata = []
    # ---- Phase 1: Map all frames (zero-copy, fast) ----
    mapped = []

    try:
        for d in batch["frames"]:
            try:
                shm, arr, meta = _map_shared_frame(d, to_pil=False)
                shm_handles.append(shm)
                mapped.append((arr, meta))
            except Exception as e:
                logger.warning(
                    "Failed to map frame %s: %s",
                    d.get("frame_id", "unknown"),
                    str(e),
                )

        # ---- Phase 2: Parallel detection ----
        if mapped:
            def _task(args):
                arr, meta = args
                return process_frame_detection(arr, meta, detector=detector, crop_pool=crop_pool)

            for detected in thread_pool.map(_task, mapped):
                detected_crops_metadata.extend(detected)

    except Exception as e:
        logger.error(f"Error during detection worker processing: {e}", exc_info=True)
        raise
    finally:
        mapped.clear()
        # Cleanup mapped shared memory handles
        logger.info(f"Closing {len(shm_handles)} shared memory handles after detection")
        list(thread_pool.map(lambda shm: shm.close(), shm_handles))
        shm_handles.clear()

    return detected_crops_metadata


def detection_worker(
    detection_meta_queue: queue.Queue,
    embed_sink_queue: queue.Queue,
    crop_pool: Optional[SharedMemoryPool],
    enable_object_detection: bool,
    detection_confidence: float,
    shutdown_event: threading.Event,
    tracer: Tracer,
):
    thread_pool = ThreadPoolExecutor(
        max_workers=settings.SDK_DETECTION_WORKER_THREADS,
        thread_name_prefix="detection_worker_thread",
    )
    detector = get_global_detector(enable_object_detection, detection_confidence)

    tid = threading.get_ident()
    if tracer is not None and tracer.should_trace():
        tracer.set_thread_name(tid=tid, name="detection_thread")
        # tracer.set_thread_name(tid=tid + 1, name="decode_detect_queue_wait")

    while True:
        try:
            if shutdown_event.is_set():
                logger.debug("[DETECTION WORKER] Shutdown event set, exiting.")
                break
            batch = detection_meta_queue.get(timeout=settings.SDK_PIPELINE_QUEUE_GET_TIMEOUT_S)
            ts_deq = now_us()
        except queue.Empty:
            logger.warning("[DETECTION QUEUE EMPTY] WAITING...")
            continue

        if batch is DONE:
            logger.info("[DETECTION] Worker received shutdown signal, exiting.")
            break

        # If Object Detection is enabled, this will return detected crops metadata
        try:
            stats = batch.setdefault("stats", {})

            stream_id = batch["stream_id"]
            batch_id = batch["batch_id"]
            batch_size = batch["batch_size"]
            flow_id = f"s{stream_id}_b{batch_id}"


            if tracer and tracer.should_trace():
                tracer.flow_step(flow_id, tid=tid, ts=batch["enqueue_ts"])
                tracer.emit_complete(
                    "wait",
                    batch["enqueue_ts"],
                    ts_deq,
                    tid=tid,
                    cat="queue",
                    args={
                        "flow_id": flow_id
                    }
                )

            detection_start_time = now_us()

            # FLOW enters compute
            if tracer and tracer.should_trace():
                tracer.flow_step(flow_id, tid=tid, ts=detection_start_time)

            if enable_object_detection:
                detected_crops_metadata = allocate_detected_crops(
                    batch, thread_pool, detector, crop_pool=crop_pool
                )

                batch["frames"].extend(detected_crops_metadata)

            detection_end_time = now_us()

            if tracer.should_trace():
                tracer.emit_complete(
                    "detect",
                    detection_start_time,
                    detection_end_time,
                    tid,
                    args={
                        "batch_id": batch_id,
                        "stream_id": stream_id,
                        "input_batch_size": batch_size,
                        "detected_crops": len(batch["frames"]) - batch_size,
                        "total_processed": len(batch["frames"]),
                        "flow_id": flow_id,
                    },
                )

            stats["detect"] = (
                detection_start_time,
                detection_end_time,
                (detection_end_time - detection_start_time) / 1_000_000,
            )

            batch["total"] = len(batch["frames"])
            batch["enqueue_ts"] = detection_end_time

            if tracer and tracer.should_trace():
                tracer.flow_step(flow_id, tid=tid, ts=detection_end_time)

            embed_sink_queue.put(batch)

        except Exception as e:
            logger.error(f"Error in worker processing: {e}", exc_info=True)
            continue

        logger.info("Worker completed processing batch, putting result in embed_sink_queue")

    logger.debug("Detection worker shutting down, putting shutdown signal in embed_sink_queue")
    embed_sink_queue.put(DONE)  # Signal the embedding worker to shut down
    thread_pool.shutdown(wait=True)
    logger.info("Detection worker shutdown complete")


def embed_worker(
    embed_sink_queue: queue.Queue,
    store_queue: queue.Queue,
    shm_pool: SharedMemoryPool,
    crop_pool: Optional[SharedMemoryPool],
    shutdown_event: threading.Event,
    tracer: Tracer,
):
    thread_pool = ThreadPoolExecutor(
        max_workers=settings.SDK_EMBED_WORKER_THREADS,
        thread_name_prefix="embed_worker_thread",
    )
    _sdk_client = get_sdk_client()

    tid = threading.get_ident()

    if tracer is not None and tracer.should_trace():
        tracer.set_thread_name(tid=tid, name="embed_thread")

    while True:
        try:
            if shutdown_event.is_set():
                logger.debug("[EMBED_WORKER] Shutdown event set, exiting.")
                break

            # Batch comprises of a list of full +/- detected crops metadata
            batch = embed_sink_queue.get(timeout=settings.SDK_PIPELINE_QUEUE_GET_TIMEOUT_S)
            ts_deq = now_us()
        except queue.Empty:
            if shutdown_event.is_set():
                logger.debug("[EMBED_WORKER] Shutdown event set, exiting.")
                break
            logger.warning("[EMBED_WORKER] Queue empty, waiting...")
            continue

        if batch is DONE:
            logger.info("[EMBED_WORKER] Worker received shutdown signal, exiting.")
            break

        frame_batch = None
        shm_handles = []
        batch_frame_pil = None

        try:
            stats = batch.setdefault("stats", {})

            stream_id = batch["stream_id"]
            batch_id = batch["batch_id"]
            flow_id = f"s{stream_id}_b{batch_id}"

            # FLOW ARRIVAL
            if tracer and tracer.should_trace():
                tracer.flow_step(flow_id, tid=tid, ts=batch["enqueue_ts"])

                tracer.emit_complete(
                    "embed_wait",
                    batch["enqueue_ts"],
                    ts_deq,
                    tid=tid,
                    cat="queue",
                )

            frame_batch = list(thread_pool.map(_map_shared_frame, batch["frames"]))
            shm_handles, batch_frame_pil, batch_frame_meta = tuple(map(list, zip(*frame_batch)))
            
            # ---- EMBEDDING ----
            embedding_time = now_us()

            # FLOW enters compute
            if tracer and tracer.should_trace():
                tracer.flow_step(flow_id, tid=tid, ts=embedding_time)

            embedding, infer_time_s = _sdk_client.generate_embeddings_for_images(
                batch_frame_pil, metrics_out=True
            )

            embedding_end_time = now_us()

            if tracer and tracer.should_trace():
                tracer.emit_complete(
                    "embed",
                    embedding_time,
                    embedding_end_time,
                    tid,
                    cat="gpu",
                    args={
                        "batch_id": batch_id,
                        "stream_id": stream_id,
                        "batch_size": batch["batch_size"],
                        "total_embeddings": len(embedding),
                        "embed_infer_time": infer_time_s,
                    },
                )

            stats["embed"] = (
                embedding_time,
                embedding_end_time,
                (embedding_end_time - embedding_time) / 1_000_000,
            )

            logger.debug(
                f"[EMBED_WORKER] Worker generated embeddings for {len(embedding)} frames/crops in {(embedding_end_time - embedding_time) / 1_000_000}s"
            )

            if infer_time_s:
                logger.debug(f"Embedding inference time for batch: {infer_time_s}s")
                stats["embed_infer_time"] = infer_time_s

            batch["enqueue_ts"] = embedding_end_time

            if tracer and tracer.should_trace():
                tracer.flow_step(flow_id, tid=tid, ts=embedding_end_time)

            store_queue.put((embedding, batch_frame_meta, batch))

        except Exception as e:
            logger.error(
                f"[EMBED_WORKER] Error in embed store worker processing: {e}", exc_info=True
            )
            continue
        finally:
            if batch_frame_pil:
                del batch_frame_pil  # Ensure PIL images are dereferenced before SHM cleanup
            
            if frame_batch is not None:
                del frame_batch

            logger.info(f"Closing {len(shm_handles)} shared memory handles in finally block of embed_worker")
            for shm in shm_handles:
                try:
                    shm.close()
                except Exception as e:
                    logger.warning(f"Failed to close shared memory handle {shm.name}: {e}")
                    raise

            for meta in batch_frame_meta:
                try:
                    if "is_detected_crop" in meta:
                        crop_pool.release(meta["shm"])
                    else:
                        shm_pool.release(meta["shm"])
                except Exception as e:
                    logger.warning(f"release failed {meta['shm']}: {e}")
            
            del shm_handles
            gc.collect()

        logger.debug("[EMBED_WORKER] ONTO NEXT BATCH...")

    logger.debug("[EMBED_WORKER] Worker shutting down, putting None signal in store_queue")
    store_queue.put(DONE)
    thread_pool.shutdown(wait=True)
    logger.info("[EMBED_WORKER] Worker shutdown complete")


def store_worker(
    store_queue: queue.Queue,
    result_queue: queue.Queue,
    shutdown_event: threading.Event,
    tracer: Tracer,
):
    _sdk_client = get_sdk_client()

    tid = threading.get_ident()

    if tracer is not None and tracer.should_trace():
        tracer.set_thread_name(tid=tid, name="store_thread")

    while True:
        try:
            if shutdown_event.is_set():
                logger.debug("[STORE_WORKER] Shutdown event set, exiting.")
                break

            # Batch comprises of a list of full +/- detected crops metadata
            batch_result = store_queue.get(timeout=settings.SDK_PIPELINE_QUEUE_GET_TIMEOUT_S)
            ts_deq = now_us()
        except queue.Empty:
            if shutdown_event.is_set():
                logger.debug("[STORE_WORKER] Shutdown event set, exiting.")
                break
            logger.warning("[STORE_WORKER] Queue empty, waiting...")
            continue

        if batch_result is DONE:
            logger.info("[STORE_WORKER] Worker received shutdown signal, exiting.")
            break

        try:
            embedding, batch_frame_meta, batch = batch_result
            stats = batch.setdefault("stats", {})

            stream_id = batch["stream_id"]
            batch_id = batch["batch_id"]
            batch_size = batch["batch_size"]
            flow_id = f"s{stream_id}_b{batch_id}"

            # FLOW ARRIVAL
            if tracer and tracer.should_trace():
                tracer.flow_step(flow_id, tid=tid, ts=batch["enqueue_ts"])

                tracer.emit_complete(
                    "wait",
                    batch["enqueue_ts"],
                    ts_deq,
                    tid=tid,
                    cat="queue",
                    args={
                        "flow_id": flow_id,
                    }
                )

            storage_time = now_us()

            if tracer and tracer.should_trace():
                tracer.flow_step(flow_id, tid=tid, ts=storage_time)
            

            saved_ids = _sdk_client.store_frame_embeddings(embedding, batch_frame_meta)
            batch["stored_ids"] = saved_ids

            storage_end_time = now_us()

            if tracer and tracer.should_trace():
                tracer.emit_complete(
                    "store",
                    storage_time,
                    storage_end_time,
                    tid,
                    args={
                        "batch_id": batch_id,
                        "stream_id": stream_id,
                        "batch_size": batch_size,
                        "total_stored_ids": len(saved_ids),
                    },
                )
                if tracer and tracer.should_trace():
                    tracer.flow_end(flow_id, tid=tid, ts=storage_end_time)

            batch["enqueue_ts"] = storage_end_time
            stats["store"] = (
                storage_time,
                storage_end_time,
                (storage_end_time - storage_time) / 1_000_000,
            )

            logger.info(
                f"[EMBED_WORKER] Worker stored embeddings for {len(saved_ids)} frames/crops in {(storage_end_time - storage_time) / 1_000_000}s"
            )

            stats["total"] = (
                stats["decode"][2] + stats["detect"][2] + stats["embed"][2] + stats["store"][2]
            )
            stats["max"] = max(
                stats["decode"][2],
                stats["detect"][2],
                stats["embed"][2],
                stats["store"][2],
            )

            # Calculate Batch Level Metrics
            metrics = batch.setdefault("metrics", {})

            # Latency
            metrics["e2e_batch_latency_s"] = (stats["store"][1] - stats["decode"][0]) / 1_000_000
            metrics["decode_batch_latency_s"] = stats["decode"][2]
            metrics["detect_batch_latency_s"] = stats["detect"][2]
            metrics["embed_batch_latency_s"] = stats["embed"][2]
            metrics["store_batch_latency_s"] = stats["store"][2]
            metrics["raw_embed_infer_batch_latency_s"] = stats.get("embed_infer_time", 0.0)

            # Queue Wait times
            metrics["decode_detect_queue_wait_s"] = (
                stats["detect"][0] - stats["decode"][1]
            ) / 1_000_000
            metrics["detect_embed_queue_wait_s"] = (
                stats["embed"][0] - stats["detect"][1]
            ) / 1_000_000
            metrics["embed_store_queue_wait_s"] = (
                stats["store"][0] - stats["embed"][1]
            ) / 1_000_000

            # Throughput
            metrics["decode_batch_tput_fps"] = batch.get("batch_size", 0) / stats["decode"][2]
            metrics["detect_batch_tput_fps"] = batch.get("batch_size", 0) / (stats["detect"][2] + 1e-8)
            metrics["embed_batch_tput_fps"] = batch.get("total", 0) / stats["embed"][2]
            metrics["store_batch_tput_fps"] = batch.get("total", 0) / stats["store"][2]
            metrics["raw_embed_infer_batch_tput_fps"] = (
                batch.get("total", 0) / stats.get("embed_infer_time", 1e-8)
            )

            result_queue.put(batch)

            logger.debug(
                f"[STORE_WORKER] Worker completed batch processing, releasing shared memory blocks"
            )

        except Exception as e:
            logger.error(
                f"[STORE_WORKER] Error in embed store worker processing: {e}", exc_info=True
            )
            continue

    logger.debug("[STORE_WORKER] Worker shutting down, putting None signal in result_queue")
    result_queue.put(DONE)
    logger.info("[STORE_WORKER] Worker shutdown complete")


def _summarize_stage_times(samples: List[float]) -> Dict[str, float]:
    """Compute aggregate statistics for a collection of stage timings."""
    if not samples:
        return {
            "total": 0.0,
            "avg": 0.0,
            "max": 0.0,
            "min": 0.0,
            "count": 0,
        }

    total = float(sum(samples))
    return {
        "total": total,
        "avg": total / len(samples),
        "max": max(samples),
        "min": min(samples),
        "count": len(samples),
    }


def save_batch_results(completed_batches, all_stream_metadata):
    # Placeholder for any batch-level result aggregation or logging if needed

    # Summarize per stream stats if needed
    stream_stats = {}

    for index, batch in enumerate(completed_batches):
        stream_id = batch.get("stream_id", "unknown")

        if f"{stream_id}" not in stream_stats:
            stream_stats[f"{stream_id}"] = {
                "stream_id": stream_id,
                "total_frames_processed": 0,
                "total_detected_crops": 0,
                "total_stored_ids": 0,
                "decode_detect_queue_wait_s": 0.0,
                "detect_embed_queue_wait_s": 0.0,
                "embed_store_queue_wait_s": 0.0,
                "stats": {
                    "detect": [],
                    "embed": [],
                    "store": [],
                    "decode": [],
                    "embed_inference_time": [],
                    "pipeline_wall_start_us": float("inf"),
                    "pipeline_wall_end_us": float("-inf"),
                    "total": [],
                },
                "batch_details": [],
                "stored_ids": [],
                "metrics": {},
            }

        stream_stats[f"{stream_id}"]["batch_details"].append(batch)
        if index == 0 or index == len(completed_batches) - 1:
            stream_stats[f"{stream_id}"]["stats"]["pipeline_wall_start_us"] = min(
                stream_stats[f"{stream_id}"]["stats"]["pipeline_wall_start_us"],
                batch["stats"].get("decode", (0, 0, 0))[0],
            )
            stream_stats[f"{stream_id}"]["stats"]["pipeline_wall_end_us"] = max(
                stream_stats[f"{stream_id}"]["stats"]["pipeline_wall_end_us"],
                batch["stats"].get("store", (0, 0, 0))[1],
            )

        stream_stats[f"{stream_id}"]["total_frames_processed"] += batch.get("batch_size", 0)
        stream_stats[f"{stream_id}"]["total_stored_ids"] += batch.get("total", 0)
        stream_stats[f"{stream_id}"]["total_detected_crops"] += batch.get("total", 0) - batch.get(
            "batch_size", 0
        )
        stream_stats[f"{stream_id}"]["stored_ids"].extend(batch.get("stored_ids", []))

        stream_stats[f"{stream_id}"]["stats"]["decode"].append(
            batch["stats"].get("decode", (0, 0, 0))[2]
        )
        stream_stats[f"{stream_id}"]["stats"]["detect"].append(
            batch["stats"].get("detect", (0, 0, 0))[2]
        )
        stream_stats[f"{stream_id}"]["stats"]["embed"].append(
            batch["stats"].get("embed", (0, 0, 0))[2]
        )
        stream_stats[f"{stream_id}"]["stats"]["embed_inference_time"].append(
            batch["stats"].get("embed_infer_time", 0.0)
        )
        stream_stats[f"{stream_id}"]["stats"]["store"].append(
            batch["stats"].get("store", (0, 0, 0))[2]
        )
        stream_stats[f"{stream_id}"]["stats"]["total"].append(batch["stats"].get("total", 0.0))

        # metrics
        stream_stats[f"{stream_id}"]["decode_detect_queue_wait_s"] += batch["metrics"].get(
            "decode_detect_queue_wait_s", 0.0
        )
        stream_stats[f"{stream_id}"]["detect_embed_queue_wait_s"] += batch["metrics"].get(
            "detect_embed_queue_wait_s", 0.0
        )
        stream_stats[f"{stream_id}"]["embed_store_queue_wait_s"] += batch["metrics"].get(
            "embed_store_queue_wait_s", 0.0
        )

    for k, v in stream_stats.items():
        stream_stats[f"{k}"]["metrics"]["decode"] = _summarize_stage_times(v["stats"]["decode"])

        stream_stats[f"{k}"]["metrics"]["decode"]["throughput"] = (
            v["total_frames_processed"] / stream_stats[f"{k}"]["metrics"]["decode"]["total"]
        )

        stream_stats[f"{k}"]["metrics"]["detect"] = _summarize_stage_times(v["stats"]["detect"])
        stream_stats[f"{k}"]["metrics"]["detect"]["throughput"] = (
            v["total_frames_processed"] / stream_stats[f"{k}"]["metrics"]["detect"]["total"]
        )

        stream_stats[f"{k}"]["metrics"]["embed"] = _summarize_stage_times(v["stats"]["embed"])
        stream_stats[f"{k}"]["metrics"]["embed"]["throughput"] = (
            v["total_stored_ids"] / stream_stats[f"{k}"]["metrics"]["embed"]["total"]
        )

        stream_stats[f"{k}"]["metrics"]["store"] = _summarize_stage_times(v["stats"]["store"])
        stream_stats[f"{k}"]["metrics"]["store"]["throughput"] = (
            v["total_stored_ids"] / stream_stats[f"{k}"]["metrics"]["store"]["total"]
        )

        stream_stats[f"{k}"]["metrics"]["total"] = _summarize_stage_times(v["stats"]["total"])

        stream_stats[f"{k}"]["metrics"]["embed_inference_time"] = _summarize_stage_times(
            v["stats"]["embed_inference_time"]
        )
        stream_stats[f"{k}"]["metrics"]["embed_inference_time"]["throughput"] = (
            v["total_stored_ids"] / stream_stats[f"{k}"]["metrics"]["embed_inference_time"]["total"]
        )

        pipeline_wall_duration = (
            stream_stats[f"{k}"]["stats"]["pipeline_wall_end_us"]
            - stream_stats[f"{k}"]["stats"]["pipeline_wall_start_us"]
        ) / 1_000_000
        stream_stats[f"{k}"]["pipeline_wall_duration_s"] = pipeline_wall_duration
        stream_stats[f"{k}"]["pipeline_throughput_fps"] = (
            stream_stats[f"{k}"]["total_frames_processed"] / pipeline_wall_duration
        )

        stream_stats[f"{k}"]["pipeline_throughput_fps_with_OD"] = (
            stream_stats[f"{k}"]["total_stored_ids"] / pipeline_wall_duration
        )

        # Pipeline/concurrency efficiencies
        # Total time taken by (decode, detect and embed+store / total wall duration)
        # If pipeline_concurrency_factor results 2.5 means, 2.5 seconds worth of work done in 1 second due to concurrency.
        # Higher is better, capped by number of threads.
        stream_stats[f"{k}"]["pipeline_concurrency_factor"] = (
            stream_stats[f"{k}"]["metrics"]["total"]["total"] / pipeline_wall_duration
        )

        # 3 concurrent threads (decode, detect, embed+store) in action.
        stream_stats[f"{k}"]["pipeline_efficiency_pct"] = round(
            (stream_stats[f"{k}"]["pipeline_concurrency_factor"] / 3) * 100, 3
        )

        stream_stats[f"{k}"]["parallel_efficiency_pct"] = round(
            max(
                stream_stats[f"{k}"]["metrics"]["decode"]["total"],
                stream_stats[f"{k}"]["metrics"]["detect"]["total"],
                stream_stats[f"{k}"]["metrics"]["embed"]["total"],
                stream_stats[f"{k}"]["metrics"]["store"]["total"],
            )
            * 100
            / pipeline_wall_duration,
            3,
        )

        stream_stats[f"{k}"]["decode_pipeline_efficiency_pct"] = (
            stream_stats[f"{k}"]["metrics"]["decode"]["total"] / pipeline_wall_duration
        )
        stream_stats[f"{k}"]["detect_pipeline_efficiency_pct"] = (
            stream_stats[f"{k}"]["metrics"]["detect"]["total"] / pipeline_wall_duration
        )
        stream_stats[f"{k}"]["embed_store_pipeline_efficiency_pct"] = (
            stream_stats[f"{k}"]["metrics"]["embed"]["total"]
            + stream_stats[f"{k}"]["metrics"]["store"]["total"]
        ) / pipeline_wall_duration

    for k, _ in stream_stats.items():
        stream_stats[f"{k}"]["video_metadata"] = (
            all_stream_metadata[int(k)] if k.isdigit() and int(k) < len(all_stream_metadata) else {}
        )

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    logger.info("SAVE_RUNTIME_PIPELINE_STATS is set to %s", settings.SAVE_RUNTIME_PIPELINE_STATS)
    if settings.SAVE_RUNTIME_PIPELINE_STATS:
        logger.info(f"Saving batch results for {len(completed_batches)} batches")
        with open(f"batch_stat_results_{timestamp}.json", "w") as f:
            json.dump(completed_batches, f, indent=2)

        with open(f"stream_stats_results_{timestamp}.json", "w") as f:
            json.dump(stream_stats, f, indent=2)

    return stream_stats


def process_result_worker(result_queue, completion_queue, all_stream_metadata):
    completed_batches = []
    while True:
        try:
            result = result_queue.get(timeout=settings.SDK_PIPELINE_QUEUE_GET_TIMEOUT_S)
        except queue.Empty:
            logger.warning("[RESULT WORKER] Queue empty, waiting...")
            continue

        if result is DONE:
            logger.info("[RESULT WORKER] Received shutdown signal, exiting.")
            break

        logger.info(f"[RESULT WORKER] Result: {result['stream_id']} -> {result['stored_ids']}")
        completed_batches.append(result)

    stream_stats = save_batch_results(completed_batches, all_stream_metadata)
    # stream_stats["batch_details"] = completed_batches

    completion_queue.put(stream_stats)
    logger.info("[RESULT WORKER] All batches processed, Result Saved!!!")


def generate_rtsp_video_embedding_sdk(
    video_uris: list[str],
    metadata_dict: Dict[str, Any],
    frame_interval: int = 1,
    enable_object_detection: bool = True,
    detection_confidence: float = 0.85,
    shutdown_event: Optional[threading.Event] = None,
) -> Dict[str, Any]:
    """
    Generate RTSP video embeddings using SDK approach with parallel processing.

    Args:
        video_uris: List of RTSP video URIs
        metadata_dict: Video metadata dictionary
        frame_interval: Number of frames between extractions
        enable_object_detection: Whether to enable object detection (currently not implemented)
        detection_confidence: Confidence threshold (currently not used)
        shutdown_event: Optional threading.Event to signal graceful shutdown

    Returns:
        Dictionary containing processing results and timing information
    """
    total_start_time = now_us()
    logger.info("ID of shutdown_event in generate_rtsp_video_embedding_sdk: %s", id(shutdown_event))
    try:
        # Get SDK client
        sdk_client = get_sdk_client()

        if not sdk_client.supports_image:
            logger.info(
                "Embedding model %s reports no image/video support; skipping video embedding pipeline",
                sdk_client.model_id,
            )
            total_time = (now_us() - total_start_time) / 1_000_000
            return {
                "status": "skipped_no_image_support",
                "stored_ids": [],
                "total_embeddings": 0,
                "total_frames_processed": 0,
                "frame_interval": frame_interval,
                "timing": {
                    "frame_extraction_time": 0.0,
                    "parallel_stage_time": 0.0,
                    "pipeline_wall_time": total_time,
                    "avg_batch_time": 0.0,
                    "max_batch_time": 0.0,
                    "stage_breakdown": {},
                },
                "frame_counts": {
                    "extracted_frames": 0,
                    "post_detection_items": 0,
                    "stored_embeddings": 0,
                },
                "processing_mode": "sdk_simple_pipeline_with_batch_storage",
            }

        # Process video using simple pipeline approach
        result = _process_video_from_memory_simple_pipeline(
            video_uris=video_uris,
            sdk_client=sdk_client,
            metadata_dict=metadata_dict,
            frame_interval=frame_interval,
            enable_object_detection=enable_object_detection,
            detection_confidence=detection_confidence,
            shutdown_event=shutdown_event,
        )

        total_time = (now_us() - total_start_time) / 1_000_000
        logger.info(f"SDK video processing completed in {total_time:.3f}s")

        # result["total_processing_time"] = total_time
        return result

    except Exception as e:
        total_time = now_us() - total_start_time / 1_000_000
        logger.error(f"SDK video processing failed after {total_time:.3f}s: {e}")
        raise
