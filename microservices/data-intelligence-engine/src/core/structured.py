# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Structured documents (docx/pptx/xlsx/html) into one content stream.

A born-digital office/web file is not a flat page of pixels like a PDF: its text,
tables and images are already typed nodes in an XML tree (OOXML) or a DOM. So the
visual reconstruction a PDF needs -- render the page, detect a figure's region,
OCR a scanned patch -- does not apply; the structure already says where every
picture is. What *is* the same as the PDF path is the slow half's job: locate each
figure, locate the prose around it, and pair the two into a caption. That pairing
is shared here (`_assemble` -> `fused.reference_text_for`), exactly the primitive
the PDF path uses; a format only has to say how it finds its figures and how it
orders its text. The PDF path could adopt the same contract later -- for now it is
left as is, and this drives docx/pptx/xlsx/html.

The one trick that lets one pairing serve every format: `reference_text_for`
scores a candidate mainly by vertical distance. A PDF supplies real pixel boxes;
a structured file has none, so each block is given a synthetic box at its position
in document order. "Vertical distance" then means "how many blocks apart", so the
`Figure 3`/`图 3` reference search works with no change to the pairing code. What a
structured file does *not* share is the PDF's no-key fallback (every caption-like
line on the page): a docx has no pages, so that read the whole document. A figure
here instead takes the caption paragraph right beside it (`_caption_line`).

Why a native walk and not `SimpleDirectoryReader`: the plain-text reader returns
one flat blob with no per-image position, which is exactly what figure/text
pairing needs. The reader stays the fast path for a file with *no* images
(`extractor.extract_text`); a file that carries pictures is walked here so each
picture lands between the paragraphs that talk about it, and `surrounding_text`
(derived from the stream at node time) can see them.

