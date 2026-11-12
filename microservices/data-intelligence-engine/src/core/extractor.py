# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import mimetypes
import os
import subprocess
from typing import Any, Callable, List, Mapping, Optional, Sequence

import config
from core.content import (
    AUDIO,
    BINARY_KINDS,
    IMAGE,
    TEXT,
    ROLE_AUDIO,
    ROLE_DOC_IMAGE,
    ROLE_IMAGE,
    ROLE_LONG_VIDEO,
    ROLE_SHORT_VIDEO,
    VIDEO,
    ContentBlock,
    ContentStream,
    asset_family,
    file_uri,
)
from core.loader import SUPPORTED_EXTS, file_to_documents

#: Writes bytes (with an optional content type) and returns the key to read them back.
BlobWriter = Callable[[bytes, Optional[str]], str]

def media_kind(path: str) -> str:
    """The binary block kind for a file that is itself media, else `""`."""
    family = asset_family(os.path.splitext(path)[1])
    return family if family in BINARY_KINDS else ""


def is_supported(path: str) -> bool:
    """Whether `extract` can turn this file into content."""
    return bool(media_kind(path)) or os.path.splitext(path)[1].lower() in SUPPORTED_EXTS


def media_role(path: str, kind: str = "") -> str:
    """The processing role of the media file at `path`, else `""`; unknown video duration means long."""
    kind = kind or media_kind(path)
    if kind == IMAGE:
        return ROLE_IMAGE
    if kind == AUDIO:
        return ROLE_AUDIO
    if kind != VIDEO:
        return ""
    duration = video_duration(path)
    if duration is not None and 0 < duration <= config.SHORT_VIDEO_MAX_SECONDS:
        return ROLE_SHORT_VIDEO
    return ROLE_LONG_VIDEO


def video_duration(path: str) -> Optional[float]:
    """Seconds of video at `path` via ffprobe then OpenCV, or None."""
    duration = _ffprobe_duration(path)
    if duration is not None:
        return duration
    return _opencv_duration(path)


def _ffprobe_duration(path: str) -> Optional[float]:
    try:
        completed = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json", path,
            ],
            capture_output=True,
            timeout=30,
            check=True,
        )
        value = json.loads(completed.stdout)["format"]["duration"]
        return float(value)
    except Exception:  # noqa: BLE001
        return None


