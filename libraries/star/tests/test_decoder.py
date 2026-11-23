# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace
import zlib

import numpy as np
import pytest
from PIL import Image, ImageDraw

from semantic_img_comp.decoder import codecs as decoder_codecs
from semantic_img_comp.decoder.decoder import Decoder
from semantic_img_comp.encoder.codecs import encode_mono_mask_1bit, encode_mono_skel_v1
from semantic_img_comp.encoder.codecs import encode_mono_shape_v1
from semantic_img_comp.encoder.codecs import encode_mono_2bit
from semantic_img_comp.encoder.codecs import encode_mono_2bit_mixed_n1bit
from semantic_img_comp.encoder.codecs import encode_mono_2bit_template_drop1bit
from semantic_img_comp.utils.preprocessing import bboxes_to_mask


class _Bg:
    def __init__(self):
        self.encoder_index = 1
        self.encoded_data = b"abc"
        self.scaled_size = (2, 2)
        self.recon_pil = None
        self.mask = None


class _Crop:
    def __init__(self):
        self.encoder_index = 1
        self.decoded_obj = b"abc"
        self.obj_size_scaled = (2, 2)
        self.expanded_bbox = (4, 4, 3, 3)
        self.recon_pil = None


def _cfg():
    return SimpleNamespace(
        dec=SimpleNamespace(avif_timeout_sec=120, smooth_sigma=0.0, bg_max_level=150),
        io=SimpleNamespace(annot_file=None),
        enc=SimpleNamespace(
            mono_2bit_mixed_two_bit_run=4,
            mono_2bit_mixed_one_bit_run=1,
            mono_2bit_drop1bit_neighbor_k=2,
            mono_2bit_drop1bit_fill_gray_level=128,
        ),
        img_process=SimpleNamespace(
            encoders_tag_bg={"mono-2bit": 1, "skip_bg": 99},
            encoders_tag_objs={"mono-4bit": 2},
            encoders_tag={"mono-2bit": 1, "mono-4bit": 2, "skip_bg": 99},
        ),
    )


def test_decode_img_invalid_encoder_raises():
    with pytest.raises(ValueError, match="Invalid encoder name"):
        Decoder.decode_img(encoded_data=b"x", scaled_size=(2, 2), enc_name="bad-encoder")


def test_decode_img_avif_like_unknown_name_rejected():
    with pytest.raises(ValueError, match="Invalid encoder name"):
        Decoder.decode_img(encoded_data=b"x", scaled_size=(2, 2), enc_name="custom-avif")


def test_decode_img_requires_bytes_like_input():
    with pytest.raises(TypeError, match="bytes-like"):
        Decoder.decode_img(encoded_data="not-bytes", scaled_size=(2, 2), enc_name="mono-2bit")  # type: ignore[arg-type]


def test_decode_img_requires_scaled_size_for_non_avif():
    with pytest.raises(ValueError, match="scaled_size"):
        Decoder.decode_img(encoded_data=b"x", scaled_size=None, enc_name="mono-2bit")


def test_decode_mono_2bit_rejects_invalid_payload_length():
    import zlib

    bad_payload = zlib.compress(b"\x00")
    with pytest.raises(ValueError, match="mono-2bit"):
        decoder_codecs.decode_mono_2bit(bad_payload, (4, 4))


def test_decode_color_8bit_rejects_invalid_payload_length():
    import zlib

    raw = b"\x00" * 4
    encoded = zlib.compress(raw)
    with pytest.raises(ValueError, match="color-8bit"):
        decoder_codecs.decode_color_8bit(encoded, (2, 2))  # expects 12 bytes


def test_decode_mono_mask_1bit_roundtrip():
    img = Image.new("L", (5, 3), color=0)
    expected_mask = np.array(
        [
            [0, 1, 0, 1, 1],
            [1, 0, 0, 1, 0],
            [1, 1, 0, 0, 1],
        ],
        dtype=np.uint8,
    )
    mask = Image.fromarray((expected_mask * 255).astype(np.uint8), mode="L")

    encoded = encode_mono_mask_1bit(img, mask=mask)
    decoded_img, decoded_mask = Decoder.decode_img(
        encoded_data=encoded,
        scaled_size=img.size,
        enc_name="mono-mask-1bit",
    )

    assert decoded_img.mode == "L"
    assert decoded_img.size == img.size
    assert np.array_equal(decoded_mask, expected_mask)
    assert np.array_equal(np.array(decoded_img), expected_mask * 255)


