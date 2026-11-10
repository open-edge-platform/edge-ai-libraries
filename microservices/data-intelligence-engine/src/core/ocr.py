# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

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
    raise NotImplementedError(f"OCR backend {backend!r} is not implemented yet")


__all__ = [
    "OCR",
    "CallableOCR",
    "HybridOCR",
    "PdfPlumberReader",
    "TesseractOCR",
    "as_ocr",
    "build_ocr",
]