def _opencv_duration(path: str) -> Optional[float]:
    try:
        import cv2  # noqa: PLC0415
    except ImportError:
        return None
    capture = cv2.VideoCapture(path)
    try:
        if not capture.isOpened():
            return None
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0)
        frames = float(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    finally:
        capture.release()
    if fps <= 0 or frames <= 0:
        return None
    return frames / fps


def extract(
    path: str,
    asset_id: str,
    put_blob: Optional[BlobWriter] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> ContentStream:
    """The content of the file at `path`, normalized; without `put_blob` only text is extracted."""
    if media_kind(path):
        return extract_media(path, asset_id, put_blob, metadata)
    if put_blob is not None and path.lower().endswith(".pdf") and _pdf_libs():
        try:
            return extract_pdf(path, asset_id, put_blob, metadata)
        except Exception:  # noqa: BLE001
            # Layout failure falls back to plain text: lose the figures, not the document.
            pass
    if put_blob is not None:
        from core import structured

        if structured.structured_kind(path) and structured.has_media(path):
            try:
                return structured.extract_structured(path, asset_id, put_blob, metadata)
            except Exception:  # noqa: BLE001
                pass
    return extract_text(path, asset_id, metadata)


# --- text ---------------------------------------------------------------------


def extract_text(
    path: str, asset_id: str, metadata: Optional[Mapping[str, Any]] = None
) -> ContentStream:
    """One block per piece the reader returns, in the order it returned them."""
    return ContentStream.from_documents(file_to_documents(path), asset_id, metadata)


# --- media --------------------------------------------------------------------


def extract_media(
    path: str,
    asset_id: str,
    put_blob: Optional[BlobWriter] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> ContentStream:
    """A media file as one binary block pointing at the file itself; `put_blob` is unused."""
    content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    name = os.path.basename(path)
    kind = media_kind(path)
    block_metadata: dict = {
        "content_type": content_type,
        "byte_size": os.path.getsize(path),
        "role": media_role(path, kind),
    }
    if kind == VIDEO:
        duration = video_duration(path)
        if duration is not None:
            block_metadata["duration_s"] = round(duration, 3)
    block = ContentBlock(
        block_id=f"{asset_id}:0",
        kind=kind,
        media_key=file_uri(path),
        caption=_name_as_caption(name),
        reading_order=0,
        metadata=block_metadata,
    )
    stream_metadata = {
        "file_name": name,
        "file_path": os.path.abspath(path),
        "content_type": content_type,
    }
    return ContentStream(
        asset_id=asset_id,
        blocks=[block],
        metadata={
            **stream_metadata,
            **dict(metadata or {}),
            "asset_id": asset_id,
        },
    )


def _name_as_caption(name: str) -> str:
    """`q3-teardown_thermal.mp4` -> `q3 teardown thermal`."""
    stem = os.path.splitext(name)[0]
    return " ".join(part for part in stem.replace("_", " ").replace("-", " ").split())


# --- layout -------------------------------------------------------------------


def render_pdf(path: str, dpi: int = 150) -> List[Any]:
    """Each PDF page as an upright RGB PIL image at `dpi` (honours `/Rotate`)."""
    pdfium = _pypdfium2()
    if pdfium is None:
        raise RuntimeError("pypdfium2 is not installed")

    zoom = dpi / 72.0
    document = pdfium.PdfDocument(path)
    pages: List[Any] = []
    try:
        for page in document:
            image = page.render(scale=zoom).to_pil().convert("RGB")
            pages.append(image)
    finally:
        document.close()
    return pages


def _clamp_crop(bbox, size):
    """`bbox` clamped to the image, or None if it has no area to crop."""
    width, height = size
    x1, y1, x2, y2 = (int(round(value)) for value in bbox[:4])
    x1, x2 = sorted((x1, x2))
    y1, y2 = sorted((y1, y2))
    x1 = max(0, min(width, x1))
    x2 = max(0, min(width, x2))
    y1 = max(0, min(height, y1))
    y2 = max(0, min(height, y2))
    if x2 <= x1 or y2 <= y1:
        return None
    return (x1, y1, x2, y2)


def _caption_fallback_box(rect, size, ratio: float):
    """`rect` extended downward by `ratio` of its height to catch a caption, clamped, or None."""
    if ratio <= 0.0:
        return None
    _, height = size
    x1, y1, x2, y2 = (float(value) for value in rect[:4])
    box_height = y2 - y1
    if box_height <= 0.0:
        return None
    extended_y2 = min(float(height), y2 + box_height * ratio)
    if extended_y2 <= y2:
        return None
    return _clamp_crop((x1, y1, x2, extended_y2), size)


def extract_layout(
    path: str,
    asset_id: str,
    put_blob: BlobWriter,
    metadata: Optional[Mapping[str, Any]] = None,
    *,
    detector: Any = None,
    ocr: Any = None,
    render: Optional[Callable[[str, int], List[Any]]] = None,
    dpi: Optional[int] = None,
    caption_fallback_extend_ratio: Optional[float] = None,
) -> ContentStream:
    """A scanned PDF's text and figures via a layout model + OCR + figure pairing."""
    import config
    from core.fused import extract_caption_keys, reference_text_for
    from core.layout import VISUAL_TYPES, build_layout_detector
    from core.ocr import as_ocr, build_ocr

    render = render or render_pdf
    detector = detector or build_layout_detector()
    ocr = as_ocr(ocr) if ocr is not None else build_ocr()
    dpi = int(dpi if dpi is not None else config.LAYOUT_RENDER_DPI)
    fallback_ratio = float(
        caption_fallback_extend_ratio
        if caption_fallback_extend_ratio is not None
        else config.LAYOUT_CAPTION_FALLBACK_EXTEND_RATIO
    )

    pages = render(path, dpi)
    page_layouts = detector.detect(pages)
    records: List[dict] = []
    text_items: List[dict] = []
    image_items: List[dict] = []
    for page_index, (page_image, blocks) in enumerate(zip(pages, page_layouts)):
        ordered = sorted(blocks, key=lambda block: (block.bbox[1], block.bbox[0]))
        for block in ordered:
            rect = _clamp_crop(block.bbox, page_image.size)
            if rect is None:
                continue
            crop = page_image.crop(rect).convert("RGB")
            # `bbox`/`page_size` are rendered-page pixels; `page_id` is 0-based.
            context = {
                "pdf_path": path,
                "bbox": rect,
                "page_size": list(page_image.size),
                "page_id": page_index,
                "layout_type": block.label,
                "visual": block.label in VISUAL_TYPES,
            }
            record = {
                "label": block.label,
                "page": page_index + 1,
                "bbox": tuple(float(v) for v in rect),
                "text": ocr.read(crop, context),
                "visual": context["visual"],
            }
            if record["visual"]:
                if not extract_caption_keys(record["text"]):
                    extended = _caption_fallback_box(rect, page_image.size, fallback_ratio)
                    if extended is not None and extended != rect:
                        retry = ocr.read(
                            page_image.crop(extended).convert("RGB"),
                            {**context, "bbox": extended},
                        )
                        if extract_caption_keys(retry):
                            record["text"] = retry
                record["crop_bytes"] = _encode_jpeg(crop)
                image_items.append(record)
            else:
                text_items.append(record)
            records.append(record)

    texts_by_page: dict = {}
    for item in text_items:
        texts_by_page.setdefault(item["page"], []).append(item)
    for item in image_items:
        item["reference_text"] = reference_text_for(
            item, texts_by_page.get(item["page"], []), text_items
        )

    # One merged TEXT block per page (no bbox), followed by that page's IMAGE blocks.
    blocks_out: List[ContentBlock] = []
    for page in sorted({record["page"] for record in records}):
        page_records = [record for record in records if record["page"] == page]
        merged_text = "\n\n".join(
            record["text"]
            for record in page_records
            if not record["visual"] and record["text"].strip()
        )
        if merged_text:
            blocks_out.append(
                ContentBlock(
                    block_id=f"{asset_id}:{len(blocks_out)}",
                    kind=TEXT,
                    text=merged_text,
                    page=page,
                    reading_order=len(blocks_out),
                    metadata={"type": "page"},
                )
            )
        for record in page_records:
            if not record["visual"]:
                continue
            crop_bytes = record["crop_bytes"]
            blocks_out.append(
                ContentBlock(
                    block_id=f"{asset_id}:{len(blocks_out)}",
                    kind=IMAGE,
                    media_key=put_blob(crop_bytes, "image/jpeg"),
                    caption=record.get("reference_text", ""),
                    page=record["page"],
                    bbox=record["bbox"],
                    reading_order=len(blocks_out),
                    metadata={
                        "type": record["label"],
                        "content_type": "image/jpeg",
                        "byte_size": len(crop_bytes),
                        "role": ROLE_DOC_IMAGE,
                    },
                )
            )
    return ContentStream(
        asset_id=asset_id,
        blocks=blocks_out,
        metadata={
            "file_name": os.path.basename(path),
            "file_path": os.path.abspath(path),
            **dict(metadata or {}),
            "asset_id": asset_id,
        },
    )


# --- layout: a digital PDF via its text layer ---------------------------------


class _PdfTextLayer:
    """A digital PDF's text layer reported in rendered-pixel space (`pixel = point * dpi / 72`)."""

    def __init__(self, path: str, dpi: int):
        pdfplumber = _pdfplumber()
        if pdfplumber is None:
            raise RuntimeError("pdfplumber is not installed")
        self._pdf = pdfplumber.open(path)
        self._zoom = dpi / 72.0
        self._candidate_cache: dict = {}

    def page_count(self) -> int:
        return len(self._pdf.pages)

    def page_text(self, index: int) -> str:
        return self._pdf.pages[index].extract_text() or ""

    def candidates(self, index: int) -> List[dict]:
        """This page's text lines as pairing candidates `{bbox, page, text}`, bbox in pixels."""
        if index in self._candidate_cache:
            return self._candidate_cache[index]
        page = self._pdf.pages[index]
        zoom = self._zoom
        out: List[dict] = []
        for line in page.extract_text_lines():
            text = str(line.get("text") or "").strip()
            if not text:
                continue
            out.append(
                {
                    "bbox": (
                        line["x0"] * zoom,
                        line["top"] * zoom,
                        line["x1"] * zoom,
                        line["bottom"] * zoom,
                    ),
                    "page": index + 1,
                    "text": text,
                }
            )
        self._candidate_cache[index] = out
        return out

    def region_text(self, index: int, pixel_bbox: Sequence[float]) -> str:
        """The text-layer text under a region given in rendered pixels."""
        page = self._pdf.pages[index]
        zoom = self._zoom
        x0, top, x1, bottom = (value / zoom for value in pixel_bbox[:4])
        x0, x1 = sorted((x0, x1))
        top, bottom = sorted((top, bottom))
        x0 = max(0.0, min(float(page.width), x0))
        x1 = max(0.0, min(float(page.width), x1))
        top = max(0.0, min(float(page.height), top))
        bottom = max(0.0, min(float(page.height), bottom))
        if x1 <= x0 or bottom <= top:
            return ""
        return page.crop((x0, top, x1, bottom)).extract_text() or ""

    def close(self) -> None:
        try:
            self._pdf.close()
        except Exception:  # noqa: BLE001
            pass


def pdf_has_text_layer(text_layer: Any) -> bool:
    """Whether any page yields extractable text."""
    for index in range(text_layer.page_count()):
        if text_layer.page_text(index).strip():
            return True
    return False


def extract_pdf(
    path: str,
    asset_id: str,
    put_blob: BlobWriter,
    metadata: Optional[Mapping[str, Any]] = None,
    *,
    detector: Any = None,
    ocr: Any = None,
    render: Optional[Callable[[str, int], List[Any]]] = None,
    dpi: Optional[int] = None,
    text_layer: Any = None,
    read_text: Optional[Callable[[str], "dict[int, str]"]] = None,
    caption_fallback_extend_ratio: Optional[float] = None,
) -> ContentStream:
    """A PDF: digital ones via `extract_layout_digital`, scanned ones via `extract_layout`."""
    import config

    dpi = int(dpi if dpi is not None else config.LAYOUT_RENDER_DPI)
    layer = text_layer or _PdfTextLayer(path, dpi)
    try:
        digital = pdf_has_text_layer(layer)
    except Exception:  # noqa: BLE001
        layer.close()
        return extract_layout(
            path, asset_id, put_blob, metadata,
            detector=detector, ocr=ocr, render=render, dpi=dpi,
            caption_fallback_extend_ratio=caption_fallback_extend_ratio,
        )
    if not digital:
        layer.close()
        return extract_layout(
            path, asset_id, put_blob, metadata,
            detector=detector, ocr=ocr, render=render, dpi=dpi,
            caption_fallback_extend_ratio=caption_fallback_extend_ratio,
        )
    try:
        return extract_layout_digital(
            path, asset_id, put_blob, metadata,
            text_layer=layer, detector=detector, render=render,
            dpi=dpi, read_text=read_text,
            caption_fallback_extend_ratio=caption_fallback_extend_ratio,
        )
    finally:
        layer.close()


#: Reading-order lanes within a page: page text, then visual blocks; lane 1 is reserved.
_LANE_TEXT, _LANE_VISUAL = 0, 2


def _reading_key(page: int, lane: int, index: int) -> int:
    """A document-wide reading-order key computed from the block alone."""
    return page * 1_000_000 + lane * 100_000 + index


def digital_text_blocks(
    path: str,
    asset_id: str,
    *,
    text_layer: Any,
    read_text: Optional[Callable[[str], "dict[int, str]"]] = None,
) -> List[ContentBlock]:
    """One TEXT block per page of a digital PDF, taken from the plain-text reader."""
    read_text = read_text or _pdf_page_texts
    page_count = text_layer.page_count()
    page_texts = read_text(path)
    blocks: List[ContentBlock] = []
    for index in range(page_count):
        text = (page_texts.get(index) or "").strip()
        if text:
            order = _reading_key(index + 1, _LANE_TEXT, 0)
            blocks.append(
                ContentBlock(
                    block_id=f"{asset_id}:{order}", kind=TEXT, text=text,
                    page=index + 1, reading_order=order, metadata={"type": "text"},
                )
            )
    return blocks


def digital_visual_blocks(
    path: str,
    asset_id: str,
    put_blob: BlobWriter,
    *,
    text_layer: Any,
    detector: Any = None,
    render: Optional[Callable[[str, int], List[Any]]] = None,
    dpi: Optional[int] = None,
    caption_fallback_extend_ratio: Optional[float] = None,
) -> List[ContentBlock]:
    """A digital PDF's detected figures as IMAGE blocks captioned from the text layer."""
    import config
    from core.fused import extract_caption_keys
    from core.layout import build_layout_detector
    from core.visual import Figure, caption_for

    dpi = int(dpi if dpi is not None else config.LAYOUT_RENDER_DPI)
    render = render or render_pdf
    detector = detector or build_layout_detector()
    fallback_ratio = float(
        caption_fallback_extend_ratio
        if caption_fallback_extend_ratio is not None
        else config.LAYOUT_CAPTION_FALLBACK_EXTEND_RATIO
    )
    page_count = text_layer.page_count()

    pages = render(path, dpi)
    all_candidates: List[dict] = []
    for index in range(min(page_count, len(pages))):
        all_candidates.extend(text_layer.candidates(index))
    per_page_seq: dict = {}
    blocks: List[ContentBlock] = []

    def _next_order(page_index: int) -> int:
        seq = per_page_seq.get(page_index, 0)
        per_page_seq[page_index] = seq + 1
        return _reading_key(page_index + 1, _LANE_VISUAL, seq)

    for page_index, (page_image, detected) in enumerate(zip(pages, detector.detect(pages))):
        if page_index >= page_count:
            break
        for block in sorted(detected, key=lambda b: (b.bbox[1], b.bbox[0])):
            rect = _clamp_crop(block.bbox, page_image.size)
            if rect is None:
                continue
            label = block.label
            if label != IMAGE:
                continue
            crop = page_image.crop(rect).convert("RGB")
            region_text = text_layer.region_text(page_index, rect)
            if not extract_caption_keys(region_text):
                extended = _caption_fallback_box(rect, page_image.size, fallback_ratio)
                if extended is not None and extended != rect:
                    retry = text_layer.region_text(page_index, extended)
                    if extract_caption_keys(retry):
                        region_text = retry
            caption = caption_for(
                Figure(region_text=region_text, page=page_index + 1,
                       bbox=tuple(float(v) for v in rect), label=label),
                text_layer.candidates(page_index),
                all_candidates,
            )
            crop_bytes = _encode_jpeg(crop)
            order = _next_order(page_index)
            blocks.append(
                ContentBlock(
                    block_id=f"{asset_id}:{order}", kind=IMAGE,
                    media_key=put_blob(crop_bytes, "image/jpeg"),
                    caption=caption, page=page_index + 1,
                    bbox=tuple(float(v) for v in rect), reading_order=order,
                    metadata={"type": label, "content_type": "image/jpeg",
                              "byte_size": len(crop_bytes), "role": ROLE_DOC_IMAGE},
                )
            )
    return blocks


def assemble_stream(
    asset_id: str,
    path: str,
    metadata: Optional[Mapping[str, Any]],
    blocks: Sequence[ContentBlock],
) -> ContentStream:
    """Merge text and visual blocks into one stream ordered by reading key."""
    ordered = sorted(blocks, key=lambda block: block.reading_order)
    return ContentStream(
        asset_id=asset_id,
        blocks=ordered,
        metadata={
            "file_name": os.path.basename(path),
            "file_path": os.path.abspath(path),
            **dict(metadata or {}),
            "asset_id": asset_id,
        },
    )


def extract_layout_digital(
    path: str,
    asset_id: str,
    put_blob: BlobWriter,
    metadata: Optional[Mapping[str, Any]] = None,
    *,
    text_layer: Any,
    detector: Any = None,
    render: Optional[Callable[[str, int], List[Any]]] = None,
    dpi: Optional[int] = None,
    read_text: Optional[Callable[[str], "dict[int, str]"]] = None,
    caption_fallback_extend_ratio: Optional[float] = None,
) -> ContentStream:
    """A digital PDF's text and figures without OCR; a figure failure keeps the text."""
    text_blocks = digital_text_blocks(
        path, asset_id, text_layer=text_layer, read_text=read_text,
    )
    visual_blocks: List[ContentBlock] = []
    try:
        visual_blocks = digital_visual_blocks(
            path, asset_id, put_blob, text_layer=text_layer,
            detector=detector, render=render, dpi=dpi,
            caption_fallback_extend_ratio=caption_fallback_extend_ratio,
        )
    except Exception:  # noqa: BLE001
        pass
    return assemble_stream(asset_id, path, metadata, text_blocks + visual_blocks)


def _pdf_page_texts(path: str) -> "dict[int, str]":
    """Each page's text keyed by 0-based page index (reader `page_label` is 1-based)."""
    from core.content import _content_of
    from core.loader import file_to_documents

    out: "dict[int, str]" = {}
    for doc in file_to_documents(path):
        try:
            index = int(doc.metadata.get("page_label")) - 1
        except (TypeError, ValueError):
            continue
        text = _content_of(doc)
        if not text.strip():
            continue
        out[index] = f"{out[index]}\n{text}" if index in out else text
    return out


def _encode_jpeg(image) -> bytes:
    from io import BytesIO

    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=95)
    return buffer.getvalue()


def _pdfplumber():
    try:
        import pdfplumber  # noqa: PLC0415
    except ImportError:
        return None
    return pdfplumber


def _pypdfium2():
    try:
        import pypdfium2  # noqa: PLC0415
    except ImportError:
        return None
    return pypdfium2


def _pdf_libs() -> bool:
    return _pdfplumber() is not None and _pypdfium2() is not None


__all__ = [
    "BlobWriter",
    "assemble_stream",
    "digital_text_blocks",
    "digital_visual_blocks",
    "extract",
    "extract_layout",
    "extract_layout_digital",
    "extract_media",
    "extract_pdf",
    "extract_text",
    "is_supported",
    "media_kind",
    "pdf_has_text_layer",
    "render_pdf",
    "media_role",
    "video_duration",
]