def test_decode_mono_2bit_sparse_roundtrip_with_skip_mask():
    img = Image.fromarray(np.array([[0, 64, 128, 255]], dtype=np.uint8), mode="L")
    skip_mask = bboxes_to_mask(img.size, [(1, 0, 2, 1)], fill=255)

    encoded = encode_mono_2bit(img, skip_mask=skip_mask)
    decoded = decoder_codecs.decode_mono_2bit(encoded, img.size, skip_mask=skip_mask)

    arr = np.array(decoded)
    # skipped middle region is reconstructed as 0
    assert arr[0, 1] == 0
    assert arr[0, 2] == 0
    assert arr[0, 0] == 0
    assert arr[0, 3] == 255


def test_decode_mono_mask_1bit_sparse_roundtrip_with_skip_mask():
    img = Image.new("L", (4, 1), color=0)
    mask_arr = np.array([[1, 1, 0, 1]], dtype=np.uint8)
    mask = Image.fromarray((mask_arr * 255).astype(np.uint8), mode="L")
    skip_mask = bboxes_to_mask(img.size, [(1, 0, 2, 1)], fill=255)

    encoded = encode_mono_mask_1bit(img, mask=mask, skip_mask=skip_mask)
    decoded_img, decoded_mask = decoder_codecs.decode_mono_mask_1bit(
        encoded,
        img.size,
        skip_mask=skip_mask,
    )

    assert np.array_equal(decoded_mask, np.array([[1, 0, 0, 1]], dtype=np.uint8))
    assert np.array_equal(np.array(decoded_img), np.array([[255, 0, 0, 255]], dtype=np.uint8))


def test_decode_mono_2bit_sparse_tolerates_trailing_bytes():
    img = Image.fromarray(np.array([[0, 64, 128, 255]], dtype=np.uint8), mode="L")
    skip_mask = bboxes_to_mask(img.size, [(1, 0, 2, 1)], fill=255)

    encoded = encode_mono_2bit(img, skip_mask=skip_mask)
    raw = zlib.decompress(encoded)
    # Append one trailing packed byte to simulate mixed-version sparse payloads.
    encoded_with_trailing = zlib.compress(raw + b"\x00")

    decoded = decoder_codecs.decode_mono_2bit(encoded_with_trailing, img.size, skip_mask=skip_mask)
    arr = np.array(decoded)
    assert arr.shape == (1, 4)
    assert arr[0, 3] == 255


def test_decode_mono_mask_1bit_sparse_tolerates_trailing_bytes():
    img = Image.new("L", (4, 1), color=0)
    mask_arr = np.array([[1, 1, 0, 1]], dtype=np.uint8)
    mask = Image.fromarray((mask_arr * 255).astype(np.uint8), mode="L")
    skip_mask = bboxes_to_mask(img.size, [(1, 0, 2, 1)], fill=255)

    encoded = encode_mono_mask_1bit(img, mask=mask, skip_mask=skip_mask)
    raw = zlib.decompress(encoded)
    # Append one trailing packed byte to simulate mixed-version sparse payloads.
    encoded_with_trailing = zlib.compress(raw + b"\x00")

    decoded_img, decoded_mask = decoder_codecs.decode_mono_mask_1bit(
        encoded_with_trailing,
        img.size,
        skip_mask=skip_mask,
    )
    assert np.array_equal(decoded_mask, np.array([[1, 0, 0, 1]], dtype=np.uint8))
    assert np.array_equal(np.array(decoded_img), np.array([[255, 0, 0, 255]], dtype=np.uint8))


def test_decode_mono_skel_v1_roundtrip_draws_sparse_lines():
    src = Image.new("L", (16, 16), color=0)
    for i in range(3, 13):
        src.putpixel((i, i), 255)

    encoded = encode_mono_skel_v1(src, max_segments=6)
    decoded_img, decoded_mask = Decoder.decode_img(
        encoded_data=encoded,
        scaled_size=src.size,
        enc_name="mono-skel-v1",
    )

    arr = np.array(decoded_img)
    assert decoded_mask is None
    assert decoded_img.mode == "L"
    assert decoded_img.size == src.size
    assert arr.max() == 255
    assert arr.sum() > 0


