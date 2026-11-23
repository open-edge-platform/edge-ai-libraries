# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace

from PIL import Image

from semantic_img_comp.utils.postprocessing import paste_with_margin



def _make_img_dec_data():
    bg = SimpleNamespace(recon_pil=Image.new("RGB", (6, 6), color=(0, 0, 0)))
    crop = SimpleNamespace(
        bbox=(2, 2, 4, 4),
        expanded_bbox=(1, 1, 5, 5),
        recon_pil=Image.new("RGB", (4, 4), color=(255, 255, 255)),
    )
    return SimpleNamespace(bg=bg, crops=[crop])



def test_paste_with_margin_zero_margin_pastes_entire_expanded_crop():
    img_dec_data = _make_img_dec_data()

    out = paste_with_margin(img_dec_data, margin_percent=0)

    # Outside bbox but inside expanded bbox: fully pasted when margin is zero.
    assert out.getpixel((1, 1)) == (255, 255, 255)



def test_paste_with_margin_nonzero_margin_feathers_expanded_edge():
    img_dec_data = _make_img_dec_data()

    out = paste_with_margin(img_dec_data, margin_percent=50)

    # Outside bbox region remains background after feathering.
    assert out.getpixel((1, 1)) == (0, 0, 0)
    # Interior object region is still pasted.
    assert out.getpixel((3, 3)) == (255, 255, 255)


def test_paste_with_margin_custom_feather_parameters_change_edge_blend():
    img_dec_data = _make_img_dec_data()

    no_feather = paste_with_margin(
        img_dec_data,
        margin_percent=50,
        feather_ratio=0.0,
        feather_min_px=0,
    )
    strong_feather = paste_with_margin(
        img_dec_data,
        margin_percent=50,
        feather_ratio=1.0,
        feather_min_px=1,
    )

    assert no_feather.getpixel((1, 1)) == (255, 255, 255)
    assert strong_feather.getpixel((1, 1)) == (0, 0, 0)


def test_paste_with_margin_ignores_crop_margin_pixel_and_uses_configured_margin():
    img_dec_data = _make_img_dec_data()
    img_dec_data.crops[0].margin_pixel = 999

    out = paste_with_margin(img_dec_data, margin_percent=0)

    assert out.getpixel((1, 1)) == (255, 255, 255)


def test_paste_with_margin_resizes_alpha_mask_with_bicubic(monkeypatch):
    img_dec_data = _make_img_dec_data()
    original_resize = Image.Image.resize
    seen = []

    def _recording_resize(self, size, resample=None, box=None, reducing_gap=None):
        seen.append((self.mode, size, resample))
        return original_resize(self, size, resample=resample, box=box, reducing_gap=reducing_gap)

    monkeypatch.setattr(Image.Image, "resize", _recording_resize)

    out = paste_with_margin(img_dec_data, margin_percent=50)

    assert out.size == (6, 6)
    assert ("L", (4, 4), Image.Resampling.BICUBIC) in seen


def test_paste_with_margin_rejects_invalid_feather_parameters():
    img_dec_data = _make_img_dec_data()

    try:
        paste_with_margin(img_dec_data, margin_percent=50, feather_ratio=float("inf"), feather_min_px=1)
        raise AssertionError("Expected ValueError for non-finite feather_ratio")
    except ValueError as exc:
        assert "feather_ratio" in str(exc)

    try:
        paste_with_margin(img_dec_data, margin_percent=50, feather_ratio=0.5, feather_min_px=-1)
        raise AssertionError("Expected ValueError for negative feather_min_px")
    except ValueError as exc:
        assert "feather_min_px" in str(exc)


def test_paste_with_margin_sparse_overlay_only_draws_line_pixels():
    bg = SimpleNamespace(recon_pil=Image.new("RGB", (8, 8), color=(10, 20, 30)))
    line = Image.new("L", (4, 4), color=0)
    line.putpixel((0, 0), 255)
    line.putpixel((1, 1), 255)
    crop = SimpleNamespace(
        bbox=(2, 2, 4, 4),
        expanded_bbox=(2, 2, 6, 6),
        recon_pil=line,
        sparse_overlay=True,
    )
    img_dec_data = SimpleNamespace(bg=bg, crops=[crop])

    out = paste_with_margin(img_dec_data, margin_percent=0)

    # Non-line pixels in expanded crop keep original background.
    assert out.getpixel((5, 5)) == (10, 20, 30)
    # Line pixels are composited as bright strokes.
    assert out.getpixel((2, 2)) != (10, 20, 30)


