# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Adapted from YOLOX: https://github.com/Megvii-BaseDetection/YOLOX

import os
import logging
import tarfile
import urllib.request
import urllib.error
from typing import List, Optional, Tuple, Union

import cv2
import numpy as np
from PIL import Image

# Import VDMS local modules
from ..utils.config_utils import get_config
from .yolox_utils import preproc, multiclass_nms, demo_postprocess, compute_iou
from .default_class_names import DEFAULT_COCO_CLASS_NAMES

logger = logging.getLogger(__name__)

try:
    import openvino as ov
    OPENVINO_AVAILABLE = True
except ImportError:
    OPENVINO_AVAILABLE = False
    logger.warning("OpenVINO not available. Object detection will be disabled.")

class YOLOXDetector:
    """
    YOLOX object detector using OpenVINO inference.
    
    Provides object detection capabilities for frame-based video processing,
    including configurable confidence thresholds and crop extraction.
    """
    
    def __init__(self, config: Optional[dict] = None):
        """
        Initialize YOLOX detector.
        
        Args:
            config: Configuration dictionary. If None, loads from effective config.
        """
        if not OPENVINO_AVAILABLE:
            raise ImportError("OpenVINO is required for object detection. Please install openvino.")
        
        # Load configuration
        if config is None:
            config = get_config()

        self.config = config
        self.detection_config = config.get('object_detection', {}).copy()
        
        # Detection parameters
        self.device = self.detection_config.get('device', 'CPU')
        self.confidence_threshold = self.detection_config.get('confidence_threshold', 0.5)
        self.nms_threshold = self.detection_config.get('nms_threshold', 0.45)
        self.input_size = tuple(self.detection_config.get('input_size', [640, 640]))
        
        # Model configuration - use persistent mount path
        self.model_dir = self.detection_config.get('model_dir', '/app/models/yolox')
        self.model_name = self.detection_config.get('model_name')  # No default - must be explicitly provided
        if not self.model_name:
            raise ValueError("Object detection model name must be explicitly provided via DETECTION_MODEL_NAME environment variable or config file")
        self.model_file = os.path.join(self.model_dir, f"{self.model_name}.xml")

        class_names_config = self.detection_config.get('class_names')
        class_names: Optional[List[str]] = None

        if class_names_config:
            if isinstance(class_names_config, str):
                class_names = [entry.strip() for entry in class_names_config.split(',') if entry.strip()]
            else:
                class_names = [str(entry).strip() for entry in class_names_config if str(entry).strip()]

            if not class_names:
                class_names = None

        if class_names is None:
            fallback_class_names = self._load_default_class_names()
            if fallback_class_names is not None:
                class_names = fallback_class_names
                logger.info(
                    "Object detection class names not specified; falling back to built-in YOLOX COCO labels (%d entries).",
                    len(class_names),
                )
            else:
                logger.info(
                    "Object detection class names not specified; detection metadata will use generated placeholders. "
                    "Provide object_detection.class_names in config.yaml to map IDs to labels."
                )

        self.class_names = tuple(class_names) if class_names is not None else None
        
        # Initialize OpenVINO
        self._init_openvino()
        
        logger.info(f"YOLOX detector initialized: device={self.device}, confidence={self.confidence_threshold}")
    
    def _init_openvino(self):
        """Initialize OpenVINO core and load model."""
        try:
            # Download model if needed
            self._ensure_model_available()
            
            # Initialize OpenVINO
            self.core = ov.Core()
            self.net = self.core.read_model(model=self.model_file)
            self.exec_net = self.core.compile_model(self.net, self.device)
            
            # Get input/output information
            self.input_tensor = self.exec_net.inputs[0]
            self.output_tensor = self.exec_net.outputs[0]
            
            _, _, self.h, self.w = self.input_tensor.shape
            
            logger.info(f"Model loaded successfully: input_shape=({self.h}, {self.w})")
            
        except Exception as e:
            logger.error(f"Failed to initialize OpenVINO: {e}")
            raise
    
    def _ensure_model_available(self):
        """Download YOLOX model if not available using pure Python methods."""
        if os.path.exists(self.model_file):
            logger.info(f"Model found: {self.model_file}")
            return
        
        logger.info(f"Model not found. Downloading to {self.model_dir}")
        os.makedirs(self.model_dir, exist_ok=True)
        
        try:
            # Download the model using urllib
            model_url = "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_s_openvino.tar.gz"
            tar_file = os.path.join(self.model_dir, "yolox_s_openvino.tar.gz")
            
            logger.info(f"Downloading model from {model_url}")
            
            # Download with retry logic
            max_retries = 5
            for attempt in range(max_retries):
                try:
                    with urllib.request.urlopen(model_url, timeout=30) as response:
                        with open(tar_file, 'wb') as f:
                            # Download in chunks
                            chunk_size = 8192
                            while True:
                                chunk = response.read(chunk_size)
                                if not chunk:
                                    break
                                f.write(chunk)
                    break  # Success, exit retry loop
                    
                except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"Download attempt {attempt + 1} failed: {e}. Retrying...")
                        continue
                    else:
                        raise RuntimeError(f"Download failed after {max_retries} attempts: {e}")
            
            # Extract the model using tarfile
            logger.info(f"Extracting model archive")
            try:
                # Try as gzipped tar first, then fallback to regular tar
                try:
                    with tarfile.open(tar_file, 'r:gz') as tar:
                        tar.extractall(path=self.model_dir)
                except tarfile.TarError:
                    # If gzip fails, try as regular tar
                    logger.info("Gzip extraction failed, trying as regular tar")
                    with tarfile.open(tar_file, 'r') as tar:
                        tar.extractall(path=self.model_dir)
                    
            except tarfile.TarError as e:
                raise RuntimeError(f"Extraction failed: {e}")
            
            # Cleanup downloaded archive
            try:
                os.remove(tar_file)
                logger.info("Cleaned up downloaded archive")
            except OSError:
                logger.warning("Failed to cleanup archive file")
            
            # Verify model file exists after extraction
            if not os.path.exists(self.model_file):
                raise FileNotFoundError(f"Model file not found after download: {self.model_file}")
                
            logger.info("Model downloaded and extracted successfully")
            
        except Exception as e:
            logger.error(f"Failed to download model: {e}")
            raise
    
    def detect_objects(self, image: Union[np.ndarray, Image.Image]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Detect objects in an image.
        
        Args:
            image: Input image (numpy array or PIL Image)
            
        Returns:
            Tuple of (bounding_boxes, confidence_scores, class_indices)
        """
        # Convert PIL Image to numpy array if needed
        if isinstance(image, Image.Image):
            image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        
        # Preprocess image
        processed_image, ratio = preproc(image, (self.h, self.w))
        
        # Run inference
        try:
            result = self.exec_net.infer_new_request({self.input_tensor: processed_image})
            output = result[self.output_tensor]
            
            # Post-process results
            predictions = demo_postprocess(output, (self.h, self.w))[0]
            
            boxes = predictions[:, :4]
            scores = predictions[:, 4, None] * predictions[:, 5:]
            
            # Convert center format to corner format
            boxes_xyxy = np.ones_like(boxes)
            boxes_xyxy[:, 0] = boxes[:, 0] - boxes[:, 2] / 2.0
            boxes_xyxy[:, 1] = boxes[:, 1] - boxes[:, 3] / 2.0
            boxes_xyxy[:, 2] = boxes[:, 0] + boxes[:, 2] / 2.0
            boxes_xyxy[:, 3] = boxes[:, 1] + boxes[:, 3] / 2.0
            boxes_xyxy /= ratio
            
            # Apply NMS
            dets = multiclass_nms(
                boxes_xyxy, 
                scores, 
                nms_thr=self.nms_threshold, 
                score_thr=self.confidence_threshold
            )
            
            final_boxes = np.empty((0, 4), dtype=int)
            final_scores = np.empty((0,), dtype=float)
            final_cls_inds = np.empty((0,), dtype=int)
            if dets is not None:
                # Convert bounding boxes to integers for compatibility with embedding service
                final_boxes = np.round(dets[:, :4]).astype(int)
                final_scores = dets[:, 4]
                final_cls_inds = dets[:, 5].astype(int)

            # Default metadata for per-box ROI consolidation stats (used by detect()).
            self._last_roi_metadata = [
                {"merged_boxes_count": 1, "context_expansion_applied": False}
                for _ in range(len(final_boxes))
            ]
            
            if len(final_boxes) > 0:
                # Optional ROI consolidation happens after NMS so we only merge
                # high-confidence, non-overlapping detections that survived filtering.
                final_boxes, final_scores, final_cls_inds, roi_metadata = self._consolidate_rois(
                    final_boxes,
                    final_scores,
                    final_cls_inds,
                    image.shape[:2],
                )
                self._last_roi_metadata = roi_metadata

            return final_boxes, final_scores, final_cls_inds
            
        except Exception as e:
            logger.error(f"Detection failed: {e}")
            return (
                np.empty((0, 4), dtype=int),
                np.empty((0,), dtype=float),
                np.empty((0,), dtype=int),
            )

    def detect(
        self,
        image: Union[np.ndarray, Image.Image],
        *,
        return_metadata: bool = True,
    ) -> Union[List[dict], Tuple[np.ndarray, np.ndarray, np.ndarray]]:
        """Backward-compatible detection helper.

        This method provides the legacy ``detect`` interface that some callers
        expect (for example the object detector preload routine). By default it
        returns rich detection metadata dictionaries; callers that need the raw
        tensors can set ``return_metadata=False`` to receive the tuple produced
        by :meth:`detect_objects`.

        Args:
            image: Input image to run detection against.
            return_metadata: When ``True`` (default) return a list of detection
                metadata dictionaries. When ``False`` return the raw
                ``(boxes, scores, class_ids)`` tuple.

        Returns:
            Either a list of detection metadata dictionaries or the raw tuple
            from :meth:`detect_objects`, depending on ``return_metadata``.
        """

        boxes, scores, class_ids = self.detect_objects(image)

        if not return_metadata:
            return boxes, scores, class_ids

        metadata: List[dict] = []
        roi_metadata = getattr(self, "_last_roi_metadata", [])
        for i, (box, score, class_id) in enumerate(zip(boxes, scores, class_ids)):
            roi_info = roi_metadata[i] if i < len(roi_metadata) else {
                "merged_boxes_count": 1,
                "context_expansion_applied": False,
            }
            metadata.append(
                {
                    "detection_id": i,
                    "bbox": box.tolist() if hasattr(box, "tolist") else list(map(int, box)),
                    "confidence": float(score),
                    "class_id": int(class_id),
                    "class_name": self._get_class_name(int(class_id)),
                    "area": float((box[2] - box[0]) * (box[3] - box[1])),
                    "merged_boxes_count": int(roi_info.get("merged_boxes_count", 1)),
                    "context_expansion_applied": bool(roi_info.get("context_expansion_applied", False)),
                }
            )

        return metadata
    
    def extract_crops(self, image: Union[np.ndarray, Image.Image]) -> List[Union[np.ndarray, Image.Image]]:
        """
        Detect objects and extract crop regions.
        
        Args:
            image: Input image
            
        Returns:
            List of cropped images
        """
        # Remember input format for output consistency
        input_is_pil = isinstance(image, Image.Image)
        
        # Convert PIL to numpy for processing if needed
        if input_is_pil:
            image_np = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        else:
            image_np = image
        
        # Detect objects
        boxes, scores, class_ids = self.detect_objects(image_np)
        
        crops = []
        for box, score, class_id in zip(boxes, scores, class_ids):
            x1, y1, x2, y2 = map(int, box)
            
            # Ensure bounds are within image
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(image_np.shape[1], x2)
            y2 = min(image_np.shape[0], y2)
            
            # Skip invalid boxes
            if x1 >= x2 or y1 >= y2:
                continue
            
            # Extract crop
            crop = image_np[y1:y2, x1:x2]
            
            # Convert back to PIL if input was PIL
            if input_is_pil:
                crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                crop = Image.fromarray(crop_rgb)
            
            crops.append(crop)
        
        return crops
    
    def get_detection_metadata(self, image: Union[np.ndarray, Image.Image]) -> List[dict]:
        """
        Get detection metadata for all detected objects.
        
        Args:
            image: Input image
            
        Returns:
            List of detection metadata dictionaries
        """
        return self.detect(image, return_metadata=True)
    
    def is_available(self) -> bool:
        """Check if detector is available and functional."""
        return OPENVINO_AVAILABLE and hasattr(self, 'exec_net')

    @staticmethod
    def _load_default_class_names() -> Optional[Tuple[str, ...]]:
        """Return the packaged YOLOX COCO class labels, if available."""
        if not DEFAULT_COCO_CLASS_NAMES:
            return None

        filtered = tuple(name for name in DEFAULT_COCO_CLASS_NAMES if isinstance(name, str) and name)
        if filtered:
            return filtered

        logger.warning(
            "Default YOLOX class label list was present but empty; detection metadata will use generated placeholders."
        )
        return None

    def _get_class_name(self, class_id: int) -> str:
        """Map a class index to a human-readable label."""
        if self.class_names and 0 <= class_id < len(self.class_names):
            return self.class_names[class_id]

        if 0 <= class_id < len(DEFAULT_COCO_CLASS_NAMES):
            return DEFAULT_COCO_CLASS_NAMES[class_id]

        return f"class_{class_id}"

    def _consolidate_rois(
        self,
        boxes: np.ndarray,
        scores: np.ndarray,
        class_ids: np.ndarray,
        image_shape: Tuple[int, int],
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, List[dict]]:
        # ROI consolidation is an optional post-processing stage that groups
        # overlapping boxes into a single region for downstream embedding.
        roi_cfg = self.detection_config.get("roi_consolidation", {})
        if not roi_cfg.get("enabled", False):
            # Fast-path: return raw detections unchanged when disabled.
            return (
                np.asarray(boxes),
                np.asarray(scores),
                np.asarray(class_ids),
                [
                {"merged_boxes_count": 1, "context_expansion_applied": False}
                for _ in range(len(boxes))
                ],
            )

        # IoU threshold controls cluster connectivity (higher = stricter merges).
        iou_threshold = roi_cfg.get("iou_threshold", 0.2)
        # When class_aware is True, only boxes of the same class can merge.
        class_aware = roi_cfg.get("class_aware", False)
        # context_scale expands merged ROIs to include extra scene context.
        context_scale = roi_cfg.get("context_scale", 0.2)

        def _cluster_boxes(input_boxes: np.ndarray, threshold: float) -> List[List[int]]:
            # Build clusters of overlapping boxes using IoU threshold.
            # Each cluster is a list of indices into input_boxes.
            if len(input_boxes) == 0:
                return []
            visited = [False] * len(input_boxes)
            clusters: List[List[int]] = []
            for i in range(len(input_boxes)):
                if visited[i]:
                    continue
                stack = [i]
                visited[i] = True
                cluster = [i]
                while stack:
                    idx = stack.pop()
                    for j in range(len(input_boxes)):
                        if visited[j]:
                            continue
                        # Adjacency is based on IoU between the current box and candidate.
                        if compute_iou(input_boxes[idx], input_boxes[j : j + 1])[0] >= threshold:
                            visited[j] = True
                            stack.append(j)
                            cluster.append(j)
                clusters.append(cluster)
            return clusters

        def _merge_union(input_boxes: np.ndarray) -> np.ndarray:
            # Union merge expands to cover all boxes in the cluster.
            x1 = np.min(input_boxes[:, 0])
            y1 = np.min(input_boxes[:, 1])
            x2 = np.max(input_boxes[:, 2])
            y2 = np.max(input_boxes[:, 3])
            return np.array([x1, y1, x2, y2], dtype=np.float32)

        def _expand_box(
            box: np.ndarray,
            shape: Tuple[int, int],
            scale: float,
        ) -> Tuple[np.ndarray, bool]:
            # Expand merged ROI by a fraction of its size for context.
            # Clamp the expanded box to image boundaries.
            height, width = shape
            x1, y1, x2, y2 = box
            box_w = max(1.0, x2 - x1)
            box_h = max(1.0, y2 - y1)
            pad_w = box_w * scale
            pad_h = box_h * scale
            nx1 = max(0.0, x1 - pad_w)
            ny1 = max(0.0, y1 - pad_h)
            nx2 = min(float(width), x2 + pad_w)
            ny2 = min(float(height), y2 + pad_h)
            expanded = np.array([nx1, ny1, nx2, ny2], dtype=np.float32)
            expansion_applied = scale > 0 and not np.allclose(expanded, box)
            return expanded, expansion_applied

        # Consolidate ROIs per class (optional) and expand context.
        merged_boxes: List[np.ndarray] = []
        merged_scores: List[float] = []
        merged_class_ids: List[int] = []
        merged_metadata: List[dict] = []

        # Iterate through class buckets or a single pooled bucket.
        unique_classes = np.unique(class_ids) if class_aware else np.array([-1])
        for cls in unique_classes:
            if class_aware:
                idx = np.where(class_ids == cls)[0]
            else:
                idx = np.arange(len(class_ids))
            # Select boxes/scores for the current bucket.
            class_boxes = boxes[idx]
            class_scores = scores[idx]
            clusters = _cluster_boxes(class_boxes, iou_threshold)
            for cluster in clusters:
                cluster_boxes = class_boxes[cluster]
                cluster_scores = class_scores[cluster]
                # Merge the cluster into a single ROI then expand for context.
                merged = _merge_union(cluster_boxes)
                merged, expansion_applied = _expand_box(merged, image_shape, context_scale)
                # Keep the best score in the cluster as the representative score.
                merged_boxes.append(merged)
                merged_scores.append(float(cluster_scores.max()))
                merged_metadata.append(
                    {
                        "merged_boxes_count": len(cluster),
                        "context_expansion_applied": expansion_applied,
                    }
                )
                if class_aware:
                    merged_class_ids.append(int(cls))
                else:
                    # When class-agnostic, retain the class id of the top-scoring box.
                    merged_class_ids.append(int(class_ids[idx][cluster_scores.argmax()]))

        if merged_boxes:
            boxes_array = np.asarray(merged_boxes, dtype=np.float32)
            scores_array = np.asarray(merged_scores, dtype=float)
            class_ids_array = np.asarray(merged_class_ids, dtype=int)
        else:
            boxes_array = np.empty((0, 4), dtype=np.float32)
            scores_array = np.empty((0,), dtype=float)
            class_ids_array = np.empty((0,), dtype=int)

        return boxes_array, scores_array, class_ids_array, merged_metadata


def create_detector(config: Optional[dict] = None) -> Optional[YOLOXDetector]:
    """
    Factory function to create YOLOXDetector instance.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        YOLOXDetector instance or None if detection is disabled
    """
    try:
        if config is None:
            config = get_config()
        
        detection_config = config.get('object_detection', {})
        is_enabled = detection_config.get('enabled', False)
        
        logger.info(f"Creating detector with config: enabled={is_enabled}")
        logger.debug(f"Full detection config: {detection_config}")
        
        if not is_enabled:
            logger.info("Object detection disabled in configuration - returning None")
            return None
        
        if not OPENVINO_AVAILABLE:
            logger.error("OpenVINO is not available - cannot create detector")
            raise ImportError("OpenVINO is required for object detection but is not available")
        
        logger.info("Creating YOLOXDetector instance...")
        try:
            detector = YOLOXDetector(config)
            logger.info("YOLOXDetector created successfully")
            return detector
        except Exception as detector_error:
            logger.error(f"YOLOXDetector creation failed: {detector_error}")
            logger.error(f"YOLOXDetector exception type: {type(detector_error).__name__}")
            import traceback
            logger.error(f"YOLOXDetector traceback: {traceback.format_exc()}")
            raise  # Re-raise the exception instead of returning None
        
    except Exception as e:
        logger.error(f"Failed to create detector: {e}")
        logger.error(f"Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None