def test_decode_mono_shape_v1_roundtrip_draws_polygon_outline():
    src = Image.new("L", (20, 20), color=0)
    for x in range(5, 15):
        src.putpixel((x, 7), 255)
        src.putpixel((x, 13), 255)
    for y in range(7, 14):
        src.putpixel((5, y), 255)
        src.putpixel((14, y), 255)

    encoded = encode_mono_shape_v1(src, max_points=24)
    decoded_img, decoded_mask = Decoder.decode_img(
        encoded_data=encoded,
        scaled_size=src.size,
        enc_name="mono-shape-v1",
    )

    arr = np.array(decoded_img)
    assert decoded_mask is None
    assert decoded_img.mode == "L"
    assert decoded_img.size == src.size
    assert arr.max() == 255
    assert arr.sum() > 0


def test_decode_mono_2bit_supports_muted_max_level():
    img = Image.fromarray(np.array([[0, 64, 128, 255]], dtype=np.uint8), mode="L")

    encoded = encode_mono_2bit(img)

    default_img, _ = Decoder.decode_img(
        encoded_data=encoded,
        scaled_size=img.size,
        enc_name="mono-2bit",
    )
    muted_img, _ = Decoder.decode_img(
        encoded_data=encoded,
        scaled_size=img.size,
        enc_name="mono-2bit",
        max_level=150,
    )

    assert np.array_equal(np.array(default_img), np.array([[0, 85, 170, 255]], dtype=np.uint8))
    assert np.array_equal(np.array(muted_img), np.array([[0, 50, 100, 150]], dtype=np.uint8))


def test_decode_mono_2bit_mixed_n1bit_roundtrip():
    img = Image.fromarray(np.array([[0, 64, 128, 255, 64]], dtype=np.uint8), mode="L")
    encoded = encode_mono_2bit_mixed_n1bit(img, two_bit_run=2, one_bit_run=1)

    decoded = decoder_codecs.decode_mono_2bit_mixed_n1bit(
        encoded,
        img.size,
        two_bit_run=2,
        one_bit_run=1,
    )
    arr = np.array(decoded)
    assert arr.shape == (1, 5)
    # 3rd sample in each 2+1 cycle uses 1-bit branch (values map to {0,255}).
    assert np.array_equal(arr, np.array([[0, 85, 255, 255, 85]], dtype=np.uint8))


def test_decode_mono_2bit_mixed_n1bit_sparse_roundtrip_with_skip_mask():
    img = Image.fromarray(np.array([[0, 64, 128, 255, 64]], dtype=np.uint8), mode="L")
    skip_mask = bboxes_to_mask(img.size, [(3, 0, 4, 1)], fill=255)
    encoded = encode_mono_2bit_mixed_n1bit(
        img,
        two_bit_run=2,
        one_bit_run=1,
        skip_mask=skip_mask,
    )

    decoded = decoder_codecs.decode_mono_2bit_mixed_n1bit(
        encoded,
        img.size,
        two_bit_run=2,
        one_bit_run=1,
        skip_mask=skip_mask,
    )
    arr = np.array(decoded)
    assert arr.shape == (1, 5)
    assert arr[0, 3] == 0


def test_decode_mono_2bit_template_drop1bit_subsample_upsample_roundtrip():
    """Uniform image roundtrips via area-downsample + 2-bit encode + bicubic upsample."""
    img = Image.fromarray(np.full((6, 4), 128, dtype=np.uint8), mode="L")
    encoded = encode_mono_2bit_template_drop1bit(img, two_bit_run=2, one_bit_run=1)
    decoded = decoder_codecs.decode_mono_2bit_template_drop1bit(
        encoded, img.size, two_bit_run=2, one_bit_run=1,
    )
    assert decoded.size == img.size
    # 128 -> q=2 -> 2/3*255=170; uniform field is preserved through resize
    assert abs(int(np.array(decoded).mean()) - 170) <= 5


