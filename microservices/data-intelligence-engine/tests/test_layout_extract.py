# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""The layout path: a PDF becomes text and figure blocks via model + OCR + pairing.

The layout model, OCR and PDF renderer are heavy and not present in CI, so the
chain is exercised through its injectable seams -- a fake renderer, a fake
detector returning `LayoutBlock`s, and a fake OCR -- with a real blob writer
double. What is pinned here is the extractor's own work: cropping detected
regions, storing a figure's bytes and keeping only the key, pairing a figure with
the prose that references it, and emitting blocks in reading order.
"""

from core import extractor
from core.content import IMAGE, TABLE, TEXT, ContentStream
from core.fused import extract_caption_keys, reference_text_for
from core.layout import LayoutBlock
from core.ocr import OCR
from PIL import Image


class FakeBlobWriter:
    def __init__(self):
        self.written = []

    def __call__(self, data, content_type=None):
        self.written.append((data, content_type))
        return f"blobs/{len(self.written)}"


class FakeDetector:
    """Returns pre-canned blocks per page, ignoring the pixels."""

    def __init__(self, per_page):
        self._per_page = per_page

    def detect(self, images):
        assert len(images) == len(self._per_page)
        return self._per_page


def _queue_ocr(texts):
    """A bare image->str OCR that returns the given texts in call order."""
    iterator = iter(texts)

    def read(_image):
        return next(iterator)

    return read


# --- fused pairing (pure) -----------------------------------------------------


def test_caption_keys_are_normalized_across_spacing():
    assert extract_caption_keys("see Figure 3 for details") == ["fig 3"]
    # `Fig` and its number are joined; `Table10` is split so it still matches
    # `table 10`. The digit-letter split also drops a `2a` suffix down to `2`
    # (ported from mmdir) -- fine, since image and text are normalized alike.
    assert extract_caption_keys("Fig 3") == ["fig 3"]
    assert extract_caption_keys("Table10 and table 10") == ["table 10"]
    assert extract_caption_keys("Fig.2a") == ["fig 2"]
    assert extract_caption_keys("如图1所示，详见表 2。") == ["fig 1", "table 2"]
    assert extract_caption_keys("no captions here") == []


def test_reference_text_prefers_a_matching_caption_key_over_proximity():
    image = {"bbox": (0, 0, 10, 10), "page": 1, "text": "Figure 2"}
    near = {"bbox": (0, 11, 10, 20), "page": 1, "text": "unrelated prose"}
    keyed = {"bbox": (0, 500, 10, 510), "page": 1, "text": "Figure 2: the setup"}

    assert reference_text_for(image, [near, keyed], [near, keyed]) == "Figure 2: the setup"


def test_reference_text_keeps_every_matching_line_from_each_layout():
    """`line` mode: every caption-key-bearing sentence of each matched layout,
    nearest layout first, joined by newlines -- not just the single best line."""
    image = {"bbox": (0, 0, 10, 10), "page": 1, "text": "Figure 2 and Table 3"}
    nearer = {
        "bbox": (0, 20, 10, 30),
        "page": 1,
        "text": "Unrelated introduction\nFigure 2 shows the setup.\nUnrelated conclusion",
    }
    farther = {
        "bbox": (0, 40, 10, 50),
        "page": 1,
        "text": "Table 3 lists results.\nFigure 2 and Table 3 summarize the evaluation.",
    }

    # nearer contributes its one key-bearing line; farther contributes both of its
    # lines (each matches a key), in reading order, after it.
    assert reference_text_for(image, [farther, nearer], [farther, nearer]) == (
        "Figure 2 shows the setup.\n"
        "Table 3 lists results.\n"
        "Figure 2 and Table 3 summarize the evaluation."
    )


def test_reference_text_falls_back_to_no_relevant_texts():
    image = {"bbox": (0, 0, 10, 10), "page": 2, "text": "just pixels"}
    assert reference_text_for(image, [], []) == "(no relevant texts)"


def test_reference_text_falls_back_to_page_chinese_captions_nearest_first():
    """With no caption key on the image, the fallback keeps every caption-like line
    on the page (a number is required to look like a caption), ordered nearest first."""
    image = {"bbox": (0, 100, 100, 200), "page": 1, "text": "pixel labels"}
    nearest = {"bbox": (20, 205, 80, 220), "page": 1, "text": "图 1 总流程图"}
    farther = {"bbox": (20, 500, 80, 520), "page": 1, "text": "表 2 数据集统计"}

    assert reference_text_for(image, [farther, nearest], [farther, nearest]) == (
        "图 1 总流程图\n表 2 数据集统计"
    )


# --- extract_layout end to end ------------------------------------------------


def _run_two_page_pdf(writer):
    pages = [Image.new("RGB", (100, 200), "white"), Image.new("RGB", (100, 100), "white")]
    detector = FakeDetector(
        [
            [
                LayoutBlock(bbox=(10, 10, 90, 40), label="text", score=0.9, raw_label="text"),
                LayoutBlock(bbox=(10, 50, 90, 150), label="image", score=0.9, raw_label="image"),
            ],
            [
                LayoutBlock(bbox=(10, 10, 90, 90), label="table", score=0.9, raw_label="table"),
            ],
        ]
    )
    ocr = _queue_ocr(
        ["Figure 1 shows the results.", "Figure 1", "Table data"]
    )
    return extractor.extract_layout(
        "/w/report.pdf",
        "asset-1",
        writer,
        detector=detector,
        ocr=ocr,
        render=lambda path, dpi: pages,
    )


def test_layout_emits_text_and_figure_blocks_in_reading_order():
    stream = _run_two_page_pdf(FakeBlobWriter())

    assert [block.kind for block in stream.blocks] == [TEXT, IMAGE, IMAGE]
    assert [block.reading_order for block in stream.blocks] == [0, 1, 2]
    assert [block.page for block in stream.blocks] == [1, 1, 2]
    # The page's text regions merge into one block typed "page"; figures keep theirs.
    assert [block.metadata["type"] for block in stream.blocks] == ["page", "image", "table"]


def test_a_text_region_becomes_a_text_block_with_its_ocr():
    stream = _run_two_page_pdf(FakeBlobWriter())
    text_block = stream.blocks[0]
    assert text_block.kind == TEXT
    assert text_block.text == "Figure 1 shows the results."


def test_a_pages_text_regions_merge_into_one_block_before_its_figures():
    """A scanned page's text regions join into a single TEXT block (matching the
    digital path), with that page's figures following it, so one page is one text
    chunk rather than one per layout region."""
    page = Image.new("RGB", (100, 300), "white")
    detector = FakeDetector(
        [[
            LayoutBlock((10, 10, 90, 40), "text", 0.9, "text"),    # first paragraph
            LayoutBlock((10, 50, 90, 150), "image", 0.9, "image"),  # a figure between them
            LayoutBlock((10, 160, 90, 190), "text", 0.9, "text"),  # second paragraph
        ]]
    )
    ocr = _queue_ocr(["First paragraph.", "Figure 1", "Second paragraph."])
    stream = extractor.extract_layout(
        "/w/report.pdf", "asset-1", FakeBlobWriter(),
        detector=detector, ocr=ocr,
        render=lambda path, dpi: [page],
    )
    assert [block.kind for block in stream.blocks] == [TEXT, IMAGE]
    # Both text regions merged, in reading order, into the one page block.
    assert stream.blocks[0].text == "First paragraph.\n\nSecond paragraph."
    assert stream.blocks[0].metadata["type"] == "page"
    # The merged text block carries no bbox -- citation falls back to the page.
    assert stream.blocks[0].bbox == ()
    assert stream.blocks[0].page == 1
    # The text block sorts before the page's figure.
    assert stream.blocks[0].reading_order < stream.blocks[1].reading_order


def test_a_figure_is_paired_with_the_prose_that_references_it():
    stream = _run_two_page_pdf(FakeBlobWriter())
    figure = stream.blocks[1]
    assert figure.kind == IMAGE
    # OCR of the figure said "Figure 1"; the text block carries the same key.
    assert figure.caption == "Figure 1 shows the results."


def test_a_table_becomes_an_image_block_even_with_no_reference():
    stream = _run_two_page_pdf(FakeBlobWriter())
    table = stream.blocks[2]
    assert table.kind == IMAGE
    assert table.metadata["type"] == "table"
    assert table.caption == "(no relevant texts)"


def test_a_figures_bytes_go_to_the_store_and_only_the_key_is_kept():
    writer = FakeBlobWriter()
    stream = _run_two_page_pdf(writer)

    # Two visual regions (image + table) were stored; the text region was not.
    assert len(writer.written) == 2
    assert all(content_type == "image/jpeg" for _, content_type in writer.written)
    figure = stream.blocks[1]
    assert figure.media_key == "blobs/1"
    assert figure.metadata["content_type"] == "image/jpeg"
    assert figure.metadata["byte_size"] > 0
    # The pixels are in the store, not the stream record.
    assert "byte_size" in figure.metadata and figure.text == ""


def test_stream_metadata_carries_provenance():
    stream = _run_two_page_pdf(FakeBlobWriter())
    assert stream.metadata["file_name"] == "report.pdf"
    assert stream.metadata["file_path"].endswith("/w/report.pdf")
    assert stream.metadata["asset_id"] == "asset-1"


def test_layout_tells_ocr_which_regions_are_visual():
    class ContextOCR(OCR):
        def __init__(self):
            self.contexts = []

        def read(self, image, context=None):
            del image
            self.contexts.append(context)
            return "text"

    engine = ContextOCR()
    extractor.extract_layout(
        "/w/report.pdf",
        "asset-1",
        FakeBlobWriter(),
        detector=FakeDetector(
            [[
                LayoutBlock((0, 0, 50, 50), "text", 0.9, "text"),
                LayoutBlock((50, 0, 100, 50), "image", 0.9, "image"),
            ]]
        ),
        ocr=engine,
        render=lambda path, dpi: [Image.new("RGB", (100, 100), "white")],
    )

    assert [context["visual"] for context in engine.contexts] == [False, True]
    assert [context["layout_type"] for context in engine.contexts] == ["text", "image"]


# --- the digital path: a PDF with a text layer (paths 1 + 2) ------------------
#
# A digital PDF never OCRs its prose: path 1 reads the page text and tables from
# the text layer; path 2 finds figures and missed tables and OCRs equations.
# The text layer is a seam too, so the whole chain runs here with no pdfplumber --
# `FakeTextLayer` returns canned page text, pairing candidates and per-region
# text, keyed by the clamped detection box.


class FakeTextLayer:
    """A stand-in for `_PdfTextLayer`, driven entirely by canned data."""

    def __init__(self, pages_text, candidates=None, region_texts=None):
        self._pages_text = list(pages_text)
        self._candidates = (
            candidates if candidates is not None else [[] for _ in pages_text]
        )
        self._region_texts = dict(region_texts or {})
        self.closed = False

    def page_count(self):
        return len(self._pages_text)

    def page_text(self, index):
        return self._pages_text[index]

    def candidates(self, index):
        return self._candidates[index]

    def region_text(self, index, pixel_bbox):
        return self._region_texts.get(tuple(pixel_bbox), "")

    def close(self):
        self.closed = True


# --- routing: get the text layer, then pick a path ----------------------------


def test_a_scanned_pdf_with_no_text_layer_goes_to_full_ocr():
    """No extractable text anywhere -> path 3 (`extract_layout`), OCR every region."""
    calls = []
    original = extractor.extract_layout
    extractor.extract_layout = lambda *a, **k: calls.append(a) or ContentStream("a1")
    try:
        layer = FakeTextLayer(["", ""])  # a scan: no page yields text
        extractor.extract_pdf("/w/report.pdf", "a1", FakeBlobWriter(), text_layer=layer)
    finally:
        extractor.extract_layout = original
    assert calls, "scanned PDF should route to extract_layout (path 3)"
    assert layer.closed


def test_a_digital_pdf_is_read_through_its_text_layer_not_full_ocr():
    called = []
    original = extractor.extract_layout
    extractor.extract_layout = lambda *a, **k: called.append("path3") or ContentStream("a1")
    try:
        layer = FakeTextLayer(["hello world"])
        stream = extractor.extract_pdf(
            "/w/report.pdf",
            "a1",
            FakeBlobWriter(),
            text_layer=layer,
            detector=FakeDetector([[]]),
            render=lambda path, dpi: [Image.new("RGB", (100, 100), "white")],
            read_text=lambda path: {0: "hello world"},
        )
    finally:
        extractor.extract_layout = original
    assert called == [], "a digital PDF must not fall into the full-OCR path"
    assert [block.kind for block in stream.blocks] == [TEXT]
    assert stream.blocks[0].text == "hello world"
    assert layer.closed


def test_pdf_has_text_layer_is_decided_by_extractable_text_not_fonts():
    assert extractor.pdf_has_text_layer(FakeTextLayer(["", "  ", "real text"]))
    assert not extractor.pdf_has_text_layer(FakeTextLayer(["", "   ", ""]))


# --- path 1 ∥ path 2 on a digital page ----------------------------------------


def test_digital_pdf_takes_text_from_the_reader_and_figures_from_detection():
    writer = FakeBlobWriter()
    page = Image.new("RGB", (100, 200), "white")
    detector = FakeDetector(
        [[
            LayoutBlock((10, 10, 90, 40), "text", 0.9, "text"),  # owned by path 1
            LayoutBlock((10, 50, 90, 150), "image", 0.9, "image"),  # path 2 figure
        ]]
    )
    layer = FakeTextLayer(
        pages_text=["Body text. See Figure 1."],
        candidates=[[{"bbox": (10, 10, 90, 40), "page": 1, "text": "Figure 1 shows the setup."}]],
        region_texts={(10, 50, 90, 150): "Figure 1"},
    )
    stream = extractor.extract_layout_digital(
        "/w/report.pdf",
        "asset-1",
        writer,
        text_layer=layer,
        detector=detector,
        render=lambda path, dpi: [page],
        read_text=lambda path: {0: "Body text. See Figure 1."},
    )
    assert [block.kind for block in stream.blocks] == [TEXT, IMAGE]
    assert stream.blocks[0].text == "Body text. See Figure 1."
    figure = stream.blocks[1]
    assert figure.media_key == "blobs/1"
    assert figure.caption == "Figure 1 shows the setup."  # paired from the text layer
    assert figure.metadata["type"] == "image"
    # The detected text region is not re-emitted; one TEXT block only.
    assert sum(block.kind == TEXT for block in stream.blocks) == 1
    # Reading order is a page/lane/position key, so text sorts before its figure
    # and the two blocks get distinct ids (the exact integers are not contractual).
    assert stream.blocks[0].reading_order < stream.blocks[1].reading_order
    assert len({block.block_id for block in stream.blocks}) == 2


def test_a_formula_is_left_to_the_fast_text_path():
    writer = FakeBlobWriter()
    page = Image.new("RGB", (100, 200), "white")
    detector = FakeDetector([[LayoutBlock((10, 60, 90, 100), "equation", 0.9, "formula")]])
    layer = FakeTextLayer(
        pages_text=["Energy is defined by Equation 1 below."],
        candidates=[[{"bbox": (10, 10, 90, 50), "page": 1, "text": "Equation 1 defines energy."}]],
        region_texts={(10, 60, 90, 100): "E=mc^2 公式(1)"},
    )
    stream = extractor.extract_layout_digital(
        "/w/report.pdf",
        "asset-1",
        writer,
        text_layer=layer,
        detector=detector,
        render=lambda path, dpi: [page],
        read_text=lambda path: {0: "Energy is defined by Equation 1 below."},
    )
    assert [block.kind for block in stream.blocks] == [TEXT]
    assert stream.blocks[0].text == "Energy is defined by Equation 1 below."
    assert writer.written == []


def test_a_text_region_without_local_text_is_left_to_the_fast_text_path():
    """A digital PDF's slow path never OCRs individual text regions."""
    writer = FakeBlobWriter()
    page = Image.new("RGB", (100, 200), "white")
    detector = FakeDetector([[LayoutBlock((10, 60, 90, 120), "text", 0.9, "text")]])
    layer = FakeTextLayer(
        pages_text=["Header only."],
        candidates=[[]],
        region_texts={(10, 60, 90, 120): ""},  # empty in the layer -> OCR this box
    )
    stream = extractor.extract_layout_digital(
        "/w/report.pdf",
        "asset-1",
        writer,
        text_layer=layer,
        detector=detector,
        render=lambda path, dpi: [page],
        read_text=lambda path: {0: "Header only."},
    )
    texts = [block.text for block in stream.blocks if block.kind == TEXT]
    assert texts == ["Header only."]


