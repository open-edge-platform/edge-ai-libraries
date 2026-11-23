# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Object detection with Hugging Face ``OpenVINO/*`` models via OpenVINO Model API.

The configured model (``MM_DATAPREP_DETECTION_MODEL_NAME``, an ``OpenVINO/<repo>``
Hugging Face repo) is downloaded once into the model directory and
loaded with ``model_api``, which picks the right pre/post-processing wrapper
(SSD-style exports with in-graph NMS, YOLO, ...) from the model's runtime info.
"""

import logging
import threading
import time
from pathlib import Path
from typing import List, Optional, Tuple, Union

import cv2
import numpy as np
from PIL import Image

from src.common.logger import sanitize_for_log

from ..utils.config_utils import (
    get_config,
    normalize_class_name,
    parse_detection_classes,
    validate_detection_model_name,
)

logger = logging.getLogger(__name__)

MODEL_DOWNLOAD_PATTERNS = ["*.xml", "*.bin"]
MODEL_DOWNLOAD_ATTEMPTS = 3

try:
    from model_api.models import DetectionModel, Model

    MODEL_API_AVAILABLE = True
except ImportError:
    MODEL_API_AVAILABLE = False
    logger.warning("openvino-model-api not available. Object detection will be disabled.")


def compute_iou(box, boxes):
    """Compute IoU between a single [x1, y1, x2, y2] box and an (N, 4) array of boxes."""
    boxes = np.asarray(boxes)
    box = np.asarray(box)
    if boxes.size == 0:
        return np.asarray([])

    xx1 = np.maximum(box[0], boxes[:, 0])
    yy1 = np.maximum(box[1], boxes[:, 1])
    xx2 = np.minimum(box[2], boxes[:, 2])
    yy2 = np.minimum(box[3], boxes[:, 3])

    inter = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
    area_box = (box[2] - box[0] + 1) * (box[3] - box[1] + 1)
    area_boxes = (boxes[:, 2] - boxes[:, 0] + 1) * (boxes[:, 3] - boxes[:, 1] + 1)
    union = area_box + area_boxes - inter
    return np.where(union > 0, inter / union, 0.0)


def _empty_detections() -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    return (
        np.empty((0, 4), dtype=int),
        np.empty((0,), dtype=float),
        np.empty((0,), dtype=int),
    )


class ObjectDetector:
    """Object detector for frame-based video processing.

    Wraps an OpenVINO Model API detection model and adds an optional class
    filter and ROI consolidation.
    """

    def __init__(self, config: Optional[dict] = None):
        """
        Initialize the detector, downloading the model if it is not cached yet.

        Args:
            config: Configuration dictionary. If None, loads from effective config.
        """
        if not MODEL_API_AVAILABLE:
            raise ImportError(
                "openvino-model-api is required for object detection. "
                "Please install openvino-model-api."
            )

        if config is None:
            config = get_config()

        self.config = config
        self.detection_config = config.get("object_detection", {}).copy()

        self.device = self.detection_config.get("device") or "CPU"
        self.confidence_threshold = float(self.detection_config.get("confidence_threshold", 0.85))
        self.model_dir = self.detection_config.get("model_dir") or "/app/models/object-detection"
        self.model_name = validate_detection_model_name(self.detection_config.get("model_name"))
        if not self.model_name:
            raise ValueError(
                "Object detection model name must be set via MM_DATAPREP_DETECTION_MODEL_NAME"
            )
        self.class_filter = parse_detection_classes(self.detection_config.get("classes"))
        self.model_path = self._local_model_dir()

        self._local = threading.local()
        self.model = None
        self.class_names: Tuple[str, ...] = ()

        xml_path = self._ensure_model_available()
        self._load_model(xml_path)
        self._validate_class_filter()

        logger.info(
            "Object detector initialized: model=%s, wrapper=%s, device=%s, confidence=%s, classes=%s",
            sanitize_for_log(self.model_name, max_length=128),
            type(self.model).__name__,
            sanitize_for_log(self.device, max_length=64),
            sanitize_for_log(self.confidence_threshold, max_length=32),
            sanitize_for_log(",".join(self.class_filter) if self.class_filter else "all", max_length=512),
        )

    def _local_model_dir(self) -> Path:
        """Return ``<model_dir>/<namespace>/<repo>``, refusing paths that escape model_dir."""
        root = Path(self.model_dir).resolve()
        target = root.joinpath(*self.model_name.split("/")).resolve()
        if not target.is_relative_to(root):
            raise ValueError(f"Invalid object detection model name: {self.model_name!r}")
        return target

    def _find_model_xml(self) -> Optional[Path]:
        """Return the cached model IR (.xml with matching .bin), if present."""
        if not self.model_path.is_dir():
            return None
        candidates = [
            xml for xml in sorted(self.model_path.glob("*.xml")) if xml.with_suffix(".bin").is_file()
        ]
        if len(candidates) > 1:
            raise RuntimeError(
                f"Expected one OpenVINO IR model in {self.model_path}, found: "
                f"{', '.join(c.name for c in candidates)}"
            )
        return candidates[0] if candidates else None

    def _ensure_model_available(self) -> Path:
        """Download the configured Hugging Face model unless it is already cached."""
        xml_path = self._find_model_xml()
        if xml_path is not None:
            logger.info("Detection model found: %s", xml_path)
            return xml_path

        from huggingface_hub import snapshot_download

        logger.info(
            "Detection model %s not found locally. Downloading from Hugging Face to %s",
            sanitize_for_log(self.model_name, max_length=128),
            self.model_path,
        )
        self.model_path.mkdir(parents=True, exist_ok=True)
        for attempt in range(1, MODEL_DOWNLOAD_ATTEMPTS + 1):
            try:
                snapshot_download(
                    repo_id=self.model_name,
                    local_dir=str(self.model_path),
                    allow_patterns=MODEL_DOWNLOAD_PATTERNS,
                )
                break
            except Exception as exc:
                if attempt == MODEL_DOWNLOAD_ATTEMPTS:
                    raise RuntimeError(
                        f"Failed to download detection model {self.model_name} from Hugging Face "
                        f"after {MODEL_DOWNLOAD_ATTEMPTS} attempts: {exc}"
                    ) from exc
                logger.warning("Download attempt %d failed: %s. Retrying...", attempt, exc)
                time.sleep(2 * attempt)

        xml_path = self._find_model_xml()
        if xml_path is None:
            raise FileNotFoundError(
                f"{self.model_name} does not contain an OpenVINO IR model (.xml/.bin). "
                "Use an OpenVINO object detection model from https://huggingface.co/OpenVINO."
            )
        logger.info("Detection model downloaded: %s", xml_path)
        return xml_path

    def _load_model(self, xml_path: Path) -> None:
        """Load the model with the Model API wrapper named in its runtime info."""
        model = Model.create_model(
            str(xml_path),
            device=self.device,
            configuration={"confidence_threshold": self.confidence_threshold},
            preload=True,
        )
        if not isinstance(model, DetectionModel):
            raise ValueError(
                f"{self.model_name} is not an object detection model "
                f"(Model API wrapper: {type(model).__name__})."
            )
        self._prefilter_nms_by_confidence(model)
        self.model = model
        self.class_names = tuple(str(label) for label in (model.params.labels or []))
        logger.info(
            "Detection model loaded on %s: wrapper=%s, input=%sx%s, classes=%d",
            sanitize_for_log(self.device, max_length=64),
            type(model).__name__,
            getattr(model, "w", "?"),
            getattr(model, "h", "?"),
            len(self.class_names),
        )

    @staticmethod
    def _prefilter_nms_by_confidence(model: "DetectionModel") -> None:
        """Run NMS only on boxes above the confidence threshold.

        Some Model API wrappers (e.g. SSD, used by Geti-style exports) run a
        pure-Python NMS over every candidate box (thousands per frame) and only
        drop low-confidence boxes afterwards. Greedy NMS lets a box suppress only
        lower-scoring boxes, so discarding boxes the wrapper would filter out
        anyway gives identical results at a fraction of the cost.
        """
        calculate_nms = model._calculate_nms

        def _calculate_nms(boxes, scores, labels, *args, **kwargs):
            candidates = np.flatnonzero(np.asarray(scores) > model.params.confidence_threshold)
            if candidates.size == len(scores):
                return calculate_nms(boxes, scores, labels, *args, **kwargs)
            keep = calculate_nms(
                boxes[candidates], scores[candidates], labels[candidates], *args, **kwargs
            )
            return candidates[np.asarray(keep, dtype=np.int64)].tolist()

        model._calculate_nms = _calculate_nms

    def _validate_class_filter(self) -> None:
        """Fail fast when the class filter names labels the model does not have."""
        if not self.class_filter:
            return
        if not self.class_names:
            raise ValueError(
                f"{self.model_name} has no class labels, so MM_DATAPREP_DETECTION_CLASSES "
                "cannot be applied."
            )
        available = {normalize_class_name(name) for name in self.class_names}
        unknown = [name for name in self.class_filter if name not in available]
        if unknown:
            raise ValueError(
                f"MM_DATAPREP_DETECTION_CLASSES contains classes not provided by {self.model_name}: "
                f"{', '.join(unknown)}. Available classes: {', '.join(self.class_names)}"
            )

    def _infer(self, image_bgr: np.ndarray):
        """Run one detection on a BGR image; safe to call from multiple threads.

        Model API's own ``__call__`` shares one infer request across callers, so
        reuse its stateless pre/post-processing with a per-thread infer request.
        """
        adapter = self.model.inference_adapter
        dict_data, meta = self.model.base_preprocess(image_bgr)
        if getattr(adapter, "use_python_preprocessing", False):
            dict_data = {key: adapter.preprocessor(value) for key, value in dict_data.items()}

        request = getattr(self._local, "request", None)
        if request is None:
            request = adapter.compiled_model.create_infer_request()
            self._local.request = request
        request.infer(dict_data)
        raw_result = {name: request.get_tensor(name).data for name in adapter.get_output_layers()}
        return self.model.postprocess(raw_result, meta)

    def detect_objects(
        self, image: Union[np.ndarray, Image.Image]
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Detect objects in an image.

        Args:
            image: Input image (BGR numpy array or PIL Image)

        Returns:
            Tuple of (bounding_boxes, confidence_scores, class_indices)
        """
        if isinstance(image, Image.Image):
            image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

        self._local.roi_metadata = []
        try:
            result = self._infer(image)

            boxes = np.asarray(result.bboxes, dtype=int).reshape(-1, 4)
            scores = np.asarray(result.scores, dtype=float).reshape(-1)
            class_ids = np.asarray(result.labels, dtype=int).reshape(-1)

            if self.class_filter and len(class_ids):
                keep = np.array(
                    [normalize_class_name(self._get_class_name(cid)) in self.class_filter for cid in class_ids],
                    dtype=bool,
                )
                boxes, scores, class_ids = boxes[keep], scores[keep], class_ids[keep]

            roi_metadata = [
                {"merged_boxes_count": 1, "context_expansion_applied": False}
                for _ in range(len(boxes))
            ]
            if len(boxes) > 0:
                boxes, scores, class_ids, roi_metadata = self._consolidate_rois(
                    boxes, scores, class_ids, image.shape[:2]
                )
            self._local.roi_metadata = roi_metadata
            return boxes, scores, class_ids

        except Exception as e:
            logger.error(f"Detection failed: {e}")
            return _empty_detections()

    def detect(
        self,
        image: Union[np.ndarray, Image.Image],
        *,
        return_metadata: bool = True,
    ) -> Union[List[dict], Tuple[np.ndarray, np.ndarray, np.ndarray]]:
        """Detect objects and return metadata dictionaries (or the raw tuple).

        Args:
            image: Input image to run detection against.
            return_metadata: When ``True`` (default) return a list of detection
                metadata dictionaries. When ``False`` return the raw
                ``(boxes, scores, class_ids)`` tuple.
        """
        boxes, scores, class_ids = self.detect_objects(image)

        if not return_metadata:
            return boxes, scores, class_ids

        metadata: List[dict] = []
        roi_metadata = getattr(self._local, "roi_metadata", [])
        for i, (box, score, class_id) in enumerate(zip(boxes, scores, class_ids)):
            roi_info = roi_metadata[i] if i < len(roi_metadata) else {
                "merged_boxes_count": 1,
                "context_expansion_applied": False,
            }
            metadata.append(
                {
                    "detection_id": i,
                    "bbox": [int(round(float(v))) for v in box],
                    "confidence": float(score),
                    "class_id": int(class_id),
                    "class_name": self._get_class_name(int(class_id)),
                    "area": float((box[2] - box[0]) * (box[3] - box[1])),
                    "merged_boxes_count": int(roi_info.get("merged_boxes_count", 1)),
                    "context_expansion_applied": bool(roi_info.get("context_expansion_applied", False)),
                }
            )

        return metadata

    def _get_class_name(self, class_id: int) -> str:
        """Map a class index to the model's label."""
        if 0 <= class_id < len(self.class_names):
            return self.class_names[class_id]
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


def create_detector(config: Optional[dict] = None) -> Optional[ObjectDetector]:
    """
    Factory function to create an ObjectDetector instance.

    Args:
        config: Configuration dictionary

    Returns:
        ObjectDetector instance or None if detection is disabled or fails to initialize
    """
    try:
        if config is None:
            config = get_config()

        detection_config = config.get("object_detection", {})
        is_enabled = detection_config.get("enabled", False)

        logger.info(
            "Creating detector with config: enabled=%s",
            sanitize_for_log(is_enabled, max_length=32),
        )
        logger.debug(
            "Full detection config: %s",
            sanitize_for_log(detection_config, max_length=512),
        )

        if not is_enabled:
            logger.info("Object detection disabled in configuration - returning None")
            return None

        if not MODEL_API_AVAILABLE:
            raise ImportError("openvino-model-api is required for object detection but is not available")

        detector = ObjectDetector(config)
        logger.info("ObjectDetector created successfully")
        return detector

    except Exception as e:
        logger.error(f"Failed to create object detector: {type(e).__name__}: {e}")
        logger.debug("Object detector creation traceback", exc_info=True)
        return None
