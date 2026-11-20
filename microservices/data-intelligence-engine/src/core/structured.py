# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import base64
import os
import re
import shutil
import signal
import subprocess
import zipfile
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, List, Optional, Mapping, Sequence, Tuple, Union

from core.content import IMAGE, ROLE_DOC_IMAGE, TABLE, TEXT, ContentBlock, ContentStream
from core.visual import Figure, caption_for

#: Extension -> walker key. Legacy binary .doc/.ppt/.xls are not handled (OOXML only).
_KINDS = {
    ".docx": "docx",
    ".pptx": "pptx",
    ".xlsx": "xlsx",
    ".html": "html",
    ".htm": "html",
}

#: OOXML zip dirs holding pictures; `xl/charts/` counts since xlsx charts are re-plotted as figures.
_OOXML_MEDIA_DIRS = ("word/media/", "ppt/media/", "xl/media/", "xl/charts/")


def structured_kind(path: str) -> str:
    """The walker key for `path`, or `""` if no structured walker handles it."""
    return _KINDS.get(os.path.splitext(path)[1].lower(), "")


def has_media(path: str) -> bool:
    """Whether `path` embeds any picture, from the zip listing or an `<img>` scan only."""
    kind = structured_kind(path)
    if kind in ("docx", "pptx", "xlsx"):
        try:
            with zipfile.ZipFile(path) as archive:
                return any(name.startswith(_OOXML_MEDIA_DIRS) for name in archive.namelist())
        except Exception:  # noqa: BLE001
            return False
    if kind == "html":
        try:
            with open(path, "rb") as handle:
                return b"<img" in handle.read().lower()
        except Exception:  # noqa: BLE001
            return False
    return False


Slot = Union[ContentBlock, Figure]


def _text_slot(text: str, *, kind: str = TEXT, page: int = 0, label: str = "text") -> Optional[ContentBlock]:
    """A text/table block stub (its id and reading order are stamped in `_assemble`)."""
    if not (text and text.strip()):
        return None
    return ContentBlock(block_id="", kind=kind, text=text, page=page, metadata={"type": label})


def _synthetic_bbox(order: int) -> Tuple[float, float, float, float]:
    """A one-unit-tall box at position `order`, so block distance reads as height."""
    return (0.0, float(order), 1.0, float(order) + 1.0)


#: A paragraph opening with a caption marker and number (`图 4｜…`, `Figure 1: …`, `Table 2.`).
_CAPTION_HEAD = re.compile(
    r"^\s*(?:fig(?:ure)?|table|equation|formula|图|表|公式)"
    r"\s*[.．:：]?\s*[(（]?\s*\d+[a-z]?(?![0-9A-Za-z])",
    re.IGNORECASE,
)

#: How many slots either side of a figure its caption line may sit.
_CAPTION_WINDOW = 2


def _caption_line(slots: Sequence[Slot], order: int, page: int) -> Optional[int]:
    """Position of the caption paragraph beside the figure at `order` on its page, nearest first, below before above."""
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
    """The whole caption paragraph beside the figure at `order`, then the prose citing its number."""
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
    # No page candidates, so an uncited number adds nothing.
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
    """Turn ordered slots into a stream, captioning each figure from its neighbours."""
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
    return _assemble(asset_id, path, metadata, put_blob, _rasterize_metafiles(slots))


def _rows_to_markdown(rows: Sequence[Sequence[Any]]) -> str:
    """A grid of cells as a GitHub Markdown table, the first row its header."""
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


def _walk_docx(path: str) -> List[Slot]:
    """A .docx body in XML order: paragraphs (with OMML math as LaTeX), pictures, tables."""
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
            except Exception:  # noqa: BLE001
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

#: OMML n-ary operator character -> LaTeX command; others are emitted literally.
_NARY_OPS = {
    "∑": r"\sum", "∫": r"\int", "∏": r"\prod",
    "∐": r"\coprod", "∮": r"\oint",
    "⋃": r"\bigcup", "⋂": r"\bigcap",
}

#: Delimiter characters that need a LaTeX escape inside `\left`/`\right`.
_DELIM_ESCAPE = {"{": r"\{", "}": r"\}", "⟨": r"\langle", "⟩": r"\rangle", "": "."}


