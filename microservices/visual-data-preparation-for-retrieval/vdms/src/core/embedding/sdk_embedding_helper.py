# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
SDK-based Embedding Helper for Optimized Video Processing

This module provides optimized video processing using the multimodal embedding service
as an SDK for direct function calls. Final implementation strategy:

1. **SDK-based Embedding Generation**: Direct function calls instead of HTTP API
2. **Parallel Processing**: Process embeddings in parallel using ThreadPoolExecutor
3. **Bulk Vector DB Storage**: Store all embeddings in VDMS in single bulk operation
4. **Memory-based Video Processing**: Process video directly from memory using decord

Performance Benefits:
- Eliminates network latency for embedding generation
- Parallel embedding generation for better CPU utilization
- Bulk storage reduces VDMS operation overhead
- Memory-only processing avoids disk I/O
"""

import io
import tempfile
import pathlib
import time
import os
import multiprocessing
import threading
import datetime
from typing import Dict, Any, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import cv2
import numpy as np
from PIL import Image
import decord

from src.common import logger, settings
from src.core.embedding.sdk_client import SDKVDMSClient

# Global SDK client instance (initialized once per worker process)
_sdk_client: Optional[SDKVDMSClient] = None

# Global object detector instance (initialized once per worker process)
_global_detector = None


def _get_decord_context(device: Optional[str] = None):
    """Return the decord context used for frame extraction."""
    # Current container images ship without GPU-enabled decord builds, so
    # attempting to select a GPU context raises runtime failures. Always use
    # the default CPU context to keep video extraction reliable regardless of
    # the configured DEVICE.
    if device and device.upper().startswith("GPU"):
        logger.info("Decord GPU context requested; using CPU context instead")
    else:
        logger.info("Using CPU context for decord video processing")

    return decord.cpu(0)


def get_pipeline_config():
    """Get optimized pipeline configuration based on CPU cores."""
    from src.common import settings
    
    cpu_cores = multiprocessing.cpu_count()
    enable_pipelines = os.getenv('ENABLE_PARALLEL_PIPELINE', 'true').lower() == 'true'
    use_openvino = settings.SDK_USE_OPENVINO

    performance_mode = (os.getenv('OV_PERFORMANCE_MODE') or os.getenv('OPENVINO_PERFORMANCE_MODE') or '').strip().upper()

    max_workers_env = os.getenv('MAX_PARALLEL_WORKERS', None)
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
            for env_key in ("OV_PERFORMANCE_HINT_NUM_REQUESTS", "PERFORMANCE_HINT_NUM_REQUESTS", "OV_NUM_STREAMS"):
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

            max_workers = base_worker_count if ov_parallel_limit is None else min(base_worker_count, ov_parallel_limit)
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
        'pipeline_count': max_workers,
        'batch_size': max(1, settings.EMBEDDING_BATCH_SIZE),
        'enable_pipelines': enable_pipelines,
        'use_openvino': use_openvino
    }

    if performance_mode:
        logger.info(
            "Pipeline config: %s pipelines, batch size %s, OpenVINO: %s (performance_mode=%s)",
            config['pipeline_count'],
            config['batch_size'],
            use_openvino,
            performance_mode,
        )
    else:
        logger.info(
            "Pipeline config: %s pipelines, batch size %s, OpenVINO: %s",
            config['pipeline_count'],
            config['batch_size'],
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
            raise ValueError("MULTIMODAL_EMBEDDING_MODEL_NAME must be explicitly provided when using SDK embedding mode - no default model is allowed")
        
        # Ensure OpenVINO models directory exists if using OpenVINO
        if settings.SDK_USE_OPENVINO:
            import os
            os.makedirs(settings.OV_MODELS_DIR, exist_ok=True)
            logger.info(f"Using OpenVINO optimization with models directory: {settings.OV_MODELS_DIR}")
        else:
            logger.info("Using PyTorch native model (OpenVINO disabled)")
        
        _sdk_client = SDKVDMSClient(
            model_id=settings.MULTIMODAL_EMBEDDING_MODEL_NAME,
            device=settings.DEVICE,
            use_openvino=settings.SDK_USE_OPENVINO,
            ov_models_dir=settings.OV_MODELS_DIR
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
                detection_confidence=detection_confidence
            )
            
            if _global_detector is None:
                logger.warning("Global object detector initialization failed")
            else:
                logger.info(f"Global object detector initialized with confidence threshold: {detection_confidence}")
                
        except Exception as e:
            logger.error(f"Failed to initialize global object detector: {e}")
            _global_detector = None
    
    return _global_detector


def preload_object_detector(enable_object_detection: bool = True, detection_confidence: float = 0.85) -> bool:
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
        logger.info(f"Object Detection Configuration: enabled={enable_object_detection}, confidence={detection_confidence}, device={settings.DEVICE}")
        
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
                logger.info(f"Object detection model preloaded successfully! Model cached and ready (warmup found {len(test_detections) if test_detections else 0} test objects)")
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
        logger.info(f"SDK Configuration: Model={settings.MULTIMODAL_EMBEDDING_MODEL_NAME}, Device={settings.DEVICE}, OpenVINO={settings.SDK_USE_OPENVINO}")
        
        # Validate GPU setup if GPU device is requested
        if settings.DEVICE.upper() == "GPU":
            logger.info("GPU device requested - validating GPU setup...")
            
            # Check if running in OpenVINO mode (recommended for GPU)
            if not settings.SDK_USE_OPENVINO:
                logger.warning("GPU device specified but OpenVINO is disabled. For best GPU performance, enable OpenVINO with GPU device.")
            else:
                logger.info("GPU device with OpenVINO enabled - optimal configuration for GPU acceleration")
                
            # Test decord GPU context
            try:
                _get_decord_context(settings.DEVICE)
                logger.info("Decord GPU context validated successfully")
            except Exception as e:
                logger.warning(f"Decord GPU context validation failed, will fall back to CPU: {e}")
        
        # Initialize the client (this loads the model)
        sdk_client = get_sdk_client()

        if sdk_client.supports_image:
            # Perform image warmup with a small test pattern
            import numpy as np
            from PIL import Image

            test_image = Image.fromarray(
                np.random.randint(0, 255, (8, 8, 3), dtype=np.uint8)
            )
            test_embedding = sdk_client.generate_embedding_for_image(test_image)

            if test_embedding is not None:
                openvino_status = "OpenVINO optimized" if settings.SDK_USE_OPENVINO else "PyTorch native"
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
                openvino_status = "OpenVINO optimized" if settings.SDK_USE_OPENVINO else "PyTorch native"
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
    
    def __init__(self, sdk_client: SDKVDMSClient, enable_object_detection: bool = False, detection_confidence: float = 0.85):
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
        if self.config['use_openvino']:
            logger.info("OpenVINO parallel mode: Using thread-safe infer_new_request pattern (maximum performance)")
        else:
            logger.info("PyTorch mode: Using shared model instance across all threads (thread-safe)")
    
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
            detection_confidence=self.detection_confidence
        )
        
        if self.detector is None:
            logger.warning("Object detector not available - disabling object detection")
            self.enable_object_detection = False
        else:
            logger.info(f"Using global object detector with confidence threshold: {self.detection_confidence}")
        
    
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
                                logger.debug("Skipping detection %d due to incomplete metadata", crop_idx)
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
    
    def _process_frames_with_parallel_detection(self, all_frames: List[np.ndarray], all_metadata: List[Dict[str, Any]]) -> Tuple[List[Image.Image], List[Dict[str, Any]]]:
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
        detection_batch_size = max(1, len(all_frames) // self.config['pipeline_count'])
        detection_batches = []
        
        for i in range(0, len(all_frames), detection_batch_size):
            batch_frames = all_frames[i:i + detection_batch_size]
            batch_metadata = all_metadata[i:i + detection_batch_size]
            detection_batches.append((batch_frames, batch_metadata))
        
        logger.info(f"Created {len(detection_batches)} detection batches (batch_size={detection_batch_size})")
        
        # Process detection batches in parallel
        all_images_for_embedding = []
        all_metadata_for_embedding = []
        
        with ThreadPoolExecutor(max_workers=self.config['pipeline_count']) as executor:
            detection_futures = [
                executor.submit(self._process_detection_batch, batch_frames, batch_metadata)
                for batch_frames, batch_metadata in detection_batches
            ]
            
            # Process completed futures as they finish (true parallel processing)
            for future in as_completed(detection_futures):
                batch_images, batch_metadata = future.result()
                all_images_for_embedding.extend(batch_images)
                all_metadata_for_embedding.extend(batch_metadata)
        
        logger.info(f"Parallel object detection completed: {len(all_frames)} frames -> {len(all_images_for_embedding)} items")
        return all_images_for_embedding, all_metadata_for_embedding
    
    def _process_detection_batch(self, batch_frames: List[np.ndarray], batch_metadata: List[Dict[str, Any]]) -> Tuple[List[Image.Image], List[Dict[str, Any]]]:
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
        
        logger.debug(f"Detection batch processed: {len(batch_frames)} frames -> {len(batch_images)} items")
        return batch_images, batch_metadata_results
    
    def process_frames_parallel(self, all_frames: List[np.ndarray], all_metadata: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Process frames in parallel for embedding generation with optional object detection and per-batch storage."""
        logger.info(f"Processing {len(all_frames)} frames with {self.config['pipeline_count']} maximum parallel workers")
        
        if self.enable_object_detection:
            logger.info(f"Object detection enabled with confidence threshold: {self.detection_confidence}")
        
        try:
            # Create batches of frames for parallel processing
            logger.info(f"About to create batches from {len(all_frames)} frames with batch_size={self.config['batch_size']}")
            batches = self.create_frame_batches(all_frames, all_metadata)
            detection_status = "with object detection" if self.enable_object_detection else "without object detection"
            logger.info(f"Created {len(batches)} batches for parallel processing ({detection_status})")
            
            # Process batches in parallel - each batch will do optional object detection + embedding generation + immediate storage
            total_embeddings_stored = 0
            all_stored_ids = []
            batch_processing_times: List[float] = []
            detection_times: List[float] = []
            embedding_times: List[float] = []
            storage_times: List[float] = []
            total_items_after_detection = 0
            completed_batches: List[Dict[str, Any]] = []
            
            logger.info(f"Starting parallel execution of {len(batches)} batches with {self.config['pipeline_count']} maximum workers")
            
            parallel_start_time = time.time()
            with ThreadPoolExecutor(max_workers=self.config['pipeline_count']) as executor:
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
                logger.info(f"True parallel processing enabled - batches will complete in any order as they finish")
                
                # Process completed batches as they finish (true parallel processing)
                batch_counter = 0
                timeout_per_batch = 300  # 5 minutes per batch maximum
                for future in as_completed(batch_futures, timeout=timeout_per_batch * len(batch_futures)):
                    batch_counter += 1
                    try:
                        batch_result = future.result()
                        embeddings_count = batch_result['embeddings_count']
                        stored_ids = batch_result['stored_ids']
                        processing_time = batch_result['processing_time']
                        batch_index = future_to_index.get(future, batch_counter)
                        batch_detection_time = batch_result.get('detection_time', 0.0)
                        batch_embedding_time = batch_result.get('embedding_time', 0.0)
                        batch_storage_time = batch_result.get('storage_time', 0.0)
                        batch_items_after_detection = batch_result.get('items_after_detection', 0)
                        
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
            logger.info(f"Parallel processing completed: {total_embeddings_stored} embeddings generated and stored")
            
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
                    "avg_pct_of_batch": (avg_time / avg_batch_time * 100.0) if avg_batch_time else 0.0,
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
                'total_embeddings': total_embeddings_stored,
                'stored_ids': all_stored_ids,
                'processing_time': parallel_time,
                'batches_processed': len(batches),
                'avg_batch_time': avg_batch_time,
                'max_batch_time': max_batch_time,
                'stage_breakdown': stage_breakdown,
                'batch_stats': {
                    'avg_s': avg_batch_time,
                    'max_s': max_batch_time,
                    'count': batch_time_stats.get('count', 0),
                },
                'batch_details': completed_batches,
                'pipeline_config': {
                    'pipeline_count': self.config.get('pipeline_count'),
                    'batch_size': self.config.get('batch_size'),
                    'use_openvino': self.config.get('use_openvino'),
                    'object_detection_enabled': self.enable_object_detection,
                    'detection_confidence': self.detection_confidence,
                },
                'post_detection_items': total_items_after_detection,
                'input_frames': len(all_frames)
            }
            
        except Exception as e:
            logger.error(f"Error in parallel processing: {e}")
            return {
                'total_embeddings': 0,
                'stored_ids': [],
                'processing_time': 0,
                'batches_processed': 0,
                'avg_batch_time': 0.0,
                'max_batch_time': 0.0,
                'stage_breakdown': {
                    'detection': {'avg_s': 0.0, 'max_s': 0.0, 'total_s': 0.0, 'avg_pct_of_batch': 0.0},
                    'embedding': {'avg_s': 0.0, 'max_s': 0.0, 'total_s': 0.0, 'avg_pct_of_batch': 0.0},
                    'storage': {'avg_s': 0.0, 'max_s': 0.0, 'total_s': 0.0, 'avg_pct_of_batch': 0.0},
                },
                'batch_stats': {'avg_s': 0.0, 'max_s': 0.0, 'count': 0},
                'batch_details': completed_batches,
                'pipeline_config': {
                    'pipeline_count': self.config.get('pipeline_count'),
                    'batch_size': self.config.get('batch_size'),
                    'use_openvino': self.config.get('use_openvino'),
                    'object_detection_enabled': self.enable_object_detection,
                    'detection_confidence': self.detection_confidence,
                },
                'post_detection_items': 0,
                'input_frames': len(all_frames)
            }
    
    def create_frame_batches(self, frames: List[np.ndarray], metadata: List[Dict[str, Any]]) -> List[tuple]:
        """Create batches of frames for parallel processing (including object detection)."""
        batch_size = self.config['batch_size']
        total_frames = len(frames)
        
        logger.info(f"Creating frame batches: {total_frames} frames, batch_size={batch_size}")
        
        batches = []
        
        for i in range(0, total_frames, batch_size):
            batch_frames = frames[i:i + batch_size]
            batch_metadata = metadata[i:i + batch_size]
            batch_num = len(batches) + 1
            
            logger.debug(f"Batch {batch_num}: frames {i} to {min(i + batch_size - 1, total_frames - 1)} ({len(batch_frames)} frames)")
            batches.append((batch_frames, batch_metadata))
        
        logger.info(f"Created {len(batches)} batches from {total_frames} frames (avg {total_frames/len(batches):.1f} frames/batch)")
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
                    'status': 'skipped_no_image_support',
                    'embeddings_count': 0,
                    'stored_ids': [],
                    'processing_time': time.time() - batch_start_time,
                    'detection_time': 0.0,
                    'embedding_time': 0.0,
                    'storage_time': 0.0,
                    'items_after_detection': 0,
                    'input_frames': len(batch_frames)
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
            
            expansion_info = f"(including crops)" if self.enable_object_detection else "(frames only)"
            logger.info(
                f"[Batch {batch_index}/{total_batches}] Expanded from {len(batch_frames)} frames "
                f"to {len(all_images_for_embedding)} items {expansion_info} in {detection_time:.3f}s"
            )
            items_after_detection = len(all_images_for_embedding)
            # Step 2: Generate embeddings for all images in the expanded batch
            logger.debug(f"Step 2: Starting embedding generation for {len(all_images_for_embedding)} images")
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
            for i, (image, metadata, embedding) in enumerate(zip(all_images_for_embedding, all_metadata_for_embedding, embeddings)):
                if embedding is not None:
                    valid_embeddings.append(embedding)
                    valid_metadatas.append(metadata)
                else:
                    if self.supports_image_embeddings:
                        logger.warning(f"Failed to generate embedding for image {metadata['frame_id']}")
                    else:
                        logger.debug(
                            "Skipping embedding for %s because model does not support image modality", 
                            metadata['frame_id']
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
                stored_ids = thread_sdk_client.store_frame_embeddings(valid_embeddings, valid_metadatas)
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
                'batch_index': batch_index,
                'embeddings_count': len(valid_embeddings),
                'stored_ids': stored_ids,
                'processing_time': batch_time,
                'detection_time': detection_time,
                'embedding_time': embedding_time,
                'storage_time': storage_time,
                'items_after_detection': items_after_detection,
                'input_frames': len(batch_frames)
            }
            
        except Exception as e:
            logger.error(f"[Batch {batch_index}/{total_batches}] Error processing batch: {e}")
            return {
                'batch_index': batch_index,
                'embeddings_count': 0,
                'stored_ids': [],
                'processing_time': time.time() - batch_start_time,
                'detection_time': detection_time if 'detection_time' in locals() else 0.0,
                'embedding_time': embedding_time if 'embedding_time' in locals() else 0.0,
                'storage_time': storage_time if 'storage_time' in locals() else 0.0,
                'items_after_detection': len(all_images_for_embedding) if 'all_images_for_embedding' in locals() else 0,
                'input_frames': len(batch_frames)
            }
    
    def _process_sequential_fallback(self, frames: List[np.ndarray], metadata: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
                            embeddings.append({
                                'embedding': embedding,
                                'metadata': metadata_item
                            })
                    except Exception as e:
                        logger.error(f"Error generating embedding for {metadata_item.get('frame_id', 'unknown')}: {e}")
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
    detection_confidence: float = 0.85
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
    total_start_time = time.time()
    logger.info(f"Starting SDK video processing with frame_interval={frame_interval}")
    
    try:
        # Get SDK client
        sdk_client = get_sdk_client()

        if not sdk_client.supports_image:
            logger.info(
                "Embedding model %s reports no image/video support; skipping video embedding pipeline",
                sdk_client.model_id,
            )
            total_time = time.time() - total_start_time
            return {
                'status': 'skipped_no_image_support',
                'stored_ids': [],
                'total_embeddings': 0,
                'total_frames_processed': 0,
                'frame_interval': frame_interval,
                'timing': {
                    'frame_extraction_time': 0.0,
                    'parallel_stage_time': 0.0,
                    'pipeline_wall_time': total_time,
                    'avg_batch_time': 0.0,
                    'max_batch_time': 0.0,
                    'stage_breakdown': {},
                },
                'frame_counts': {
                    'extracted_frames': 0,
                    'post_detection_items': 0,
                    'stored_embeddings': 0,
                },
                'processing_mode': 'sdk_simple_pipeline_with_batch_storage',
            }
        
        # Process video using simple pipeline approach
        result = _process_video_from_memory_simple_pipeline(
            video_content=video_content,
            sdk_client=sdk_client,
            metadata_dict=metadata_dict,
            frame_interval=frame_interval,
            enable_object_detection=enable_object_detection,
            detection_confidence=detection_confidence
        )
        
        total_time = time.time() - total_start_time
        logger.info(f"SDK video processing completed in {total_time:.3f}s")
        
        result['total_processing_time'] = total_time
        return result
        
    except Exception as e:
        total_time = time.time() - total_start_time
        logger.error(f"SDK video processing failed after {total_time:.3f}s: {e}")
        raise


def _process_video_from_memory_simple_pipeline(
    video_content: bytes,
    sdk_client: SDKVDMSClient,
    metadata_dict: Dict[str, Any],
    frame_interval: int,
    enable_object_detection: bool,
    detection_confidence: float
) -> Dict[str, Any]:
    """
    Process video from memory using simple parallel pipeline approach.
    
    This is the main implementation that extracts frames from video in memory,
    generates embeddings in parallel, and stores them in bulk.
    """
    method_start_time = time.time()
    logger.info("Processing video using simple parallel pipeline")
    
    try:
        # Step 1: Extract frames from video in memory
        frame_extraction_start = time.time()
        
        # Create temporary file for decord processing
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
            temp_file.write(video_content)
            temp_video_path = temp_file.name
        
        try:
            # Use decord to process video with appropriate device context (use SDK device)
            decord_ctx = _get_decord_context(sdk_client.device)
            vr = decord.VideoReader(temp_video_path, ctx=decord_ctx)
            fps = vr.get_avg_fps()
            total_frames = len(vr)
            video_duration_seconds = None
            if fps and fps > 0:
                try:
                    video_duration_seconds = float(total_frames) / float(fps)
                except ZeroDivisionError:
                    video_duration_seconds = None
            
            logger.info(f"Video info: {total_frames} total frames, {fps:.2f} fps")
            
            # Extract frames at specified interval
            frame_indices = list(range(0, total_frames, frame_interval))
            logger.info(f"Extracting {len(frame_indices)} frames with interval {frame_interval}")
            
            frames = []
            frames_metadata = []
            
            for i, frame_idx in enumerate(frame_indices):
                try:
                    # Get frame using decord
                    frame_tensor = vr[frame_idx]
                    
                    # Convert to numpy array with robust tensor handling
                    try:
                        # Handle different tensor types from decord VideoReader
                        if hasattr(frame_tensor, 'asnumpy'):
                            # It's a decord NDArray - convert to numpy first
                            frame_numpy = frame_tensor.asnumpy()
                        elif hasattr(frame_tensor, 'numpy'):
                            # It's a PyTorch tensor - convert to numpy first
                            frame_numpy = frame_tensor.numpy()
                        elif hasattr(frame_tensor, 'detach'):
                            # It's a PyTorch tensor with gradients - detach first
                            frame_numpy = frame_tensor.detach().numpy()
                        elif isinstance(frame_tensor, np.ndarray):
                            # It's already a numpy array
                            frame_numpy = frame_tensor
                        else:
                            # Try generic conversion for any array-like object
                            try:
                                frame_numpy = np.array(frame_tensor)
                            except Exception as conv_error:
                                logger.error(f"Failed to convert tensor to numpy for frame {frame_idx}: {conv_error}")
                                logger.error(f"Frame tensor type: {type(frame_tensor)}, available methods: {dir(frame_tensor)}")
                                continue
                        
                        # Ensure the array is in the correct format (H, W, C) and convert to PIL
                        if len(frame_numpy.shape) == 3 and frame_numpy.shape[-1] == 3:
                            # Format is correct (H, W, C), convert directly to numpy array for batching
                            # Ensure uint8 format for consistent processing
                            frame_numpy = frame_numpy.astype(np.uint8)
                            frames.append(frame_numpy)  # Store as numpy array for batch processing
                        else:
                            logger.error(f"Unexpected frame shape for frame {frame_idx}: {frame_numpy.shape}")
                            continue
                            
                    except Exception as tensor_error:
                        logger.error(f"Failed to convert frame tensor for frame {frame_idx}: {tensor_error}")
                        logger.error(f"Frame tensor type: {type(frame_tensor)}, shape: {getattr(frame_tensor, 'shape', 'unknown')}")
                        continue
                    
                    # Create frame metadata with frame_id for tracking (including video URLs for search-ms compatibility)
                    timestamp = frame_idx / fps
                    frame_metadata = {
                        'frame_id': f"{metadata_dict.get('video_id', 'unknown')}_{frame_idx}",
                        'frame_number': frame_idx,
                        'timestamp': timestamp,
                        'frame_type': 'full_frame',
                        'video_id': metadata_dict.get('video_id', 'unknown'),
                        'filename': metadata_dict.get('filename', 'unknown'),
                        'bucket_name': metadata_dict.get('bucket_name', 'unknown'),
                        'tags': metadata_dict.get('tags', []),
                        'video_url': metadata_dict.get('video_url', ''),
                        'video_rel_url': metadata_dict.get('video_rel_url', '')
                    }

                    # Ensure created_at exists for downstream time filtering
                    created_at_value = metadata_dict.get('created_at')
                    if isinstance(created_at_value, dict) and '_date' in created_at_value:
                        created_at_value = created_at_value.get('_date')
                    if not created_at_value:
                        created_at_value = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    frame_metadata['created_at'] = created_at_value

                    # Attach video-level metadata needed by search aggregation
                    if total_frames is not None:
                        frame_metadata['total_frames'] = int(total_frames)
                    if fps:
                        frame_metadata['fps'] = float(fps)
                    if video_duration_seconds is not None:
                        frame_metadata['video_duration'] = video_duration_seconds
                        frame_metadata['video_duration_seconds'] = video_duration_seconds
                    frames_metadata.append(frame_metadata)
                    
                    # DEBUG: Print first frame metadata to verify video URLs are included
                    if frame_idx == 0:
                        logger.info(f"DEBUG: First frame metadata sample: {frame_metadata}")
                        logger.info(f"DEBUG: Source metadata_dict video_url: '{metadata_dict.get('video_url', 'NOT_FOUND')}'")
                        logger.info(f"DEBUG: Source metadata_dict video_rel_url: '{metadata_dict.get('video_rel_url', 'NOT_FOUND')}'") 
                    
                except Exception as e:
                    logger.error(f"Error extracting frame {frame_idx}: {e}")
                    continue
            
            frame_extraction_time = time.time() - frame_extraction_start
            logger.info(f"Frame extraction completed in {frame_extraction_time:.3f}s: {len(frames)} frames")
            
        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_video_path)
            except Exception as e:
                logger.warning(f"Failed to clean up temp file: {e}")
        
        # Step 2: Generate embeddings in parallel with immediate per-batch storage
        embedding_start_time = time.time()
        
        # Log device consistency across all components
        logger.info(f"Device consistency: SDK={sdk_client.device}, Decord={sdk_client.device}, Object Detection will use={sdk_client.device}")
        
        pipeline_manager = SimplePipelineManager(
            sdk_client, 
            enable_object_detection=enable_object_detection, 
            detection_confidence=detection_confidence
        )
        processing_result = pipeline_manager.process_frames_parallel(frames, frames_metadata)
        
        parallel_stage_time = time.time() - embedding_start_time
        total_embeddings = processing_result.get('total_embeddings', 0)
        stored_ids = processing_result.get('stored_ids', [])
        batches_processed = processing_result.get('batches_processed', 0)

        stage_breakdown = processing_result.get('stage_breakdown', {}) or {}
        detection_stats = stage_breakdown.get('detection', {})
        embedding_stats = stage_breakdown.get('embedding', {})
        storage_stats = stage_breakdown.get('storage', {})
        batch_stats = processing_result.get('batch_stats', {}) or {}
        post_detection_items = (
            processing_result.get('post_detection_items')
            or total_embeddings
            or len(frames)
        )
        
        logger.info(
            "Embedding generation pipeline completed in %.3fs: %d embeddings across %d batches",
            parallel_stage_time,
            total_embeddings,
            batches_processed,
        )
        
        # Step 3: Return results (storage already completed per-batch)
        method_time = time.time() - method_start_time
        
        result = {
            'status': 'success',
            'stored_ids': stored_ids,
            'total_embeddings': len(stored_ids),
            'total_frames_processed': len(frames),
            'frame_interval': frame_interval,
            'timing': {
                'frame_extraction_time': frame_extraction_time,
                'parallel_stage_time': parallel_stage_time,
                'pipeline_wall_time': method_time,
                'avg_batch_time': batch_stats.get('avg_s', 0.0),
                'max_batch_time': batch_stats.get('max_s', 0.0),
                'stage_breakdown': stage_breakdown,
            },
            'frame_counts': {
                'extracted_frames': len(frames),
                'post_detection_items': post_detection_items,
                'stored_embeddings': len(stored_ids)
            },
            'processing_mode': 'sdk_simple_pipeline_with_batch_storage',
            'batch_details': processing_result.get('batch_details', []),
            'pipeline_config': processing_result.get('pipeline_config', {}),
            'video_properties': {
                'fps': float(fps) if fps else None,
                'total_frames': int(total_frames) if total_frames is not None else None,
                'video_duration_seconds': video_duration_seconds,
            },
        }
        
        logger.info("Simple pipeline processing completed successfully")
        
        return result
        
    except Exception as e:
        method_time = time.time() - method_start_time
        logger.error(f"Simple pipeline processing failed after {method_time:.3f}s: {e}")
        raise


