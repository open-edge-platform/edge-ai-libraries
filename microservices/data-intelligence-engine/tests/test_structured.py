# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""A structured file's pictures land between the paragraphs that talk about them.

docx/pptx/xlsx/html are born with their text, tables and images as typed nodes, so
a native walk produces the same `ContentBlock` stream a PDF does -- no render, no
layout model. The invariants under test: a picture becomes an IMAGE block whose
bytes went to the store (not the stream), a figure sits in reading order next to
its prose so `surrounding_text` can find it, a caption-styled line beside a figure
becomes its caption, and a file with no pictures is left to the plain-text reader.
"""

import base64
import os
import tempfile

import pytest

from core import extractor, structured
from core.content import IMAGE, ROLE_DOC_IMAGE, TABLE, TEXT, media_block


class FakeBlobWriter:
    """Stands in for the content store, and remembers write order (like test_extractor)."""

    def __init__(self):
        self.written = []

    def __call__(self, data, content_type=None):
        self.written.append((data, content_type))
        return f"blobs/{len(self.written)}"


def _tmp(name: str) -> str:
    return os.path.join(tempfile.mkdtemp(), name)


def _png_bytes() -> bytes:
    """A real 8x8 PNG -- the office parsers validate the stream, so a stub won't do."""
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (8, 8), (123, 200, 90)).save(buffer, format="PNG")
    return buffer.getvalue()


_PNG = _png_bytes()


# --- docx ---------------------------------------------------------------------


def _make_docx(path: str, with_image: bool = True) -> None:
    from docx import Document
    from docx.shared import Inches

    document = Document()
    document.add_paragraph("Intro paragraph about the system.")
    if with_image:
        img = _tmp("fig.png")
        with open(img, "wb") as handle:
            handle.write(_PNG)
        document.add_picture(img, width=Inches(1))
        document.add_paragraph("Figure 1: the thermal camera mount.")
    table = document.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "name"
    table.rows[0].cells[1].text = "value"
    table.rows[1].cells[0].text = "temp"
    table.rows[1].cells[1].text = "42"
    document.save(path)


def test_docx_interleaves_a_picture_between_its_paragraphs():
    path = _tmp("report.docx")
    _make_docx(path, with_image=True)
    writer = FakeBlobWriter()

    stream = extractor.extract(path, "a1", writer)
    kinds = [block.kind for block in stream.ordered()]

    assert IMAGE in kinds and TABLE in kinds
    image_at = kinds.index(IMAGE)
    # The picture sits between the intro text and the table, not appended at the end.
    assert TEXT in kinds[:image_at]
    assert kinds[image_at + 1:], "the picture is not the last block"
    # Bytes went to the store; only the key is in the stream.
    assert writer.written and writer.written[0][0] == _PNG
    assert _PNG not in repr(stream.to_record()).encode("utf-8", "ignore")


def test_docx_caption_line_becomes_the_figure_caption():
    path = _tmp("report.docx")
    _make_docx(path, with_image=True)

    stream = extractor.extract(path, "a1", FakeBlobWriter())
    image = next(b for b in stream.ordered() if b.kind == IMAGE)

    assert image.caption.startswith("Figure 1")
    assert image.metadata["role"] == ROLE_DOC_IMAGE
    assert media_block(stream) is None


def test_a_docx_with_no_pictures_takes_the_plain_text_reader():
    path = _tmp("notes.docx")
    _make_docx(path, with_image=False)

    assert structured.has_media(path) is False
    stream = extractor.extract(path, "a1", FakeBlobWriter())
    # No figures to place, so the fast reader handles it: text only.
    assert all(block.kind in (TEXT, TABLE) for block in stream.ordered())


# --- pptx ---------------------------------------------------------------------


def _make_pptx(path: str) -> None:
    from pptx import Presentation
    from pptx.util import Inches

    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[5])
    slide.shapes.title.text = "Teardown"
    img = _tmp("fig.png")
    with open(img, "wb") as handle:
        handle.write(_PNG)
    slide.shapes.add_picture(img, Inches(1), Inches(2), width=Inches(1))
    presentation.save(path)


def test_pptx_picture_becomes_an_image_block_on_its_slide():
    path = _tmp("deck.pptx")
    _make_pptx(path)
    writer = FakeBlobWriter()

    stream = extractor.extract(path, "a1", writer)
    images = [block for block in stream.ordered() if block.kind == IMAGE]

    assert len(images) == 1
    assert images[0].page == 1
    assert images[0].metadata["role"] == ROLE_DOC_IMAGE
    assert writer.written[0][0] == _PNG


# --- WMF/EMF ------------------------------------------------------------------


