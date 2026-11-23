# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import math
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

import config


class OCR(ABC):
    """Reads the text out of an image; `context` describes the crop's PDF region."""

    @abstractmethod
    def read(self, image: Any, context: Optional[Mapping[str, Any]] = None) -> str:
        """The text in one image (a PIL image or a crop of a page)."""

    def read_batch(
        self,
        images: Sequence[Any],
        contexts: Optional[Sequence[Mapping[str, Any]]] = None,
    ) -> List[str]:
        """One string per image. Overridable where a backend batches natively."""
        contexts = contexts or [None] * len(images)
        return [self.read(image, ctx) for image, ctx in zip(images, contexts)]


class CallableOCR(OCR):
    """Adapts a plain `image -> str` callable to the `OCR` interface; `context` is dropped."""

    def __init__(self, fn: Callable[[Any], str]):
        self._fn = fn

    def read(self, image: Any, context: Optional[Mapping[str, Any]] = None) -> str:
        return self._fn(image)


def as_ocr(ocr: Any) -> OCR:
    """Coerce an `OCR`, or a bare `image -> str` callable, into an `OCR`."""
    if isinstance(ocr, OCR):
        return ocr
    if callable(ocr):
        return CallableOCR(ocr)
    raise TypeError(f"Not an OCR or a callable: {type(ocr).__name__}")


# --- backends -----------------------------------------------------------------


class TesseractOCR(OCR):
    """Reads a crop's pixels with the lightweight Tesseract runtime."""

    def __init__(self, lang: str = config.OCR_LANG):
        self.lang = lang
        self._runtime: Any = None

    @staticmethod
    def _normalize_lang(lang: Optional[str]) -> Optional[str]:
        if not lang:
            return None
        aliases = {
            "en": "eng",
            "english": "eng",
            "zh": "chi_sim",
            "zh-cn": "chi_sim",
            "zh_cn": "chi_sim",
            "zh-hans": "chi_sim",
        }
        parts = [part.strip().lower() for part in str(lang).split("+") if part.strip()]
        return "+".join(aliases.get(part, part) for part in parts) or None

    def _ensure_loaded(self) -> None:
        if self._runtime is not None:
            return
        try:
            import pytesseract  # pyright: ignore[reportMissingImports]
        except ImportError as err:
            raise ImportError(
                "The 'tesseract' OCR backend needs pytesseract and the Tesseract "
                "binary. Install pytesseract and tesseract-ocr."
            ) from err
        self._runtime = pytesseract

    def read(self, image: Any, context: Optional[Mapping[str, Any]] = None) -> str:
        del context
        self._ensure_loaded()
        import numpy as np
        from PIL import Image

        if isinstance(image, Image.Image):
            payload = image.convert("RGB")
        elif isinstance(image, np.ndarray):
            payload = Image.fromarray(image).convert("RGB")
        else:
            payload = image
        kwargs: Dict[str, Any] = {}
        lang = self._normalize_lang(self.lang)
        if lang:
            kwargs["lang"] = lang
        return str(self._runtime.image_to_string(payload, **kwargs)).strip()


class PdfPlumberReader(OCR):
    """Lifts a region's text from a digital PDF's text layer; "" when there is none."""

    def read(self, image: Any, context: Optional[Mapping[str, Any]] = None) -> str:
        context = context or {}
        pdf_path = context.get("pdf_path")
        bbox = context.get("bbox")
        page_size = context.get("page_size")
        page_id = context.get("page_id")
        if not pdf_path or not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            return ""
        if not isinstance(page_size, (list, tuple)) or len(page_size) != 2:
            return ""
        try:
            page_id = int(page_id)
        except (TypeError, ValueError):
            return ""
        path = Path(str(pdf_path)).expanduser()
        if not path.exists() or page_id < 0:
            return ""
        import pdfplumber

        x1, y1, x2, y2 = (float(v) for v in bbox)
        src_w, src_h = (float(v) for v in page_size)
        try:
            with pdfplumber.open(str(path)) as pdf:
                if page_id >= len(pdf.pages):
                    return ""
                page = pdf.pages[page_id]
                sx = (page.width / src_w) if src_w > 0 else 1.0
                sy = (page.height / src_h) if src_h > 0 else 1.0
                bx0 = max(0.0, min(page.width, min(x1, x2) * sx))
                bx1 = max(0.0, min(page.width, max(x1, x2) * sx))
                by0 = max(0.0, min(page.height, min(y1, y2) * sy))
                by1 = max(0.0, min(page.height, max(y1, y2) * sy))
                if bx1 <= bx0 or by1 <= by0:
                    return ""
                return self._words(page.within_bbox((bx0, by0, bx1, by1)))
        except Exception:  # noqa: BLE001
            return ""

    @staticmethod
    def _words(cropped: Any) -> str:
        try:
            words = cropped.extract_words(
                keep_blank_chars=False, use_text_flow=True, x_tolerance=2, y_tolerance=2
            )
        except Exception:  # noqa: BLE001
            words = []
        if words:
            ordered = sorted(
                words,
                key=lambda w: (float(w.get("top", 0.0)), float(w.get("x0", 0.0))),
            )
            lines: List[List[str]] = []
            tops: List[float] = []
            for word in ordered:
                token = str(word.get("text", "")).strip()
                if not token:
                    continue
                top = float(word.get("top", 0.0))
                if not tops or abs(top - tops[-1]) > 3.0:
                    lines.append([token])
                    tops.append(top)
                else:
                    lines[-1].append(token)
            if lines:
                return "\n".join(" ".join(line).strip() for line in lines if line)
        text = cropped.extract_text()
        return str(text).strip() if text else ""


