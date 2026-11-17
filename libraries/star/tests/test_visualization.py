# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import numpy as np
from PIL import Image
from types import SimpleNamespace

from semantic_img_comp.utils.visualization import save_enc_mask
from semantic_img_comp.utils.visualization import draw_boxes_on_pil


def test_save_enc_mask_writes_file_for_single_mask(tmp_path):
    out_path = tmp_path / "single_mask.png"
    mask = np.zeros((4, 4), dtype=np.uint8)
    mask[1:3, 1:3] = 1

    save_enc_mask(mask, (16, 16), out_path)

    assert out_path.exists()
    assert out_path.stat().st_size > 0


def test_save_enc_mask_writes_file_for_tuple_mask(tmp_path):
    out_path = tmp_path / "tuple_mask.png"
    mask_2 = np.zeros((4, 4), dtype=np.uint8)
    mask_4 = np.zeros((4, 4), dtype=np.uint8)
    mask_8 = np.zeros((4, 4), dtype=np.uint8)
    mask_2[0, 0] = 1
    mask_4[1, 1] = 1
    mask_8[2, 2] = 1

    save_enc_mask((mask_2, mask_4, mask_8), (16, 16), out_path)

    assert out_path.exists()
    assert out_path.stat().st_size > 0


def test_draw_boxes_on_pil_can_skip_labels_without_category_conf():
    img = Image.new("RGB", (20, 20), color="black")
    crops = [SimpleNamespace(bbox=(2, 2, 10, 10), category_id=None, det_conf=None)]

    result = draw_boxes_on_pil(img, crops, show_labels=False)

    assert result is img