# --- tables belong entirely to the fast text path ----------------------------


def test_a_detected_table_is_left_in_page_text_not_re_emitted():
    """A digital table's cells already sit in the page text, so it is neither a
    separate TABLE block (would be a duplicate chunk) nor a path-2 image."""
    writer = FakeBlobWriter()
    page = Image.new("RGB", (100, 200), "white")
    detector = FakeDetector([[LayoutBlock((10, 60, 90, 120), "table", 0.9, "table")]])
    layer = FakeTextLayer(pages_text=["Doc text."], candidates=[[]], region_texts={})
    stream = extractor.extract_layout_digital(
        "/w/report.pdf",
        "asset-1",
        writer,
        text_layer=layer,
        detector=detector,
        render=lambda path, dpi: [page],
        read_text=lambda path: {0: "Doc text.\nh1 h2 a b"},
    )
    # The only block is the page text; no standalone TABLE, no fused image.
    assert [block.kind for block in stream.blocks] == [TEXT]
    assert not any(block.kind == TABLE for block in stream.blocks)
    assert not any(block.kind == IMAGE for block in stream.blocks)
    # path 2 treats the detected region as a duplicate, so no pixels are stored.
    assert writer.written == []


def test_a_detected_table_never_falls_back_to_a_fused_image():
    """A digital PDF assumes every table is already represented in page text."""
    writer = FakeBlobWriter()
    page = Image.new("RGB", (100, 200), "white")
    detector = FakeDetector([[LayoutBlock((10, 60, 90, 120), "table", 0.9, "table")]])
    layer = FakeTextLayer(
        pages_text=["Doc text."], candidates=[[]], region_texts={(10, 60, 90, 120): ""}
    )
    stream = extractor.extract_layout_digital(
        "/w/report.pdf",
        "asset-1",
        writer,
        text_layer=layer,
        detector=detector,
        render=lambda path, dpi: [page],
        read_text=lambda path: {0: "Doc text.\nh1 h2 a b"},
    )
    assert [block.kind for block in stream.blocks] == [TEXT]
    assert writer.written == []


