# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""OVMS gRPC client used by the VIPPET detection-to-classification proof of concept."""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore, Event
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
import tritonclient.grpc as grpcclient


OVMS_ENDPOINT = os.environ.get("OVMS_GRPC_ENDPOINT", "ovms:9000")
OVMS_TIMEOUT_S = float(os.environ.get("OVMS_TIMEOUT_S", "2"))
OVMS_MAX_IN_FLIGHT = int(os.environ.get("OVMS_MAX_IN_FLIGHT", "2"))
YOLO_MODEL_NAME = os.environ.get("OVMS_DETECTION_MODEL", "yolo11n-int8")
YOLO_INPUT_NAME = os.environ.get("OVMS_DETECTION_INPUT", "x")
YOLO_OUTPUT_NAME = os.environ.get("OVMS_DETECTION_OUTPUT", "out_0")
CLASSIFICATION_MODEL_NAME = os.environ.get(
    "OVMS_CLASSIFICATION_MODEL", "efficientnet-b0-int8"
)
CLASSIFICATION_INPUT_NAME = os.environ.get("OVMS_CLASSIFICATION_INPUT", "sub")
CLASSIFICATION_OUTPUT_NAME = os.environ.get(
    "OVMS_CLASSIFICATION_OUTPUT", "efficientnet-b0/model/head/dense/BiasAdd/Add"
)
CLASSIFICATION_LABELS_FILE = Path(
    os.environ.get(
        "OVMS_CLASSIFICATION_LABELS_FILE",
        "/models/output/pipeline-zoo-models/efficientnet-b0_INT8/efficientnet-b0.json",
    )
)

YOLO_INPUT_SIZE = 640
YOLO_CONFIDENCE_THRESHOLD = 0.5
YOLO_NMS_IOU_THRESHOLD = 0.45

if OVMS_MAX_IN_FLIGHT < 1:
    raise ValueError("OVMS_MAX_IN_FLIGHT must be at least one")

_in_flight_requests = BoundedSemaphore(OVMS_MAX_IN_FLIGHT)

COCO_LABELS = (
    "person",
    "bicycle",
    "car",
    "motorcycle",
    "airplane",
    "bus",
    "train",
    "truck",
    "boat",
    "traffic light",
    "fire hydrant",
    "stop sign",
    "parking meter",
    "bench",
    "bird",
    "cat",
    "dog",
    "horse",
    "sheep",
    "cow",
    "elephant",
    "bear",
    "zebra",
    "giraffe",
    "backpack",
    "umbrella",
    "handbag",
    "tie",
    "suitcase",
    "frisbee",
    "skis",
    "snowboard",
    "sports ball",
    "kite",
    "baseball bat",
    "baseball glove",
    "skateboard",
    "surfboard",
    "tennis racket",
    "bottle",
    "wine glass",
    "cup",
    "fork",
    "knife",
    "spoon",
    "bowl",
    "banana",
    "apple",
    "sandwich",
    "orange",
    "broccoli",
    "carrot",
    "hot dog",
    "pizza",
    "donut",
    "cake",
    "chair",
    "couch",
    "potted plant",
    "bed",
    "dining table",
    "toilet",
    "tv",
    "laptop",
    "mouse",
    "remote",
    "keyboard",
    "cell phone",
    "microwave",
    "oven",
    "toaster",
    "sink",
    "refrigerator",
    "book",
    "clock",
    "vase",
    "scissors",
    "teddy bear",
    "hair drier",
    "toothbrush",
)


@dataclass(frozen=True)
class Detection:
    """One detected object in source-image pixel coordinates."""

    x: int
    y: int
    width: int
    height: int
    label: str
    confidence: float


@dataclass(frozen=True)
class Classification:
    """One ImageNet class predicted for a detected region."""

    label: str
    confidence: float
    class_id: int


class OvmsInferenceError(RuntimeError):
    """Raised when a request to OVMS fails or returns an unexpected tensor."""


@lru_cache(maxsize=1)
def _client() -> grpcclient.InferenceServerClient:
    return grpcclient.InferenceServerClient(url=OVMS_ENDPOINT)


@lru_cache(maxsize=1)
def _classification_labels() -> tuple[str, ...]:
    try:
        model_proc = json.loads(CLASSIFICATION_LABELS_FILE.read_text(encoding="utf-8"))
        labels = model_proc["output_postproc"][0]["labels"]
    except (KeyError, OSError, TypeError, ValueError) as error:
        raise OvmsInferenceError(
            f"Cannot load classification labels from {CLASSIFICATION_LABELS_FILE}: {error}"
        ) from error

    if not isinstance(labels, list) or not all(
        isinstance(label, str) for label in labels
    ):
        raise OvmsInferenceError(
            f"Classification labels in {CLASSIFICATION_LABELS_FILE} are invalid"
        )
    return tuple(labels)