def _omml_paragraph_latex(paragraph_xml: Any) -> str:
    """Every OMML formula in a paragraph converted to inline LaTeX, `$...$` each."""
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
        # Containers and unhandled constructs: concatenate their children.
        return "".join(conv(c) for c in node)

    return conv(element)


_METAFILE_SIDE = 2048
_METAFILE_MAX_SCALE = 8.0


def _metafile_suffix(data: bytes) -> str:
    if data[:4] == b"\x01\x00\x00\x00" and data[40:44] == b" EMF":
        return ".emf"
    if data[:4] == b"\xd7\xcd\xc6\x9a" or (
        data[:2] in (b"\x01\x00", b"\x02\x00") and data[2:6] in (b"\x09\x00\x00\x01", b"\x09\x00\x00\x03")
    ):
        return ".wmf"
    return ""


def _rasterize_metafiles(slots: List[Slot]) -> List[Slot]:
    figures = [slot for slot in slots if isinstance(slot, Figure) and _metafile_suffix(slot.data)]
    if not figures:
        return slots
    soffice = shutil.which("soffice")
    pngs = _metafiles_to_png(soffice, [f.data for f in figures]) if soffice else [None] * len(figures)
    dropped = set()
    for figure, png in zip(figures, pngs):
        if png is None:
            dropped.add(id(figure))
        else:
            figure.data, figure.content_type = png, "image/png"
    return [slot for slot in slots if id(slot) not in dropped]