# --- vector quality and resilience --------------------------------------------


def test_an_unreferenced_figure_keeps_an_empty_caption_not_the_sentinel():
    """The `(no relevant texts)` sentinel must not be fused into an image vector."""
    writer = FakeBlobWriter()
    page = Image.new("RGB", (100, 200), "white")
    detector = FakeDetector([[LayoutBlock((10, 50, 90, 150), "image", 0.9, "image")]])
    layer = FakeTextLayer(
        pages_text=["Unrelated prose."], candidates=[[]], region_texts={(10, 50, 90, 150): ""}
    )
    stream = extractor.extract_layout_digital(
        "/w/report.pdf",
        "asset-1",
        writer,
        text_layer=layer,
        detector=detector,
        render=lambda path, dpi: [page],
        read_text=lambda path: {0: "Unrelated prose."},
    )
    figure = next(block for block in stream.blocks if block.kind == IMAGE)
    assert figure.caption == ""


def test_a_layout_failure_degrades_to_the_text_only_path():
    """A detect/render failure keeps all page text rather than losing the document."""

    class BoomDetector:
        def detect(self, images):
            raise RuntimeError("boom")

    writer = FakeBlobWriter()
    layer = FakeTextLayer(pages_text=["Page one text.", "Page two text."], candidates=[[], []])
    stream = extractor.extract_layout_digital(
        "/w/report.pdf",
        "asset-1",
        writer,
        text_layer=layer,
        detector=BoomDetector(),
        render=lambda path, dpi: [Image.new("RGB", (100, 100), "white")] * 2,
        read_text=lambda path: {0: "Page one text.", 1: "Page two text."},
    )
    assert [block.kind for block in stream.blocks] == [TEXT, TEXT]
    assert [block.text for block in stream.blocks] == ["Page one text.", "Page two text."]
    assert writer.written == []