def test_decode_mono_2bit_template_drop1bit_skip_mask_zeroes_input():
    """Skip-masked region is zeroed at encoder so output decodes to 0."""
    img = Image.fromarray(np.full((4, 4), 255, dtype=np.uint8), mode="L")
    skip_mask = bboxes_to_mask(img.size, [(0, 0, 4, 4)], fill=255)
    encoded = encode_mono_2bit_template_drop1bit(
        img, two_bit_run=1, one_bit_run=1, skip_mask=skip_mask,
    )
    decoded = decoder_codecs.decode_mono_2bit_template_drop1bit(
        encoded, img.size, two_bit_run=1, one_bit_run=1,
    )
    assert decoded.size == img.size
    assert np.array(decoded).max() == 0


def test_decode_mono_2bit_template_drop1bit_output_matches_input_size():
    """Decoded image always matches original size regardless of subsample ratio."""
    np.random.seed(42)
    img = Image.fromarray(np.random.randint(0, 256, (8, 6), dtype=np.uint8), mode="L")
    for n, m in [(1, 1), (2, 1), (3, 1)]:
        encoded = encode_mono_2bit_template_drop1bit(img, two_bit_run=n, one_bit_run=m)
        decoded = decoder_codecs.decode_mono_2bit_template_drop1bit(
            encoded, img.size, two_bit_run=n, one_bit_run=m,
        )
        assert decoded.size == img.size

def test_decode_mono_mask_1bit_supports_muted_max_level():
    img = Image.new("L", (2, 2), color=0)
    expected_mask = np.array([[0, 1], [1, 1]], dtype=np.uint8)
    mask = Image.fromarray((expected_mask * 255).astype(np.uint8), mode="L")

    encoded = encode_mono_mask_1bit(img, mask=mask)

    _, decoded_mask = Decoder.decode_img(
        encoded_data=encoded,
        scaled_size=img.size,
        enc_name="mono-mask-1bit",
    )
    muted_img, _ = Decoder.decode_img(
        encoded_data=encoded,
        scaled_size=img.size,
        enc_name="mono-mask-1bit",
        max_level=150,
    )

    muted_arr = np.array(muted_img)
    assert np.array_equal(decoded_mask, expected_mask)
    assert muted_arr.max() <= 150
    assert muted_arr[1, 1] == 150


def test_decode_mono_mask_1bit_rejects_missing_payload():
    import zlib

    bad_payload = zlib.compress(b"\x00")
    with pytest.raises(ValueError, match="too small for header|missing 1-bit mask payload"):
        decoder_codecs.decode_mono_mask_1bit(bad_payload, (4, 4))


def test_decode_avif_without_avifdec_raises(monkeypatch):
    def _missing(*args, **kwargs):
        raise FileNotFoundError("avifdec not found")

    monkeypatch.setattr(decoder_codecs.subprocess, "run", _missing)

    with pytest.raises(FileNotFoundError, match="avifdec"):
        decoder_codecs.decode_avif(b"dummy")


def test_decode_avif_subprocess_failure_raises_runtime(monkeypatch):

    def _fail(*args, **kwargs):
        raise decoder_codecs.subprocess.CalledProcessError(returncode=2, cmd=args[0], stderr="decode failed")

    monkeypatch.setattr(decoder_codecs.subprocess, "run", _fail)

    with pytest.raises(RuntimeError, match="decode failed"):
        decoder_codecs.decode_avif(b"dummy")


def test_decompress_background_validates_output_size(monkeypatch):
    dec = Decoder(_cfg())
    bg = _Bg()

    monkeypatch.setattr(Decoder, "decode_img", classmethod(lambda cls, **kwargs: (Image.new("L", (2, 2)), None)))

    with pytest.raises(ValueError, match="org_img_size"):
        dec.decompress_background(bg, (0, 10))


def test_decompress_objs_rejects_invalid_expanded_bbox(monkeypatch):
    dec = Decoder(_cfg())
    crop = _Crop()
    crop.encoder_index = 2

    monkeypatch.setattr(Decoder, "decode_img", classmethod(lambda cls, **kwargs: (Image.new("L", (2, 2)), None)))

    with pytest.raises(ValueError, match="expanded_bbox"):
        dec.decompress_objs([crop])


def test_decompress_background_rejects_unknown_encoder_index():
    dec = Decoder(_cfg())
    bg = _Bg()
    bg.encoder_index = 999

    with pytest.raises(ValueError, match="Unknown encoder_index"):
        dec.decompress_background(bg, (10, 10))


