# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Files in, one normalized `ContentStream` out.

This is the seam between "what a file happens to be" and "what the engine
stores". An asset is a file of any kind, so a caller ingests a path and gets
back blocks in reading order without having to know whether the path was a
spreadsheet, a scanned report, or a recording. Everything downstream -- chunking,
figures, knowledge extraction -- reads blocks and never touches the file again.

Three extractors, chosen by MIME type:

- **text** (the default) runs the llama-index reader and turns each piece it
  returns into a text block, keeping its page number.
- **layout** runs over a PDF (`extract_pdf`): a PDF is routed by whether it
    carries a text layer. A digital PDF
    takes its prose, tables, and equations from the fast text path and only renders
    + detects to find figures, which become fused `IMAGE` blocks. Its slow path
    performs no OCR (`extract_layout_digital`, paths 1 and 2). A scanned PDF
  with no text layer falls back to detecting every region and OCRing each one
  (`extract_layout`, path 3). Either way tables and vector charts become blocks
  with captions, not just embedded bitmaps.
- **media** handles a file that *is* the picture or the recording: one binary
  block, no text.

Bytes never go into the stream. A standalone media file is not copied at all --
its block points at the file itself (`file://`). A figure's pixels, which have no
file of their own, are written to the object
store first and the block keeps the returned key, so the record a caller
persists afterwards can never reference a blob that is not there yet. That
ordering is why `put_blob` is a parameter rather than something this module
reaches for: the writer belongs to the library whose content source the blobs
are going into.

