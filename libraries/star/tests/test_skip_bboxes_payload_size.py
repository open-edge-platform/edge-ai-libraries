# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: tests/test_skip_bboxes_payload_size.py
Description: Compare background and total wire-payload sizes when
             skip_object_bboxes_in_background is True vs False.

             Uses real sample images from tests/fixtures/sample_images/ and
             the mono-2bit background codec, which is one of the two codecs
             that honours the skip flag (BG_BBOX_SKIP_SUPPORTED_ENCODERS).

Strategy
--------
- Build a lightweight Encoder via ``Encoder.__new__`` (no YOLO model needed).
- Use ``max_iter_bg=0`` (fast path) so both variants always encode at the same
  fixed scale (100 %), making the comparison deterministic: the only difference
  is whether a ``skip_mask`` is passed to ``encode_mono_2bit``.
- Supply a synthetic pre-encoded crop whose ``expanded_bbox`` covers the top
  half of each image (~50 % of pixels), which guarantees a measurable size
  reduction when the flag is True.
"""
from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from semantic_img_comp.core.frame import ImgEncData
from semantic_img_comp.core.object import ObjData
from semantic_img_comp.encoder.encoder import Encoder
from semantic_img_comp.utils.config import MuxStructConfig

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_IMAGES_DIR = Path(__file__).parent / "fixtures" / "sample_images"
SAMPLE_IMAGES = sorted(SAMPLE_IMAGES_DIR.glob("*.jpg")) + sorted(SAMPLE_IMAGES_DIR.glob("*.jpeg"))

assert SAMPLE_IMAGES, (
    f"No JPEG files found under {SAMPLE_IMAGES_DIR}. "
    "Make sure the fixtures directory is populated."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_encoder(*, skip_bboxes: bool) -> Encoder:
    """Return an Encoder configured for mono-2bit background encoding.

    ``max_iter_bg=0`` forces the fast path: both True/False variants use the
    same fixed scale (100 %), so size differences are caused solely by the
    skip_mask mechanism.
    """
    enc = Encoder.__new__(Encoder)
    enc.cfg = SimpleNamespace(
        enc=SimpleNamespace(
            min_bg_bytes=10,
            min_bg_pixels=100,
            max_iter_bg=0,          # fast path – fixed scale, no binary search
            max_iter_obj=1,
            zlib_level=5,
            avif_quality=0,
            avif_speed=6,
            avif_timeout_sec=120,
            avif_mono_quality_map={},
            avif_jobs=0,
            avif_codec=None,
            compression_rate=100.0,
            obj_budget_ratio=0.9,
            min_bytes_for_budget_allocation=10,
            object_budget_soft=True,
            min_obj_pixels=100,
            min_bytes_for_encoded_data=500,
            scale_search_step_size=1,
        ),
        img_process=SimpleNamespace(
            # mono-2bit is in BG_BBOX_SKIP_SUPPORTED_ENCODERS so the flag
            # takes effect; index 5 matches DEFAULT_ENCODERS_TAG.
            encoders_tag_bg_level_1={"mono-2bit": 5},
            encoders_tag_objs_level_1={"mono-2bit": 5},
            # 100 % scale → no resize, identical image dimensions for both
            # variants, making byte-count differences attributable to the flag.
            bg_scaling_min1_level_1=100,
            bg_scaling_min2_level_1=100,
            bg_scaling_max_level_1=100,
            obj_scaling_min_level_1=10,
            obj_scaling_max_level_1=100,
            additional_crop_margin=0,
            canny_mode="old",
            canny_sigma=1.0,
            canny_low=12,
            canny_high=45,
            canny_deriche_bilateral_d=9,
            canny_deriche_bilateral_sigma_color=60.0,
            canny_deriche_bilateral_sigma_space=60.0,
            canny_deriche_gaussian_sigma=2.0,
            canny_deriche_morph_close_kernel=7,
            canny_deriche_morph_close_iterations=2,
            mono_skel_max_segments=8,
            mono_skel_min_segment_length=5,
            mono_skel_hough_threshold=20,
            mono_skel_max_segment_gap=2,
            mono_skel_work_max_dim=128,
            mono_skel_stitch_angle_tol_deg=20.0,
            mono_shape_max_points=120,
            mono_shape_epsilon_ratio=0.01,
            vessel_theta_offset_deg=90.0,
            skip_object_bboxes_in_background=skip_bboxes,
        ),
        mux_cfg=MuxStructConfig(),
    )
    return enc


def _make_crop(pil_img: Image.Image, bbox: tuple[int, int, int, int]) -> ObjData:
    """Build a synthetic pre-encoded crop for budget accounting and muxing.

    ``encoder_index=5`` resolves to ``mono-2bit`` in ``encoders_tag_objs``, which
    is a dense (non-sparse) codec, so the bbox will be added to the skip list
    when ``skip_object_bboxes_in_background=True``.
    """
    x1, y1, x2, y2 = bbox
    return ObjData(
        obj_pil=pil_img.crop(bbox),
        obj_size=(x2 - x1, y2 - y1),
        bbox=bbox,
        expanded_bbox=bbox,
        category_id=1,          # Car (dense encoder; not in SPARSE_OVERLAY_OBJECT_ENCODERS)
        det_conf=0.95,
        encoder_index=5,        # mono-2bit → triggers bg skip logic
        encoded_obj=b"\x00" * 64,  # dummy pre-encoded bytes (for budget accounting)
        scaling_factor=100,
        obj_size_scaled=(x2 - x1, y2 - y1),
    )


def _jpeg_byte_len(img: Image.Image) -> int:
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return len(buf.getvalue())


# ---------------------------------------------------------------------------
# Parametrised unit tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("img_path", SAMPLE_IMAGES, ids=lambda p: p.name)
def test_skip_bboxes_reduces_background_payload(img_path: Path) -> None:
    """Background encoded bytes are smaller when skip_object_bboxes_in_background=True.

    A bbox covering the top half of the image is passed as the single crop.
    With ``skip=True``, ``encode_mono_2bit`` receives a ``skip_mask`` that marks
    those ~50 % of pixels as excluded, so its zlib output is strictly smaller.
    """
    pil_img = Image.open(img_path).convert("L")
    w, h = pil_img.size

    # bbox = top half of the image → approximately 50 % of all pixels skipped
    bbox = (0, 0, w, h // 2)
    crop_skip    = _make_crop(pil_img, bbox)
    crop_no_skip = _make_crop(pil_img, bbox)

    enc_skip    = _make_encoder(skip_bboxes=True)
    enc_no_skip = _make_encoder(skip_bboxes=False)

    org_jpeg_bytes = _jpeg_byte_len(pil_img)
    _, tar_enc = enc_skip.set_tar_objs_bytes(org_jpeg_bytes, num_objs=1)

    bg_skip,    _ = enc_skip.compress_background(pil_img, tar_enc, crops=[crop_skip])
    bg_no_skip, _ = enc_no_skip.compress_background(pil_img, tar_enc, crops=[crop_no_skip])

    skip_bytes    = len(bg_skip.encoded_data)
    no_skip_bytes = len(bg_no_skip.encoded_data)

    assert skip_bytes < no_skip_bytes, (
        f"{img_path.name}: expected background payload with skip_object_bboxes_in_background=True "
        f"({skip_bytes} B) to be strictly smaller than with False ({no_skip_bytes} B). "
        f"Bbox covers the top {h // 2}/{h} rows (~50 % of pixels)."
    )


@pytest.mark.parametrize("img_path", SAMPLE_IMAGES, ids=lambda p: p.name)
def test_skip_bboxes_reduces_total_wire_payload(img_path: Path) -> None:
    """Total muxed wire payload is smaller when skip_object_bboxes_in_background=True.

    Object bytes are held constant (same dummy pre-encoded bytes), so the saving
    comes entirely from the reduced background portion.
    """
    pil_img = Image.open(img_path).convert("L")
    w, h = pil_img.size
    bbox = (0, 0, w, h // 2)

    enc_skip    = _make_encoder(skip_bboxes=True)
    enc_no_skip = _make_encoder(skip_bboxes=False)

    org_jpeg_bytes = _jpeg_byte_len(pil_img)
    _, tar_enc = enc_skip.set_tar_objs_bytes(org_jpeg_bytes, num_objs=1)

    crop_skip    = _make_crop(pil_img, bbox)
    crop_no_skip = _make_crop(pil_img, bbox)

    bg_skip,    _ = enc_skip.compress_background(pil_img, tar_enc, crops=[crop_skip])
    bg_no_skip, _ = enc_no_skip.compress_background(pil_img, tar_enc, crops=[crop_no_skip])

    img_data_skip = ImgEncData(
        img_idx=0,
        org_jpeg_bytes=org_jpeg_bytes,
        org_img_size=(w, h),
        bg=bg_skip,
        crops=[crop_skip],
    )
    img_data_no_skip = ImgEncData(
        img_idx=0,
        org_jpeg_bytes=org_jpeg_bytes,
        org_img_size=(w, h),
        bg=bg_no_skip,
        crops=[crop_no_skip],
    )

    payload_skip,    _ = enc_skip.encode_payload(img_data_skip)
    payload_no_skip, _ = enc_no_skip.encode_payload(img_data_no_skip)

    assert len(payload_skip) < len(payload_no_skip), (
        f"{img_path.name}: total wire payload with skip_object_bboxes_in_background=True "
        f"({len(payload_skip)} B) should be strictly less than False ({len(payload_no_skip)} B)."
    )


@pytest.mark.parametrize("img_path", SAMPLE_IMAGES, ids=lambda p: p.name)
def test_skip_bboxes_no_effect_without_objects(img_path: Path) -> None:
    """When crops=[], both skip=True and skip=False produce identical background payloads.

    ``_get_bg_skippable_bboxes`` returns an empty list when there are no crops,
    so the skip_mask is never constructed and the encoding path is identical.
    """
    pil_img = Image.open(img_path).convert("L")

    enc_skip    = _make_encoder(skip_bboxes=True)
    enc_no_skip = _make_encoder(skip_bboxes=False)

    org_jpeg_bytes = _jpeg_byte_len(pil_img)
    _, tar_enc = enc_skip.set_tar_objs_bytes(org_jpeg_bytes, num_objs=0)

    bg_skip,    _ = enc_skip.compress_background(pil_img, tar_enc, crops=[])
    bg_no_skip, _ = enc_no_skip.compress_background(pil_img, tar_enc, crops=[])

    assert len(bg_skip.encoded_data) == len(bg_no_skip.encoded_data), (
        f"{img_path.name}: with no crops, skip=True ({len(bg_skip.encoded_data)} B) "
        f"and skip=False ({len(bg_no_skip.encoded_data)} B) should produce identical "
        f"background payloads."
    )


# ---------------------------------------------------------------------------
# Summary table (informational, not a strict assertion)
# ---------------------------------------------------------------------------


class TestSkipBboxesPayloadSizeSummary:
    """Print a per-image size comparison table across all sample images."""

    def test_payload_size_comparison_table(self, capsys: pytest.CaptureFixture) -> None:
        rows: list[tuple[str, int, int, int, int, int]] = []

        for img_path in sorted(SAMPLE_IMAGES):
            pil_img = Image.open(img_path).convert("L")
            w, h = pil_img.size
            bbox = (0, 0, w, h // 2)

            enc_skip    = _make_encoder(skip_bboxes=True)
            enc_no_skip = _make_encoder(skip_bboxes=False)

            org_jpeg_bytes = _jpeg_byte_len(pil_img)
            _, tar_enc = enc_skip.set_tar_objs_bytes(org_jpeg_bytes, num_objs=1)

            crop_skip    = _make_crop(pil_img, bbox)
            crop_no_skip = _make_crop(pil_img, bbox)

            bg_skip,    _ = enc_skip.compress_background(pil_img, tar_enc, crops=[crop_skip])
            bg_no_skip, _ = enc_no_skip.compress_background(pil_img, tar_enc, crops=[crop_no_skip])

            img_data_skip = ImgEncData(
                img_idx=0, org_jpeg_bytes=org_jpeg_bytes, org_img_size=(w, h),
                bg=bg_skip, crops=[crop_skip],
            )
            img_data_no_skip = ImgEncData(
                img_idx=0, org_jpeg_bytes=org_jpeg_bytes, org_img_size=(w, h),
                bg=bg_no_skip, crops=[crop_no_skip],
            )

            payload_skip,    _ = enc_skip.encode_payload(img_data_skip)
            payload_no_skip, _ = enc_no_skip.encode_payload(img_data_no_skip)

            rows.append((
                img_path.name,
                len(bg_no_skip.encoded_data),
                len(bg_skip.encoded_data),
                len(payload_no_skip),
                len(payload_skip),
                w * h,
            ))

        with capsys.disabled():
            col = (50, 14, 16, 14, 13, 11)
            header = (
                f"{'Image':<{col[0]}} "
                f"{'bg no-skip (B)':>{col[1]}} "
                f"{'bg skip=True (B)':>{col[2]}} "
                f"{'bg saving (B)':>{col[3]}} "
                f"{'wire no-skip':>{col[4]}} "
                f"{'wire skip':>{col[5]}}"
            )
            separator = "-" * len(header)
            print(f"\n\nskip_object_bboxes_in_background – payload size comparison")
            print(separator)
            print(header)
            print(separator)
            for name, bg_ns, bg_sk, wire_ns, wire_sk, pixels in rows:
                print(
                    f"{name:<{col[0]}} "
                    f"{bg_ns:>{col[1]},} "
                    f"{bg_sk:>{col[2]},} "
                    f"{bg_ns - bg_sk:>{col[3]},} "
                    f"{wire_ns:>{col[4]},} "
                    f"{wire_sk:>{col[5]},}"
                )
            print(separator)