def test_decompress_background_skip_bg_uses_black_canvas(monkeypatch):
    dec = Decoder(_cfg())
    bg = _Bg()
    bg.encoder_index = 99
    bg.encoded_data = b""
    bg.scaled_size = (1, 1)

    def _should_not_decode(cls, **kwargs):
        raise AssertionError("decode_img should not be called for skip_bg")

    monkeypatch.setattr(Decoder, "decode_img", classmethod(_should_not_decode))

    dec.decompress_background(bg, (4, 3))

    assert bg.recon_pil.size == (4, 3)
    assert bg.recon_pil.mode == "RGB"
    assert bg.recon_pil.getbbox() is None
    assert bg.mask is None


def test_decompress_objs_uses_object_tag_mapping(monkeypatch):
    dec = Decoder(_cfg())
    crop = _Crop()
    crop.encoder_index = 2
    crop.expanded_bbox = (0, 0, 2, 2)

    called = {}

    def _fake_decode_img(cls, **kwargs):
        called["enc_name"] = kwargs["enc_name"]
        return Image.new("L", kwargs["scaled_size"], color=0), None

    monkeypatch.setattr(Decoder, "decode_img", classmethod(_fake_decode_img))

    dec.decompress_objs([crop])

    assert called["enc_name"] == "mono-4bit"


def test_decompress_objs_prefers_unified_encoder_map_over_split_map(monkeypatch):
    cfg = _cfg()
    cfg.img_process.encoders_tag_objs = {"mono-2bit": 2}
    cfg.img_process.encoders_tag = {"mono-4bit": 2}
    dec = Decoder(cfg)

    crop = _Crop()
    crop.encoder_index = 2
    crop.expanded_bbox = (0, 0, 2, 2)

    called = {}

    def _fake_decode_img(cls, **kwargs):
        called["enc_name"] = kwargs["enc_name"]
        return Image.new("L", kwargs["scaled_size"], color=0), None

    monkeypatch.setattr(Decoder, "decode_img", classmethod(_fake_decode_img))

    dec.decompress_objs([crop])

    assert called["enc_name"] == "mono-4bit"


def test_decompress_background_mutes_mono_2bit_levels():
    dec = Decoder(_cfg())
    bg = _Bg()
    bg.encoded_data = encode_mono_2bit(Image.fromarray(np.array([[0, 64, 128, 255]], dtype=np.uint8), mode="L"))
    bg.scaled_size = (4, 1)

    dec.decompress_background(bg, (4, 1))

    assert np.array_equal(np.array(bg.recon_pil), np.array([[0, 50, 100, 150]], dtype=np.uint8))


def test_decompress_background_mutes_mono_mask_1bit_levels():
    cfg = _cfg()
    cfg.img_process.encoders_tag_bg = {"mono-mask-1bit": 6}
    cfg.img_process.encoders_tag = {"mono-mask-1bit": 6}
    dec = Decoder(cfg)
    bg = _Bg()
    bg.encoder_index = 6
    bg.scaled_size = (2, 2)
    expected_mask = np.array([[0, 1], [1, 0]], dtype=np.uint8)
    mask = Image.fromarray((expected_mask * 255).astype(np.uint8), mode="L")
    bg.encoded_data = encode_mono_mask_1bit(Image.new("L", (2, 2), color=0), mask=mask)

    dec.decompress_background(bg, (2, 2))

    assert np.array_equal(bg.mask, expected_mask)
    assert np.array_equal(np.array(bg.recon_pil), expected_mask * 150)


def test_decompress_objects_keep_full_levels_for_mono_2bit():
    cfg = _cfg()
    cfg.img_process.encoders_tag_objs = {"mono-2bit": 7}
    cfg.img_process.encoders_tag = {"mono-2bit": 7}
    dec = Decoder(cfg)
    crop = _Crop()
    crop.encoder_index = 7
    crop.obj_size_scaled = (4, 1)
    crop.expanded_bbox = (0, 0, 4, 1)
    crop.decoded_obj = encode_mono_2bit(Image.fromarray(np.array([[0, 64, 128, 255]], dtype=np.uint8), mode="L"))

    dec.decompress_objs([crop])

    assert np.array_equal(np.array(crop.recon_pil), np.array([[0, 85, 170, 255]], dtype=np.uint8))


