# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
Lightweight YOLO-Pose inference using OpenVINO Runtime directly.

Replaces ultralytics.YOLO to avoid pulling in PyTorch (~2 GB).
Expects an OpenVINO IR model (.xml/.bin) exported from yolo26n-pose.

YOLO26 uses an end-to-end architecture with built-in NMS.
Output shape: (1, 300, 57)
  - 300 = max post-NMS detections
  - 57  = 4 (x1,y1,x2,y2 bbox) + 1 (score) + 1 (class_id) + 51 (17 kp * 3)
"""

import logging
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import openvino as ov

logger = logging.getLogger(__name__)

_INPUT_SIZE = 640  # YOLO default


@dataclass
class _KeypointsResult:
    """Mirrors the subset of ultralytics result API used by PoseAnalyzer."""

    xy: np.ndarray  # Shape: [num_persons, 17, 2]
    conf: np.ndarray  # Shape: [num_persons, 17]


@dataclass
class _PoseResult:
    """Single-image result matching the ultralytics interface we use."""

    keypoints: _KeypointsResult | None


class YOLOPoseOV:
    """
    Drop-in replacement for ``ultralytics.YOLO`` (pose task only).

    Only the ``__call__`` interface used by ``PoseAnalyzer`` is implemented:

        results = model(frame, verbose=False)
        kp_xy   = results[0].keypoints.xy[0].cpu().numpy()
        kp_conf = results[0].keypoints.conf[0].cpu().numpy()
    """

    def __init__(self, model_path: str, device: str = "AUTO"):
        path = Path(model_path)
        if path.suffix != ".xml":
            raise ValueError(f"Expected .xml model path, got: {path}")

        core = ov.Core()
        logger.info("Compiling YOLO-Pose model %s on %s", path, device)
        self._model = core.compile_model(str(path), device)
        self._input_layer = self._model.input(0)
        self._output_layer = self._model.output(0)

    # ------------------------------------------------------------------
    def __call__(
        self, image: np.ndarray, *, verbose: bool = False  # noqa: ARG002
    ) -> list[_PoseResult]:
        """Run inference on a single BGR image."""
        img, ratio, (pad_w, pad_h) = self._preprocess(image)
        output = self._model([img])[self._output_layer]  # (1, 300, 57)
        results = self._postprocess(output, ratio, pad_w, pad_h)
        return results

    # ------------------------------------------------------------------
    @staticmethod
    def _preprocess(
        image: np.ndarray,
    ) -> tuple[np.ndarray, float, tuple[int, int]]:
        """Letterbox + normalise to (1, 3, 640, 640) float32."""
        # Coerce to 3-channel BGR. Decoded JPEGs may be grayscale (2D) or
        # BGRA (4 channels) depending on the source camera.
        if image.ndim == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        elif image.ndim == 3 and image.shape[2] == 4:
            image = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
        elif image.ndim == 3 and image.shape[2] == 1:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

        h, w = image.shape[:2]
        ratio = min(_INPUT_SIZE / h, _INPUT_SIZE / w)
        new_w, new_h = max(int(w * ratio), 1), max(int(h * ratio), 1)
        resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

        pad_w = (_INPUT_SIZE - new_w) // 2
        pad_h = (_INPUT_SIZE - new_h) // 2
        padded = np.full((_INPUT_SIZE, _INPUT_SIZE, 3), 114, dtype=np.uint8)
        padded[pad_h : pad_h + new_h, pad_w : pad_w + new_w] = resized

        blob = padded.astype(np.float32) / 255.0
        blob = blob.transpose(2, 0, 1)[np.newaxis]  # (1,3,640,640)
        return blob, ratio, (pad_w, pad_h)

    # ------------------------------------------------------------------
    def _postprocess(
        self,
        output: np.ndarray,
        ratio: float,
        pad_w: int,
        pad_h: int,
        conf_threshold: float = 0.25,
    ) -> list[_PoseResult]:
        """
        Parse YOLO26-Pose end-to-end output tensor.

        YOLO26 has built-in NMS — output is already post-NMS.
        output shape: (1, 300, 57)
          - 0:4   = bbox (x1, y1, x2, y2) in letterbox coords
          - 4     = confidence score
          - 5     = class id (always 0 for single-class pose)
          - 6:57  = 17 keypoints * 3 (x, y, conf)
        """
        detections = output[0]  # (300, 57)

        scores = detections[:, 4]
        mask = scores > conf_threshold
        detections = detections[mask]

        if len(detections) == 0:
            return [_PoseResult(keypoints=None)]

        # Sort by score descending (highest confidence first)
        order = detections[:, 4].argsort()[::-1]
        detections = detections[order]

        # Extract keypoints — columns 6..57 → (N, 17, 3)
        raw_kp = detections[:, 6:].reshape(-1, 17, 3)
        kp_xy = raw_kp[:, :, :2].copy()
        kp_conf = raw_kp[:, :, 2].copy()

        # Undo letterbox transform
        kp_xy[:, :, 0] = (kp_xy[:, :, 0] - pad_w) / ratio
        kp_xy[:, :, 1] = (kp_xy[:, :, 1] - pad_h) / ratio

        return [_PoseResult(keypoints=_KeypointsResult(xy=kp_xy, conf=kp_conf))]
