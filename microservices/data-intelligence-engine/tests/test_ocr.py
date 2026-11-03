# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# pyright: reportMissingImports=false

import sys
from types import SimpleNamespace

from core import ocr


class _Reader:
    def __init__(self, value):
        self.value = value
        self.calls = 0

    def read(self, image, context=None):
        del image, context
        self.calls += 1
        return self.value


def test_hybrid_uses_text_layer_when_region_has_text():
    engine = ocr.HybridOCR()
    pdf_reader = _Reader("digital text")
    tesseract_reader = _Reader("pixel text")
    engine._pdfplumber = pdf_reader
    engine._tesseract = tesseract_reader

    assert engine.read(object(), {"pdf_path": "document.pdf"}) == "digital text"
    assert pdf_reader.calls == 1
    assert tesseract_reader.calls == 0


def test_hybrid_falls_back_to_tesseract_when_region_text_is_empty():
    engine = ocr.HybridOCR()
    engine._pdfplumber = _Reader("")
    tesseract_reader = _Reader("pixel text")
    engine._tesseract = tesseract_reader

    assert engine.read(object(), {"pdf_path": "document.pdf"}) == "pixel text"
    assert tesseract_reader.calls == 1


def test_hybrid_reads_visual_regions_with_tesseract_first():
    engine = ocr.HybridOCR()
    pdf_reader = _Reader("digital text")
    tesseract_reader = _Reader("pixel text")
    engine._pdfplumber = pdf_reader
    engine._tesseract = tesseract_reader

    assert engine.read(object(), {"visual": True}) == "pixel text"
    assert tesseract_reader.calls == 1
    assert pdf_reader.calls == 0


def test_hybrid_visual_region_falls_back_to_pdf_text_when_pixels_are_empty():
    engine = ocr.HybridOCR()
    pdf_reader = _Reader("digital text")
    engine._pdfplumber = pdf_reader
    engine._tesseract = _Reader("")

    assert engine.read(object(), {"visual": True}) == "digital text"
    assert pdf_reader.calls == 1


def test_tesseract_reads_pixels_lazily(monkeypatch):
    captured = {}

    def image_to_string(image, **kwargs):
        captured["image"] = image
        captured.update(kwargs)
        return "  pixel text  "

    monkeypatch.setitem(
        sys.modules,
        "pytesseract",
        SimpleNamespace(image_to_string=image_to_string),
    )

    image = object()
    assert ocr.TesseractOCR(lang="en").read(image) == "pixel text"
    assert captured == {"image": image, "lang": "eng"}


def test_ocr_factory_caches_by_backend_and_lang(monkeypatch):
    monkeypatch.setattr(ocr, "_CACHE", {})
    first = ocr.build_ocr(backend="tesseract", lang="en")
    same = ocr.build_ocr(backend="tesseract", lang="en")
    second = ocr.build_ocr(backend="tesseract", lang="zh_cn")

    assert first is same
    assert first is not second


def test_ocr_factory_builds_tesseract(monkeypatch):
    monkeypatch.setattr(ocr, "_CACHE", {})

    engine = ocr.build_ocr(backend="tesseract", lang="en")

    assert isinstance(engine, ocr.TesseractOCR)
    assert engine.lang == "en"