def test_decompress_objects_mono_mask_1bit_resize_preserves_binary_levels():
    cfg = _cfg()
    cfg.img_process.encoders_tag_objs = {"mono-mask-1bit": 6}
    cfg.img_process.encoders_tag = {"mono-mask-1bit": 6}
    dec = Decoder(cfg)

    crop = _Crop()
    crop.encoder_index = 6
    crop.obj_size_scaled = (2, 2)
    crop.expanded_bbox = (0, 0, 8, 8)

    expected_mask = np.array([[0, 1], [1, 0]], dtype=np.uint8)
    mask = Image.fromarray((expected_mask * 255).astype(np.uint8), mode="L")
    crop.decoded_obj = encode_mono_mask_1bit(Image.new("L", (2, 2), color=0), mask=mask)

    dec.decompress_objs([crop])

    uniq = set(np.unique(np.array(crop.recon_pil)).tolist())
    assert uniq <= {0, 255}
    assert uniq == {0, 255}


def test_decompress_objects_mono_skel_marks_sparse_overlay_flag():
    cfg = _cfg()
    cfg.img_process.encoders_tag_objs = {"mono-skel-v1": 8}
    cfg.img_process.encoders_tag = {"mono-skel-v1": 8}
    dec = Decoder(cfg)

    crop = _Crop()
    crop.encoder_index = 8
    crop.obj_size_scaled = (16, 16)
    crop.expanded_bbox = (0, 0, 16, 16)

    src = Image.new("L", (16, 16), color=0)
    for i in range(2, 14):
        src.putpixel((i, 8), 255)
    crop.decoded_obj = encode_mono_skel_v1(src, max_segments=4)

    dec.decompress_objs([crop])

    assert getattr(crop, "sparse_overlay", False) is True
    assert np.array(crop.recon_pil).sum() > 0


def test_decompress_objects_mono_shape_marks_sparse_overlay_flag():
    cfg = _cfg()
    cfg.img_process.encoders_tag_objs = {"mono-shape-v1": 9}
    cfg.img_process.encoders_tag = {"mono-shape-v1": 9}
    dec = Decoder(cfg)

    crop = _Crop()
    crop.encoder_index = 9
    crop.obj_size_scaled = (20, 20)
    crop.expanded_bbox = (0, 0, 20, 20)

    src = Image.new("L", (20, 20), color=0)
    for x in range(5, 15):
        src.putpixel((x, 8), 255)
        src.putpixel((x, 12), 255)
    for y in range(8, 13):
        src.putpixel((5, y), 255)
        src.putpixel((14, y), 255)

    crop.decoded_obj = encode_mono_shape_v1(src, max_points=24)

    dec.decompress_objs([crop])

    assert getattr(crop, "sparse_overlay", False) is True
    assert np.array(crop.recon_pil).sum() > 0


def test_decode_airplane_symbol_v1_two_byte_payload_roundtrip_metadata():
    category_id, theta_deg = decoder_codecs.decode_airplane_symbol_v1(bytes((3, 128)))

    assert category_id == 3
    assert theta_deg == pytest.approx((128 / 255.0) * 360.0)


def test_decompress_objs_airplane_symbol_uses_airplane_icon_for_category_2(monkeypatch):
    cfg = _cfg()
    cfg.img_process.encoders_tag_objs = {"airplane-symbol-v1": 10}
    cfg.img_process.encoders_tag = {"airplane-symbol-v1": 10}
    dec = Decoder(cfg)

    crop = _Crop()
    crop.encoder_index = 10
    crop.obj_size_scaled = (12, 12)
    crop.expanded_bbox = (0, 0, 12, 12)
    crop.decoded_obj = bytes((2, 64))

    monkeypatch.setattr(decoder_codecs, "decode_airplane_symbol_v1", lambda data: (2, 15.0))
    monkeypatch.setattr(decoder_codecs, "render_airplane_symbol", lambda size, theta_deg=0.0: Image.new("L", size, color=77))
    monkeypatch.setattr(decoder_codecs, "render_tanker_symbol", lambda size, theta_deg=0.0: Image.new("L", size, color=155))

    dec.decompress_objs([crop])

    assert int(np.array(crop.recon_pil).mean()) == 77
    assert getattr(crop, "sparse_overlay", False) is True


