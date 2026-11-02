# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Any file becomes one content stream, and its bytes go to the store first.

A report, a spreadsheet and a recording all arrive as a path and leave as
blocks in reading order, so nothing downstream has to know which it was. The
one thing an extractor may not do is put bytes in the stream: a figure's pixels
go to the object store and the block keeps the key, which is also why the blob
is written before the record that names it.
"""

import os
import tempfile

import pytest

from core import extractor
from core.content import IMAGE, ROLE_DOC_IMAGE, TEXT, VIDEO, ContentBlock, ContentStream, media_block
from core.layout import LayoutBlock
from llama_index.core.schema import Document


class FakeBlobWriter:
    """Stands in for the library's content store, and remembers the order."""

    def __init__(self):
        self.written = []

    def __call__(self, data, content_type=None):
        self.written.append((data, content_type))
        return f"blobs/{len(self.written)}"


def _file(name: str, data: bytes = b"\x89PNG\r\n") -> str:
    path = os.path.join(tempfile.mkdtemp(), name)
    with open(path, "wb") as handle:
        handle.write(data)
    return path


# --- which extractor runs -----------------------------------------------------


def test_media_is_recognized_by_mime_type_not_by_a_flag_on_the_request():
    assert extractor.media_kind("/w/clip.mp4") == VIDEO
    assert extractor.media_kind("/w/figure.png") == IMAGE
    assert extractor.media_kind("/w/report.pdf") == ""


def test_only_reader_documents_and_media_files_are_supported():
    for path in ("/w/report.pdf", "/w/sheet.XLSX", "/w/page.htm", "/w/figure.png", "/w/clip.mp4"):
        assert extractor.is_supported(path), path
    for path in ("/w/legacy.doc", "/w/slides.ppt", "/w/book.epub", "/w/archive.zip", "/w/noext"):
        assert not extractor.is_supported(path), path


def test_the_reader_refuses_a_file_it_would_misread():
    # SimpleDirectoryReader ignores `required_exts` for a file it is handed and
    # would read a binary .doc as text, so the loader checks the type itself.
    from core.loader import file_to_documents

    with pytest.raises(ValueError, match="Unsupported file type '.doc'"):
        file_to_documents(_file("legacy.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"))


def test_a_text_file_goes_through_the_reader(monkeypatch):
    path = _file("a.txt", b"hello")
    monkeypatch.setattr(
        extractor, "file_to_documents", lambda _: [Document(text="hello", id_="d")]
    )

    stream = extractor.extract(path, "a1", FakeBlobWriter())

    assert [block.kind for block in stream.blocks] == [TEXT]
    assert stream.text() == "hello"


# --- a media file is a file like any other ------------------------------------


def test_a_media_file_is_one_binary_block_with_no_text():
    path = _file("clip.mp4")
    writer = FakeBlobWriter()

    stream = extractor.extract(path, "a1", writer)

    assert len(stream.blocks) == 1
    block = stream.blocks[0]
    assert block.kind == VIDEO
    assert block.text == "", "there is no text in a video"
    assert stream.text() == ""


def test_a_media_file_is_not_copied_its_block_points_at_the_file_itself():
    path = _file("clip.mp4", b"\x00\x01\x02")
    writer = FakeBlobWriter()

    stream = extractor.extract(path, "a1", writer)

    assert writer.written == [], "the file is the asset, so there is nothing to store"
    assert stream.blocks[0].media_key == f"file://{os.path.abspath(path)}"
    assert stream.blocks[0].metadata["byte_size"] == 3
    assert b"\x00\x01\x02" not in repr(stream.to_record()).encode("utf-8", "ignore")


@pytest.mark.parametrize("digital", [False, True])
def test_document_figures_are_stored_and_have_doc_image_roles(digital):
    """Both main PDF paths keep branch's figure role, without a PyMuPDF seam."""
    from PIL import Image

    writer = FakeBlobWriter()
    page = Image.new("RGB", (32, 32), "white")
    detector = type("Detector", (), {
        "detect": lambda self, pages: [[LayoutBlock((0, 0, 32, 32), "image", 1.0, "image")]]
    })()
    kwargs = dict(detector=detector, render=lambda path, dpi: [page])
    if digital:
        from types import SimpleNamespace

        layer = SimpleNamespace(
            page_count=lambda: 1,
            candidates=lambda index: [],
            region_text=lambda index, bbox: "Figure 1",
        )
        figures = extractor.digital_visual_blocks(
            "/w/report.pdf", "doc", writer, text_layer=layer, **kwargs
        )
    else:
        figures = extractor.extract_layout(
            "/w/report.pdf", "doc", writer,
            ocr=lambda image, context=None: "Figure 1", **kwargs
        ).blocks

    assert len(figures) == 1
    figure = figures[0]
    assert figure.kind == IMAGE and figure.metadata["role"] == ROLE_DOC_IMAGE
    assert figure.media_key == "blobs/1"
    assert len(writer.written) == 1 and writer.written[0][1] == "image/jpeg"
    assert writer.written[0][0].startswith(b"\xff\xd8"), "cropped pixels are stored"
    assert figure.metadata["byte_size"] == len(writer.written[0][0])
    stream = ContentStream(
        asset_id="doc", blocks=[ContentBlock("doc:prose", text="prose"), figure]
    )
    assert media_block(stream) is None, "a PDF with figures is still a document"


def test_the_file_name_becomes_the_caption():
    """Often the only words attached to a recording, so the only way to find it."""
    stream = extractor.extract(
        _file("q3-teardown_thermal.mp4", b"x"), "a1", FakeBlobWriter()
    )

    assert stream.blocks[0].caption == "q3 teardown thermal"


def test_a_media_file_needs_no_blob_writer():
    """Nothing is written, so there is nothing to be missing a place to write to."""
    stream = extractor.extract(_file("clip.mp4"), "a1", put_blob=None)

    assert stream.blocks[0].kind == VIDEO


def test_media_metadata_carries_what_deletion_and_display_need():
    path = _file("clip.mp4", b"xy")

    stream = extractor.extract(path, "a1", FakeBlobWriter())

    assert stream.metadata["file_name"] == "clip.mp4"
    assert stream.metadata["file_path"] == os.path.abspath(path)
    assert stream.metadata["asset_id"] == "a1"
    assert stream.blocks[0].metadata["byte_size"] == 2