def _infer(
    model_name: str, input_name: str, output_name: str, tensor: np.ndarray
) -> np.ndarray:
    """Submit one bounded asynchronous OVMS request and wait for its result."""
    request = grpcclient.InferInput(input_name, tensor.shape, "FP32")
    request.set_data_from_numpy(tensor)

    if not _in_flight_requests.acquire(timeout=OVMS_TIMEOUT_S):
        raise OvmsInferenceError(
            f"Timed out waiting for an OVMS request slot at {OVMS_ENDPOINT}"
        )

    completed = Event()
    response: dict[str, object] = {}

    def _on_response(result: object, error: Exception | None) -> None:
        response["result"] = result
        response["error"] = error
        completed.set()

    try:
        _client().async_infer(
            model_name=model_name,
            inputs=[request],
            callback=_on_response,
            outputs=[grpcclient.InferRequestedOutput(output_name)],
            client_timeout=OVMS_TIMEOUT_S,
        )
        if not completed.wait(OVMS_TIMEOUT_S):
            raise TimeoutError(f"OVMS request exceeded {OVMS_TIMEOUT_S} seconds")
        if error := response.get("error"):
            raise error
        result = response.get("result")
        if result is None:
            raise RuntimeError("OVMS completed an inference request without a result")
        output = result.as_numpy(output_name)
    except Exception as error:
        raise OvmsInferenceError(
            f"OVMS inference failed for model '{model_name}' at {OVMS_ENDPOINT}: {error}"
        ) from error
    finally:
        _in_flight_requests.release()

    if output is None:
        raise OvmsInferenceError(
            f"OVMS returned no '{output_name}' output for model '{model_name}'"
        )
    return output


def _letterbox(image_bgr: np.ndarray, size: int) -> tuple[np.ndarray, float, int, int]:
    """Resize an image to a square while preserving aspect ratio and using YOLO padding."""
    height, width = image_bgr.shape[:2]
    scale = min(size / width, size / height)
    resized_width = round(width * scale)
    resized_height = round(height * scale)
    resized = cv2.resize(
        image_bgr, (resized_width, resized_height), interpolation=cv2.INTER_LINEAR
    )

    pad_x = (size - resized_width) // 2
    pad_y = (size - resized_height) // 2
    padded = cv2.copyMakeBorder(
        resized,
        pad_y,
        size - resized_height - pad_y,
        pad_x,
        size - resized_width - pad_x,
        cv2.BORDER_CONSTANT,
        value=(114, 114, 114),
    )
    return padded, scale, pad_x, pad_y


def _iou(box: np.ndarray, boxes: np.ndarray) -> np.ndarray:
    left = np.maximum(box[0], boxes[:, 0])
    top = np.maximum(box[1], boxes[:, 1])
    right = np.minimum(box[2], boxes[:, 2])
    bottom = np.minimum(box[3], boxes[:, 3])
    intersection = np.maximum(0, right - left) * np.maximum(0, bottom - top)
    box_area = (box[2] - box[0]) * (box[3] - box[1])
    boxes_area = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    return intersection / np.maximum(box_area + boxes_area - intersection, 1e-6)


def _nms(boxes: np.ndarray, scores: np.ndarray) -> np.ndarray:
    """Return kept detection indices using class-agnostic non-maximum suppression."""
    order = scores.argsort()[::-1]
    kept: list[int] = []
    while order.size:
        current = order[0]
        kept.append(int(current))
        if order.size == 1:
            break
        remaining = order[1:]
        order = remaining[
            _iou(boxes[current], boxes[remaining]) < YOLO_NMS_IOU_THRESHOLD
        ]
    return np.asarray(kept, dtype=np.int64)


def detect(image_bgr: np.ndarray) -> list[Detection]:
    """Run YOLO11n inference in OVMS and return detections in source-image coordinates."""
    if image_bgr.ndim != 3 or image_bgr.shape[2] != 3:
        raise ValueError("Detection input must be a BGR image with three channels")

    source_height, source_width = image_bgr.shape[:2]
    letterboxed, scale, pad_x, pad_y = _letterbox(image_bgr, YOLO_INPUT_SIZE)
    rgb = cv2.cvtColor(letterboxed, cv2.COLOR_BGR2RGB)
    tensor = rgb.astype(np.float32).transpose(2, 0, 1)[None, ...] / 255.0
    output = _infer(YOLO_MODEL_NAME, YOLO_INPUT_NAME, YOLO_OUTPUT_NAME, tensor)

    predictions = np.asarray(output, dtype=np.float32).squeeze(0).T
    if predictions.ndim != 2 or predictions.shape[1] != 4 + len(COCO_LABELS):
        raise OvmsInferenceError(
            f"Unexpected YOLO output shape {output.shape}; expected [1, {4 + len(COCO_LABELS)}, anchors]"
        )

    class_ids = predictions[:, 4:].argmax(axis=1)
    confidences = predictions[np.arange(predictions.shape[0]), class_ids + 4]
    selected = confidences >= YOLO_CONFIDENCE_THRESHOLD
    predictions = predictions[selected]
    class_ids = class_ids[selected]
    confidences = confidences[selected]
    if not predictions.size:
        return []

    center_x, center_y, width, height = predictions[:, :4].T
    boxes = np.column_stack(
        (
            center_x - width / 2,
            center_y - height / 2,
            center_x + width / 2,
            center_y + height / 2,
        )
    )
    boxes[:, [0, 2]] = (boxes[:, [0, 2]] - pad_x) / scale
    boxes[:, [1, 3]] = (boxes[:, [1, 3]] - pad_y) / scale
    boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, source_width)
    boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, source_height)

    kept_indices = _nms(boxes, confidences)
    detections: list[Detection] = []
    for index in kept_indices:
        x_min, y_min, x_max, y_max = boxes[index].astype(int)
        if x_max <= x_min or y_max <= y_min:
            continue
        detections.append(
            Detection(
                x=int(x_min),
                y=int(y_min),
                width=int(x_max - x_min),
                height=int(y_max - y_min),
                label=COCO_LABELS[int(class_ids[index])],
                confidence=float(confidences[index]),
            )
        )
    return detections