def test_render_airplane_symbol_theta_matches_payload_convention():
    img0 = decoder_codecs.render_airplane_symbol((48, 48), theta_deg=0.0)
    img90 = decoder_codecs.render_airplane_symbol((48, 48), theta_deg=90.0)

    arr0 = np.array(img0)
    arr90 = np.array(img90)

    ys0, xs0 = np.where(arr0 > 0)
    ys1, xs1 = np.where(arr90 > 0)

    assert xs0.size > 0 and ys0.size > 0
    assert xs1.size > 0 and ys1.size > 0

    # theta=0 should point right, so horizontal spread should dominate.
    span_x0 = int(xs0.max()) - int(xs0.min())
    span_y0 = int(ys0.max()) - int(ys0.min())
    assert span_x0 > span_y0

    # theta=90 should point down, so vertical spread should dominate.
    span_x1 = int(xs1.max()) - int(xs1.min())
    span_y1 = int(ys1.max()) - int(ys1.min())
    assert span_y1 > span_x1

    assert not np.array_equal(arr0, arr90)


def test_render_tanker_symbol_preserves_luminance_details(monkeypatch):
    icon = Image.new("RGBA", (32, 20), color=(0, 0, 0, 0))
    for x in range(4, 28):
        for y in range(4, 16):
            shade = 220 if x < 16 else 120
            icon.putpixel((x, y), (shade, shade, shade, 255))

    monkeypatch.setattr(decoder_codecs, "_VESSEL_ICON", icon)

    out = decoder_codecs.render_tanker_symbol((48, 30), theta_deg=0.0)
    arr = np.array(out)
    nonzero = arr[arr > 0]

    assert nonzero.size > 0
    assert int(nonzero.min()) < int(nonzero.max())


def test_decompress_objs_airplane_symbol_uses_tanker_icon_for_category_3(monkeypatch):
    cfg = _cfg()
    cfg.img_process.encoders_tag_objs = {"airplane-symbol-v1": 10}
    cfg.img_process.encoders_tag = {"airplane-symbol-v1": 10}
    dec = Decoder(cfg)

    crop = _Crop()
    crop.encoder_index = 10
    crop.obj_size_scaled = (12, 12)
    crop.expanded_bbox = (0, 0, 12, 12)
    crop.decoded_obj = bytes((3, 64))

    monkeypatch.setattr(decoder_codecs, "decode_airplane_symbol_v1", lambda data: (3, 25.0))
    monkeypatch.setattr(decoder_codecs, "render_airplane_symbol", lambda size, theta_deg=0.0: Image.new("L", size, color=77))
    monkeypatch.setattr(decoder_codecs, "render_tanker_symbol", lambda size, theta_deg=0.0: Image.new("L", size, color=155))

    dec.decompress_objs([crop])

    assert int(np.array(crop.recon_pil).mean()) == 155
    assert getattr(crop, "sparse_overlay", False) is True


def test_decompress_objs_airplane_symbol_renders_vessel_at_expanded_bbox_size(monkeypatch):
    cfg = _cfg()
    cfg.img_process.encoders_tag_objs = {"airplane-symbol-v1": 10}
    cfg.img_process.encoders_tag = {"airplane-symbol-v1": 10}
    dec = Decoder(cfg)

    crop = _Crop()
    crop.encoder_index = 10
    crop.obj_size_scaled = (8, 8)
    crop.expanded_bbox = (0, 0, 20, 10)
    crop.decoded_obj = bytes((3, 64))

    seen = {}

    monkeypatch.setattr(decoder_codecs, "decode_airplane_symbol_v1", lambda data: (3, 45.0))

    def _fake_tanker(size, theta_deg=0.0):
        seen["size"] = size
        seen["theta"] = theta_deg
        return Image.new("L", size, color=255)

    monkeypatch.setattr(decoder_codecs, "render_tanker_symbol", _fake_tanker)

    dec.decompress_objs([crop])

    assert seen["size"] == (20, 10)
    assert seen["theta"] == 45.0
    assert crop.recon_pil.size == (20, 10)


