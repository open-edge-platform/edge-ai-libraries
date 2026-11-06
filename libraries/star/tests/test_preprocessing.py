# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from PIL import Image
import numpy as np

from semantic_img_comp.utils.preprocessing import bboxes_to_mask
from semantic_img_comp.utils.preprocessing import clear_bboxes_in_mask
from semantic_img_comp.utils.preprocessing import crop_boxes_with_margin
from semantic_img_comp.utils.preprocessing import canny_deriche_edge_det
from semantic_img_comp.utils.preprocessing import downsize_img
from semantic_img_comp.utils.preprocessing import select_canny_edge_det


def test_crop_boxes_with_margin_treats_none_as_zero_margin():
    img = Image.new("RGB", (20, 10), color="white")

    crops, boxes, expanded_boxes = crop_boxes_with_margin(
        img,
        [(2, 3, 8, 9, 0.9, 1)],
        margin_percent=None,
    )

    assert boxes == [(2, 3, 8, 9)]
    assert expanded_boxes == [(2, 3, 8, 9)]
    assert crops[0].size == (6, 6)



def test_crop_boxes_with_margin_clips_expansion_to_image_bounds():
    img = Image.new("RGB", (10, 10), color="white")

    crops, boxes, expanded_boxes = crop_boxes_with_margin(
        img,
        [(1, 1, 9, 9, 0.8, 3)],
        margin_percent=50,
    )

    assert boxes == [(1, 1, 9, 9)]
    assert expanded_boxes == [(0, 0, 10, 10)]
    assert crops[0].size == (10, 10)



def test_crop_boxes_with_margin_skips_invalid_boxes():
    img = Image.new("RGB", (10, 10), color="white")

    crops, boxes, expanded_boxes = crop_boxes_with_margin(
        img,
        [(5, 5, 5, 9, 0.7, 2), (2, 2, 6, 6, 0.9, 1)],
        margin_percent=0,
    )

    assert len(crops) == 1
    assert boxes == [(2, 2, 6, 6)]
    assert expanded_boxes == [(2, 2, 6, 6)]


def test_clear_bboxes_in_mask_zeros_only_requested_regions():
    mask = Image.new("L", (8, 6), color=255)

    cleared = clear_bboxes_in_mask(mask, [(2, 1, 5, 4)])
    arr = np.array(cleared)

    assert arr[0, 0] == 255
    assert arr[2, 3] == 0
    assert arr[5, 7] == 255


def test_bboxes_to_mask_marks_requested_regions():
    mask = bboxes_to_mask((8, 6), [(2, 1, 5, 4)])
    arr = np.array(mask)

    assert arr[0, 0] == 0
    assert arr[2, 3] == 255
    assert arr[5, 7] == 0


def test_downsize_img_defaults_to_bicubic(monkeypatch):
    img = Image.new("RGB", (20, 10), color="white")
    seen = {}

    def _fake_resize(size, resample=None):
        seen["size"] = size
        seen["resample"] = resample
        return Image.new("RGB", size, color="white")

    monkeypatch.setattr(img, "resize", _fake_resize)

    resized = downsize_img(img, scale_percent=50)

    assert resized.size == (10, 5)
    assert seen["size"] == (10, 5)
    assert seen["resample"] == Image.Resampling.BICUBIC


def test_canny_deriche_edge_det_returns_binary_mask_image():
    img = Image.new("RGB", (16, 16), color="black")
    for x in range(4, 12):
        img.putpixel((x, 8), (255, 255, 255))

    mask = canny_deriche_edge_det(img)

    assert mask.mode == "L"
    assert mask.size == img.size
    vals = set(mask.get_flattened_data())
    assert vals.issubset({0, 255})


def test_select_canny_edge_det_accepts_old_and_new_modes():
    img = Image.new("RGB", (12, 12), color="white")

    old_mask = select_canny_edge_det(img, mode="old")
    new_mask = select_canny_edge_det(img, mode="new")

    assert old_mask.size == img.size
    assert new_mask.size == img.size