# --- Chinese / formula caption keys -------------------------------------------


def test_digital_blocks_split_into_a_fast_text_half_and_a_slow_visual_half():
    """The two halves the two-phase materializer runs separately: path-1 text
    (fast, no render) and path-2 visuals (slow). Together they equal the full path."""
    layer = FakeTextLayer(
        pages_text=["Body text."],
        candidates=[[]],
        region_texts={(10, 50, 90, 150): ""},
    )
    text_blocks = extractor.digital_text_blocks(
        "/w/report.pdf", "a1", text_layer=layer,
        read_text=lambda path: {0: "Body text."},
    )
    assert [block.kind for block in text_blocks] == [TEXT]

    writer = FakeBlobWriter()
    page = Image.new("RGB", (100, 200), "white")
    detector = FakeDetector([[LayoutBlock((10, 50, 90, 150), "image", 0.9, "image")]])
    visual_blocks = extractor.digital_visual_blocks(
        "/w/report.pdf", "a1", writer, text_layer=layer,
        detector=detector, render=lambda path, dpi: [page],
    )
    assert [block.kind for block in visual_blocks] == [IMAGE]
    assert len(writer.written) == 1
    # Independent numbering, no collision when merged (text sorts before its figure).
    ids = {block.block_id for block in text_blocks + visual_blocks}
    assert len(ids) == 2
    assert min(b.reading_order for b in visual_blocks) > max(
        b.reading_order for b in text_blocks
    )