def _preprocess_classification(image_bgr: np.ndarray) -> np.ndarray:
    """Resize one BGR ROI into the EfficientNet NCHW input tensor."""
    if image_bgr.ndim != 3 or image_bgr.shape[2] != 3:
        raise ValueError("Classification input must be a BGR image with three channels")

    height, width = image_bgr.shape[:2]
    if height < 1 or width < 1:
        raise ValueError("Classification input must have non-zero width and height")
    scale = max(224 / width, 224 / height)
    resized = cv2.resize(
        image_bgr,
        (round(width * scale), round(height * scale)),
        interpolation=cv2.INTER_LINEAR,
    )
    start_x = (resized.shape[1] - 224) // 2
    start_y = (resized.shape[0] - 224) // 2
    cropped = resized[start_y : start_y + 224, start_x : start_x + 224]
    return cropped.astype(np.float32).transpose(2, 0, 1)


def _postprocess_classification(output: np.ndarray, top_k: int) -> list[Classification]:
    """Convert one EfficientNet output vector into ranked classifications."""
    output = np.asarray(output, dtype=np.float32).reshape(-1)
    labels = _classification_labels()
    if output.size != len(labels):
        raise OvmsInferenceError(
            f"Classification output has {output.size} classes; expected {len(labels)}"
        )

    top_indices = output.argsort()[-top_k:][::-1]
    return [
        Classification(
            label=labels[int(index)],
            confidence=float(output[int(index)]),
            class_id=int(index),
        )
        for index in top_indices
    ]


@lru_cache(maxsize=1)
def _classification_batch_supported() -> bool:
    """Return whether OVMS currently exposes EfficientNet with batch capacity > 1."""
    try:
        metadata = _client().get_model_metadata(CLASSIFICATION_MODEL_NAME)
        if not metadata.inputs:
            raise ValueError("metadata has no inputs")
        shape = metadata.inputs[0].shape
        return int(shape[0]) != 1
    except Exception as error:
        raise OvmsInferenceError(
            f"Cannot read OVMS metadata for '{CLASSIFICATION_MODEL_NAME}': {error}"
        ) from error


def classify_batch(
    images_bgr: list[np.ndarray], top_k: int = 1
) -> list[list[Classification]]:
    """Classify ROI images in one OVMS request when its served batch is dynamic."""
    if top_k < 1:
        raise ValueError("top_k must be at least one")
    if not images_bgr:
        return []

    tensors = [_preprocess_classification(image_bgr) for image_bgr in images_bgr]
    if _classification_batch_supported():
        output = _infer(
            CLASSIFICATION_MODEL_NAME,
            CLASSIFICATION_INPUT_NAME,
            CLASSIFICATION_OUTPUT_NAME,
            np.stack(tensors),
        )
        if output.shape[0] != len(tensors):
            raise OvmsInferenceError(
                f"Classification batch returned {output.shape[0]} results for {len(tensors)} ROIs"
            )
        return [_postprocess_classification(result, top_k) for result in output]

    def _classify_static_batch(tensor: np.ndarray) -> list[Classification]:
        output = _infer(
            CLASSIFICATION_MODEL_NAME,
            CLASSIFICATION_INPUT_NAME,
            CLASSIFICATION_OUTPUT_NAME,
            tensor[None, ...],
        )
        return _postprocess_classification(output, top_k)

    workers = min(len(tensors), OVMS_MAX_IN_FLIGHT)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(executor.map(_classify_static_batch, tensors))


def classify(image_bgr: np.ndarray, top_k: int = 1) -> list[Classification]:
    """Classify one BGR ROI through EfficientNet B0 served by OVMS."""
    return classify_batch([image_bgr], top_k=top_k)[0]