def _metafiles_to_png(soffice: str, blobs: Sequence[bytes]) -> List[Optional[bytes]]:
    with TemporaryDirectory(prefix="engine-metafile-") as directory:
        root = Path(directory)
        sources = [root / f"{index}{_metafile_suffix(data)}" for index, data in enumerate(blobs)]
        for source, data in zip(sources, blobs):
            source.write_bytes(data)
        with subprocess.Popen(
            [soffice, "--headless", "--norestore", "--nolockcheck",
             f"-env:UserInstallation={(root / 'profile').as_uri()}",
             "--convert-to", "pdf", "--outdir", str(root / "out"), *map(str, sources)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        ) as process:
            try:
                process.wait(timeout=60 + 10 * len(sources))
            except subprocess.TimeoutExpired:
                # soffice forks soffice.bin, so kill the whole process group.
                os.killpg(process.pid, signal.SIGKILL)
        return [_render_metafile_pdf(root / "out" / f"{source.stem}.pdf") for source in sources]


def _render_metafile_pdf(path: Path) -> Optional[bytes]:
    import pypdfium2 as pdfium
    from PIL import Image, ImageChops

    if not path.is_file():
        return None
    try:
        document = pdfium.PdfDocument(str(path))
        try:
            page = document[0]
            width, height = page.get_size()
            # The picture sits on a full (locale-sized) page: find its extent, then re-render just that.
            preview = page.render(scale=1).to_pil().convert("RGB")
            box = ImageChops.difference(preview, Image.new("RGB", preview.size, "white")).getbbox()
            if box is None:
                return None
            left, top, right, bottom = box
            scale = min(_METAFILE_SIDE / max(right - left, bottom - top), _METAFILE_MAX_SCALE)
            crop = (max(left - 1, 0), max(height - bottom - 1, 0), max(width - right - 1, 0), max(top - 1, 0))
            image = page.render(scale=scale, crop=crop).to_pil().convert("RGB")
        finally:
            document.close()
    except Exception:  # noqa: BLE001
        return None
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _walk_pptx(path: str) -> List[Slot]:
    """Each slide's shapes sorted top-to-bottom, left-to-right; pictures captioned by shape geometry."""
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
            except Exception:  # noqa: BLE001
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
    """The horizontally overlapping caption frame nearest a slide picture, below before above, or `""`."""
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


#: Rows per Markdown block; each block repeats the header row.
_XLSX_ROWS_PER_BLOCK = 50


def _walk_xlsx(path: str) -> List[Slot]:
    """Each sheet as header-carrying Markdown tables, charts, and embedded pictures."""
    from openpyxl import load_workbook

    workbook = load_workbook(path, data_only=True)
    try:
        cell_images = _xlsx_cell_images(path)
    except Exception:  # noqa: BLE001
        cell_images = {}
    slots: List[Slot] = []
    for number, sheet in enumerate(workbook.worksheets, start=1):
        in_cell = cell_images.get(sheet.title, {})
        rows = [
            [None if cell.coordinate in in_cell else _format_cell(cell) for cell in row]
            for row in sheet.iter_rows()
        ]
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
        for data, content_type in in_cell.values():
            slots.append(Figure(data=data, content_type=content_type, page=number))
    return slots


def _xlsx_cell_images(path: str) -> Dict[str, Dict[str, Tuple[bytes, str]]]:
    import mimetypes
    import posixpath
    from xml.etree import ElementTree

    rid = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())

        def xml(name: str) -> Any:
            return ElementTree.fromstring(archive.read(name)) if name in names else None

        def rels(name: str) -> Mapping[str, str]:
            folder, base = posixpath.split(name)
            tree = xml(f"{folder}/_rels/{base}.rels")
            return {
                rel.get("Id"): posixpath.normpath(posixpath.join(folder, rel.get("Target"))).lstrip("/")
                for rel in ([] if tree is None else tree)
            }

        metadata = xml("xl/metadata.xml")
        values = xml("xl/richData/rdrichvalue.xml")
        structures = xml("xl/richData/rdrichvaluestructure.xml")
        rel_list = xml("xl/richData/richValueRel.xml")
        if any(part is None for part in (metadata, values, structures, rel_list)):
            return {}
        targets = rels("xl/richData/richValueRel.xml")
        images = [targets.get(rel.get(rid)) for rel in rel_list]
        positions = [
            next((i for i, key in enumerate(structure) if key.get("n") == "_rvRel:LocalImageIdentifier"), None)
            for structure in structures
        ]
        value_images = []
        for value in values:
            position = positions[int(value.get("s"))]
            value_images.append(None if position is None else images[int(value[position].text)])
        future = metadata.find("{*}futureMetadata[@name='XLRICHVALUE']")
        future = [int(block.find(".//{*}rvb").get("i")) for block in future]
        cell_values = [future[int(block.find("{*}rc").get("v"))] for block in metadata.find("{*}valueMetadata")]

        sheets = rels("xl/workbook.xml")
        found: Dict[str, Dict[str, Tuple[bytes, str]]] = {}
        for sheet in xml("xl/workbook.xml").iterfind(".//{*}sheet"):
            tree = xml(sheets.get(sheet.get(rid), ""))
            for cell in [] if tree is None else tree.iterfind(".//{*}c"):
                target = value_images[cell_values[int(cell.get("vm")) - 1]] if cell.get("vm") else None
                if target in names:
                    content_type = mimetypes.guess_type(target)[0] or "image/png"
                    found.setdefault(sheet.get("name"), {})[cell.get("r")] = (archive.read(target), content_type)
    return found


def _format_cell(cell: Any) -> Optional[str]:
    """A cell's value as displayed, with its number format applied."""
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
    """A chart's title text, or `""`."""
    try:
        title = chart.title
        if title is None:
            return ""
        if isinstance(title, str):
            return title
        runs = title.tx.rich.p[0].r  # CharacterProperties-wrapped rich text
        return "".join(run.t for run in runs if run.t).strip()
    except Exception:  # noqa: BLE001
        return ""


def _chart_image(workbook: Any, chart: Any) -> bytes:
    """An openpyxl chart re-plotted from its series data to a PNG, or `b""` if it cannot be rendered."""
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
            else:
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
    except Exception:  # noqa: BLE001
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


#: Tags that close an inline run: text accumulated inside one is a block.
_HTML_BLOCK_TAGS = frozenset({
    "p", "div", "section", "article", "header", "footer", "li", "blockquote",
    "h1", "h2", "h3", "h4", "h5", "h6", "pre", "td", "th", "tr", "figcaption",
})


def _walk_html(path: str) -> List[Slot]:
    """A DOM in document order: text runs, tables, and local/data-URI `<img>` with its caption."""
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
    if "://" in src:
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