def _wmf_bytes() -> bytes:
    import struct
    from functools import reduce

    placeable = struct.pack("<IHhhhhHI", 0x9AC6CDD7, 0, 0, 0, 1440, 720, 1440, 0)
    placeable += struct.pack("<H", reduce(lambda a, b: a ^ b, struct.unpack("<10H", placeable)))
    records = struct.pack("<IHhhhh", 7, 0x041B, 600, 1200, 100, 100) + struct.pack("<IH", 3, 0)
    header = struct.pack("<HHHIHIH", 1, 9, 0x0300, (18 + len(records)) // 2, 0, 7, 0)
    return placeable + header + records


def _make_metafile_pptx(path: str) -> None:
    from io import BytesIO

    from pptx import Presentation
    from pptx.util import Inches

    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[5])
    slide.shapes.title.text = "Architecture"
    slide.shapes.add_picture(BytesIO(_wmf_bytes()), Inches(1), Inches(2))
    slide.shapes.add_picture(BytesIO(_PNG), Inches(5), Inches(2), width=Inches(1))
    presentation.save(path)


class _FakeSoffice:
    def __init__(self, command, **kwargs):
        from pathlib import Path

        from PIL import Image, ImageDraw

        outdir = Path(command[command.index("--outdir") + 1])
        outdir.mkdir()
        for source in command[command.index("--outdir") + 2:]:
            page = Image.new("RGB", (595, 842), "white")
            ImageDraw.Draw(page).rectangle([200, 300, 399, 399], fill="red")
            page.convert("P").save(outdir / f"{Path(source).stem}.pdf", resolution=72)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def wait(self, timeout=None):
        return 0


def test_metafile_suffix_detects_emf_and_wmf_only():
    emf = b"\x01\x00\x00\x00" + b"\x00" * 36 + b" EMF"

    assert structured._metafile_suffix(emf) == ".emf"
    assert structured._metafile_suffix(_wmf_bytes()) == ".wmf"
    assert structured._metafile_suffix(b"\x01\x00\x09\x00\x00\x03") == ".wmf"
    assert structured._metafile_suffix(_PNG) == ""


def test_metafile_without_libreoffice_is_dropped_and_the_rest_kept(monkeypatch):
    path = _tmp("deck.pptx")
    _make_metafile_pptx(path)
    monkeypatch.setattr(structured.shutil, "which", lambda name: None)
    writer = FakeBlobWriter()

    stream = extractor.extract(path, "a1", writer)

    assert [block.kind for block in stream.ordered()].count(IMAGE) == 1
    assert writer.written == [(_PNG, "image/png")]
    assert any("Architecture" in block.text for block in stream.ordered() if block.kind == TEXT)