Adding a real layout model (docling, unstructured) means writing one more
function of the same shape and registering it -- nothing above this file
changes, and nothing already persisted is re-interpreted.
"""

import json
import mimetypes
import os
import subprocess
from typing import Any, Callable, List, Mapping, Optional, Sequence

import config
from core.content import (
    AUDIO,
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
    file_uri,
)
from core.loader import SUPPORTED_EXTS, file_to_documents

#: Writes bytes somewhere and returns the key they can be read back by.
BlobWriter = Callable[[bytes, Optional[str]], str]

_MEDIA_KINDS = {"image": IMAGE, "audio": AUDIO, "video": VIDEO}

def media_kind(path: str) -> str:
    """The binary block kind for a file that is itself media, else `""`."""
    media_type = mimetypes.guess_type(path)[0] or ""
    return _MEDIA_KINDS.get(media_type.split("/")[0], "")


def is_supported(path: str) -> bool:
    """Whether `extract` can turn this file into content: a media file, or a
    document type the reader accepts. Asked before an ingest is accepted, so an
    unsupported file is a bad request rather than an asset that never appears."""
    return bool(media_kind(path)) or os.path.splitext(path)[1].lower() in SUPPORTED_EXTS


def media_role(path: str, kind: str = "") -> str:
    """The role of the media file at `path` -- how it is processed -- else `""`.

    A video is short or long by its duration, because that is what decides
    whether the whole of it can go to a vision model in one piece. Duration
    that cannot be read means **long**: guessing short would hand an unbounded
    recording to a VLM, and the cost of being wrong is wildly asymmetric.
    """
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
    """Seconds of video at `path`, or None if neither prober could say.

    ffprobe reads the container metadata and is both faster and more honest
    about variable frame rates; OpenCV has to be decoded against and reports
    frame-count/fps, which some containers lie about. Hence the order.
    """
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
    except Exception:  # noqa: BLE001 - absent, old, or confused by the file
        return None


def _opencv_duration(path: str) -> Optional[float]:
    try:
        import cv2  # noqa: PLC0415 - optional, and probed rather than required
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
    """The content of the file at `path`, normalized.

    `put_blob` is required only for files that carry bytes; without it a figure
    has nowhere to go, so layout extraction is skipped and the text is taken on
    its own rather than silently dropping the pictures.
    """
    if media_kind(path):
        return extract_media(path, asset_id, put_blob, metadata)
    if put_blob is not None and path.lower().endswith(".pdf") and _pdf_libs():
        try:
            return extract_pdf(path, asset_id, put_blob, metadata)
        except Exception:  # noqa: BLE001 - a readable file must still ingest
            # Layout extraction is an improvement on reading the text, not a
            # precondition for it. Falling through loses the figures, which is
            # a far better outcome than losing the document.
            pass
    if put_blob is not None:
        from core import structured

        # A docx/pptx/xlsx/html file that carries pictures is walked natively so
        # each figure lands between the paragraphs about it; one with no pictures
        # takes the plain-text reader below, unchanged. Same contract as the PDF
        # branch: a parse failure loses the figures, never the document.
        if structured.structured_kind(path) and structured.has_media(path):
            try:
                return structured.extract_structured(path, asset_id, put_blob, metadata)
            except Exception:  # noqa: BLE001 - a readable file must still ingest
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
    """A media file as a stream of exactly one binary block.

    There is no `MediaAsset` and no modality flag on the asset: a recording is a
    file, like a report is a file, and the difference is one block's `kind`. A
    projection that can embed it does; one that cannot skips it, and the pool
    holds both either way. Which projections can is not recorded here: the block
    states only what the file *is* (its `role`), so adding a model later needs
    no re-ingest.

    The file name goes in as the caption because it is often the only words
    attached to the thing -- `q3-teardown-thermal-camera.mp4` is a genuinely
    useful thing for a text query to match, and without it a media file with no
    caption is unsearchable. It is kept, not replaced, when a real caption
    arrives, because a model's description can fail and this cannot.

    The block's `media_key` is the file's own `file://` URI, and nothing is
    copied: the file *is* the asset, and the decoders downstream want a path, so
    a second copy in the content store would be read back and written out to a
    temporary file just to be opened. `put_blob` is accepted so callers need not
    care which kind of file they hold, and is unused here.
    """
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


# --- layout: a PDF via a layout model + OCR + figure pairing ------------------


def render_pdf(path: str, dpi: int = 150) -> List[Any]:
    """Each PDF page as an RGB PIL image at `dpi`.

    The layout detector runs on these rendered pages, so a detected box is
    already in image pixels and a crop is `page.crop(bbox)` with no coordinate
    conversion. Injectable in `extract_layout` so the chain can run without
    pypdfium2.

    pypdfium2 (Apache-2.0 / BSD-3, wrapping Google PDFium) renders upright,
    honouring `/Rotate`, so the image's pixel frame matches the text-layer
    coordinates `_PdfTextLayer` reports -- both describe the same upright page.
    """
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
    """`rect` extended downward by `ratio` of its height, clamped, or None.

    A figure's caption usually sits just below its detected box, so when the crop's
    own text yields no caption key, re-reading a taller box can pull the caption
    (and its `Figure N` key) in for pairing. Returns None when disabled, degenerate,
    or already at the page's lower edge -- the caller then keeps the original text.
    Only the text-reading box grows; the stored crop stays the detected region.
    Ported from mmdir `related_text_extract._extend_bbox_downward`.
    """
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
    """A PDF's text and figures via a layout model + OCR + figure pairing.

    This multimodal layout path renders each page, detects its regions, OCRs every
    region, pairs each
    figure with the prose that references it, and emit one `ContentStream`. A
    textual region becomes a `TEXT` block; a visual one (image/table/figure)
    becomes an `IMAGE` block whose crop goes to the object store and whose
    caption is the reference text -- exactly the two block shapes the indexer
    already handles.

    `detector`, `ocr` and `render` are injectable seams: each defaults to the
    configured backend but can be supplied, which is how the chain runs without
    the real models or pypdfium2.
    """
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
    # One record per detected region, in document reading order (page-major, then
    # top-to-bottom / left-to-right within a page). Figures also carry their crop.
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
            # Where this crop came from, so a text-layer OCR can read the PDF
            # directly. `bbox` and `page_size` are both in rendered-page pixels,
            # and `page_id` is 0-based -- what `PdfPlumberReader` expects.
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

    # One TEXT block per page (its text regions merged in reading order) followed
    # by that page's figures, each still its own IMAGE block. Merging matches the
    # digital path, which already reads a whole page as one block; a scanned page
    # otherwise fragments into a block per layout region. The merged text block
    # carries no bbox -- per-region coordinates are gone, and citation falls back
    # to the page, exactly as the digital path does.
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


# --- layout: a digital PDF via its text layer (paths 1 + 2) -------------------


class _PdfTextLayer:
    """A digital PDF's text layer, read once and reported in rendered-pixel space.

    The layout detector runs on pages rendered at `dpi`, so its boxes are in image
    pixels; pdfplumber reports text in PDF points. pdfplumber already resolves
    `/Rotate` and a non-zero CropBox internally -- its coordinates describe the
    upright page in a top-left frame, the very same orientation pypdfium2 renders
    (verified against a `/Rotate 90` page: both place the text in matching upright
    pixel columns). So the only mapping between text points and rendered pixels is
    a scale `zoom = dpi / 72`: `pixel = point * zoom` for `candidates`, and the
    inverse `point = pixel / zoom` for `region_text`, with no rotation matrix.

    Opens the document once and holds it; `candidates` caches its page's lines so
    detecting N regions on a page does not re-read the file N times. Injectable:
    `extract_layout_digital` takes a `text_layer`, so the chain runs in CI against
    a fake with the same surface and never opens a real PDF.
    """

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
        """The whole page's text, for path 1's per-page text block."""
        return self._pdf.pages[index].extract_text() or ""

    def candidates(self, index: int) -> List[dict]:
        """This page's text lines as pairing candidates, `{bbox, page, text}`.

        `bbox` is in rendered-page pixels (`point * zoom`), the same frame as a
        detected region, so `fused.reference_text_for` can score nearness.
        """
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
        """The text under a detected region, read from the text layer, no OCR.

        `pixel_bbox` is in rendered pixels; it is scaled back to points (`/ zoom`)
        and clamped to the page before `crop(...).extract_text()` reads it.
        """
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
        except Exception:  # noqa: BLE001 - closing is best effort
            pass


def pdf_has_text_layer(text_layer: Any) -> bool:
    """Whether any page yields extractable text -- a digital or already-OCR'd PDF.

    Routed on real extractable text rather than `page.get_fonts()`: a scanned PDF
    routinely embeds a font for an invisible/empty OCR layer or a single
    watermark, so a non-empty font list is a weak proxy that would send a scan
    down the zero-OCR path and lose all its text. A page whose `get_text` is
    non-whitespace is one the text layer can read without OCR; none at all
    means a scan, which is path 3.
    """
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
    """A PDF, routed by whether it carries a text layer.

    Digital (any page has extractable text) -> `extract_layout_digital` (paths 1 +
    2, zero per-text-box OCR). Scanned (no text anywhere) -> `extract_layout`
    (path 3, OCR every region). The text layer decides the route; path 1's prose
    comes from `read_text` (the plain-text reader), not the layer.

    The seams (`detector`, `ocr`, `render`, `text_layer`, `read_text`) default to
    the configured backends but can be supplied, which is
    how the chain runs in CI without the real models, pypdfium2 or pdfplumber.
    """
    import config

    dpi = int(dpi if dpi is not None else config.LAYOUT_RENDER_DPI)
    layer = text_layer or _PdfTextLayer(path, dpi)
    try:
        digital = pdf_has_text_layer(layer)
    except Exception:  # noqa: BLE001 - unreadable text layer: try the scanned path
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


#: Reading-order lanes within a page: path-1 page text, then path-2 visual blocks
#: top-to-bottom. Lane 1 is reserved (formerly path-1 Markdown tables, now left in
#: the page text) so visual blocks keep lane 2 and reading-order keys are unchanged.
_LANE_TEXT, _LANE_VISUAL = 0, 2


def _reading_key(page: int, lane: int, index: int) -> int:
    """A reading-order key sortable across the whole document, assignable per block.

    `page * 1e6 + lane * 1e5 + index` orders a page as text -> tables -> visuals and
    a document page by page, yet depends only on the block itself -- so path 1 and
    path 2 can number their own blocks independently (even in different threads)
    and the two sets still merge into one correct order with no renumbering, and no
    `block_id` collision. That independence is what lets the two-phase materializer
    embed path-1 text before path 2 has run (`core/materialize.py`).
    """
    return page * 1_000_000 + lane * 100_000 + index


def digital_text_blocks(
    path: str,
    asset_id: str,
    *,
    text_layer: Any,
    read_text: Optional[Callable[[str], "dict[int, str]"]] = None,
) -> List[ContentBlock]:
    """Path 1: a digital PDF's page text, taken from the plain-text reader.

    One TEXT block per page, sourced from `read_text` (SimpleDirectoryReader by
    default) so the prose is identical to the plain-text path -- enabling layout
    extraction only adds figures, it never changes a text chunk. No prose is OCRed.

    Tables and equations are not emitted as their own blocks: their text already
    sits in the page text, so separate blocks would be duplicate chunks. This is
    the fast half: no render, detect, table parsing, or OCR.
    """
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
    """Path 2: a digital PDF's figures, paired from the text layer.

    Renders and detects, then keeps only IMAGE regions as fused blocks whose
    captions are the prose that references them (`reference_text_for` over
    text-layer candidates). Text, table, and equation regions are all left to
    path 1. Because the PDF has a text layer, this path performs no OCR and does
    not inspect whether individual regions have local text.

    The slow half: render + detect + crop. Raises on a layout failure; the caller
    decides whether to degrade to text-only.
    """
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
    """Merge path-1 and path-2 blocks into one stream, ordered by reading key.

    The blocks already carry their final `reading_order`/`block_id` (`_reading_key`),
    so this only sorts and stamps document metadata -- which is why the two halves
    can be produced separately (two-phase) or together (`extract_layout_digital`)
    and land identically.
    """
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
    """A digital PDF's text and figures without OCRing its prose.

    Path 1 (`digital_text_blocks`) takes the page text from the plain-text reader
    (`read_text`); path 2 (`digital_visual_blocks`) renders and detects only
    figures. Path 1 is produced unconditionally; path 2 is wrapped so a layout
    failure degrades to the text-only path rather than losing the document.
    The two-phase materializer calls the same two halves separately to embed path-1
    text before path 2 has run (`core/materialize.py:two_phase_ingest`).
    """
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
    except Exception:  # noqa: BLE001 - detect/render failed: keep the text-only path
        pass
    return assemble_stream(asset_id, path, metadata, text_blocks + visual_blocks)


def _pdf_page_texts(path: str) -> "dict[int, str]":
    """Each page's prose keyed by 0-based page index, via SimpleDirectoryReader.

    Path 1's text comes from the *same* reader as the plain-text path
    (`extract_text` -> `file_to_documents`), so turning layout extraction on adds
    figures without changing a single text chunk -- the digital stream's prose is
    byte-for-byte the legacy text, just with IMAGE blocks interleaved. pdfplumber
    is kept only for geometry (`candidates`/`region_text`) and table detection,
    which SimpleDirectoryReader's flat text cannot provide.

    SimpleDirectoryReader returns one Document per PDF page with a 1-based
    `page_label`; this buckets them to 0-based indices, joining any that share a
    page so no page's text is dropped. The text is taken via `_content_of` (the
    same accessor `ContentStream.from_documents` uses) and kept verbatim -- not
    stripped -- so a page's block is byte-for-byte what the plain-text path emits.
    """
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
        import pdfplumber  # noqa: PLC0415 - optional, and probed rather than required
    except ImportError:
        return None
    return pdfplumber


def _pypdfium2():
    try:
        import pypdfium2  # noqa: PLC0415 - optional, and probed rather than required
    except ImportError:
        return None
    return pypdfium2


def _pdf_libs() -> bool:
    """Whether the permissively-licensed PDF stack is available for layout.

    Layout extraction needs both pypdfium2 (render) and pdfplumber (text layer);
    without either, `extract` falls back to plain text rather than failing.
    """
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