# --- #5 caption-key fallback: re-read a box extended downward ------------------
#
# A figure's own text often lacks its caption key -- the `Figure N` line sits just
# below the detected box. When so, the extractor re-reads a box extended downward
# and adopts that text if it recovers a key, so keyed pairing can beat the nearest
# caption-like line. Only the text-reading box grows; the stored crop is unchanged.


class _BboxOCR(OCR):
    """OCR that answers by the region's clamped box, so a retry on a taller box
    can return different text from the original crop."""

    def __init__(self, by_bbox):
        self._by_bbox = dict(by_bbox)

    def read(self, image, context=None):
        del image
        box = tuple((context or {}).get("bbox") or ())
        return self._by_bbox.get(box, "")


def _fallback_scene_detector():
    """A page with a decoy caption above the figure and the real caption below it."""
    return FakeDetector(
        [[
            LayoutBlock((10, 42, 90, 49), "text", 0.9, "text"),    # nearer decoy
            LayoutBlock((10, 50, 90, 150), "image", 0.9, "image"),  # the figure
            LayoutBlock((10, 152, 90, 178), "text", 0.9, "text"),  # real caption below
        ]]
    )


def _fallback_ocr():
    return _BboxOCR({
        (10, 42, 90, 49): "Figure 9 unrelated",
        (10, 50, 90, 150): "",                       # figure crop: no key
        (10, 152, 90, 178): "Figure 1 shows the setup.",
        (10, 50, 90, 180): "Figure 1",               # extended box: recovers the key
    })