class PPOCR(OCR):
    def __init__(
        self,
        det_model: str = config.PPOCR_DET_MODEL_ID,
        rec_model: str = config.PPOCR_REC_MODEL_ID,
        device: str = config.PPOCR_DEVICE,
        det_limit_side_len: int = config.PPOCR_DET_LIMIT_SIDE_LEN,
        rec_batch_size: int = config.PPOCR_REC_BATCH_SIZE,
        drop_score: float = config.PPOCR_DROP_SCORE,
    ):
        self.det_model = det_model
        self.rec_model = rec_model
        self.device = device
        self.det_limit_side_len = int(det_limit_side_len)
        self.rec_batch_size = int(rec_batch_size)
        self.drop_score = float(drop_score)
        self._det: Any = None
        self._rec: Any = None
        self._det_config: Dict[str, Any] = {}
        self._characters: List[str] = []
        self._rec_height = 48
        self._rec_width = 320
        self._load_lock = threading.Lock()
        self._infer_lock = threading.Lock()

    @staticmethod
    def _model_files(model: str) -> Tuple[Path, Dict[str, Any]]:
        import yaml

        from core.embedding import resolve_model_path

        directory = Path(resolve_model_path(model))
        onnx_path = directory / "inference.onnx"
        yml_path = directory / "inference.yml"
        if not onnx_path.is_file() or not yml_path.is_file():
            raise FileNotFoundError(
                f"No prepared PP-OCR model at {str(directory)!r}; it needs inference.onnx "
                f"and inference.yml. Download PaddlePaddle/{directory.name} from Hugging Face "
                "into the model root before starting the engine."
            )
        with open(yml_path, encoding="utf-8") as handle:
            return onnx_path, yaml.safe_load(handle) or {}

    @staticmethod
    def _transform_op(model_config: Mapping[str, Any], name: str) -> Dict[str, Any]:
        for op in (model_config.get("PreProcess") or {}).get("transform_ops") or []:
            if isinstance(op, dict) and name in op:
                return op[name] or {}
        return {}

    def _ensure_loaded(self) -> None:
        if self._rec is not None:
            return
        with self._load_lock:
            if self._rec is not None:
                return
            import openvino as ov

            det_path, det_config = self._model_files(self.det_model)
            rec_path, rec_config = self._model_files(self.rec_model)
            normalize = self._transform_op(det_config, "NormalizeImage")
            scale = normalize.get("scale", 1.0 / 255.0)
            if isinstance(scale, str):
                numerator, denominator = scale.split("/")
                scale = float(numerator) / float(denominator)
            post = det_config.get("PostProcess") or {}
            self._det_config = {
                "mean": np.array(normalize.get("mean", [0.485, 0.456, 0.406]), dtype=np.float32),
                "std": np.array(normalize.get("std", [0.229, 0.224, 0.225]), dtype=np.float32),
                "scale": float(scale),
                "thresh": float(post.get("thresh", 0.3)),
                "box_thresh": float(post.get("box_thresh", 0.6)),
                "unclip_ratio": float(post.get("unclip_ratio", 1.5)),
                "max_candidates": int(post.get("max_candidates", 1000)),
            }
            shape = self._transform_op(rec_config, "RecResizeImg").get("image_shape", [3, 48, 320])
            self._rec_height, self._rec_width = int(shape[1]), int(shape[2])
            characters = (rec_config.get("PostProcess") or {}).get("character_dict") or []
            self._characters = ["blank"] + [str(character) for character in characters] + [" "]
            core = ov.Core()
            self._det = core.compile_model(str(det_path), self.device)
            self._rec = core.compile_model(str(rec_path), self.device)

    def read(self, image: Any, context: Optional[Mapping[str, Any]] = None) -> str:
        del context
        self._ensure_loaded()
        from core.layout import as_pil_image

        page = np.ascontiguousarray(np.asarray(as_pil_image(image))[:, :, ::-1])
        boxes = self._detect(page)
        if not boxes:
            return ""
        crops = [self._crop(page, box) for box in boxes]
        items = [
            (box, text.strip())
            for box, (text, score) in zip(boxes, self._recognize(crops))
            if text.strip() and score >= self.drop_score
        ]
        return self._join(items)

    def _detect(self, image: np.ndarray) -> List[np.ndarray]:
        import cv2

        height, width = image.shape[:2]
        ratio = 1.0
        if min(height, width) < self.det_limit_side_len:
            ratio = self.det_limit_side_len / float(min(height, width))
        if max(height, width) * ratio > config.PPOCR_DET_MAX_SIDE_LEN:
            ratio = config.PPOCR_DET_MAX_SIDE_LEN / float(max(height, width))
        resize_h = max(int(round(height * ratio / 32) * 32), 32)
        resize_w = max(int(round(width * ratio / 32) * 32), 32)
        resized = cv2.resize(image, (resize_w, resize_h)).astype(np.float32)
        det = self._det_config
        tensor = (resized * det["scale"] - det["mean"]) / det["std"]
        tensor = np.expand_dims(tensor.transpose(2, 0, 1), 0)
        with self._infer_lock:
            pred = np.asarray(self._det(tensor)[0])[0, 0]
        return self._boxes(pred, width, height)

    def _boxes(self, pred: np.ndarray, width: int, height: int) -> List[np.ndarray]:
        import cv2
        import pyclipper

        det = self._det_config
        bitmap = (pred > det["thresh"]).astype(np.uint8) * 255
        contours, _ = cv2.findContours(bitmap, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        map_h, map_w = pred.shape
        boxes = []
        for contour in contours[: det["max_candidates"]]:
            points, side = self._mini_box(contour)
            if side < 3 or self._box_score(pred, points) < det["box_thresh"]:
                continue
            length = cv2.arcLength(points, True)
            if length <= 0:
                continue
            offset = pyclipper.PyclipperOffset()
            offset.AddPath(points.tolist(), pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
            expanded = offset.Execute(cv2.contourArea(points) * det["unclip_ratio"] / length)
            if len(expanded) != 1:
                continue
            box, side = self._mini_box(np.array(expanded[0], dtype=np.float32).reshape(-1, 1, 2))
            if side < 5:
                continue
            box[:, 0] = np.clip(np.round(box[:, 0] / map_w * width), 0, width - 1)
            box[:, 1] = np.clip(np.round(box[:, 1] / map_h * height), 0, height - 1)
            if np.linalg.norm(box[0] - box[1]) <= 3 or np.linalg.norm(box[0] - box[3]) <= 3:
                continue
            boxes.append(box)
        return boxes

    @staticmethod
    def _mini_box(contour: np.ndarray) -> Tuple[np.ndarray, float]:
        import cv2

        rect = cv2.minAreaRect(contour)
        points = sorted(cv2.boxPoints(rect).tolist(), key=lambda point: point[0])
        left = sorted(points[:2], key=lambda point: point[1])
        right = sorted(points[2:], key=lambda point: point[1])
        box = np.array([left[0], right[0], right[1], left[1]], dtype=np.float32)
        return box, float(min(rect[1]))

    @staticmethod
    def _box_score(pred: np.ndarray, box: np.ndarray) -> float:
        import cv2

        height, width = pred.shape
        xmin = int(np.clip(np.floor(box[:, 0].min()), 0, width - 1))
        xmax = int(np.clip(np.ceil(box[:, 0].max()), 0, width - 1))
        ymin = int(np.clip(np.floor(box[:, 1].min()), 0, height - 1))
        ymax = int(np.clip(np.ceil(box[:, 1].max()), 0, height - 1))
        mask = np.zeros((ymax - ymin + 1, xmax - xmin + 1), dtype=np.uint8)
        cv2.fillPoly(mask, [(box - [xmin, ymin]).astype(np.int32)], 1)
        return float(cv2.mean(pred[ymin:ymax + 1, xmin:xmax + 1], mask)[0])

    @staticmethod
    def _crop(image: np.ndarray, box: np.ndarray) -> np.ndarray:
        import cv2

        crop_w = int(max(np.linalg.norm(box[0] - box[1]), np.linalg.norm(box[2] - box[3])))
        crop_h = int(max(np.linalg.norm(box[0] - box[3]), np.linalg.norm(box[1] - box[2])))
        target = np.float32([[0, 0], [crop_w, 0], [crop_w, crop_h], [0, crop_h]])
        crop = cv2.warpPerspective(
            image,
            cv2.getPerspectiveTransform(box.astype(np.float32), target),
            (crop_w, crop_h),
            borderMode=cv2.BORDER_REPLICATE,
            flags=cv2.INTER_CUBIC,
        )
        if crop.shape[0] >= 1.5 * crop.shape[1]:
            crop = np.ascontiguousarray(np.rot90(crop))
        return crop

    def _recognize(self, crops: Sequence[np.ndarray]) -> List[Tuple[str, float]]:
        import cv2

        results: List[Tuple[str, float]] = [("", 0.0)] * len(crops)
        order = np.argsort([crop.shape[1] / float(crop.shape[0]) for crop in crops])
        for start in range(0, len(crops), self.rec_batch_size):
            indices = order[start:start + self.rec_batch_size]
            batch = [crops[index] for index in indices]
            ratio = max(
                [self._rec_width / self._rec_height]
                + [crop.shape[1] / float(crop.shape[0]) for crop in batch]
            )
            batch_w = int(self._rec_height * ratio)
            tensor = np.zeros((len(batch), 3, self._rec_height, batch_w), dtype=np.float32)
            for row, crop in enumerate(batch):
                resized_w = min(
                    batch_w,
                    max(1, int(math.ceil(self._rec_height * crop.shape[1] / float(crop.shape[0])))),
                )
                resized = cv2.resize(crop, (resized_w, self._rec_height)).astype(np.float32)
                tensor[row, :, :, :resized_w] = (resized.transpose(2, 0, 1) / 255.0 - 0.5) / 0.5
            with self._infer_lock:
                probs = np.asarray(self._rec(tensor)[0])
            for index, decoded in zip(indices, self._decode(probs)):
                results[index] = decoded
        return results

    def _decode(self, probs: np.ndarray) -> List[Tuple[str, float]]:
        decoded = []
        for indices, scores in zip(probs.argmax(axis=2), probs.max(axis=2)):
            keep = np.ones(len(indices), dtype=bool)
            keep[1:] = indices[1:] != indices[:-1]
            keep &= indices != 0
            text = "".join(self._characters[int(index)] for index in indices[keep])
            decoded.append((text, float(np.mean(scores[keep])) if keep.any() else 0.0))
        return decoded

    @staticmethod
    def _join(items: Sequence[Tuple[np.ndarray, str]]) -> str:
        rows: List[Tuple[float, List[Tuple[float, str]]]] = []
        for box, text in sorted(items, key=lambda item: (item[0][:, 1].min(), item[0][:, 0].min())):
            top, bottom = float(box[:, 1].min()), float(box[:, 1].max())
            center = (top + bottom) / 2
            if rows and abs(center - rows[-1][0]) <= (bottom - top) / 2:
                rows[-1][1].append((float(box[:, 0].min()), text))
            else:
                rows.append((center, [(float(box[:, 0].min()), text)]))
        return "\n".join(" ".join(text for _, text in sorted(row)) for _, row in rows)


class HybridOCR(OCR):
    """Read text regions from the PDF and visual regions from their pixels."""

    def __init__(self, lang: str = config.OCR_LANG):
        self._pdfplumber = PdfPlumberReader()
        self._tesseract = TesseractOCR(lang=lang)

    def read(self, image: Any, context: Optional[Mapping[str, Any]] = None) -> str:
        context = context or {}
        if context.get("visual"):
            text = self._tesseract.read(image, context)
            if text.strip():
                return text
            return self._pdfplumber.read(image, context)
        text = self._pdfplumber.read(image, context)
        if text.strip():
            return text
        return self._tesseract.read(image, context)


# --- factory ------------------------------------------------------------------

_CACHE: Dict[Tuple, OCR] = {}
_CACHE_LOCK = threading.Lock()


def build_ocr(
    backend: Optional[str] = None,
    lang: Optional[str] = None,
) -> OCR:
    """An OCR engine, built at most once per configuration."""
    backend = (backend or config.OCR_BACKEND).lower()
    if backend not in config.OCR_BACKENDS:
        raise ValueError(
            f"OCR backend {backend!r} is not supported; "
            f"supported: {', '.join(config.OCR_BACKENDS)}"
        )
    lang = lang or config.OCR_LANG

    key = (backend, lang)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached is None:
            cached = _build(backend, lang)
            _CACHE[key] = cached
    return cached


def _build(backend: str, lang: str) -> OCR:
    if backend == "pdfplumber":
        return PdfPlumberReader()
    if backend == "tesseract":
        return TesseractOCR(lang=lang)
    if backend == "hybrid":
        return HybridOCR(lang=lang)
    if backend == "ppocr":
        return PPOCR()
    raise NotImplementedError(f"OCR backend {backend!r} is not implemented yet")


__all__ = [
    "OCR",
    "CallableOCR",
    "HybridOCR",
    "PPOCR",
    "PdfPlumberReader",
    "TesseractOCR",
    "as_ocr",
    "build_ocr",
]