Parsers are all permissively licensed (python-docx/pptx/openpyxl MIT, lxml BSD,
beautifulsoup4 MIT), so this adds nothing that blocks an external release.
"""

import base64
import os
import re
import zipfile
from typing import Any, List, Optional, Mapping, Sequence, Tuple, Union

from core.content import IMAGE, ROLE_DOC_IMAGE, TABLE, TEXT, ContentBlock, ContentStream
from core.visual import Figure, caption_for

#: Extension -> walker key. `.htm`/`.html` share one; the legacy binary formats
#: (`.ppt`/`.doc`/`.xls`) are absent: python-pptx/docx/openpyxl read only the OOXML
#: (zipped XML) variants, so an old binary file falls through to the plain-text
#: reader rather than erroring here.
_KINDS = {
    ".docx": "docx",
    ".pptx": "pptx",
    ".xlsx": "xlsx",
    ".html": "html",
    ".htm": "html",
}

#: Inside an OOXML zip, embedded pictures live under the `media/` directories. An
#: xlsx chart has no bitmap -- it is a drawing under `xl/charts/` -- but the xlsx
#: walker re-plots it as a figure (`_chart_image`), so a workbook holding only
#: charts must take the structured walk too.
_OOXML_MEDIA_DIRS = ("word/media/", "ppt/media/", "xl/media/", "xl/charts/")


def structured_kind(path: str) -> str:
    """The walker key for `path`, or `""` if no structured walker handles it."""
    return _KINDS.get(os.path.splitext(path)[1].lower(), "")


# --- fast pre-check: does the file carry any image at all? --------------------


def has_media(path: str) -> bool:
    """Whether `path` embeds any picture -- a cheap routing check, not a parse.

    For an OOXML file this reads the zip's central directory only (the file
    listing, never the compressed bytes), so the answer costs microseconds and
    does not depend on how big the pictures are. For HTML it scans for an `<img>`
    tag. A file with no media skips the structure walk and takes the plain-text
    reader, exactly as before.
    """
    kind = structured_kind(path)
    if kind in ("docx", "pptx", "xlsx"):
        try:
            with zipfile.ZipFile(path) as archive:
                return any(name.startswith(_OOXML_MEDIA_DIRS) for name in archive.namelist())
        except Exception:  # noqa: BLE001 - not a readable zip: treat as no media
            return False
    if kind == "html":
        try:
            with open(path, "rb") as handle:
                return b"<img" in handle.read().lower()
        except Exception:  # noqa: BLE001
            return False
    return False


#: A walker yields these in document order: a ready text/table block, or a figure
#: to be captioned against the text around it. `Figure` is the shared slow-path
#: unit (`core/visual.py`), the same one the PDF path builds -- here with a
#: synthetic order-box for `bbox`, there with a real pixel box.
Slot = Union[ContentBlock, Figure]


def _text_slot(text: str, *, kind: str = TEXT, page: int = 0, label: str = "text") -> Optional[ContentBlock]:
    """A text/table block stub (its id and reading order are stamped in `_assemble`)."""
    if not (text and text.strip()):
        return None
    return ContentBlock(block_id="", kind=kind, text=text, page=page, metadata={"type": label})


def _synthetic_bbox(order: int) -> Tuple[float, float, float, float]:
    """A one-unit-tall box at position `order`, so block distance reads as height."""
    return (0.0, float(order), 1.0, float(order) + 1.0)


#: A paragraph that *is* a caption, not prose that mentions one: the marker and its
#: number open the line (`图 4｜…`, `Figure 1: …`, `Table 2.`), where the PDF
#: path's `CAPTION_LIKE_PATTERN` matches a marker anywhere in the text.
_CAPTION_HEAD = re.compile(
    r"^\s*(?:fig(?:ure)?|table|equation|formula|图|表|公式)"
    r"\s*[.．:：]?\s*[(（]?\s*\d+[a-z]?(?![0-9A-Za-z])",
    re.IGNORECASE,
)

#: How many slots either side of a figure its caption line may sit.
_CAPTION_WINDOW = 2


def _caption_line(slots: Sequence[Slot], order: int, page: int) -> Optional[int]:
    """The position of the caption paragraph beside the figure at `order`, if any.

    Only the figure's immediate neighbours on its own page (slide, sheet) are
    looked at, nearest first and below before above at equal distance, since a
    figure's caption usually follows it. A structured file has no real page to
    bound the search -- a docx is one `page=0` -- so without this window the
    PDF fallback (every caption-like line on the page) read the whole document
    and gave every figure the same wall of captions.
    """
    for distance in range(1, _CAPTION_WINDOW + 1):
        for position in (order + distance, order - distance):
            if not 0 <= position < len(slots):
                continue
            slot = slots[position]
            if (
                isinstance(slot, ContentBlock) and slot.kind == TEXT
                and slot.page == page and _CAPTION_HEAD.match(slot.text)
            ):
                return position
    return None


def _paired_caption(
    slots: Sequence[Slot], order: int, figure: Figure,
    candidates: Sequence[Mapping[str, Any]],
) -> str:
    """The caption paragraph beside the figure at `order`, then the prose citing it.

    The paragraph is kept whole -- the keyed pairing keeps only the sentences
    carrying the key, which would cut a multi-sentence caption short. Only the
    number heading it (`图 4`) is the key, so a caption that also mentions
    `表 3` does not pull in the prose citing that table. `""` when no caption
    paragraph sits beside the figure.

    A walker that located the caption from geometry (`figure.caption_line`) is
    believed over reading-order neighbours -- including when it found none
    (`""`), since there the neighbours are exactly what it could not trust.
    """
    if figure.caption_line is not None:
        line = figure.caption_line.strip()
        if not line:
            return ""
        others = [c for c in candidates if c["text"].strip() != line]
    else:
        position = _caption_line(slots, order, figure.page)
        if position is None:
            return ""
        line = slots[position].text.strip()
        line_bbox = _synthetic_bbox(position)
        others = [c for c in candidates if c["bbox"] != line_bbox]
    head = _CAPTION_HEAD.match(line).group(0)
    # No page candidates: the pairing's no-match fallback reads only those, so
    # a number nothing else cites adds nothing rather than every caption-like
    # line in the document.
    citing = caption_for(
        Figure(region_text=head, page=figure.page, bbox=figure.bbox), [], others,
    )
    return "\n".join(part for part in (line, citing) if part)


def _assemble(
    asset_id: str,
    path: str,
    metadata: Optional[Mapping[str, Any]],
    put_blob: Any,
    slots: Sequence[Slot],
) -> ContentStream:
    """Turn ordered slots into a stream, captioning each figure from its neighbours.

    Text/table slots keep their document position as `reading_order`, so a figure
    inserted between them sits where it was found -- which is what lets
    `surrounding_text` read the right prose at node time. A figure without a
    preset caption takes the caption paragraph right beside it (`_caption_line`),
    followed by the prose elsewhere that cites its number -- the shared keyed
    pairing (`visual.caption_for`), every text slot a candidate with a synthetic
    box at its order. With no caption paragraph beside it the caption stays
    empty, and `surrounding_text` stands in at node time.
    """
    candidates = [
        {"text": slot.text, "page": slot.page, "bbox": _synthetic_bbox(order)}
        for order, slot in enumerate(slots)
        if isinstance(slot, ContentBlock) and slot.text and slot.text.strip()
    ]

    blocks: List[ContentBlock] = []
    for order, slot in enumerate(slots):
        if isinstance(slot, ContentBlock):
            slot.block_id = f"{asset_id}:{order}"
            slot.reading_order = order
            blocks.append(slot)
            continue

        figure = slot
        figure.bbox = _synthetic_bbox(order)
        caption = figure.caption
        if caption is None:
            caption = _paired_caption(slots, order, figure, candidates)
        blocks.append(
            ContentBlock(
                block_id=f"{asset_id}:{order}", kind=IMAGE,
                media_key=put_blob(figure.data, figure.content_type),
                caption=caption or "", page=figure.page, reading_order=order,
                metadata={"type": figure.label, "content_type": figure.content_type,
                          "byte_size": len(figure.data), "role": ROLE_DOC_IMAGE},
            )
        )

    return ContentStream(
        asset_id=asset_id,
        blocks=blocks,
        metadata={
            "file_name": os.path.basename(path),
            "file_path": os.path.abspath(path),
            **dict(metadata or {}),
            "asset_id": asset_id,
        },
    )


# --- entry point --------------------------------------------------------------


def extract_structured(
    path: str,
    asset_id: str,
    put_blob: Any,
    metadata: Optional[Mapping[str, Any]] = None,
    kind: Optional[str] = None,
) -> ContentStream:
    """One structured file as a stream of typed blocks in document order."""
    kind = kind or structured_kind(path)
    slots = {
        "docx": _walk_docx,
        "pptx": _walk_pptx,
        "xlsx": _walk_xlsx,
        "html": _walk_html,
    }[kind](path)
    return _assemble(asset_id, path, metadata, put_blob, slots)


# --- shared: cells -> Markdown ------------------------------------------------


def _rows_to_markdown(rows: Sequence[Sequence[Any]]) -> str:
    """A grid of cells as a GitHub Markdown table, the first row its header.

    Row/column structure is a table's whole meaning, so it is kept as Markdown
    rather than flattened to prose. `None` cells become empty; a pipe or newline
    in a cell is neutralized so it cannot break the grid.
    """
    def cell(value: Any) -> str:
        if value is None:
            return ""
        return str(value).replace("|", "\\|").replace("\n", " ").strip()

    body = [[cell(value) for value in row] for row in rows if row is not None]
    body = [row for row in body if any(c for c in row)]
    if not body:
        return ""
    width = max(len(row) for row in body)
    body = [row + [""] * (width - len(row)) for row in body]
    lines = [
        "| " + " | ".join(body[0]) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    for row in body[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


# --- docx ---------------------------------------------------------------------


def _walk_docx(path: str) -> List[Slot]:
    """A .docx body in order: paragraphs, inline/anchored pictures, tables.

    python-docx exposes paragraphs and tables as separate lists, losing their
    interleaving, so the body's XML children are walked directly. Within a
    paragraph each `a:blip` (a picture reference) is resolved through the part's
    relationships in the order it appears, so a figure lands at its real spot in
    the prose. A math formula (`m:oMath`, Office's native equation markup) keeps
    its symbols as text rather than vanishing -- python-docx omits it from
    `paragraph.text`.
    """
    from docx import Document
    from docx.oxml.ns import qn
    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = Document(path)
    part = document.part
    slots: List[Slot] = []

    def paragraph_slots(paragraph: Paragraph) -> None:
        math = _omml_paragraph_latex(paragraph._p)
        combined = "\n".join(p for p in (paragraph.text or "", math) if p.strip())
        block = _text_slot(combined)
        if block is not None:
            slots.append(block)
        for blip in paragraph._p.findall(".//" + qn("a:blip")):
            rid = blip.get(qn("r:embed")) or blip.get(qn("r:link"))
            if not rid:
                continue
            try:
                image_part = part.related_parts[rid]
                data = image_part.blob
                content_type = getattr(image_part, "content_type", "") or "image/png"
            except Exception:  # noqa: BLE001 - a missing relationship is skipped
                continue
            slots.append(Figure(data=data, content_type=content_type))

    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            paragraph_slots(Paragraph(child, document))
        elif isinstance(child, CT_Tbl):
            table = Table(child, document)
            rows = [[c.text for c in row.cells] for row in table.rows]
            block = _text_slot(_rows_to_markdown(rows), kind=TABLE, label="table")
            if block is not None:
                slots.append(block)
    return slots


#: The OMML (Office Math Markup Language) namespace.
_OMML_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"

#: An n-ary operator (sum/integral/product/...) by its OMML character. These are
#: the ones with a LaTeX command; anything else is emitted as the literal char.
_NARY_OPS = {
    "∑": r"\sum", "∫": r"\int", "∏": r"\prod",
    "∐": r"\coprod", "∮": r"\oint",
    "⋃": r"\bigcup", "⋂": r"\bigcap",
}

#: Delimiter characters that need a LaTeX escape inside `\left`/`\right`.
_DELIM_ESCAPE = {"{": r"\{", "}": r"\}", "⟨": r"\langle", "⟩": r"\rangle", "": "."}


def _omml_paragraph_latex(paragraph_xml: Any) -> str:
    """Every OMML formula in a paragraph converted to inline LaTeX, `$...$` each.

    OMML is Office's structured equation markup -- fractions, scripts, radicals and
    n-ary operators are nested elements, not glyphs -- so a structural conversion
    keeps `x^2` and `\\frac{a}{b}` instead of the bare symbols a flat text read
    leaves behind. Unconverted constructs degrade to their concatenated text rather
    than being dropped, so an equation is never lost, only ever simplified.
    """
    pieces = [
        _omml_to_latex(math).strip()
        for math in paragraph_xml.findall(".//{%s}oMath" % _OMML_NS)
    ]
    return " ".join("$%s$" % piece for piece in pieces if piece)


def _omml_to_latex(element: Any) -> str:
    """One OMML element as LaTeX, recursing structurally over its children."""
    from lxml import etree

    def local(node: Any) -> str:
        return etree.QName(node).localname

    def kids(node: Any, name: str) -> List[Any]:
        return [c for c in node if local(c) == name]

    def one(node: Any, name: str) -> Optional[Any]:
        found = kids(node, name)
        return found[0] if found else None

    def seq(node: Optional[Any]) -> str:
        return conv(node) if node is not None else ""

    def val(node: Optional[Any]) -> str:
        return node.get("{%s}val" % _OMML_NS, "") if node is not None else ""

    def conv(node: Any) -> str:
        tag = local(node)
        if tag == "t":
            return node.text or ""
        if tag.endswith("Pr"):  # property elements carry formatting, not content
            return ""
        if tag == "f":  # fraction
            return r"\frac{%s}{%s}" % (seq(one(node, "num")), seq(one(node, "den")))
        if tag == "sSup":
            return "{%s}^{%s}" % (seq(one(node, "e")), seq(one(node, "sup")))
        if tag == "sSub":
            return "{%s}_{%s}" % (seq(one(node, "e")), seq(one(node, "sub")))
        if tag == "sSubSup":
            return "{%s}_{%s}^{%s}" % (
                seq(one(node, "e")), seq(one(node, "sub")), seq(one(node, "sup")))
        if tag == "rad":  # radical
            body = seq(one(node, "e"))
            degree = seq(one(node, "deg")).strip()
            return r"\sqrt[%s]{%s}" % (degree, body) if degree else r"\sqrt{%s}" % body
        if tag == "nary":  # sum / integral / product with limits
            chr_el = one(one(node, "naryPr"), "chr") if one(node, "naryPr") is not None else None
            char = val(chr_el) or "∫"  # OMML's default n-ary is the integral
            operator = _NARY_OPS.get(char, char)
            sub, sup = seq(one(node, "sub")).strip(), seq(one(node, "sup")).strip()
            if sub:
                operator += "_{%s}" % sub
            if sup:
                operator += "^{%s}" % sup
            return "%s{%s}" % (operator, seq(one(node, "e")))
        if tag == "d":  # delimiter (parentheses/brackets around its elements)
            pr = one(node, "dPr")
            beg = val(one(pr, "begChr")) if pr is not None else "("
            end = val(one(pr, "endChr")) if pr is not None else ")"
            beg = _DELIM_ESCAPE.get(beg, beg or "(")
            end = _DELIM_ESCAPE.get(end, end or ")")
            inner = " , ".join(conv(e) for e in kids(node, "e"))
            return r"\left%s %s \right%s" % (beg, inner, end)
        if tag == "func":  # named function, e.g. sin(x)
            name = seq(one(node, "fName")).strip()
            return r"\%s{%s}" % (name, seq(one(node, "e"))) if name else seq(one(node, "e"))
        if tag == "acc":  # accent
            return r"\hat{%s}" % seq(one(node, "e"))
        if tag == "bar":
            return r"\overline{%s}" % seq(one(node, "e"))
        # A run, a base/num/den/sup/... container, or anything not special-cased:
        # concatenate the LaTeX of its children (text leaves end the recursion).
        return "".join(conv(c) for c in node)

    return conv(element)


# --- pptx ---------------------------------------------------------------------


def _walk_pptx(path: str) -> List[Slot]:
    """Each slide's shapes in reading order: text frames, tables, pictures.

    A slide stores exact shape coordinates, so reading order is recovered by
    sorting shapes top-to-bottom then left-to-right -- the geometry is in the
    file, no layout model. Group shapes are recursed into; the slide number is
    each block's `page`.

    Reading order is not enough to caption a picture, though: two pictures side
    by side, each captioned below, read as picture, picture, caption, caption, so
    the second picture's nearest slot is the first one's caption. The shape boxes
    are used instead (`_slide_caption`), and the paragraph found is handed to
    the pairing as the figure's `caption_line`.
    """
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    presentation = Presentation(path)
    slots: List[Slot] = []

    def shape_key(shape: Any):
        return (getattr(shape, "top", None) or 0, getattr(shape, "left", None) or 0)

    def shape_box(shape: Any) -> Tuple[float, float, float, float]:
        left = getattr(shape, "left", None) or 0
        top = getattr(shape, "top", None) or 0
        width = getattr(shape, "width", None) or 0
        height = getattr(shape, "height", None) or 0
        return (float(left), float(top), float(left + width), float(top + height))

    def handle(shape: Any, page: int, pictures: List[Any], texts: List[Any]) -> None:
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            for member in sorted(shape.shapes, key=shape_key):
                handle(member, page, pictures, texts)
            return
        if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
            try:
                image = shape.image
                figure = Figure(
                    data=image.blob, content_type=image.content_type or "image/png", page=page,
                )
            except Exception:  # noqa: BLE001 - an unreadable picture is skipped
                return
            slots.append(figure)
            pictures.append((figure, shape_box(shape)))
            return
        if getattr(shape, "has_table", False) and shape.has_table:
            rows = [[c.text for c in row.cells] for row in shape.table.rows]
            block = _text_slot(_rows_to_markdown(rows), kind=TABLE, page=page, label="table")
            if block is not None:
                slots.append(block)
            return
        if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
            block = _text_slot(shape.text_frame.text, page=page)
            if block is not None:
                slots.append(block)
                texts.append((block.text, shape_box(shape)))

    for number, slide in enumerate(presentation.slides, start=1):
        pictures: List[Any] = []
        texts: List[Any] = []
        for shape in sorted(slide.shapes, key=shape_key):
            handle(shape, number, pictures, texts)
        for figure, box in pictures:
            figure.caption_line = _slide_caption(box, texts)
    return slots


def _slide_caption(
    picture: Tuple[float, float, float, float],
    texts: Sequence[Tuple[str, Tuple[float, float, float, float]]],
) -> str:
    """The caption text frame of a picture on a slide, judged by the shape boxes.

    A caption shares the picture's column: only frames that overlap it
    horizontally and open with a caption marker (`_CAPTION_HEAD`) qualify, and
    the one with the smallest vertical gap wins, below before above at equal
    gap. `""` when no frame qualifies -- the figure is then left to its
    surrounding text, like any figure without a caption.
    """
    left, top, right, bottom = picture
    best = None
    for text, (t_left, t_top, t_right, t_bottom) in texts:
        if t_right <= left or t_left >= right or not _CAPTION_HEAD.match(text):
            continue
        below = t_top >= bottom
        gap = t_top - bottom if below else max(0.0, top - t_bottom)
        key = (gap, not below)
        if best is None or key < best[0]:
            best = (key, text)
    return best[1] if best else ""


# --- xlsx ---------------------------------------------------------------------

#: Rows per Markdown block. A sheet is split into windows that each repeat the
#: header, so a chunk the downstream splitter cuts still names its columns instead
#: of becoming a wall of headerless numbers.
_XLSX_ROWS_PER_BLOCK = 50


def _walk_xlsx(path: str) -> List[Slot]:
    """Each sheet as header-carrying Markdown tables, charts, and embedded pictures.

    `data_only=True` yields a formula cell's cached computed value, not its formula
    text -- the number is what a query matches -- and each value is then rendered
    through its cell's number format, so a date reads `2023-03-15` and a ratio reads
    `5%` rather than `45000` or `0.05`. A large sheet is split into windows that
    each repeat the header row. A chart is re-plotted to a bitmap (`_chart_image`);
    embedded pictures (`xl/media`) become figures as they are.
    """
    from openpyxl import load_workbook

    workbook = load_workbook(path, data_only=True)
    slots: List[Slot] = []
    for number, sheet in enumerate(workbook.worksheets, start=1):
        rows = [[_format_cell(cell) for cell in row] for row in sheet.iter_rows()]
        rows = [row for row in rows if any(cell is not None for cell in row)]
        if rows:
            title = _text_slot(f"# {sheet.title}", page=number)
            if title is not None:
                slots.append(title)
            header, body = rows[0], rows[1:]
            windows = (
                [rows] if not body
                else [[header] + body[start:start + _XLSX_ROWS_PER_BLOCK]
                      for start in range(0, len(body), _XLSX_ROWS_PER_BLOCK)]
            )
            for window in windows:
                block = _text_slot(_rows_to_markdown(window), kind=TABLE, page=number, label="table")
                if block is not None:
                    slots.append(block)
        for chart in list(getattr(sheet, "_charts", []) or []):
            data = _chart_image(workbook, chart)
            if data:
                slots.append(Figure(
                    data=data, content_type="image/png", page=number,
                    label="chart", caption=_chart_title(chart) or None,
                ))
        for image in list(getattr(sheet, "_images", []) or []):
            data = _openpyxl_image_bytes(image)
            if data:
                content_type = "image/" + (getattr(image, "format", None) or "png").lower()
                slots.append(Figure(data=data, content_type=content_type, page=number))
    return slots


def _format_cell(cell: Any) -> Optional[str]:
    """A cell's value as it is displayed: its number format applied to the value.

    openpyxl already hands back a date-formatted cell as a `datetime`, so the work
    is picking a readable rendering (date vs datetime vs time) and turning a percent
    or plain number into its shown form. An unrecognized format falls through to the
    plain value, never an error.
    """
    import datetime

    value = cell.value
    if value is None:
        return None
    fmt = (getattr(cell, "number_format", "") or "").lower()
    if isinstance(value, datetime.datetime):
        wants_time = any(token in fmt for token in ("h", "s", "am/pm"))
        wants_date = any(token in fmt for token in ("y", "d")) or "mmm" in fmt
        if wants_time and not wants_date:
            return value.strftime("%H:%M:%S")
        if wants_time:
            return value.strftime("%Y-%m-%d %H:%M:%S")
        return value.strftime("%Y-%m-%d")
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, datetime.time):
        return value.strftime("%H:%M:%S")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "%" in fmt:
            return f"{value * 100:g}%"
        return f"{int(value)}" if isinstance(value, float) and value.is_integer() else f"{value:g}"
    return str(value)


def _chart_title(chart: Any) -> str:
    """A chart's title text, or `""` -- the title lives a few layers deep in OOXML."""
    try:
        title = chart.title
        if title is None:
            return ""
        if isinstance(title, str):
            return title
        runs = title.tx.rich.p[0].r  # CharacterProperties-wrapped rich text
        return "".join(run.t for run in runs if run.t).strip()
    except Exception:  # noqa: BLE001 - no title rather than a failed sheet
        return ""


def _chart_image(workbook: Any, chart: Any) -> bytes:
    """An openpyxl chart re-plotted to a PNG, or `b""` if it cannot be rendered.

    openpyxl reads a chart as a vector definition with no stored bitmap, so there
    is nothing to extract -- the chart is re-drawn from its series data with
    Matplotlib (Agg, no display). The result is an approximation, not Excel's exact
    styling, but it carries the shape of the data a query might ask about. Common
    types (bar/line/pie/scatter) are handled; anything else, or any failure, yields
    no image rather than breaking the sheet.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from io import BytesIO

        kind = type(chart).__name__
        series = [
            [v for v in _resolve_ref(workbook, _series_ref(s)) if isinstance(v, (int, float))]
            for s in getattr(chart, "series", []) or []
        ]
        series = [s for s in series if s]
        if not series:
            return b""

        figure, axes = plt.subplots(figsize=(4, 3))
        try:
            if "Pie" in kind:
                axes.pie(series[0])
            elif "Scatter" in kind and len(series) >= 2:
                axes.scatter(series[0], series[1])
            elif "Line" in kind:
                for s in series:
                    axes.plot(range(len(s)), s)
            else:  # bar is the sensible default for the rest
                width = 0.8 / len(series)
                for index, s in enumerate(series):
                    axes.bar([x + index * width for x in range(len(s))], s, width=width)
            title = _chart_title(chart)
            if title:
                axes.set_title(title)
            buffer = BytesIO()
            figure.savefig(buffer, format="png", dpi=100, bbox_inches="tight")
            return buffer.getvalue()
        finally:
            plt.close(figure)
    except Exception:  # noqa: BLE001 - a chart that will not render is skipped
        return b""


def _series_ref(series: Any) -> str:
    """The cell range a chart series draws its values from, as `Sheet!$A$1:$A$9`."""
    try:
        return series.val.numRef.f or ""
    except Exception:  # noqa: BLE001
        return ""


def _resolve_ref(workbook: Any, ref: str) -> List[Any]:
    """The cell values behind a chart reference like `'My Sheet'!$B$2:$B$9`."""
    if not ref:
        return []
    name, _, cells = ref.rpartition("!")
    name = name.strip().strip("'").replace("''", "'")
    try:
        sheet = workbook[name] if name and name in workbook.sheetnames else workbook.active
        values: List[Any] = []
        for row in sheet[cells.replace("$", "")]:
            cells_in_row = row if isinstance(row, tuple) else (row,)
            values.extend(cell.value for cell in cells_in_row)
        return values
    except Exception:  # noqa: BLE001
        return []


def _openpyxl_image_bytes(image: Any) -> bytes:
    """The raw bytes of an openpyxl embedded image, however it stored them."""
    try:
        data = image._data
        return data() if callable(data) else data
    except Exception:  # noqa: BLE001
        pass
    try:
        ref = image.ref
        if hasattr(ref, "read"):
            ref.seek(0)
            return ref.read()
        if isinstance(ref, (bytes, bytearray)):
            return bytes(ref)
    except Exception:  # noqa: BLE001
        pass
    return b""


# --- html ---------------------------------------------------------------------

#: Tags that close an inline run: text accumulated inside one is a block.
_HTML_BLOCK_TAGS = frozenset({
    "p", "div", "section", "article", "header", "footer", "li", "blockquote",
    "h1", "h2", "h3", "h4", "h5", "h6", "pre", "td", "th", "tr", "figcaption",
})


def _walk_html(path: str) -> List[Slot]:
    """A DOM in document order: text runs, tables, and `<img>` with its caption.

    DOM order is reading order, so the tree is walked depth-first, flushing the
    accumulated inline text at each block boundary and at every image -- which
    keeps a picture between the text before and after it. An image's caption comes
    from `alt`/`title` or an enclosing `<figure>`'s `<figcaption>` (HTML states
    what a PDF has to guess); with none, it is paired from the surrounding blocks.
    `src` is read for a data URI or a path beside the file; a remote URL is not
    fetched.
    """
    from bs4 import BeautifulSoup, NavigableString, Tag

    with open(path, "rb") as handle:
        soup = BeautifulSoup(handle.read(), "lxml")
    for junk in soup(["script", "style", "head", "noscript"]):
        junk.decompose()
    root = soup.body or soup
    base_dir = os.path.dirname(os.path.abspath(path))
    slots: List[Slot] = []
    buffer: List[str] = []

    def flush() -> None:
        text = " ".join(" ".join(buffer).split())
        buffer.clear()
        block = _text_slot(text)
        if block is not None:
            slots.append(block)

    def figcaption_of(node: Tag) -> str:
        parent = node.parent
        while parent is not None and getattr(parent, "name", None) != "figure":
            parent = parent.parent
        if parent is not None:
            caption = parent.find("figcaption")
            if caption:
                return caption.get_text(" ", strip=True)
        return ""

    def emit_image(node: Tag) -> None:
        data, content_type = _html_image_bytes(node.get("src", ""), base_dir)
        if not data:
            return
        label = (node.get("alt") or node.get("title") or figcaption_of(node) or "").strip()
        slots.append(Figure(
            data=data, content_type=content_type,
            caption=label if label else None,
        ))

    def emit_table(node: Tag) -> None:
        rows = [
            [cell.get_text(" ", strip=True) for cell in tr.find_all(["td", "th"])]
            for tr in node.find_all("tr")
        ]
        block = _text_slot(_rows_to_markdown(rows), kind=TABLE, label="table")
        if block is not None:
            slots.append(block)

    def walk(node: Tag) -> None:
        for child in node.children:
            if isinstance(child, NavigableString):
                buffer.append(str(child))
            elif not isinstance(child, Tag):
                continue
            elif child.name == "img":
                flush()
                emit_image(child)
            elif child.name == "table":
                flush()
                emit_table(child)
            else:
                walk(child)
                if child.name in _HTML_BLOCK_TAGS:
                    flush()

    walk(root)
    flush()
    return slots


def _html_image_bytes(src: str, base_dir: str) -> Tuple[bytes, str]:
    """Bytes and content-type for an `<img src>`; `(b"", "")` if not local."""
    src = (src or "").strip()
    if not src:
        return b"", ""
    if src.startswith("data:"):
        try:
            header, _, payload = src.partition(",")
            content_type = header[5:].split(";")[0] or "image/png"
            if ";base64" in header:
                return base64.b64decode(payload), content_type
            from urllib.parse import unquote_to_bytes
            return unquote_to_bytes(payload), content_type
        except Exception:  # noqa: BLE001
            return b"", ""
    if "://" in src:  # a remote URL is not fetched
        return b"", ""
    candidate = os.path.normpath(os.path.join(base_dir, src.split("?")[0]))
    if os.path.isfile(candidate):
        try:
            import mimetypes
            with open(candidate, "rb") as handle:
                data = handle.read()
            return data, mimetypes.guess_type(candidate)[0] or "image/png"
        except Exception:  # noqa: BLE001
            return b"", ""
    return b"", ""