def test_scanned_caption_fallback_recovers_the_key_for_keyed_pairing():
    stream = extractor.extract_layout(
        "/w/report.pdf", "asset-1", FakeBlobWriter(),
        detector=_fallback_scene_detector(), ocr=_fallback_ocr(),
        render=lambda path, dpi: [Image.new("RGB", (100, 200), "white")],
        caption_fallback_extend_ratio=0.3,
    )
    figure = next(block for block in stream.blocks if block.kind == IMAGE)
    # The extended re-read gave the figure `fig 1`, so pairing picks the matching
    # caption only -- not the nearer `Figure 9` decoy.
    assert figure.caption == "Figure 1 shows the setup."


def test_scanned_caption_fallback_is_off_when_ratio_is_zero():
    stream = extractor.extract_layout(
        "/w/report.pdf", "asset-1", FakeBlobWriter(),
        detector=_fallback_scene_detector(), ocr=_fallback_ocr(),
        render=lambda path, dpi: [Image.new("RGB", (100, 200), "white")],
        caption_fallback_extend_ratio=0.0,
    )
    figure = next(block for block in stream.blocks if block.kind == IMAGE)
    # No key recovered -> the keyless path keeps every caption-like line, decoy included.
    assert "Figure 9 unrelated" in figure.caption


def test_digital_caption_fallback_recovers_the_key_from_the_text_layer():
    page = Image.new("RGB", (100, 200), "white")
    detector = FakeDetector([[LayoutBlock((10, 50, 90, 150), "image", 0.9, "image")]])
    layer = FakeTextLayer(
        pages_text=["Body."],
        candidates=[[
            {"bbox": (10, 42, 90, 49), "page": 1, "text": "Figure 9 unrelated"},
            {"bbox": (10, 152, 90, 178), "page": 1, "text": "Figure 1 shows the setup."},
        ]],
        region_texts={(10, 50, 90, 150): "", (10, 50, 90, 180): "Figure 1"},
    )
    blocks = extractor.digital_visual_blocks(
        "/w/report.pdf", "a1", FakeBlobWriter(), text_layer=layer,
        detector=detector, render=lambda path, dpi: [page],
        caption_fallback_extend_ratio=0.3,
    )
    figure = next(block for block in blocks if block.kind == IMAGE)
    assert figure.caption == "Figure 1 shows the setup."


def test_caption_keys_match_equations_across_spellings():
    assert extract_caption_keys("Equation 1") == ["eq 1"]
    assert extract_caption_keys("公式(1)") == ["eq 1"]
    assert extract_caption_keys("公式（1）") == ["eq 1"]  # full-width brackets
    assert extract_caption_keys("see formula2") == ["eq 2"]
    assert extract_caption_keys("Equation 1") == extract_caption_keys("公式 1")
    # `式` alone is a common word ("方式"), so it must not be read as a formula.
    assert extract_caption_keys("有多种方式2") == []