def test_metafile_is_rendered_to_a_cropped_png(monkeypatch):
    from io import BytesIO

    from PIL import Image

    path = _tmp("deck.pptx")
    _make_metafile_pptx(path)
    monkeypatch.setattr(structured.shutil, "which", lambda name: "/usr/bin/soffice")
    monkeypatch.setattr(structured.subprocess, "Popen", _FakeSoffice)
    writer = FakeBlobWriter()

    stream = extractor.extract(path, "a1", writer)
    images = [block for block in stream.ordered() if block.kind == IMAGE]
    rendered = Image.open(BytesIO(writer.written[0][0]))

    assert [block.metadata["content_type"] for block in images] == ["image/png", "image/png"]
    assert rendered.format == "PNG"
    assert 1500 <= rendered.width <= 1650 and 750 <= rendered.height <= 850
    assert rendered.convert("RGB").getpixel((rendered.width // 2, rendered.height // 2)) == (255, 0, 0)


@pytest.mark.skipif(not structured.shutil.which("soffice"), reason="LibreOffice is not installed")
def test_metafile_is_rendered_by_libreoffice():
    from io import BytesIO

    from PIL import Image

    path = _tmp("deck.pptx")
    _make_metafile_pptx(path)
    writer = FakeBlobWriter()

    stream = extractor.extract(path, "a1", writer)

    assert [block.metadata["content_type"] for block in stream.ordered() if block.kind == IMAGE] == [
        "image/png", "image/png",
    ]
    assert Image.open(BytesIO(writer.written[0][0])).format == "PNG"


# --- xlsx ---------------------------------------------------------------------


def _make_xlsx(path: str) -> None:
    from openpyxl import Workbook
    from openpyxl.drawing.image import Image as XLImage

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Readings"
    sheet.append(["name", "value"])
    sheet.append(["temp", 42])
    img = _tmp("fig.png")
    with open(img, "wb") as handle:
        handle.write(_PNG)
    sheet.add_image(XLImage(img), "D2")
    workbook.save(path)


def test_xlsx_sheet_is_a_markdown_table_and_keeps_its_picture():
    path = _tmp("data.xlsx")
    _make_xlsx(path)

    stream = extractor.extract(path, "a1", FakeBlobWriter())
    kinds = [block.kind for block in stream.ordered()]
    table = next(block for block in stream.ordered() if block.kind == TABLE)

    assert IMAGE in kinds
    assert next(block for block in stream.blocks if block.kind == IMAGE).metadata["role"] == ROLE_DOC_IMAGE
    assert "| name | value |" in table.text
    assert "temp" in table.text


def _make_in_cell_image_xlsx(path: str) -> None:
    import zipfile

    from openpyxl import Workbook

    workbook = Workbook()
    workbook.active["A1"] = "photo"
    workbook.active["B2"] = "#VALUE!"
    workbook.save(path)
    rich = "http://schemas.microsoft.com/office/spreadsheetml/2017/richdata"
    parts = {
        "xl/metadata.xml": (
            f'<metadata xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:xlrd="{rich}">'
            '<futureMetadata name="XLRICHVALUE"><bk><extLst><ext><xlrd:rvb i="0"/></ext></extLst></bk></futureMetadata>'
            '<valueMetadata><bk><rc t="1" v="0"/></bk></valueMetadata></metadata>'
        ),
        "xl/richData/rdrichvalue.xml": f'<rvData xmlns="{rich}"><rv s="0"><v>0</v><v>5</v></rv></rvData>',
        "xl/richData/rdrichvaluestructure.xml": (
            f'<rvStructures xmlns="{rich}"><s t="_localImage">'
            '<k n="_rvRel:LocalImageIdentifier" t="i"/><k n="CalcOrigin" t="i"/></s></rvStructures>'
        ),
        "xl/richData/richValueRel.xml": (
            '<richValueRels xmlns="http://schemas.microsoft.com/office/spreadsheetml/2022/richvaluerel" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><rel r:id="rId1"/></richValueRels>'
        ),
        "xl/richData/_rels/richValueRel.xml.rels": (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
            'Target="../media/image1.png"/></Relationships>'
        ),
        "xl/media/image1.png": _PNG,
    }
    with zipfile.ZipFile(path) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    files["xl/worksheets/sheet1.xml"] = files["xl/worksheets/sheet1.xml"].replace(b'r="B2"', b'r="B2" vm="1"')
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in {**files, **parts}.items():
            archive.writestr(name, data)


def test_xlsx_picture_placed_in_a_cell_becomes_an_image_block():
    path = _tmp("in_cell.xlsx")
    _make_in_cell_image_xlsx(path)
    writer = FakeBlobWriter()

    stream = extractor.extract(path, "a1", writer)
    table = next(block for block in stream.ordered() if block.kind == TABLE)

    assert [block.kind for block in stream.ordered()].count(IMAGE) == 1
    assert writer.written == [(_PNG, "image/png")]
    assert "photo" in table.text and "#VALUE!" not in table.text


# --- html ---------------------------------------------------------------------


def _make_html(path: str, embed: bool = True) -> None:
    data_uri = "data:image/png;base64," + base64.b64encode(_PNG).decode()
    src = data_uri if embed else "https://example.com/remote.png"
    html = f"""<html><body>
      <h1>Thermal teardown</h1>
      <p>The mount is shown below.</p>
      <figure><img src="{src}" alt="camera mount"/><figcaption>Figure 2</figcaption></figure>
      <table><tr><th>name</th><th>value</th></tr><tr><td>temp</td><td>42</td></tr></table>
    </body></html>"""
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(html)


def test_html_embedded_image_lands_in_order_with_its_alt_caption():
    path = _tmp("page.html")
    _make_html(path, embed=True)

    stream = extractor.extract(path, "a1", FakeBlobWriter())
    ordered = stream.ordered()
    kinds = [block.kind for block in ordered]
    image = next(block for block in ordered if block.kind == IMAGE)

    assert kinds.count(IMAGE) == 1
    assert image.caption == "camera mount"  # alt wins over figcaption
    assert image.metadata["role"] == ROLE_DOC_IMAGE
    # Picture is between the intro prose and the table.
    image_at = kinds.index(IMAGE)
    assert TEXT in kinds[:image_at] and TABLE in kinds[image_at + 1:]


def test_html_remote_image_is_not_fetched():
    path = _tmp("page.html")
    _make_html(path, embed=False)

    # has_media sees the <img> tag, so the walk runs, but a remote src yields no
    # bytes, so no IMAGE block and no blob write.
    writer = FakeBlobWriter()
    stream = extractor.extract(path, "a1", writer)

    assert not any(block.kind == IMAGE for block in stream.ordered())
    assert writer.written == []


# --- OMML -> LaTeX (docx formulas) --------------------------------------------

_M = "http://schemas.openxmlformats.org/officeDocument/2006/math"


def _omath(inner_xml: str):
    """Parse an `<m:oMath>` fragment into an lxml element for the converter."""
    from lxml import etree

    xml = f'<m:oMath xmlns:m="{_M}">{inner_xml}</m:oMath>'
    return etree.fromstring(xml.encode("utf-8"))


def _run(text: str) -> str:
    return f"<m:r><m:t>{text}</m:t></m:r>"


def test_omml_superscript_becomes_latex():
    element = _omath(f"<m:sSup><m:e>{_run('x')}</m:e><m:sup>{_run('2')}</m:sup></m:sSup>")
    assert structured._omml_to_latex(element) == "{x}^{2}"


def test_omml_fraction_becomes_latex():
    element = _omath(f"<m:f><m:num>{_run('a')}</m:num><m:den>{_run('b')}</m:den></m:f>")
    assert structured._omml_to_latex(element) == r"\frac{a}{b}"


def test_omml_nary_sum_keeps_its_limits():
    element = _omath(
        '<m:nary><m:naryPr><m:chr m:val="∑"/></m:naryPr>'
        f"<m:sub>{_run('i')}</m:sub><m:sup>{_run('n')}</m:sup>"
        f"<m:e>{_run('i')}</m:e></m:nary>"
    )
    assert structured._omml_to_latex(element) == r"\sum_{i}^{n}{i}"


def test_omml_radical_defaults_to_sqrt():
    element = _omath(f"<m:rad><m:deg/><m:e>{_run('x')}</m:e></m:rad>")
    assert structured._omml_to_latex(element) == r"\sqrt{x}"


def test_a_paragraph_wraps_each_formula_in_inline_math():
    from lxml import etree

    xml = (
        f'<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        f'xmlns:m="{_M}"><m:oMath><m:f><m:num>{_run("a")}</m:num>'
        f'<m:den>{_run("b")}</m:den></m:f></m:oMath></w:p>'
    )
    paragraph = etree.fromstring(xml.encode("utf-8"))
    assert structured._omml_paragraph_latex(paragraph) == r"$\frac{a}{b}$"


# --- xlsx: number-format display values ---------------------------------------


def _make_xlsx_formats(path: str) -> None:
    import datetime

    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["ratio", "when", "count"])
    sheet["A2"] = 0.05
    sheet["A2"].number_format = "0%"
    sheet["B2"] = datetime.datetime(2023, 3, 15)
    sheet["B2"].number_format = "yyyy-mm-dd"
    sheet["C2"] = 42.0
    workbook.save(path)


def test_xlsx_renders_percent_and_date_as_displayed():
    path = _tmp("fmt.xlsx")
    _make_xlsx_formats(path)

    stream = extractor.extract(path, "a1", FakeBlobWriter()) if structured.has_media(path) \
        else structured.extract_structured(path, "a1", FakeBlobWriter())
    table = next(block for block in stream.ordered() if block.kind == TABLE)

    assert "5%" in table.text
    assert "2023-03-15" in table.text
    assert "42" in table.text and "42.0" not in table.text  # integer-valued float trimmed


# --- xlsx: chart rasterization ------------------------------------------------


def test_xlsx_chart_is_rasterized_to_a_png_figure():
    from openpyxl import Workbook
    from openpyxl.chart import BarChart, Reference

    path = _tmp("chart.xlsx")
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["month", "sales"])
    for month, sales in enumerate([10, 40, 25, 60], start=1):
        sheet.append([month, sales])
    chart = BarChart()
    chart.title = "Sales"
    chart.add_data(Reference(sheet, min_col=2, min_row=1, max_row=5), titles_from_data=True)
    sheet.add_chart(chart, "E2")
    workbook.save(path)

    # A chart-only workbook has nothing under xl/media/; it must still be routed
    # to the structured walk, or the chart is never rasterized.
    assert structured.has_media(path)
    stream = structured.extract_structured(path, "a1", FakeBlobWriter())
    charts = [block for block in stream.ordered()
              if block.kind == IMAGE and block.metadata.get("type") == "chart"]

    assert len(charts) == 1
    assert charts[0].caption == "Sales"
    assert charts[0].metadata["role"] == ROLE_DOC_IMAGE
    # The figure's bytes went to the store; the block holds only the key.
    assert charts[0].media_key
