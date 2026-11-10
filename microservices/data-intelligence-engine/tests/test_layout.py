# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Layout detection: a page image becomes positioned, canonically-labelled blocks.

The detector's own model is heavy and not present in CI, so these tests pin the
two things that are the engine's responsibility rather than transformers':
label normalization, and the OpenVINO inference-and-packaging pipeline. The
pipeline is exercised both with an injected fake model (deterministic, no
openvino) and with a real OpenVINO IR built from a tiny torch module (so the
convert -> compile -> infer path is genuinely run on CPU), in both cases with a
stand-in image processor so no PP-DocLayout download is needed.
"""

import numpy as np
import pytest
from PIL import Image

import config

from core.layout import (
    IMAGE,
    TABLE,
    TEXT,
    EQUATION,
    LayoutBlock,
    build_layout_detector,
    merge_layout_blocks,
    normalize_label,
)
from inference.ov_adapter import OpenVINOLayoutDetector


# --- label normalization ------------------------------------------------------


def test_label_normalization_maps_the_vocabulary_to_four_kinds():
    assert normalize_label("paragraph_title") == TEXT
    assert normalize_label("text") == TEXT
    assert normalize_label("formula") == EQUATION
    assert normalize_label("equation") == EQUATION
    assert normalize_label("table") == TABLE
    assert normalize_label("chart") == IMAGE
    assert normalize_label("figure") == IMAGE


def test_label_normalization_is_case_insensitive_and_passes_unknowns_through():
    assert normalize_label("Seal") == IMAGE
    assert normalize_label("  TABLE ") == TABLE
    # A label the model starts emitting shows up as itself, not mis-bucketed.
    assert normalize_label("watermark") == "watermark"
    assert normalize_label(None) == "unknown"


def test_merge_layout_blocks_combines_same_kind_duplicate_queries():
    blocks = [
        LayoutBlock((10, 10, 100, 40), TEXT, 0.58, "paragraph_title"),
        LayoutBlock((11, 9, 99, 41), TEXT, 0.36, "figure_title"),
        LayoutBlock((10, 10, 100, 40), IMAGE, 0.70, "image"),
    ]

    merged = merge_layout_blocks(blocks)

    assert len(merged) == 2
    text = next(block for block in merged if block.label == TEXT)
    assert text.raw_label == "paragraph_title"
    assert text.score == 0.58
    assert text.bbox == (10, 9, 100, 41)


def test_openvino_factory_builds_the_adapter_layer():
    detector = build_layout_detector(
        backend=config.LOCAL_OPENVINO,
        model_id="unused",
        device="CPU",
        score_threshold=0.123,
    )

    assert isinstance(detector, OpenVINOLayoutDetector)


# --- test doubles -------------------------------------------------------------


class FakeImageProcessor:
    """Stands in for the transformers image processor.

    Produces the one input the (fake or tiny) model expects. The detector owns
    the PP-DocLayoutV3 sigmoid/top-k/box post-processing exercised below.
    """

    def __call__(self, images, return_tensors=None):
        return {"pixel_values": np.zeros((len(images), 3, 4, 4), dtype=np.float32)}


ID2LABEL = {0: "background", 1: "table", 2: "paragraph_title"}


# --- inference pipeline, injected fake model ----------------------------------


def _fake_compiled(inputs):
    """Two queries per page: query 0 is a confident table, query 1 is below
    threshold and must be dropped."""
    batch = inputs["pixel_values"].shape[0]
    logits = np.full((batch, 2, 3), -10.0, dtype=np.float32)
    logits[:, 0, 1] = 4.0  # sigmoid -> 0.982, label 1 -> "table"
    logits[:, 1, 2] = -1.0  # sigmoid -> 0.269, below the 0.5 threshold
    boxes = np.zeros((batch, 2, 4), dtype=np.float32)
    boxes[:, 0] = [0.375, 0.375, 0.5, 0.5]  # cxcywh -> 10,10,50,50 at 80px
    boxes[:, 1] = [0.5, 0.5, 0.25, 0.25]
    return {"logits": logits, "pred_boxes": boxes}


def test_detect_packs_kept_detections_into_normalized_blocks():
    detector = OpenVINOLayoutDetector(
        model_path="unused",
        score_threshold=0.5,
        compiled_model=_fake_compiled,
        image_processor=FakeImageProcessor(),
        id2label=ID2LABEL,
    )

    pages = detector.detect([Image.new("RGB", (80, 80))])

    assert len(pages) == 1
    blocks = pages[0]
    assert len(blocks) == 1, "the sub-threshold query must be dropped"
    block = blocks[0]
    assert isinstance(block, LayoutBlock)
    assert block.raw_label == "table"
    assert block.label == TABLE
    assert block.score == pytest.approx(0.982014, abs=1e-5)
    assert tuple(round(v) for v in block.bbox) == (10, 10, 50, 50)


def test_detect_returns_one_block_list_per_page_in_order():
    detector = OpenVINOLayoutDetector(
        model_path="unused",
        score_threshold=0.5,
        compiled_model=_fake_compiled,
        image_processor=FakeImageProcessor(),
        id2label=ID2LABEL,
    )

    pages = detector.detect(
        [Image.new("RGB", (10, 10)), Image.new("RGB", (10, 10))]
    )

    assert [len(page) for page in pages] == [1, 1]


def test_detect_on_no_images_is_empty():
    detector = OpenVINOLayoutDetector(
        model_path="unused",
        compiled_model=_fake_compiled,
        image_processor=FakeImageProcessor(),
        id2label=ID2LABEL,
    )
    assert detector.detect([]) == []


def test_default_preprocessor_produces_ppdoclayout_tensor_without_transformers():
    captured = {}

    def compiled(inputs):
        captured["pixel_values"] = inputs["pixel_values"]
        return {
            "logits": np.array([[[-10.0, 4.0, -10.0]]], dtype=np.float32),
            "pred_boxes": np.array([[[0.5, 0.5, 0.5, 0.5]]], dtype=np.float32),
        }

    detector = OpenVINOLayoutDetector(
        model_path="unused",
        compiled_model=compiled,
        id2label=ID2LABEL,
    )

    pages = detector.detect([Image.new("RGB", (20, 10), (255, 128, 0))])

    pixel_values = captured["pixel_values"]
    assert pixel_values.shape == (1, 3, 800, 800)
    assert pixel_values.dtype == np.float32
    assert pixel_values[0, :, 0, 0] == pytest.approx([1.0, 128 / 255, 0.0])
    assert len(pages[0]) == 1
    assert tuple(round(value) for value in pages[0][0].bbox) == (5, 2, 15, 8)


# --- inference pipeline, real OpenVINO IR -------------------------------------


def test_openvino_runtime_runs_the_pipeline_end_to_end():
    """convert -> compile -> infer, on a tiny model, through the detector.

    Proves the OpenVINO path is real (not just the injected-callable branch):
    the tiny model returns an unnamed output tuple, so this also covers the
    order-based `(logits, boxes)` resolution in `_run`.
    """
    torch = pytest.importorskip("torch")
    ov = pytest.importorskip("openvino")

    class Tiny(torch.nn.Module):
        def forward(self, pixel_values):
            batch = pixel_values.shape[0]
            base = pixel_values.mean(dim=(1, 2, 3)).reshape(batch, 1, 1)
            logits = base.repeat(1, 2, 3)  # input-dependent -> kept in the graph
            boxes = base.repeat(1, 2, 4) + torch.tensor([0.5, 0.5, 0.5, 0.5])
            return logits, boxes

    ov_model = ov.convert_model(Tiny(), example_input=torch.zeros(1, 3, 4, 4))
    compiled = ov.Core().compile_model(ov_model, "CPU")

    detector = OpenVINOLayoutDetector(
        model_path="unused",
        device="CPU",
        score_threshold=0.49,  # sigmoid(0) == 0.5, so both queries survive
        compiled_model=compiled,
        image_processor=FakeImageProcessor(),
        id2label={0: "a", 1: "b", 2: "c"},
    )

    pages = detector.detect([Image.new("RGB", (4, 4))])

    assert len(pages) == 1
    assert len(pages[0]) == 2, "both queries survive the threshold"
    for block in pages[0]:
        assert tuple(round(v) for v in block.bbox) == (1, 1, 3, 3)