def test_decompress_objs_airplane_symbol_unknown_category_defensive_fallback(monkeypatch):
    cfg = _cfg()
    cfg.img_process.encoders_tag_objs = {"airplane-symbol-v1": 10}
    cfg.img_process.encoders_tag = {"airplane-symbol-v1": 10}
    dec = Decoder(cfg)

    crop = _Crop()
    crop.encoder_index = 10
    crop.obj_size_scaled = (12, 12)
    crop.expanded_bbox = (0, 0, 12, 12)
    crop.decoded_obj = bytes((9, 64))

    monkeypatch.setattr(decoder_codecs, "decode_airplane_symbol_v1", lambda data: (9, 35.0))
    monkeypatch.setattr(decoder_codecs, "render_airplane_symbol", lambda size, theta_deg=0.0: Image.new("L", size, color=77))
    monkeypatch.setattr(decoder_codecs, "render_tanker_symbol", lambda size, theta_deg=0.0: Image.new("L", size, color=155))

    dec.decompress_objs([crop])

    assert int(np.array(crop.recon_pil).mean()) == 77
    assert getattr(crop, "sparse_overlay", False) is True


def test_render_tanker_symbol_is_fully_contained_inside_bbox():
    img = decoder_codecs.render_tanker_symbol((48, 16), theta_deg=0.0)
    arr = np.array(img)

    ys, xs = np.where(arr > 0)
    assert xs.size > 0
    assert ys.size > 0
    # Vessel icon should stay fully inside the bbox (strictly contained).
    assert int(xs.min()) >= 1
    assert int(xs.max()) <= 46
    assert int(ys.min()) >= 0
    assert int(ys.max()) <= 15


def test_render_tanker_symbol_theta_changes_oval_orientation():
    img0 = decoder_codecs.render_tanker_symbol((48, 16), theta_deg=0.0)
    img90 = decoder_codecs.render_tanker_symbol((48, 16), theta_deg=90.0)

    arr0 = np.array(img0)
    arr90 = np.array(img90)

    # Oval orientation should rotate with theta.
    assert not np.array_equal(arr0, arr90)

    for arr, w, h in ((arr0, 48, 16), (arr90, 48, 16)):
        ys, xs = np.where(arr > 0)
        assert xs.size > 0
        assert ys.size > 0
        assert 0 <= int(xs.min()) <= int(xs.max()) <= w - 1
        assert 0 <= int(ys.min()) <= int(ys.max()) <= h - 1

    # With no canonical offset in tanker renderer, default vessel orientation
    # remains vertical at theta=0 and rotates horizontal at theta=90.
    ys0, xs0 = np.where(arr0 > 0)
    ys1, xs1 = np.where(arr90 > 0)
    span_x0 = int(xs0.max()) - int(xs0.min())
    span_y0 = int(ys0.max()) - int(ys0.min())
    span_x1 = int(xs1.max()) - int(xs1.min())
    span_y1 = int(ys1.max()) - int(ys1.min())
    assert span_x0 < span_y0
    assert span_x1 > span_y1


def test_render_tanker_symbol_theta_matches_payload_convention_for_north_icon(monkeypatch):
    icon = Image.new("RGBA", (32, 32), color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(icon)
    # Body + bright nose marker at the top (north) to disambiguate heading.
    draw.polygon([(16, 3), (24, 20), (16, 28), (8, 20)], fill=(140, 140, 140, 255))
    draw.ellipse((14, 1, 18, 5), fill=(255, 255, 255, 255))

    monkeypatch.setattr(decoder_codecs, "_VESSEL_ICON", icon)

    img0 = decoder_codecs.render_tanker_symbol((64, 64), theta_deg=0.0)
    img90 = decoder_codecs.render_tanker_symbol((64, 64), theta_deg=90.0)

    arr0 = np.array(img0)
    arr90 = np.array(img90)
    y0, x0 = np.unravel_index(int(np.argmax(arr0)), arr0.shape)
    y1, x1 = np.unravel_index(int(np.argmax(arr90)), arr90.shape)
    cx = (arr0.shape[1] - 1) / 2.0
    cy = (arr0.shape[0] - 1) / 2.0

    # No-offset behavior for a north-oriented asset: theta=0 -> up, theta=90 -> right.
    assert y0 < cy - 6
    assert abs(x0 - cx) < 12
    assert x1 > cx + 6
    assert abs(y1 - cy) < 12


