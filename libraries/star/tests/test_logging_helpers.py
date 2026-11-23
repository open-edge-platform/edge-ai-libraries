# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace

from semantic_img_comp.utils.logging_helpers import build_encoder_log_record


def test_build_encoder_log_record_includes_obj_min_dim_per_crop():
    crops = [
        SimpleNamespace(
            obj_size=(40, 30),
            obj_size_scaled=(20, 10),
            scaling_factor=None,
            encoder_index=10,
        ),
        SimpleNamespace(
            obj_size=(12, 8),
            obj_size_scaled=(7, 9),
            scaling_factor=75,
            encoder_index=1,
        ),
        SimpleNamespace(
            obj_size=(5, 5),
            obj_size_scaled=None,
            scaling_factor=None,
            encoder_index=None,
        ),
    ]
    img_data = SimpleNamespace(
        crops=crops,
        bg=None,
        org_jpeg_bytes=1000,
        org_img_size=(100, 100),
        img_idx=3,
    )

    record = build_encoder_log_record(
        frame_id=9,
        img_data=img_data,
        size_log={"header": 10, "background": 20, "objects": 30, "metadata": 5},
        obj_quota_bytes=200,
        aggregated_comp_rate=12.5,
        symbol_encoder_index=10,
    )

    # crop[1] has scaling_factor=75, so the lists are NOT all-None — keep them
    assert record["objects"]["scaled_total_pixels_per_crop"] == [None, 63, None]
    assert record["objects"]["scaled_min_dim_per_crop"] == [None, 7, None]
    assert record["objects"]["scaling_factor"] == [None, 75, None]
    assert record["objects"]["orig_min_dim_per_crop"] == [30, 8, 5]
    assert "comp_rate" not in record["payload"]
    assert "metrics" not in record
    assert record["objects"]["count"] == 3
    assert "objs_total_pixels_per_crop" not in record


def test_build_encoder_log_record_keeps_valid_scaled_pixels_for_non_symbol_crops():
    crops = [
        SimpleNamespace(
            obj_size=(10, 10),
            obj_size_scaled=(10, 10),
            scaling_factor=100,
            encoder_index=6,
        ),
    ]
    img_data = SimpleNamespace(
        crops=crops,
        bg=None,
        org_jpeg_bytes=1000,
        org_img_size=(100, 100),
        img_idx=3,
    )

    record = build_encoder_log_record(
        frame_id=9,
        img_data=img_data,
        size_log={"header": 10, "background": 20, "objects": 30, "metadata": 5},
        symbol_encoder_index=10,
    )

    assert record["objects"]["scaled_total_pixels_per_crop"] == [100]
    assert record["objects"]["scaled_min_dim_per_crop"] == [10]


def test_build_encoder_log_record_omits_all_null_scaling_fields():
    """All scaling_factor/scaled_* fields should be absent when every crop value is None."""
    crops = [
        SimpleNamespace(
            obj_size=(40, 30),
            obj_size_scaled=None,
            scaling_factor=None,
            encoder_index=10,
        ),
        SimpleNamespace(
            obj_size=(5, 5),
            obj_size_scaled=None,
            scaling_factor=None,
            encoder_index=None,
        ),
    ]
    img_data = SimpleNamespace(
        crops=crops,
        bg=None,
        org_jpeg_bytes=1000,
        org_img_size=(100, 100),
        img_idx=1,
    )

    record = build_encoder_log_record(
        frame_id=1,
        img_data=img_data,
        size_log={"header": 10, "background": 20, "objects": 30, "metadata": 5},
        symbol_encoder_index=10,
    )

    assert "scaling_factor" not in record["objects"]
    assert "scaled_total_pixels_per_crop" not in record["objects"]
    assert "scaled_min_dim_per_crop" not in record["objects"]
    # orig_min_dim_per_crop is always kept
    assert "orig_min_dim_per_crop" in record["objects"]


def test_build_encoder_log_record_does_not_emit_tar_comp_rate_in_payload_record():
    img_data = SimpleNamespace(crops=[], bg=None, org_jpeg_bytes=500, org_img_size=(8, 6), img_idx=1)
    record = build_encoder_log_record(
        frame_id=1,
        img_data=img_data,
        size_log={"header": 10, "background": 20},
        tar_comp_rate=42.0,
    )

    assert "tar_comp_rate" not in record["payload"]


def test_build_encoder_log_record_zero_objects_keeps_only_count():
    img_data = SimpleNamespace(crops=[], bg=None, org_jpeg_bytes=500, org_img_size=(8, 6), img_idx=1)
    record = build_encoder_log_record(
        frame_id=1,
        img_data=img_data,
        size_log={"header": 10, "background": 20},
        obj_quota_bytes=123,
    )

    assert record["objects"] == {"count": 0}


def test_build_encoder_log_record_omits_file_name_when_none():
    img_data = SimpleNamespace(crops=[], bg=None, org_jpeg_bytes=500, org_img_size=(8, 6), img_idx=1)
    record = build_encoder_log_record(
        frame_id=1,
        img_data=img_data,
        size_log={"header": 10, "background": 20},
        file_name=None,
    )
    assert "file_name" not in record


def test_build_encoder_log_record_omits_file_name_when_empty_string():
    img_data = SimpleNamespace(crops=[], bg=None, org_jpeg_bytes=500, org_img_size=(8, 6), img_idx=1)
    record = build_encoder_log_record(
        frame_id=1,
        img_data=img_data,
        size_log={"header": 10, "background": 20},
        file_name="",
    )
    assert "file_name" not in record


def test_build_encoder_log_record_omits_file_name_when_whitespace_only():
    img_data = SimpleNamespace(crops=[], bg=None, org_jpeg_bytes=500, org_img_size=(8, 6), img_idx=1)
    record = build_encoder_log_record(
        frame_id=1,
        img_data=img_data,
        size_log={"header": 10, "background": 20},
        file_name="   ",
    )
    assert "file_name" not in record


def test_build_encoder_log_record_includes_file_name_when_provided():
    img_data = SimpleNamespace(crops=[], bg=None, org_jpeg_bytes=500, org_img_size=(8, 6), img_idx=1)
    record = build_encoder_log_record(
        frame_id=1,
        img_data=img_data,
        size_log={"header": 10, "background": 20},
        file_name="frame_001.jpg",
    )
    assert record["file_name"] == "frame_001.jpg"
