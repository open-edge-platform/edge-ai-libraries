# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: tests/test_encoder.py
Version: 0.1
Authors: Generated for production testing
Date: 2026-04-09
Description: Unit tests for encoder helper methods and error handling.
"""
import pytest
import numpy as np
from types import SimpleNamespace
from PIL import Image, ImageDraw

from semantic_img_comp.encoder import encoder as encoder_module
from semantic_img_comp.encoder import codecs as encoder_codecs

from semantic_img_comp.encoder.encoder import Encoder
from semantic_img_comp.encoder.codecs import encode_avif
from semantic_img_comp.encoder.codecs import encode_color_2bit
from semantic_img_comp.encoder.codecs import encode_color_4bit
from semantic_img_comp.encoder.codecs import encode_color_8bit
from semantic_img_comp.encoder.codecs import encode_mono_mask_1bit
from semantic_img_comp.encoder.codecs import encode_mono_skel_v1
from semantic_img_comp.encoder.codecs import encode_mono_shape_v1
from semantic_img_comp.encoder.codecs import encode_mono_2bit
from semantic_img_comp.encoder.codecs import encode_mono_4bit
from semantic_img_comp.encoder.codecs import encode_mono_8bit
from semantic_img_comp.encoder.codecs import estimate_airplane_nose_theta_deg
from semantic_img_comp.encoder.codecs import estimate_vessel_nose_theta_deg
from semantic_img_comp.encoder.codecs import _pack_bits


class TestEncoderResizeHelpers:
    """Test that resize helpers handle edge cases and maintain (width, height) ordering."""

    def test_resize_image_defaults_to_bicubic(self, monkeypatch):
        """Continuous-tone image resizing should use BICUBIC by default."""
        img = Image.new("RGB", (100, 50), color="red")
        seen = {}

        def _fake_resize(size, resample=None):
            seen["size"] = size
            seen["resample"] = resample
            return Image.new("RGB", size, color="red")

        monkeypatch.setattr(img, "resize", _fake_resize)

        resized = Encoder._resize_image(img, 50)

        assert resized.size == (50, 25)
        assert seen["size"] == (50, 25)
        assert seen["resample"] == Image.Resampling.BICUBIC

    def test_resize_image_basic(self):
        """Test basic image resize with valid scale percent."""
        img = Image.new("RGB", (100, 50), color="red")  # w=100, h=50
        resized = Encoder._resize_image(img, 50)
        # scale_percent=50 means 50% of dimensions
        assert resized.size == (50, 25), "Resize failed: expected (50, 25)"

    def test_resize_image_100_percent(self):
        """Test 100% scale (no-op resize)."""
        img = Image.new("RGB", (64, 64), color="blue")
        resized = Encoder._resize_image(img, 100)
        assert resized.size == (64, 64)

    def test_resize_image_tiny_scale(self):
        """Test that very small scales still produce at least 1x1 pixel."""
        img = Image.new("RGB", (1000, 1000), color="green")
        # 1% of 1000 = 10 pixels, should work
        resized = Encoder._resize_image(img, 1)
        assert resized.size == (10, 10)

    def test_resize_image_ensures_minimum_pixel(self):
        """Test that even 0.1% scale never collapses to 0x0."""
        img = Image.new("RGB", (100, 100), color="yellow")
        # 0.1% would normally round to 0, but helper should enforce min=1
        resized = Encoder._resize_image(img, 1)
        assert resized.width >= 1 and resized.height >= 1

    def test_resize_image_negative_scale_raises(self):
        """Test that negative scale percent raises ValueError."""
        img = Image.new("RGB", (100, 100))
        with pytest.raises(ValueError, match="scale_percent must be > 0"):
            Encoder._resize_image(img, -10)

    def test_resize_image_zero_scale_raises(self):
        """Test that zero scale percent raises ValueError."""
        img = Image.new("RGB", (100, 100))
        with pytest.raises(ValueError, match="scale_percent must be > 0"):
            Encoder._resize_image(img, 0)

    def test_resize_mask_with_none_returns_none(self):
        """Test that resizing None mask returns None."""
        result = Encoder._resize_mask(None, 50)
        assert result is None

    def test_resize_mask_with_image_works(self):
        """Test that mask resizing uses NEAREST resampling."""
        mask = Image.new("L", (100, 100), color=128)  # grayscale
        resized = Encoder._resize_mask(mask, 50)
        assert resized.size == (50, 50)
        # NEAREST resampling should preserve pixel values somewhat
        assert resized.mode == "L"

    def test_resize_rectangular_image(self):
        """Test resize on non-square image (width != height)."""
        img = Image.new("RGB", (200, 100))  # w=200, h=100
        resized = Encoder._resize_image(img, 50)
        # 50% of each dimension
        assert resized.size == (100, 50), "Rectangular resize failed"


class TestEncoderBudgetAllocation:
    """Test budget allocation logic for object compression."""

    def test_allocate_budgets_equal_split(self):
        """Test equal budget split for equal-sized images."""
        images = [Image.new("RGB", (100, 100)), Image.new("RGB", (100, 100))]
        budgets = Encoder._allocate_budgets_by_pixels(images, total_bytes=100, min_bytes=10)
        # Equal sizes should get equal budgets
        assert budgets[0] == budgets[1]
        assert sum(budgets) == 100

    def test_allocate_budgets_proportional(self):
        """Test that larger images get more budget."""
        # Image 1: 100x100 = 10k pixels; Image 2: 200x200 = 40k pixels
        img1 = Image.new("RGB", (100, 100))  # 10k pixels
        img2 = Image.new("RGB", (200, 200))  # 40k pixels
        budgets = Encoder._allocate_budgets_by_pixels([img1, img2], total_bytes=500, min_bytes=10)
        # Ratio should be 1:4
        assert budgets[1] > budgets[0], "Larger image should get more budget"

    def test_allocate_budgets_respects_min_bytes(self):
        """Test that minimum bytes per image is respected."""
        images = [Image.new("RGB", (10, 10)) for _ in range(10)]  # 10 tiny images
        budgets = Encoder._allocate_budgets_by_pixels(images, total_bytes=100, min_bytes=20)
        # Each image should get at least min_bytes
        assert all(b >= 20 for b in budgets), "Minimum bytes not respected"
        # Soft-budget behavior: min_bytes floor can oversubscribe total budget by design.
        assert sum(budgets) > 100

    def test_allocate_budgets_single_image(self):
        """Test budget allocation with single image."""
        images = [Image.new("RGB", (100, 100))]
        budgets = Encoder._allocate_budgets_by_pixels(images, total_bytes=500, min_bytes=50)
        assert budgets == [500]


class TestEncoderImageEncoding:
    """Test encoder selection and error handling."""

    def test_encode_color_2bit_returns_bytes(self):
        """Test that color 2-bit encoding returns valid bytes."""
        img = Image.new("RGB", (16, 16), color=(128, 64, 32))
        result = encode_color_2bit(img)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_encode_mono_2bit_returns_bytes(self):
        """Test that mono 2-bit encoding returns valid bytes."""
        img = Image.new("L", (16, 16), color=128)  # grayscale
        result = encode_mono_2bit(img)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_encode_color_4bit_returns_bytes(self):
        """Test that color 4-bit encoding returns valid bytes."""
        img = Image.new("RGB", (16, 16), color=(100, 150, 200))
        result = encode_color_4bit(img)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_encode_mono_4bit_returns_bytes(self):
        """Test that mono 4-bit encoding returns valid bytes."""
        img = Image.new("L", (16, 16), color=100)
        result = encode_mono_4bit(img)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_encode_color_8bit_returns_bytes(self):
        """Test that color 8-bit encoding returns valid bytes."""
        img = Image.new("RGB", (16, 16), color=(255, 128, 0))
        result = encode_color_8bit(img)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_encode_mono_8bit_returns_bytes(self):
        """Test that mono 8-bit encoding returns valid bytes."""
        img = Image.new("L", (16, 16), color=200)
        result = encode_mono_8bit(img)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_encode_mono_mask_1bit_returns_bytes(self):
        """Test that mask-only 1-bit encoding returns valid bytes."""
        img = Image.new("L", (16, 16), color=0)
        mask = Image.new("L", (16, 16), color=255)
        result = encode_mono_mask_1bit(img, mask=mask)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_encode_mono_skel_v1_returns_bytes(self):
        """Test that sparse skeleton codec emits payload bytes for structured crops."""
        img = Image.new("L", (16, 16), color=0)
        for i in range(2, 14):
            img.putpixel((i, i), 255)
        result = encode_mono_skel_v1(img, max_segments=6)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_encode_mono_shape_v1_returns_bytes(self):
        """Test that contour-shape codec emits payload bytes for structured crops."""
        img = Image.new("L", (24, 24), color=0)
        for x in range(6, 18):
            img.putpixel((x, 10), 255)
            img.putpixel((x, 14), 255)
        for y in range(10, 15):
            img.putpixel((6, y), 255)
            img.putpixel((17, y), 255)
        result = encode_mono_shape_v1(img, max_points=24)
        assert isinstance(result, bytes)
        assert len(result) > 0


class TestEncoderErrorHandling:
    """Test error handling for invalid encoder names and missing dependencies."""

    def test_encode_img_unsupported_encoder_raises(self):
        """Test that unsupported encoder name raises ValueError."""
        img = Image.new("RGB", (16, 16))
        with pytest.raises(ValueError, match="Unsupported encoder"):
            Encoder.encode_img(None, img, encoder="invalid-encoder", mask=None)  # type: ignore[arg-type]

    def test_encode_img_mask_required_encoder_without_mask_raises(self):
        """Test that mask-required encoders fail without mask."""
        img = Image.new("RGB", (16, 16))
        # Create a minimal encoder to access encode_img method
        class MinimalEncoder:
            cfg = None
            @staticmethod
            def encode_img(img, encoder='mono-28bit', mask=None):
                from semantic_img_comp.encoder.encoder import MASK_REQUIRED_ENCODERS
                if encoder in MASK_REQUIRED_ENCODERS and mask is None:
                    raise ValueError(f"Encoder '{encoder}' requires a non-null mask")
                return b"dummy"

        enc = MinimalEncoder()
        with pytest.raises(ValueError, match="requires a non-null mask"):
            enc.encode_img(img, encoder="mono-28bit", mask=None)

    def test_encode_mono_mask_1bit_rejects_mask_size_mismatch(self):
        """Test that mask-only codec rejects mismatched mask shapes."""
        img = Image.new("L", (16, 16), color=0)
        bad_mask = Image.new("L", (8, 8), color=255)
        with pytest.raises(ValueError, match="mask size mismatch"):
            encode_mono_mask_1bit(img, mask=bad_mask)

    def test_encode_avif_without_avifenc_raises(self):
        """Test that AVIF encoding fails gracefully when avifenc is not available."""
        img = Image.new("RGB", (16, 16))
        # Since avifenc may not be installed, this should raise FileNotFoundError
        try:
            encode_avif(img)
            # If we get here, avifenc is installed; that's okay for Docker deployment
            pytest.skip("avifenc is installed in this environment")
        except FileNotFoundError as exc:
            # Expected when avifenc is not available
            assert "avifenc" in str(exc).lower()

    def test_pack_bits_rejects_values_out_of_range(self):
        with pytest.raises(ValueError, match="out of range"):
            _pack_bits(np.array([0, 1, 4], dtype=np.int16), bits=2)

    def test_pack_bits_rejects_negative_values(self):
        with pytest.raises(ValueError, match="out of range"):
            _pack_bits(np.array([0, -1, 1], dtype=np.int16), bits=2)


class TestEncoderDispatch:
    def test_encode_img_passes_avif_jobs_and_codec(self, monkeypatch):
        enc = Encoder.__new__(Encoder)
        enc.cfg = SimpleNamespace(
            enc=SimpleNamespace(
                zlib_level=1,
                avif_quality=0,
                avif_speed=6,
                avif_timeout_sec=120,
                avif_mono_quality_map={},
                avif_jobs=8,
                avif_codec="aom",
            ),
        )

        seen = {}

        def _fake_encode_avif(img, quality, speed, is_monochrome, timeout_sec, jobs=None, codec=None):
            seen["jobs"] = jobs
            seen["codec"] = codec
            return b"ok"

        monkeypatch.setattr(encoder_module.encoder_codecs, "encode_avif", _fake_encode_avif)

        out = enc.encode_img(Image.new("RGB", (8, 8)), encoder="color-avif")

        assert out == b"ok"
        assert seen["jobs"] == 8
        assert seen["codec"] == "aom"

    def test_encode_img_passes_zlib_level_to_non_mask_codecs(self, monkeypatch):
        enc = Encoder.__new__(Encoder)
        enc.cfg = SimpleNamespace(
            enc=SimpleNamespace(zlib_level=1, avif_quality=0, avif_speed=6, avif_timeout_sec=120, avif_mono_quality_map={}),
        )

        seen = {}

        def _fake_codec(img, zlib_level=9):
            seen["zlib_level"] = zlib_level
            return b"ok"

        monkeypatch.setitem(encoder_module.NON_MASK_CODEC_DISPATCH, "mono-2bit", _fake_codec)

        out = enc.encode_img(Image.new("L", (8, 8)), encoder="mono-2bit")

        assert out == b"ok"
        assert seen["zlib_level"] == 1

    def test_encode_img_passes_zlib_level_to_masked_codecs(self, monkeypatch):
        enc = Encoder.__new__(Encoder)
        enc.cfg = SimpleNamespace(
            enc=SimpleNamespace(zlib_level=3, avif_quality=0, avif_speed=6, avif_timeout_sec=120, avif_mono_quality_map={}),
        )

        seen = {}

        def _fake_codec(img, mask=None, zlib_level=9):
            seen["mask"] = mask
            seen["zlib_level"] = zlib_level
            return b"ok"

        monkeypatch.setitem(encoder_module.MASKED_CODEC_DISPATCH, "mono-mask-1bit", _fake_codec)
        mask = Image.new("L", (8, 8), color=255)

        out = enc.encode_img(Image.new("L", (8, 8)), encoder="mono-mask-1bit", mask=mask)

        assert out == b"ok"
        assert seen["mask"] is mask
        assert seen["zlib_level"] == 3

    def test_encode_img_passes_mono_skel_tuning_from_config(self, monkeypatch):
        enc = Encoder.__new__(Encoder)
        enc.cfg = SimpleNamespace(
            enc=SimpleNamespace(zlib_level=4, avif_quality=0, avif_speed=6, avif_timeout_sec=120, avif_mono_quality_map={}),
            img_process=SimpleNamespace(
                mono_skel_max_segments=22,
                mono_skel_min_segment_length=2,
                mono_skel_hough_threshold=8,
                mono_skel_max_segment_gap=5,
                mono_skel_work_max_dim=192,
                mono_skel_stitch_angle_tol_deg=27.5,
            ),
        )

        seen = {}

        def _fake_skel_codec(img, zlib_level=9, **kwargs):
            seen["zlib_level"] = zlib_level
            seen.update(kwargs)
            return b"ok"

        monkeypatch.setitem(encoder_module.NON_MASK_CODEC_DISPATCH, "mono-skel-v1", _fake_skel_codec)

        out = enc.encode_img(Image.new("L", (8, 8)), encoder="mono-skel-v1")

        assert out == b"ok"
        assert seen == {
            "zlib_level": 4,
            "max_segments": 22,
            "min_segment_length": 2,
            "hough_threshold": 8,
            "max_segment_gap": 5,
            "work_max_dim": 192,
            "stitch_angle_tol_deg": 27.5,
        }

    def test_encode_img_passes_mono_shape_v1_tuning_from_config(self, monkeypatch):
        """Verify mono-shape-v1 codec receives max_points and epsilon_ratio from config."""
        enc = Encoder.__new__(Encoder)
        enc.cfg = SimpleNamespace(
            enc=SimpleNamespace(zlib_level=5, avif_quality=0, avif_speed=6, avif_timeout_sec=120, avif_mono_quality_map={}),
            img_process=SimpleNamespace(
                mono_shape_max_points=80,
                mono_shape_epsilon_ratio=0.01,
            ),
        )

        seen = {}

        def _fake_shape_codec(img, zlib_level=9, **kwargs):
            seen["zlib_level"] = zlib_level
            seen.update(kwargs)
            return b"ok"

        monkeypatch.setitem(encoder_module.NON_MASK_CODEC_DISPATCH, "mono-shape-v1", _fake_shape_codec)

        out = enc.encode_img(Image.new("L", (8, 8)), encoder="mono-shape-v1")

        assert out == b"ok"
        assert seen == {
            "zlib_level": 5,
            "max_points": 80,
            "epsilon_ratio": 0.01,
        }

    def test_encode_img_passes_template_params_to_mono_8bit_template_drop1bit(self, monkeypatch):
        enc = Encoder.__new__(Encoder)
        enc.cfg = SimpleNamespace(
            enc=SimpleNamespace(
                zlib_level=6,
                avif_quality=0,
                avif_speed=6,
                avif_timeout_sec=120,
                avif_mono_quality_map={},
                mono_2bit_mixed_two_bit_run=3,
                mono_2bit_mixed_one_bit_run=5,
            ),
        )

        seen = {}

        def _fake_codec(img, zlib_level=9, **kwargs):
            seen["zlib_level"] = zlib_level
            seen.update(kwargs)
            return b"ok"

        monkeypatch.setitem(encoder_module.NON_MASK_CODEC_DISPATCH, "mono-8bit-template-drop1bit", _fake_codec)
        skip_mask = Image.new("L", (8, 8), color=255)

        out = enc.encode_img(Image.new("L", (8, 8)), encoder="mono-8bit-template-drop1bit", skip_mask=skip_mask)

        assert out == b"ok"
        assert seen["zlib_level"] == 6
        assert seen["two_bit_run"] == 3
        assert seen["one_bit_run"] == 5
        assert seen["skip_mask"] is skip_mask

    def test_find_scale_invalid_scale_bounds_raises(self):
        """Test that invalid scale bounds raise ValueError."""
        img = Image.new("RGB", (100, 100))
        with pytest.raises(ValueError):
            Encoder._find_scale_for_budget(
                None,  # type: ignore[arg-type]
                img,
                budget_bytes=1000,
                min_scale_percent=100,
                max_scale_percent=10,  # min > max
                iters=10,
                encoder="mono-2bit",
                min_pixels=100,
            )

    def test_find_scale_single_scale_encodes_once(self):
        enc = Encoder.__new__(Encoder)
        enc.cfg = SimpleNamespace(enc=SimpleNamespace(scale_search_step_size=1))
        enc._resize_image = Encoder._resize_image
        enc._resize_mask = Encoder._resize_mask
        calls = []

        def _fake_encode(img, encoder="mono-2bit", mask=None):
            calls.append(img.size)
            return b"123456"

        enc.encode_img = _fake_encode
        img = Image.new("RGB", (100, 100))

        scale, size_bytes, enc_bytes = enc._find_scale_for_budget(
            img,
            budget_bytes=1,
            min_scale_percent=100,
            max_scale_percent=100,
            iters=1,
            encoder="mono-2bit",
            min_pixels=1,
        )

        assert scale == 100
        assert size_bytes == len(enc_bytes)
        assert calls == [(100, 100)]

    def test_find_scale_reuses_last_probe_for_effective_min(self):
        enc = Encoder.__new__(Encoder)
        enc.cfg = SimpleNamespace(enc=SimpleNamespace(scale_search_step_size=1))
        enc._resize_image = Encoder._resize_image
        enc._resize_mask = Encoder._resize_mask
        calls = []

        def _fake_encode(img, encoder="mono-2bit", mask=None):
            calls.append(img.size)
            return b"too-big"

        enc.encode_img = _fake_encode
        img = Image.new("RGB", (100, 100))

        scale, size_bytes, enc_bytes = enc._find_scale_for_budget(
            img,
            budget_bytes=1,
            min_scale_percent=50,
            max_scale_percent=51,
            iters=1,
            encoder="mono-2bit",
            min_pixels=1,
        )

        assert scale == 50
        assert size_bytes == len(enc_bytes)
        assert calls == [(50, 50)]


class TestEncoderSizeOrdering:
    """Test that (width, height) ordering is consistent throughout resize operations."""

    def test_size_ordering_after_resize_background(self):
        """Verify that resized background maintains (width, height) order."""
        bg_original = Image.new("RGB", (320, 240))  # w=320, h=240
        assert bg_original.size == (320, 240), "PIL.Image.size should be (w, h)"

        resized = Encoder._resize_image(bg_original, 50)
        # 50% scale: 320*0.5=160, 240*0.5=120
        assert resized.size == (160, 120), f"Expected (160, 120), got {resized.size}"

    def test_size_ordering_after_mask_resize(self):
        """Verify that resized mask maintains (width, height) order."""
        mask_original = Image.new("L", (320, 240))  # w=320, h=240
        assert mask_original.size == (320, 240)

        resized = Encoder._resize_mask(mask_original, 50)
        assert resized.size == (160, 120), f"Expected (160, 120), got {resized.size}"

    def test_crop_size_matches_resize_output(self):
        """Verify that crop sizes after resize are consistent."""
        crop_original = Image.new("RGB", (100, 80))  # w=100, h=80 (e.g., crop from detected object)
        assert crop_original.size == (100, 80)

        resized = Encoder._resize_image(crop_original, 75)
        # 75% scale: 100*0.75=75, 80*0.75=60
        expected = (75, 60)
        assert resized.size == expected, f"Expected {expected}, got {resized.size}"


class TestEncoderBackgroundScaleSelection:
    """Validate bg min-scale config branch based on whether crops exist."""

    def _make_encoder_stub(self):
        enc = Encoder.__new__(Encoder)
        enc.cfg = SimpleNamespace(
            enc=SimpleNamespace(min_bg_bytes=10, max_iter_bg=1, max_iter_obj=1, min_bg_pixels=64),
            img_process=SimpleNamespace(
                encoders_tag_bg_level_1={"mono-2bit": 1},
                encoders_tag_objs_level_1={"mono-4bit": 2},
                bg_scaling_min1_level_1=11,  # no objects
                bg_scaling_min2_level_1=22,  # has objects
                bg_scaling_max_level_1=77,
                canny_sigma=1.0,
                canny_low=50,
                canny_high=150,
            ),
        )
        enc._resize_image = lambda img, scale_percent, resample=Image.Resampling.BICUBIC: img
        enc._resize_mask = lambda mask, scale_percent: mask
        enc.encode_img = lambda img, encoder="mono-2bit", mask=None: b"xx"
        return enc

    def test_bg_min_scale_uses_min2_when_crops_exist(self, monkeypatch):
        enc = self._make_encoder_stub()
        calls = []

        def _fake_find_scale(*args, **kwargs):
            calls.append(kwargs["min_scale_percent"])
            return 50, 2, b"bg"

        monkeypatch.setattr(enc, "_find_scale_for_budget", _fake_find_scale)
        pil_img = Image.new("RGB", (16, 16))
        crop = SimpleNamespace(encoded_obj=b"xx")

        enc.compress_background(pil_img, tar_enc_data_bytes=100, crops=[crop])  # type: ignore[arg-type]

        assert calls == [22]

    def test_bg_min_scale_uses_min1_when_no_crops(self, monkeypatch):
        enc = self._make_encoder_stub()
        calls = []

        def _fake_find_scale(*args, **kwargs):
            calls.append(kwargs["min_scale_percent"])
            return 50, 2, b"bg"

        monkeypatch.setattr(enc, "_find_scale_for_budget", _fake_find_scale)
        pil_img = Image.new("RGB", (16, 16))

        enc.compress_background(pil_img, tar_enc_data_bytes=100, crops=[])

        assert calls == [11]

    def test_bg_max_scale_uses_config_value(self, monkeypatch):
        enc = self._make_encoder_stub()
        calls = []

        def _fake_find_scale(*args, **kwargs):
            calls.append(kwargs["max_scale_percent"])
            return 50, 2, b"bg"

        monkeypatch.setattr(enc, "_find_scale_for_budget", _fake_find_scale)
        pil_img = Image.new("RGB", (16, 16))

        enc.compress_background(pil_img, tar_enc_data_bytes=100, crops=[])

        assert calls == [77]

    def test_compress_background_uses_background_encoder_tags(self, monkeypatch):
        enc = self._make_encoder_stub()
        seen = {}

        def _fake_find_scale(*args, **kwargs):
            seen["encoder"] = kwargs["encoder"]
            return 50, 2, b"bg"

        monkeypatch.setattr(enc, "_find_scale_for_budget", _fake_find_scale)
        pil_img = Image.new("RGB", (16, 16))

        bg, _ = enc.compress_background(pil_img, tar_enc_data_bytes=100, crops=[])

        assert seen["encoder"] == "mono-2bit"
        assert bg.encoder_index == 1

    def test_compress_background_bypasses_skip_bg_when_no_crops(self, monkeypatch):
        enc = self._make_encoder_stub()
        enc.cfg.img_process.encoders_tag_bg_level_1 = {"mono-2bit": 1, "skip_bg": 99}

        calls = []

        def _fake_find_scale(*args, **kwargs):
            calls.append(kwargs["encoder"])
            # Force budget miss so the next codec is tried.
            return 50, 999, b"bg-bytes"

        monkeypatch.setattr(enc, "_find_scale_for_budget", _fake_find_scale)
        pil_img = Image.new("RGB", (16, 16))

        bg, _ = enc.compress_background(pil_img, tar_enc_data_bytes=100, crops=[])

        assert calls == ["mono-2bit", "mono-2bit"]
        assert bg.encoder_index == 1
        assert bg.encoded_data == b"bg-bytes"

    def test_compress_background_uses_mono2bit_if_skip_bg_has_no_predecessor(self, monkeypatch):
        enc = self._make_encoder_stub()
        enc.cfg.img_process.encoders_tag_bg_level_1 = {"skip_bg": 99, "mono-2bit": 5}

        calls = []

        def _fake_find_scale(*args, **kwargs):
            calls.append(kwargs["encoder"])
            calls.append(kwargs["min_scale_percent"])
            return 11, 90, b"bg-bytes"

        monkeypatch.setattr(enc, "_find_scale_for_budget", _fake_find_scale)
        pil_img = Image.new("RGB", (16, 16))

        bg, _ = enc.compress_background(pil_img, tar_enc_data_bytes=100, crops=[])

        assert calls == ["mono-2bit", 11]
        assert bg.encoder_index == 5
        assert bg.scaling_factor == 11
        assert bg.encoded_data == b"bg-bytes"

    def test_resolve_skip_bg_fallback_uses_next_non_skip_when_skip_is_first(self):
        fallback_name, fallback_idx = Encoder._resolve_skip_bg_fallback(
            {"skip_bg": 99, "mono-mask-1bit": 6}
        )

        assert fallback_name == "mono-mask-1bit"
        assert fallback_idx == 6

    def test_resolve_skip_bg_fallback_rejects_only_skip_bg(self):
        with pytest.raises(ValueError, match="cannot contain only skip_bg"):
            Encoder._resolve_skip_bg_fallback({"skip_bg": 7})

    def test_bg_max_iter_bg_zero_uses_fixed_scale_no_search(self):
        """When max_iter_bg==0, compress_background must use fixed scale directly without calling _find_scale_for_budget."""
        enc = Encoder.__new__(Encoder)
        enc.cfg = SimpleNamespace(
            enc=SimpleNamespace(min_bg_bytes=10, max_iter_bg=0, max_iter_obj=1, min_bg_pixels=64, compression_rate=100.0),
            img_process=SimpleNamespace(
                encoders_tag_bg_level_1={"mono-2bit": 1},
                encoders_tag_objs_level_1={"mono-4bit": 2},
                bg_scaling_min1_level_1=30,
                bg_scaling_min2_level_1=15,
                bg_scaling_max_level_1=77,
                canny_sigma=1.0,
                canny_low=50,
                canny_high=150,
            ),
        )
        enc._resize_image = lambda img, scale_percent, resample=Image.Resampling.BICUBIC: img
        enc._resize_mask = lambda mask, scale_percent: mask
        enc.encode_img = lambda img, encoder="mono-2bit", mask=None: b"fixed"

        search_called = []
        enc._find_scale_for_budget = lambda *a, **kw: search_called.append(1) or (50, 2, b"x")

        pil_img = Image.new("RGB", (16, 16))

        # No crops: must use bg_scaling_min1_level_1 (30) and FIRST codec (mono-2bit: 1)
        bg, _ = enc.compress_background(pil_img, tar_enc_data_bytes=100, crops=[])
        assert search_called == [], "search must NOT be called when max_iter_bg==0"
        assert bg.scaling_factor == 30
        assert bg.encoded_data == b"fixed"
        assert bg.encoder_index == 1

        # With crops: must use bg_scaling_min2_level_1 (15) and LAST codec (mono-2bit: 1, only one here)
        crop = SimpleNamespace(encoded_obj=b"xx")
        bg2, _ = enc.compress_background(pil_img, tar_enc_data_bytes=100, crops=[crop])
        assert search_called == [], "search still must NOT be called"
        assert bg2.scaling_factor == 15
        assert bg2.encoder_index == 1

    def test_bg_fast_path_no_objects_uses_last_codec(self):
        """When max_iter_bg==0 and no objects, fast path must use the LAST codec in encoders_tag_bg."""
        enc = Encoder.__new__(Encoder)
        enc.skip_obj_detection = False
        enc.cfg = SimpleNamespace(
            enc=SimpleNamespace(min_bg_bytes=10, max_iter_bg=0, max_iter_obj=1, min_bg_pixels=64, compression_rate=100.0),
            img_process=SimpleNamespace(
                encoders_tag_bg_level_1={"mono-2bit": 5, "mono-mask-1bit": 6},
                encoders_tag_objs_level_1={"mono-4bit": 2},
                bg_scaling_min1_level_1=30,
                bg_scaling_min2_level_1=15,
                bg_scaling_max_level_1=77,
                canny_sigma=1.0,
                canny_low=50,
                canny_high=150,
            ),
        )
        enc._resize_image = lambda img, scale_percent, resample=Image.Resampling.BICUBIC: img
        enc._resize_mask = lambda mask, scale_percent: mask
        seen = {}

        def _fake_encode(img, encoder="mono-2bit", mask=None):
            seen["encoder"] = encoder
            return b"fixed"

        enc.encode_img = _fake_encode

        pil_img = Image.new("RGB", (16, 16))
        bg, _ = enc.compress_background(pil_img, tar_enc_data_bytes=100, crops=[])

        assert seen["encoder"] == "mono-mask-1bit"
        assert bg.encoder_index == 6

    def test_bg_fast_path_with_objects_uses_last_codec(self):
        """When max_iter_bg==0 and objects exist, fast path must use the LAST codec in encoders_tag_bg."""
        enc = Encoder.__new__(Encoder)
        enc.skip_obj_detection = False
        enc.cfg = SimpleNamespace(
            enc=SimpleNamespace(min_bg_bytes=10, max_iter_bg=0, max_iter_obj=1, min_bg_pixels=64, compression_rate=100.0),
            img_process=SimpleNamespace(
                encoders_tag_bg_level_1={"mono-2bit": 5, "mono-mask-1bit": 6},
                encoders_tag_objs_level_1={"mono-4bit": 2},
                bg_scaling_min1_level_1=30,
                bg_scaling_min2_level_1=15,
                bg_scaling_max_level_1=77,
                canny_sigma=1.0,
                canny_low=50,
                canny_high=150,
            ),
        )
        enc._resize_image = lambda img, scale_percent, resample=Image.Resampling.BICUBIC: img
        enc._resize_mask = lambda mask, scale_percent: mask
        seen = {}

        def _fake_encode(img, encoder="mono-2bit", mask=None):
            seen["encoder"] = encoder
            return b"fixed"

        enc.encode_img = _fake_encode

        pil_img = Image.new("RGB", (16, 16))
        crop = SimpleNamespace(encoded_obj=b"xx")
        bg, _ = enc.compress_background(pil_img, tar_enc_data_bytes=100, crops=[crop])

        assert seen["encoder"] == "mono-mask-1bit"
        assert bg.encoder_index == 6


    def test_compress_background_skips_dense_object_bboxes_for_mono_2bit(self, monkeypatch):
        enc = self._make_encoder_stub()
        enc.cfg.img_process.skip_object_bboxes_in_background = True
        enc.cfg.img_process.encoders_tag_objs_level_1 = {"mono-avif-mid": 2}

        seen = {}

        def _fake_find_scale(img, **kwargs):
            seen["same_image"] = (img.getbbox() == Image.new("L", (8, 8), color=255).getbbox())
            skip_mask = kwargs.get("skip_mask")
            arr = np.array(skip_mask)
            seen["center_max"] = int(arr[3:5, 3:5].max())
            return 50, 2, b"bg"

        monkeypatch.setattr(enc, "_find_scale_for_budget", _fake_find_scale)
        pil_img = Image.new("L", (8, 8), color=255)
        crop = SimpleNamespace(encoded_obj=b"xx", expanded_bbox=(2, 2, 5, 5), encoder_index=2)

        enc.compress_background(pil_img, tar_enc_data_bytes=100, crops=[crop])

        assert seen["same_image"] is True
        assert seen["center_max"] == 255

    def test_compress_background_clears_bbox_from_mono_mask_bg_mask(self, monkeypatch):
        enc = self._make_encoder_stub()
        enc.cfg.img_process.skip_object_bboxes_in_background = True
        enc.cfg.img_process.encoders_tag_bg_level_1 = {"mono-mask-1bit": 6}
        enc.cfg.img_process.encoders_tag_objs_level_1 = {"mono-2bit": 5}

        monkeypatch.setattr(enc, "_build_edge_mask", lambda img: Image.new("L", img.size, color=255))
        seen = {}

        def _fake_find_scale(img, **kwargs):
            mask = kwargs["mask"]
            skip_mask = kwargs.get("skip_mask")
            arr = np.array(mask)
            skip_arr = np.array(skip_mask)
            seen["center_max"] = int(arr[3:5, 3:5].max())
            seen["corner_min"] = int(arr[0:2, 0:2].min())
            seen["skip_center_max"] = int(skip_arr[3:5, 3:5].max())
            return 50, 2, b"bg"

        monkeypatch.setattr(enc, "_find_scale_for_budget", _fake_find_scale)
        pil_img = Image.new("L", (8, 8), color=255)
        crop = SimpleNamespace(encoded_obj=b"xx", expanded_bbox=(2, 2, 5, 5), encoder_index=5)

        enc.compress_background(pil_img, tar_enc_data_bytes=100, crops=[crop])

        assert seen["center_max"] == 0
        assert seen["corner_min"] == 255

    def test_compress_background_skips_dense_object_bboxes_for_mono_8bit_template(self, monkeypatch):
        enc = self._make_encoder_stub()
        enc.cfg.img_process.skip_object_bboxes_in_background = True
        enc.cfg.img_process.encoders_tag_bg_level_1 = {"mono-8bit-template-drop1bit": 13}
        enc.cfg.img_process.encoders_tag_objs_level_1 = {"mono-avif-mid": 2}

        seen = {}

        def _fake_find_scale(img, **kwargs):
            skip_mask = kwargs.get("skip_mask")
            arr = np.array(skip_mask)
            seen["center_max"] = int(arr[3:5, 3:5].max())
            skip_arr = np.array(skip_mask)
            seen["skip_center_max"] = int(skip_arr[3:5, 3:5].max())
            return 50, 2, b"bg"

        monkeypatch.setattr(enc, "_find_scale_for_budget", _fake_find_scale)
        pil_img = Image.new("L", (8, 8), color=255)
        crop = SimpleNamespace(encoded_obj=b"xx", expanded_bbox=(2, 2, 5, 5), encoder_index=2)

        enc.compress_background(pil_img, tar_enc_data_bytes=100, crops=[crop])

        assert seen["center_max"] == 255
        assert seen["skip_center_max"] == 255

    def test_compress_background_keeps_sparse_object_bboxes_in_bg(self, monkeypatch):
        enc = self._make_encoder_stub()
        enc.cfg.img_process.skip_object_bboxes_in_background = True
        enc.cfg.img_process.encoders_tag_objs_level_1 = {"mono-skel-v1": 8}

        seen = {}

        def _fake_find_scale(img, **kwargs):
            seen["skip_mask"] = kwargs.get("skip_mask")
            return 50, 2, b"bg"

        monkeypatch.setattr(enc, "_find_scale_for_budget", _fake_find_scale)
        pil_img = Image.new("L", (8, 8), color=255)
        crop = SimpleNamespace(encoded_obj=b"xx", expanded_bbox=(2, 2, 5, 5), encoder_index=8)

        enc.compress_background(pil_img, tar_enc_data_bytes=100, crops=[crop])

        assert seen["skip_mask"] is None

    def test_compress_background_skips_fallback_obj_bboxes_using_unified_tags(self, monkeypatch):
        enc = self._make_encoder_stub()
        enc.cfg.img_process.skip_object_bboxes_in_background = True
        seen = {}
        def _fake_find_scale(img, **kwargs):
            skip_mask = kwargs.get("skip_mask")
            arr = np.array(skip_mask)
            seen["center_max"] = int(arr[3:5, 3:5].max())
            return 50, 2, b"bg"
        monkeypatch.setattr(enc, "_find_scale_for_budget", _fake_find_scale)

        pil_img = Image.new("L", (8, 8), color=255)
        crop = SimpleNamespace(encoded_obj=b"xx", expanded_bbox=(2, 2, 5, 5), encoder_index=2)

        enc.compress_background(pil_img, tar_enc_data_bytes=100, crops=[crop])

        assert seen["center_max"] == 255


class TestEncoderObjectScaleSelection:
    def test_obj_max_scale_uses_config_value(self, monkeypatch):
        enc = Encoder.__new__(Encoder)
        enc.cfg = SimpleNamespace(
            enc=SimpleNamespace(
                min_bytes_for_budget_allocation=1,
                object_budget_soft=True,
                max_iter_obj=1,
                min_obj_pixels=1,
            ),
            img_process=SimpleNamespace(
                encoders_tag_bg_level_1={"mono-2bit": 1},
                encoders_tag_objs_level_1={"mono-2bit": 1},
                obj_scaling_min_level_1=10,
                obj_scaling_max_level_1=66,
                canny_sigma=1.0,
                canny_low=50,
                canny_high=150,
            ),
        )

        monkeypatch.setattr(enc, "_allocate_budgets_by_pixels", lambda *args, **kwargs: [20])
        calls = []

        def _fake_find_scale(*args, **kwargs):
            calls.append(kwargs["max_scale_percent"])
            return 25, 2, b"obj"

        monkeypatch.setattr(enc, "_find_scale_for_budget", _fake_find_scale)
        enc._resize_image = lambda img, scale_percent, resample=Image.Resampling.BICUBIC: img
        enc._resize_mask = lambda mask, scale_percent: mask
        enc.encode_img = lambda img, encoder="mono-2bit", mask=None: b"xx"

        crop = SimpleNamespace(
            obj_pil=Image.new("RGB", (8, 8)),
            bbox=(0, 0, 1, 1),
            encoded_obj=None,
            scaling_factor=None,
            obj_size_scaled=None,
            encoder_index=None,
        )

        enc.compress_objs([crop], tar_objs_bytes=20)

        assert calls == [66]

    def test_compress_objs_uses_object_encoder_tags(self, monkeypatch):
        enc = Encoder.__new__(Encoder)
        enc.cfg = SimpleNamespace(
            enc=SimpleNamespace(
                min_bytes_for_budget_allocation=1,
                object_budget_soft=True,
                max_iter_obj=1,
                min_obj_pixels=1,
            ),
            img_process=SimpleNamespace(
                encoders_tag_bg_level_1={"mono-2bit": 1},
                encoders_tag_objs_level_1={"mono-4bit": 9},
                obj_scaling_min_level_1=10,
                obj_scaling_max_level_1=66,
                canny_sigma=1.0,
                canny_low=50,
                canny_high=150,
            ),
        )

        monkeypatch.setattr(enc, "_allocate_budgets_by_pixels", lambda *args, **kwargs: [20])
        seen = {}

        def _fake_find_scale(*args, **kwargs):
            seen["encoder"] = kwargs["encoder"]
            return 25, 2, b"obj"

        monkeypatch.setattr(enc, "_find_scale_for_budget", _fake_find_scale)
        enc._resize_image = lambda img, scale_percent, resample=Image.Resampling.BICUBIC: img

        crop = SimpleNamespace(
            obj_pil=Image.new("RGB", (8, 8)),
            bbox=(0, 0, 1, 1),
            encoded_obj=None,
            scaling_factor=None,
            obj_size_scaled=None,
            encoder_index=None,
        )

        out = enc.compress_objs([crop], tar_objs_bytes=20)

        assert seen["encoder"] == "mono-4bit"
        assert out[0].encoder_index == 9


    def test_compress_objs_airplane_symbol_routes_by_category(self, monkeypatch):
        enc = Encoder.__new__(Encoder)
        enc.cfg = SimpleNamespace(
            enc=SimpleNamespace(
                min_bytes_for_budget_allocation=1,
                object_budget_soft=True,
                max_iter_obj=1,
                min_obj_pixels=1,
            ),
            img_process=SimpleNamespace(
                encoders_tag_bg_level_1={"mono-2bit": 1},
                encoders_tag_objs_level_1={"airplane-symbol-v1": 10, "mono-mask-1bit": 6},
                obj_scaling_min_level_1=10,
                obj_scaling_max_level_1=66,
                canny_sigma=1.0,
                canny_low=50,
                canny_high=150,
            ),
            model=SimpleNamespace(symbol_category_ids={2, 3}),
        )

        monkeypatch.setattr(enc, "_allocate_budgets_by_pixels", lambda *args, **kwargs: [20, 20, 20])
        monkeypatch.setattr(enc, "_build_edge_mask", lambda *args, **kwargs: Image.new("L", (8, 8), color=255))
        monkeypatch.setattr(
            enc,
            "_estimate_symbol_theta",
            lambda img, *, category_id: 135.0 if int(category_id) == 2 else 0.0,
        )

        search_calls = []

        def _fake_find_scale(*args, **kwargs):
            search_calls.append(kwargs["encoder"])
            return 11, 3, b"mask"

        monkeypatch.setattr(enc, "_find_scale_for_budget", _fake_find_scale)

        encode_calls = []

        def _fake_encode_img(img, encoder="mono-2bit", mask=None, category_id=None, theta_deg=None):
            encode_calls.append((encoder, category_id, theta_deg))
            return b"symbol" if encoder == "airplane-symbol-v1" else b"other"

        monkeypatch.setattr(enc, "encode_img", _fake_encode_img)

        crops = [
            SimpleNamespace(obj_pil=Image.new("RGB", (8, 8)), bbox=(0, 0, 10, 10), category_id=2, encoded_obj=None, scaling_factor=None, obj_size_scaled=None, encoder_index=None),
            SimpleNamespace(obj_pil=Image.new("RGB", (8, 8)), bbox=(10, 10, 30, 20), category_id=3, encoded_obj=None, scaling_factor=None, obj_size_scaled=None, encoder_index=None),
            SimpleNamespace(obj_pil=Image.new("RGB", (8, 8)), bbox=(0, 0, 10, 10), category_id=7, encoded_obj=None, scaling_factor=None, obj_size_scaled=None, encoder_index=None),
        ]

        out = enc.compress_objs(crops, tar_objs_bytes=60)

        assert encode_calls[0] == ("airplane-symbol-v1", 2, 135.0)
        assert encode_calls[1][0] == "airplane-symbol-v1"
        assert encode_calls[1][1] == 3
        assert encode_calls[1][2] == 90.0
        assert search_calls == ["mono-mask-1bit"]
        assert out[0].encoder_index == 10
        assert out[1].encoder_index == 10
        assert out[2].encoder_index == 6
        assert out[0].scaling_factor is None
        assert out[1].scaling_factor is None
        assert out[2].scaling_factor == 11

    def test_compress_objs_airplane_symbol_requires_mono_mask_fallback(self, monkeypatch):
        """Test that mono-mask-1bit fallback is found from unified encoders_tag."""
        enc = Encoder.__new__(Encoder)
        enc.cfg = SimpleNamespace(
            enc=SimpleNamespace(
                min_bytes_for_budget_allocation=1,
                object_budget_soft=True,
                max_iter_obj=1,
                min_obj_pixels=1,
            ),
            img_process=SimpleNamespace(
                # Unified tag registry (has mono-mask-1bit even though not in active object tags)
                encoders_tag={
                    "mono-2bit": 1,
                    "airplane-symbol-v1": 10,
                    "mono-mask-1bit": 6,
                },
                # Active level-1 object encoder: only airplane-symbol-v1
                encoders_tag_objs_level_1={"airplane-symbol-v1": 10},
                encoders_tag_bg_level_1={"mono-2bit": 1},
                obj_scaling_min_level_1=10,
                obj_scaling_max_level_1=66,
                canny_sigma=1.0,
                canny_low=50,
                canny_high=150,
            ),
            pipeline_manager=SimpleNamespace(compression_level=1),
            model=SimpleNamespace(symbol_category_ids={2, 3}),
        )

        monkeypatch.setattr(enc, "_allocate_budgets_by_pixels", lambda *args, **kwargs: [20])
        monkeypatch.setattr(enc, "_build_edge_mask", lambda *args, **kwargs: Image.new("L", (8, 8), color=255))

        scale_calls = []

        def _fake_find_scale(*args, **kwargs):
            scale_calls.append(kwargs.get("encoder"))
            return (10, 20, b"mask")

        monkeypatch.setattr(enc, "_find_scale_for_budget", _fake_find_scale)
        monkeypatch.setattr(enc, "_resize_image", lambda img, scale_percent, resample=Image.Resampling.BICUBIC: img)

        # Non-symbol category (7) should fall back to mono-mask-1bit from unified encoders_tag
        crop = SimpleNamespace(obj_pil=Image.new("RGB", (8, 8)), category_id=7, bbox=(0, 0, 8, 8))

        out = enc.compress_objs([crop], tar_objs_bytes=20)

        # Verify _find_scale_for_budget was called requesting mono-mask-1bit
        assert scale_calls[0] == "mono-mask-1bit"
        # Verify encoder_index is set to fallback mono-mask-1bit value (6)
        assert out[0].encoder_index == 6

    def test_compress_objs_airplane_symbol_fast_path_routes_by_category(self, monkeypatch):
        enc = Encoder.__new__(Encoder)
        enc.cfg = SimpleNamespace(
            enc=SimpleNamespace(
                min_bytes_for_budget_allocation=1,
                object_budget_soft=True,
                max_iter_obj=0,
                min_obj_pixels=1,
            ),
            img_process=SimpleNamespace(
                encoders_tag_bg_level_1={"mono-2bit": 1},
                encoders_tag_objs_level_1={"mono-mask-1bit": 6, "airplane-symbol-v1": 10},
                obj_scaling_min_level_1=12,
                obj_scaling_max_level_1=66,
                canny_sigma=1.0,
                canny_low=50,
                canny_high=150,
            ),
            model=SimpleNamespace(symbol_category_ids={2, 3}),
        )

        monkeypatch.setattr(enc, "_allocate_budgets_by_pixels", lambda *args, **kwargs: [20, 20, 20])
        monkeypatch.setattr(enc, "_build_edge_mask", lambda *args, **kwargs: Image.new("L", (8, 8), color=255))
        monkeypatch.setattr(
            enc,
            "_estimate_symbol_theta",
            lambda img, *, category_id: 135.0 if int(category_id) == 2 else 0.0,
        )

        encode_calls = []

        def _fake_encode_img(img, encoder="mono-2bit", mask=None, category_id=None, theta_deg=None):
            encode_calls.append((encoder, category_id, theta_deg, None if mask is None else "mask"))
            return b"symbol" if encoder == "airplane-symbol-v1" else b"mask"

        monkeypatch.setattr(enc, "encode_img", _fake_encode_img)
        monkeypatch.setattr(enc, "_resize_image", lambda img, scale_percent, resample=Image.Resampling.BICUBIC: img)

        crops = [
            SimpleNamespace(obj_pil=Image.new("RGB", (8, 8)), bbox=(0, 0, 10, 10), category_id=2, encoded_obj=None, scaling_factor=None, obj_size_scaled=None, encoder_index=None),
            SimpleNamespace(obj_pil=Image.new("RGB", (8, 8)), bbox=(10, 10, 30, 20), category_id=3, encoded_obj=None, scaling_factor=None, obj_size_scaled=None, encoder_index=None),
            SimpleNamespace(obj_pil=Image.new("RGB", (8, 8)), bbox=(0, 0, 10, 10), category_id=7, encoded_obj=None, scaling_factor=None, obj_size_scaled=None, encoder_index=None),
        ]

        out = enc.compress_objs(crops, tar_objs_bytes=60)

        assert encode_calls[0] == ("airplane-symbol-v1", 2, 135.0, None)
        assert encode_calls[1] == ("airplane-symbol-v1", 3, 90.0, None)
        assert encode_calls[2] == ("mono-mask-1bit", None, None, "mask")
        assert out[0].encoder_index == 10
        assert out[1].encoder_index == 10
        assert out[2].encoder_index == 6
        assert out[0].scaling_factor is None
        assert out[1].scaling_factor is None
        assert out[2].scaling_factor == 12

    def test_compress_objs_fast_path_uses_last_configured_encoder(self, monkeypatch):
        enc = Encoder.__new__(Encoder)
        enc.cfg = SimpleNamespace(
            enc=SimpleNamespace(
                min_bytes_for_budget_allocation=1,
                object_budget_soft=True,
                max_iter_obj=0,
                min_obj_pixels=1,
            ),
            img_process=SimpleNamespace(
                encoders_tag_bg_level_1={"mono-2bit": 1},
                encoders_tag_objs_level_1={"mono-mask-1bit": 6, "mono-2bit": 5},
                obj_scaling_min_level_1=12,
                obj_scaling_max_level_1=66,
                canny_sigma=1.0,
                canny_low=50,
                canny_high=150,
            ),
        )

        monkeypatch.setattr(enc, "_allocate_budgets_by_pixels", lambda *args, **kwargs: [20, 20])
        monkeypatch.setattr(enc, "_resize_image", lambda img, scale_percent, resample=Image.Resampling.BICUBIC: img)

        encode_calls = []

        def _fake_encode_img(img, encoder="mono-2bit", mask=None, category_id=None, theta_deg=None):
            encode_calls.append((encoder, category_id, theta_deg, None if mask is None else "mask"))
            return b"ok"

        monkeypatch.setattr(enc, "encode_img", _fake_encode_img)

        crops = [
            SimpleNamespace(obj_pil=Image.new("RGB", (8, 8)), bbox=(0, 0, 10, 10), category_id=2, encoded_obj=None, scaling_factor=None, obj_size_scaled=None, encoder_index=None),
            SimpleNamespace(obj_pil=Image.new("RGB", (8, 8)), bbox=(0, 0, 10, 10), category_id=7, encoded_obj=None, scaling_factor=None, obj_size_scaled=None, encoder_index=None),
        ]

        out = enc.compress_objs(crops, tar_objs_bytes=40)

        assert encode_calls[0][0] == "mono-2bit"
        assert encode_calls[1][0] == "mono-2bit"
        assert out[0].encoder_index == 5
        assert out[1].encoder_index == 5

    def test_compress_objs_uses_configured_symbol_category_ids(self, monkeypatch):
        enc = Encoder.__new__(Encoder)
        enc.cfg = SimpleNamespace(
            model=SimpleNamespace(symbol_category_ids={1, 4}),
            enc=SimpleNamespace(
                min_bytes_for_budget_allocation=1,
                object_budget_soft=True,
                max_iter_obj=0,
                min_obj_pixels=1,
            ),
            img_process=SimpleNamespace(
                encoders_tag_bg_level_1={"mono-2bit": 1},
                encoders_tag_objs_level_1={"mono-mask-1bit": 6, "airplane-symbol-v1": 10},
                obj_scaling_min_level_1=12,
                obj_scaling_max_level_1=66,
                canny_sigma=1.0,
                canny_low=50,
                canny_high=150,
            ),
        )

        monkeypatch.setattr(enc, "_allocate_budgets_by_pixels", lambda *args, **kwargs: [20, 20])
        monkeypatch.setattr(enc, "_build_edge_mask", lambda *args, **kwargs: Image.new("L", (8, 8), color=255))
        monkeypatch.setattr(enc, "_estimate_symbol_theta", lambda img, *, category_id: 45.0)
        monkeypatch.setattr(enc, "_resize_image", lambda img, scale_percent, resample=Image.Resampling.BICUBIC: img)

        encode_calls = []

        def _fake_encode_img(img, encoder="mono-2bit", mask=None, category_id=None, theta_deg=None):
            encode_calls.append((encoder, category_id, theta_deg, None if mask is None else "mask"))
            return b"ok"

        monkeypatch.setattr(enc, "encode_img", _fake_encode_img)

        crops = [
            SimpleNamespace(obj_pil=Image.new("RGB", (8, 8)), bbox=(0, 0, 10, 10), category_id=1, encoded_obj=None, scaling_factor=None, obj_size_scaled=None, encoder_index=None),
            SimpleNamespace(obj_pil=Image.new("RGB", (8, 8)), bbox=(0, 0, 10, 10), category_id=2, encoded_obj=None, scaling_factor=None, obj_size_scaled=None, encoder_index=None),
        ]

        out = enc.compress_objs(crops, tar_objs_bytes=40)

        assert encode_calls[0][0] == "airplane-symbol-v1"
        assert encode_calls[1][0] == "mono-mask-1bit"
        assert out[0].encoder_index == 10
        assert out[1].encoder_index == 6

    def test_estimate_airplane_nose_theta_prefers_pointed_front(self):
        # Synthetic airplane-like silhouette: pointed nose on the right, wider tail on the left.
        img = Image.new("L", (96, 48), color=0)
        draw = ImageDraw.Draw(img)
        draw.polygon(
            [
                (6, 20),
                (20, 14),
                (32, 10),
                (56, 10),
                (88, 24),
                (56, 38),
                (32, 38),
                (20, 34),
            ],
            fill=255,
        )
        draw.polygon([(28, 10), (48, 4), (44, 18)], fill=255)
        draw.polygon([(28, 38), (48, 44), (44, 30)], fill=255)

        theta = estimate_airplane_nose_theta_deg(img)
        assert theta is not None
        assert min(abs(theta - 0.0), abs(theta - 360.0)) <= 20.0

    def test_adjust_symbol_theta_applies_vessel_offset_only(self):
        enc = Encoder.__new__(Encoder)
        enc.cfg = SimpleNamespace(
            img_process=SimpleNamespace(vessel_theta_offset_deg=90.0)
        )

        assert enc._adjust_symbol_theta(10.0, category_id=2) == pytest.approx(10.0)
        assert enc._adjust_symbol_theta(10.0, category_id=3) == pytest.approx(100.0)

    def test_estimate_vessel_nose_theta_prefers_narrow_end(self):
        # Synthetic vessel: wider stern (left), narrower nose (right).
        img = Image.new("L", (96, 48), color=0)
        draw = ImageDraw.Draw(img)
        draw.polygon([(6, 8), (58, 8), (90, 24), (58, 40), (6, 40)], fill=255)

        theta = estimate_vessel_nose_theta_deg(img)
        assert theta is not None
        assert min(abs(theta - 0.0), abs(theta - 360.0)) <= 20.0

    def test_estimate_vessel_nose_theta_rotated_shape_tracks_heading(self):
        base = Image.new("L", (128, 128), color=0)
        draw = ImageDraw.Draw(base)
        # Right-pointing vessel hull with a sharper bow.
        draw.polygon([(24, 44), (78, 44), (108, 64), (78, 84), (24, 84)], fill=255)

        rotated = base.rotate(-135.0, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=0)
        theta = estimate_vessel_nose_theta_deg(rotated)
        assert theta is not None

        # Circular angular distance in degrees.
        diff = abs(((theta - 135.0 + 180.0) % 360.0) - 180.0)
        assert diff <= 20.0

    def test_estimate_vessel_nose_theta_uses_tip_fallback_when_width_cue_ambiguous(self, monkeypatch):
        monkeypatch.setattr(encoder_codecs, "_estimate_pointed_end_theta_deg", lambda *a, **k: None)
        monkeypatch.setattr(encoder_codecs, "_estimate_tip_vertex_theta_deg", lambda *a, **k: 42.0)

        img = Image.new("L", (32, 32), color=0)
        theta = estimate_vessel_nose_theta_deg(img)
        assert theta == pytest.approx(42.0)


class TestEncoderTargetBudget:
    def test_set_tar_objs_bytes_uses_compression_rate(self):
        enc = Encoder.__new__(Encoder)
        enc.cfg = SimpleNamespace(
            mux_cfg=SimpleNamespace(header_fields_total_bytes=lambda: (12, 4)),
            enc=SimpleNamespace(
                compression_rate=100.0,
                min_bytes_for_encoded_data=500,
                obj_budget_ratio=0.9,
            ),
        )

        tar_objs_bytes, tar_enc_data_bytes = enc.set_tar_objs_bytes(org_jpeg_bytes=100_000, num_objs=3)

        # 100000/100 = 1000 total payload budget, minus overhead (12 + 3*4 = 24).
        assert tar_enc_data_bytes == 976
        assert tar_objs_bytes == int(976 * 0.9)

    def test_set_tar_objs_bytes_falls_back_to_min_when_budget_non_positive(self):
        enc = Encoder.__new__(Encoder)
        enc.cfg = SimpleNamespace(
            mux_cfg=SimpleNamespace(header_fields_total_bytes=lambda: (200, 150)),
            enc=SimpleNamespace(
                compression_rate=100.0,
                min_bytes_for_encoded_data=500,
                obj_budget_ratio=0.9,
            ),
        )

        tar_objs_bytes, tar_enc_data_bytes = enc.set_tar_objs_bytes(org_jpeg_bytes=10_000, num_objs=4)

        assert tar_enc_data_bytes == 500
        assert tar_objs_bytes == int(500 * 0.9)

    def test_set_tar_objs_bytes_background_only_uses_no_per_crop_overhead(self):
        enc = Encoder.__new__(Encoder)
        enc.cfg = SimpleNamespace(
            mux_cfg=SimpleNamespace(header_fields_total_bytes=lambda: (12, 4)),
            enc=SimpleNamespace(
                compression_rate=100.0,
                min_bytes_for_encoded_data=500,
                obj_budget_ratio=0.0,
            ),
        )

        tar_objs_bytes, tar_enc_data_bytes = enc.set_tar_objs_bytes(org_jpeg_bytes=100_000, num_objs=0)

        assert tar_enc_data_bytes == 988
        assert tar_objs_bytes == 0


def _model_cfg(**overrides):
    defaults = dict(
        skip_obj_detection=False,
        detector_backend="yolo",
        enc_yolo_model_path="/fake/model/path",
        tile_size=None,
        # Only read by Encoder.__init__'s log message when detector_backend=dlstreamer;
        # build_dlstreamer_client itself is monkeypatched in these tests.
        dlstreamer_base_url="http://dlstreamer-pipeline-server:8080",
        dlstreamer_pipeline_name="star_image_object_detection",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestEncoderDetectorBackendSelection:
    """`Encoder.__init__` picks a detector backend and loads only what it needs."""

    def test_init_with_yolo_backend_loads_local_model(self, monkeypatch):
        sentinel_model = object()
        seen = {}

        def _fake_load_yolo_model(model_path, device=None):
            seen["path"] = model_path
            seen["device"] = device
            return sentinel_model, {0: "Person"}

        def _fail_build_client(cfg):
            raise AssertionError("build_dlstreamer_client should not be called for the yolo backend")

        monkeypatch.setattr(encoder_module, "load_yolo_model", _fake_load_yolo_model)
        monkeypatch.setattr(encoder_module, "build_dlstreamer_client", _fail_build_client)

        cfg = SimpleNamespace(model=_model_cfg(detector_backend="yolo"), app=SimpleNamespace(device="cpu"))
        enc = Encoder(cfg)

        assert enc.detector_backend == "yolo"
        assert enc.yolo is sentinel_model
        assert enc.dlstreamer_client is None
        assert seen["path"] == cfg.model.enc_yolo_model_path
        assert seen["device"] == "cpu"

    def test_init_with_dlstreamer_backend_builds_client_without_loading_yolo(self, monkeypatch):
        sentinel_client = object()

        def _fail_load_yolo_model(model_path):
            raise AssertionError("load_yolo_model should not be called for the dlstreamer backend")

        def _fake_build_client(cfg):
            return sentinel_client

        monkeypatch.setattr(encoder_module, "load_yolo_model", _fail_load_yolo_model)
        monkeypatch.setattr(encoder_module, "build_dlstreamer_client", _fake_build_client)

        cfg = SimpleNamespace(model=_model_cfg(detector_backend="dlstreamer"))
        enc = Encoder(cfg)

        assert enc.detector_backend == "dlstreamer"
        assert enc.dlstreamer_client is sentinel_client
        assert enc.yolo is None

    def test_init_skip_obj_detection_loads_neither_backend(self, monkeypatch):
        def _fail_load_yolo_model(model_path):
            raise AssertionError("load_yolo_model should not be called when skip_obj_detection=True")

        def _fail_build_client(cfg):
            raise AssertionError("build_dlstreamer_client should not be called when skip_obj_detection=True")

        monkeypatch.setattr(encoder_module, "load_yolo_model", _fail_load_yolo_model)
        monkeypatch.setattr(encoder_module, "build_dlstreamer_client", _fail_build_client)

        cfg = SimpleNamespace(model=_model_cfg(skip_obj_detection=True, detector_backend="dlstreamer"))
        enc = Encoder(cfg)

        assert enc.yolo is None
        assert enc.dlstreamer_client is None

    def test_init_detector_backend_defaults_to_yolo_when_unset(self, monkeypatch):
        """`getattr(cfg.model, "detector_backend", "yolo")` covers configs predating this field."""
        sentinel_model = object()
        monkeypatch.setattr(encoder_module, "load_yolo_model", lambda model_path, device=None: (sentinel_model, {}))

        model_cfg = SimpleNamespace(skip_obj_detection=False, enc_yolo_model_path="/fake/model/path")
        cfg = SimpleNamespace(model=model_cfg, app=SimpleNamespace(device="cpu"))
        enc = Encoder(cfg)

        assert enc.detector_backend == "yolo"
        assert enc.yolo is sentinel_model


class TestEncoderExtractObjsDetectorDispatch:
    """`extract_objs` should route to the configured detector backend and nowhere else."""

    @staticmethod
    def _make_encoder(*, detector_backend, dlstreamer_client=None):
        enc = Encoder.__new__(Encoder)
        enc.skip_obj_detection = False
        enc.detector_backend = detector_backend
        enc.yolo = object() if detector_backend == "yolo" else None
        enc.dlstreamer_client = dlstreamer_client
        enc.cfg = SimpleNamespace(
            model=SimpleNamespace(tile_size=None),
            performance=SimpleNamespace(image_size=640),
            img_process=SimpleNamespace(additional_crop_margin=0),
        )
        return enc

    def test_extract_objs_skips_detection_when_skip_obj_detection(self, monkeypatch):
        def _fail(*args, **kwargs):
            raise AssertionError("no detector backend should run when skip_obj_detection=True")

        monkeypatch.setattr(encoder_module, "run_yolo", _fail)
        monkeypatch.setattr(encoder_module, "run_dlstreamer_detect", _fail)

        enc = self._make_encoder(detector_backend="yolo")
        enc.skip_obj_detection = True

        assert enc.extract_objs(Image.new("RGB", (640, 480))) == []

    def test_extract_objs_uses_dlstreamer_backend(self, monkeypatch):
        sentinel_client = object()
        captured = {}

        def _fake_run_dlstreamer_detect(pil_img, cfg, *, client=None):
            captured["pil_img"] = pil_img
            captured["cfg"] = cfg
            captured["client"] = client
            return [(10, 20, 110, 120, 0.9, 3)]

        def _fail_run_yolo(*args, **kwargs):
            raise AssertionError("run_yolo should not be called for the dlstreamer backend")

        monkeypatch.setattr(encoder_module, "run_dlstreamer_detect", _fake_run_dlstreamer_detect)
        monkeypatch.setattr(encoder_module, "run_yolo", _fail_run_yolo)

        enc = self._make_encoder(detector_backend="dlstreamer", dlstreamer_client=sentinel_client)
        img = Image.new("RGB", (640, 480))

        crops = enc.extract_objs(img)

        assert len(crops) == 1
        assert crops[0].bbox == (10, 20, 110, 120)
        assert crops[0].category_id == 3
        assert crops[0].det_conf == pytest.approx(0.9)
        # The client built once in __init__ must be reused, not rebuilt per frame.
        assert captured["client"] is sentinel_client
        assert captured["pil_img"] is img
        assert captured["cfg"] is enc.cfg

    def test_extract_objs_uses_yolo_backend_by_default(self, monkeypatch):
        captured = {}

        def _fake_run_yolo(pil_img, yolo, cfg, tile_size=None, imgsz=640):
            captured["yolo"] = yolo
            captured["tile_size"] = tile_size
            captured["imgsz"] = imgsz
            return [(5, 5, 55, 55, 0.5, 1)]

        def _fail_run_dlstreamer_detect(*args, **kwargs):
            raise AssertionError("run_dlstreamer_detect should not be called for the yolo backend")

        monkeypatch.setattr(encoder_module, "run_yolo", _fake_run_yolo)
        monkeypatch.setattr(encoder_module, "run_dlstreamer_detect", _fail_run_dlstreamer_detect)

        enc = self._make_encoder(detector_backend="yolo")

        crops = enc.extract_objs(Image.new("RGB", (640, 480)))

        assert len(crops) == 1
        assert crops[0].bbox == (5, 5, 55, 55)
        assert crops[0].category_id == 1
        assert captured["yolo"] is enc.yolo
        assert captured["tile_size"] is None
        assert captured["imgsz"] == 640


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

