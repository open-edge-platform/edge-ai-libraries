# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Images and video frames are letterboxed to the package's one visual_size."""

import pytest

from inference.multimodal import qwen3_vl_reranker_inputs as inputs
from inference.multimodal.qwen3_vl_reranker_ov import OpenVINOVLReranking


@pytest.mark.parametrize("document", [{"image": object()}, {"video": [object()]}])
def test_image_and_video_use_the_package_visual_size(monkeypatch, document):
    seen = []

    def encode(processor, query, document, visual_size):
        seen.append(visual_size)
        return {"input_ids": [[1, 2]], "attention_mask": [[1, 1]]}

    monkeypatch.setattr(inputs, "encode", encode)
    monkeypatch.setattr(inputs, "rope_position_ids", lambda values, config: [[[0, 1]]] * 3)
    scorer = OpenVINOVLReranking.__new__(OpenVINOVLReranking)
    scorer.export_shapes = {"visual_size": [320, 320], "modes": {"image": {}, "video": {}}}
    scorer.visual_size = (320, 320)
    scorer.processor = scorer.config = None

    scorer._prepare("query", document)
    assert seen == [(320, 320)]
