# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import pytest

from semantic_img_comp.utils.config import load_config


def test_load_default_config_includes_symbol_category_ids():
    cfg = load_config()
    assert cfg.model.symbol_category_ids == {4, 8}


def test_load_default_config_includes_level_specific_encoder_tag_maps():
    cfg = load_config()

    assert cfg.img_process.encoders_tag_objs_level_1 == {
        "mono-avif-mid": 2,
    }
    assert cfg.img_process.encoders_tag_objs_level_2 == {
        "mono-avif-mid": 2,
        "mono-2bit": 5,
        "airplane-symbol-v1": 10,
    }


def test_load_default_config_includes_mixed_mono_template_fields():
    cfg = load_config()
    assert cfg.enc.mono_2bit_mixed_two_bit_run == 4
    assert cfg.enc.mono_2bit_mixed_one_bit_run == 1
    assert cfg.enc.mono_2bit_drop1bit_neighbor_k == 2
    assert cfg.enc.mono_2bit_drop1bit_fill_gray_level == 128


def test_load_config_parses_print_runtime_logs_false(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
app:
  log_level: INFO
  device: cpu
model:
  enc_yolo_model_path:
  pre_comp_conf: 0.15
  iou_threshold: 0.45
  max_detections: 300
  tile_size:
  tile_overlap:
  valid_obj_categories:
io:
  input_dir: /tmp/in
  annot_file:
  output_dir: /tmp/out
  save_visualizations: true
  print_runtime_logs: false
  pre_comp_det_filename: pre_comp_det.json
performance:
  image_size: 640
encoder:
  min_bg_bytes: 10
  min_bg_pixels: 10000
  min_bytes_for_budget_allocation: 50
  min_obj_pixels: 5000
  min_bytes_for_encoded_data: 500
  avif_quality: 0
  avif_speed: 6
  avif_timeout_sec: 120
  compression_rate: 100.0
  obj_budget_ratio: 0.9
  object_budget_soft: true
  max_iter: 20
decoder:
  avif_timeout_sec: 120
img_process:
  bg_scaling_min1_level_1: 8
  bg_scaling_min2_level_1: 10
  obj_scaling_min_level_1: 30
  additional_crop_margin: 10
  canny_sigma: 1.0
  canny_low: 50
  canny_high: 150
  encoders_tag:
mux_cfg:
  endian: ">"
  fmt_payload_len: "!I"
  fmt_img_idx: "I"
  fmt_hw: "2H"
  fmt_len_bg: "I"
  fmt_len_obj: "I"
  fmt_crops_count: "H"
  fmt_bbox: "4H"
  fmt_category_id: "H"
  fmt_det_conf: "f"
  fmt_encoder_index: "H"
""".strip(),
        encoding="utf-8",
    )

    cfg = load_config(str(config_path))

    assert cfg.io.print_runtime_logs is False
    assert cfg.io.save_visualizations is True
    assert cfg.io.annot_file is None
    assert cfg.img_process.additional_crop_margin == 10.0


def test_load_config_normalizes_annot_file_to_path(tmp_path):
    annot_path = tmp_path / "annotations.json"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
app:
  log_level: INFO
  device: cpu
model:
  enc_yolo_model_path:
  pre_comp_conf: 0.15
  iou_threshold: 0.45
  max_detections: 300
  tile_size:
  tile_overlap:
  valid_obj_categories:
io:
  input_dir: /tmp/in
  annot_file: {annot_path.as_posix()}
  output_dir: /tmp/out
  save_visualizations: true
  print_runtime_logs: false
  pre_comp_det_filename: pre_comp_det.json
performance:
  image_size: 640
encoder:
  min_bg_bytes: 10
  min_bg_pixels: 10000
  min_bytes_for_budget_allocation: 50
  min_obj_pixels: 5000
  min_bytes_for_encoded_data: 500
  avif_quality: 0
  avif_speed: 6
  avif_timeout_sec: 120
  compression_rate: 100.0
  obj_budget_ratio: 0.9
  object_budget_soft: true
  max_iter: 20
decoder:
  avif_timeout_sec: 120
img_process:
  bg_scaling_min1_level_1: 8
  bg_scaling_min2_level_1: 10
  obj_scaling_min_level_1: 30
  additional_crop_margin: 10
  canny_sigma: 1.0
  canny_low: 50
  canny_high: 150
  encoders_tag:
mux_cfg:
  endian: ">"
  fmt_payload_len: "!I"
  fmt_img_idx: "I"
  fmt_hw: "2H"
  fmt_len_bg: "I"
  fmt_len_obj: "I"
  fmt_crops_count: "H"
  fmt_bbox: "4H"
  fmt_category_id: "H"
  fmt_det_conf: "f"
  fmt_encoder_index: "H"
""".strip(),
        encoding="utf-8",
    )

    cfg = load_config(str(config_path))

    assert cfg.io.annot_file == Path(annot_path)


def test_load_config_defaults_blank_additional_crop_margin_to_zero(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
app:
  log_level: INFO
  device: cpu
model:
  enc_yolo_model_path:
  pre_comp_conf: 0.15
  iou_threshold: 0.45
  max_detections: 300
  tile_size:
  tile_overlap:
  valid_obj_categories:
io:
  input_dir: /tmp/in
  annot_file:
  output_dir: /tmp/out
  save_visualizations: true
  print_runtime_logs: false
  pre_comp_det_filename: pre_comp_det.json
performance:
  image_size: 640
encoder:
  min_bg_bytes: 10
  min_bg_pixels: 10000
  min_bytes_for_budget_allocation: 50
  min_obj_pixels: 5000
  min_bytes_for_encoded_data: 500
  avif_quality: 0
  avif_speed: 6
  avif_timeout_sec: 120
  compression_rate: 100.0
  obj_budget_ratio: 0.9
  object_budget_soft: true
  max_iter: 20
decoder:
  avif_timeout_sec: 120
img_process:
  bg_scaling_min1_level_1: 8
  bg_scaling_min2_level_1: 10
  obj_scaling_min_level_1: 30
  additional_crop_margin:
  canny_sigma: 1.0
  canny_low: 50
  canny_high: 150
  encoders_tag:
mux_cfg:
  endian: ">"
  fmt_payload_len: "!I"
  fmt_img_idx: "I"
  fmt_hw: "2H"
  fmt_len_bg: "I"
  fmt_len_obj: "I"
  fmt_crops_count: "H"
  fmt_bbox: "4H"
  fmt_category_id: "H"
  fmt_det_conf: "f"
  fmt_encoder_index: "H"
""".strip(),
        encoding="utf-8",
    )

    cfg = load_config(str(config_path))

    assert cfg.img_process.additional_crop_margin == 0.0


@pytest.mark.parametrize("raw_value,expected", [(10, 10.0), (12.5, 12.5)])
def test_load_config_normalizes_additional_crop_margin_to_float(tmp_path, raw_value, expected):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
app:
  log_level: INFO
  device: cpu
model:
  enc_yolo_model_path:
  pre_comp_conf: 0.15
  iou_threshold: 0.45
  max_detections: 300
  tile_size:
  tile_overlap:
  valid_obj_categories:
io:
  input_dir: /tmp/in
  annot_file:
  output_dir: /tmp/out
  save_visualizations: true
  print_runtime_logs: false
  pre_comp_det_filename: pre_comp_det.json
performance:
  image_size: 640
encoder:
  min_bg_bytes: 10
  min_bg_pixels: 10000
  min_bytes_for_budget_allocation: 50
  min_obj_pixels: 5000
  min_bytes_for_encoded_data: 500
  avif_quality: 0
  avif_speed: 6
  avif_timeout_sec: 120
  compression_rate: 100.0
  obj_budget_ratio: 0.9
  object_budget_soft: true
  max_iter: 20
decoder:
  avif_timeout_sec: 120
img_process:
  bg_scaling_min1_level_1: 8
  bg_scaling_min2_level_1: 10
  obj_scaling_min_level_1: 30
  additional_crop_margin: {raw_value}
  canny_sigma: 1.0
  canny_low: 50
  canny_high: 150
  encoders_tag:
mux_cfg:
  endian: ">"
  fmt_payload_len: "!I"
  fmt_img_idx: "I"
  fmt_hw: "2H"
  fmt_len_bg: "I"
  fmt_len_obj: "I"
  fmt_crops_count: "H"
  fmt_bbox: "4H"
  fmt_category_id: "H"
  fmt_det_conf: "f"
  fmt_encoder_index: "H"
""".strip(),
        encoding="utf-8",
    )

    cfg = load_config(str(config_path))

    assert cfg.img_process.additional_crop_margin == expected
    assert isinstance(cfg.img_process.additional_crop_margin, float)


@pytest.mark.parametrize("raw_value, message", [(-1, ">= 0"), (".nan", "finite"), (".inf", "finite")])
def test_load_config_rejects_invalid_additional_crop_margin(tmp_path, raw_value, message):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
app:
  log_level: INFO
  device: cpu
model:
  enc_yolo_model_path:
  pre_comp_conf: 0.15
  iou_threshold: 0.45
  max_detections: 300
  tile_size:
  tile_overlap:
  valid_obj_categories:
io:
  input_dir: /tmp/in
  annot_file:
  output_dir: /tmp/out
  save_visualizations: true
  print_runtime_logs: false
  pre_comp_det_filename: pre_comp_det.json
performance:
  image_size: 640
encoder:
  min_bg_bytes: 10
  min_bg_pixels: 10000
  min_bytes_for_budget_allocation: 50
  min_obj_pixels: 5000
  min_bytes_for_encoded_data: 500
  avif_quality: 0
  avif_speed: 6
  avif_timeout_sec: 120
  compression_rate: 100.0
  obj_budget_ratio: 0.9
  object_budget_soft: true
  max_iter: 20
decoder:
  avif_timeout_sec: 120
img_process:
  bg_scaling_min1_level_1: 8
  bg_scaling_min2_level_1: 10
  obj_scaling_min_level_1: 30
  additional_crop_margin: {raw_value}
  canny_sigma: 1.0
  canny_low: 50
  canny_high: 150
  encoders_tag:
mux_cfg:
  endian: ">"
  fmt_payload_len: "!I"
  fmt_img_idx: "I"
  fmt_hw: "2H"
  fmt_len_bg: "I"
  fmt_len_obj: "I"
  fmt_crops_count: "H"
  fmt_bbox: "4H"
  fmt_category_id: "H"
  fmt_det_conf: "f"
  fmt_encoder_index: "H"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=message):
        load_config(str(config_path))


def test_load_config_parses_paste_feather_tuning_fields(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
app:
  log_level: INFO
  device: cpu
model:
  enc_yolo_model_path:
  pre_comp_conf: 0.15
  iou_threshold: 0.45
  max_detections: 300
  tile_size:
  tile_overlap:
  valid_obj_categories:
io:
  input_dir: /tmp/in
  annot_file:
  output_dir: /tmp/out
  save_visualizations: true
  print_runtime_logs: false
  pre_comp_det_filename: pre_comp_det.json
performance:
  image_size: 640
encoder:
  min_bg_bytes: 10
  min_bg_pixels: 10000
  min_bytes_for_budget_allocation: 50
  min_obj_pixels: 5000
  min_bytes_for_encoded_data: 500
  avif_quality: 0
  avif_speed: 6
  avif_timeout_sec: 120
  compression_rate: 100.0
  obj_budget_ratio: 0.9
  object_budget_soft: true
  max_iter: 20
decoder:
  avif_timeout_sec: 120
img_process:
  bg_scaling_min1_level_1: 8
  bg_scaling_min2_level_1: 10
  obj_scaling_min_level_1: 30
  additional_crop_margin: 10
  paste_feather_ratio: 0.25
  paste_feather_min_px: 3
  canny_sigma: 1.0
  canny_low: 50
  canny_high: 150
  encoders_tag:
mux_cfg:
  endian: ">"
  fmt_payload_len: "!I"
  fmt_img_idx: "I"
  fmt_hw: "2H"
  fmt_len_bg: "I"
  fmt_len_obj: "I"
  fmt_crops_count: "H"
  fmt_bbox: "4H"
  fmt_category_id: "H"
  fmt_det_conf: "f"
  fmt_encoder_index: "H"
""".strip(),
        encoding="utf-8",
    )

    cfg = load_config(str(config_path))

    assert cfg.img_process.paste_feather_ratio == 0.25
    assert cfg.img_process.paste_feather_min_px == 3


@pytest.mark.parametrize(
    "field_name, raw_value, message",
    [
        ("paste_feather_ratio", -0.1, ">= 0"),
        ("paste_feather_ratio", ".inf", "finite"),
        ("paste_feather_min_px", -1, ">= 0"),
    ],
)
def test_load_config_rejects_invalid_paste_feather_tuning(tmp_path, field_name, raw_value, message):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
app:
  log_level: INFO
  device: cpu
model:
  enc_yolo_model_path:
  pre_comp_conf: 0.15
  iou_threshold: 0.45
  max_detections: 300
  tile_size:
  tile_overlap:
  valid_obj_categories:
io:
  input_dir: /tmp/in
  annot_file:
  output_dir: /tmp/out
  save_visualizations: true
  print_runtime_logs: false
  pre_comp_det_filename: pre_comp_det.json
performance:
  image_size: 640
encoder:
  min_bg_bytes: 10
  min_bg_pixels: 10000
  min_bytes_for_budget_allocation: 50
  min_obj_pixels: 5000
  min_bytes_for_encoded_data: 500
  avif_quality: 0
  avif_speed: 6
  avif_timeout_sec: 120
  compression_rate: 100.0
  obj_budget_ratio: 0.9
  object_budget_soft: true
  max_iter: 20
decoder:
  avif_timeout_sec: 120
img_process:
  bg_scaling_min1_level_1: 8
  bg_scaling_min2_level_1: 10
  obj_scaling_min_level_1: 30
  additional_crop_margin: 10
  paste_feather_ratio: 0.5
  paste_feather_min_px: 1
  {field_name}: {raw_value}
  canny_sigma: 1.0
  canny_low: 50
  canny_high: 150
  encoders_tag:
mux_cfg:
  endian: ">"
  fmt_payload_len: "!I"
  fmt_img_idx: "I"
  fmt_hw: "2H"
  fmt_len_bg: "I"
  fmt_len_obj: "I"
  fmt_crops_count: "H"
  fmt_bbox: "4H"
  fmt_category_id: "H"
  fmt_det_conf: "f"
  fmt_encoder_index: "H"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=message):
        load_config(str(config_path))


def test_load_config_parses_bg_and_obj_scaling_max(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
app:
  log_level: INFO
  device: cpu
model:
  enc_yolo_model_path:
  pre_comp_conf: 0.15
  iou_threshold: 0.45
  max_detections: 300
  tile_size:
  tile_overlap:
  valid_obj_categories:
io:
  input_dir: /tmp/in
  annot_file:
  output_dir: /tmp/out
  save_visualizations: true
  print_runtime_logs: false
  pre_comp_det_filename: pre_comp_det.json
performance:
  image_size: 640
encoder:
  min_bg_bytes: 10
  min_bg_pixels: 10000
  min_bytes_for_budget_allocation: 50
  min_obj_pixels: 5000
  min_bytes_for_encoded_data: 500
  avif_quality: 0
  avif_speed: 6
  avif_timeout_sec: 120
  compression_rate: 100.0
  obj_budget_ratio: 0.9
  object_budget_soft: true
  max_iter: 20
decoder:
  avif_timeout_sec: 120
img_process:
  bg_scaling_min1_level_1: 8
  bg_scaling_min2_level_1: 10
  bg_scaling_max_level_1: 96
  obj_scaling_min_level_1: 30
  obj_scaling_max_level_1: 88
  additional_crop_margin: 10
  canny_sigma: 1.0
  canny_low: 50
  canny_high: 150
  encoders_tag:
mux_cfg:
  endian: ">"
  fmt_payload_len: "!I"
  fmt_img_idx: "I"
  fmt_hw: "2H"
  fmt_len_bg: "I"
  fmt_len_obj: "I"
  fmt_crops_count: "H"
  fmt_bbox: "4H"
  fmt_category_id: "H"
  fmt_det_conf: "f"
  fmt_encoder_index: "H"
""".strip(),
        encoding="utf-8",
    )

    cfg = load_config(str(config_path))

    assert cfg.img_process.bg_scaling_max_level_1 == 96
    assert cfg.img_process.obj_scaling_max_level_1 == 88


def test_load_config_rejects_scaling_min_above_max(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
app:
  log_level: INFO
  device: cpu
model:
  enc_yolo_model_path:
  pre_comp_conf: 0.15
  iou_threshold: 0.45
  max_detections: 300
  tile_size:
  tile_overlap:
  valid_obj_categories:
io:
  input_dir: /tmp/in
  annot_file:
  output_dir: /tmp/out
  save_visualizations: true
  print_runtime_logs: false
  pre_comp_det_filename: pre_comp_det.json
performance:
  image_size: 640
encoder:
  min_bg_bytes: 10
  min_bg_pixels: 10000
  min_bytes_for_budget_allocation: 50
  min_obj_pixels: 5000
  min_bytes_for_encoded_data: 500
  avif_quality: 0
  avif_speed: 6
  avif_timeout_sec: 120
  compression_rate: 100.0
  obj_budget_ratio: 0.9
  object_budget_soft: true
  max_iter: 20
decoder:
  avif_timeout_sec: 120
img_process:
  bg_scaling_min1: 75
  bg_scaling_min2: 10
  bg_scaling_max: 50
  obj_scaling_min: 30
  obj_scaling_max: 88
  additional_crop_margin: 10
  canny_sigma: 1.0
  canny_low: 50
  canny_high: 150
  encoders_tag:
mux_cfg:
  endian: ">"
  fmt_payload_len: "!I"
  fmt_img_idx: "I"
  fmt_hw: "2H"
  fmt_len_bg: "I"
  fmt_len_obj: "I"
  fmt_crops_count: "H"
  fmt_bbox: "4H"
  fmt_category_id: "H"
  fmt_det_conf: "f"
  fmt_encoder_index: "H"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="has been removed"):
        load_config(str(config_path))


def test_load_config_parses_tile_merge_controls(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
app:
  log_level: INFO
  device: cpu
model:
  enc_yolo_model_path:
  pre_comp_conf: 0.15
  iou_threshold: 0.45
  tile_nms_iou: 0.35
  merge_tile_detections: false
  max_detections: 300
  tile_size:
  tile_overlap:
  valid_obj_categories:
io:
  input_dir: /tmp/in
  annot_file:
  output_dir: /tmp/out
  save_visualizations: true
  print_runtime_logs: false
  pre_comp_det_filename: pre_comp_det.json
performance:
  image_size: 640
encoder:
  min_bg_bytes: 10
  min_bg_pixels: 10000
  min_bytes_for_budget_allocation: 50
  min_obj_pixels: 5000
  min_bytes_for_encoded_data: 500
  avif_quality: 0
  avif_speed: 6
  avif_timeout_sec: 120
  compression_rate: 100.0
  obj_budget_ratio: 0.9
  object_budget_soft: true
  max_iter: 20
decoder:
  avif_timeout_sec: 120
img_process:
  bg_scaling_min1_level_1: 8
  bg_scaling_min2_level_1: 10
  obj_scaling_min_level_1: 30
  additional_crop_margin: 10
  canny_sigma: 1.0
  canny_low: 50
  canny_high: 150
  encoders_tag:
mux_cfg:
  endian: ">"
  fmt_payload_len: "!I"
  fmt_img_idx: "I"
  fmt_hw: "2H"
  fmt_len_bg: "I"
  fmt_len_obj: "I"
  fmt_crops_count: "H"
  fmt_bbox: "4H"
  fmt_category_id: "H"
  fmt_det_conf: "f"
  fmt_encoder_index: "H"
""".strip(),
        encoding="utf-8",
    )

    cfg = load_config(str(config_path))

    assert cfg.model.tile_nms_iou == 0.35
    assert cfg.model.merge_tile_detections is False


def _write_min_config(
    tmp_path,
    *,
    img_process_extra: str = "",
    mux_cfg_extra: str = "",
    encoder_extra: str = "",
    decoder_extra: str = "",
):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
app:
  log_level: INFO
  device: cpu
model:
  enc_yolo_model_path:
  pre_comp_conf: 0.15
  iou_threshold: 0.45
  max_detections: 300
  tile_size:
  tile_overlap:
  valid_obj_categories:
io:
  input_dir: /tmp/in
  annot_file:
  output_dir: /tmp/out
  save_visualizations: true
  print_runtime_logs: false
  pre_comp_det_filename: pre_comp_det.json
performance:
  image_size: 640
encoder:
  min_bg_bytes: 10
  min_bg_pixels: 10000
  min_bytes_for_budget_allocation: 50
  min_obj_pixels: 5000
  min_bytes_for_encoded_data: 500
  avif_quality: 0
  avif_speed: 6
  avif_timeout_sec: 120
  compression_rate: 100.0
  obj_budget_ratio: 0.9
  object_budget_soft: true
  max_iter: 20
{encoder_extra}
decoder:
  avif_timeout_sec: 120
{decoder_extra}
img_process:
  bg_scaling_min1_level_1: 8
  bg_scaling_min2_level_1: 10
  obj_scaling_min_level_1: 30
  additional_crop_margin: 10
  canny_sigma: 1.0
  canny_low: 50
  canny_high: 150
{img_process_extra}
mux_cfg:
  endian: ">"
  fmt_payload_len: "!I"
  fmt_img_idx: "I"
  fmt_hw: "2H"
  fmt_len_bg: "I"
  fmt_len_obj: "I"
  fmt_crops_count: "H"
  fmt_bbox: "4H"
  fmt_category_id: "H"
  fmt_det_conf: "f"
  fmt_encoder_index: "H"
{mux_cfg_extra}
""".strip(),
        encoding="utf-8",
    )
    return config_path


def test_load_config_supports_legacy_pre_comp_model_path(tmp_path):
    config_path = _write_min_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "  enc_yolo_model_path:\n",
            "  pre_comp_model_path: /tmp/legacy-model.pt\n",
        ),
        encoding="utf-8",
    )

    cfg = load_config(str(config_path))

    assert cfg.model.enc_yolo_model_path == Path("/tmp/legacy-model.pt")  # nosec B108 - asserting a config value, not creating a temp file


def test_load_config_prefers_enc_yolo_model_path_over_legacy_key(tmp_path):
    config_path = _write_min_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "  pre_comp_conf: 0.15",
            "  pre_comp_model_path: /tmp/legacy-model.pt\n  enc_yolo_model_path: /tmp/new-model.pt\n  pre_comp_conf: 0.15",
        ),
        encoding="utf-8",
    )

    cfg = load_config(str(config_path))

    assert cfg.model.enc_yolo_model_path == Path("/tmp/new-model.pt")  # nosec B108 - asserting a config value, not creating a temp file


def test_load_config_rejects_removed_split_encoder_tag_maps(tmp_path):
    config_path = _write_min_config(
        tmp_path,
        img_process_extra="""
  encoders_tag_bg:
    mono-2bit: 10
  encoders_tag_objs:
    mono-4bit: 20
""".rstrip(),
    )

    with pytest.raises(ValueError, match="has been removed"):
        load_config(str(config_path))


def test_load_config_parses_skip_object_bboxes_in_background(tmp_path):
    config_path = _write_min_config(
        tmp_path,
        img_process_extra="""
  skip_object_bboxes_in_background: true
""".rstrip(),
    )

    cfg = load_config(str(config_path))

    assert cfg.img_process.skip_object_bboxes_in_background is True


def test_load_config_split_maps_fallback_to_legacy_map(tmp_path):
    config_path = _write_min_config(
        tmp_path,
        img_process_extra="""
  encoders_tag:
    mono-2bit: 7
    mono-mask-1bit: 8
""".rstrip(),
    )

    cfg = load_config(str(config_path))

    assert cfg.img_process.encoders_tag == {"mono-2bit": 7, "mono-mask-1bit": 8}


def test_load_config_parses_zlib_level(tmp_path):
    config_path = _write_min_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "  max_iter: 20",
            "  max_iter: 20\n  zlib_level: 1",
        ),
        encoding="utf-8",
    )

    cfg = load_config(str(config_path))

    assert cfg.enc.zlib_level == 1


def test_load_config_parses_mixed_mono_template_fields(tmp_path):
    config_path = _write_min_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "  max_iter: 20",
            "  max_iter: 20\n  mono_2bit_mixed_two_bit_run: 6\n  mono_2bit_mixed_one_bit_run: 2",
        ),
        encoding="utf-8",
    )

    cfg = load_config(str(config_path))
    assert cfg.enc.mono_2bit_mixed_two_bit_run == 6
    assert cfg.enc.mono_2bit_mixed_one_bit_run == 2


def test_load_config_parses_drop1bit_fill_gray_level(tmp_path):
    config_path = _write_min_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "  max_iter: 20",
            "  max_iter: 20\n  mono_2bit_drop1bit_fill_gray_level: 200",
        ),
        encoding="utf-8",
    )

    cfg = load_config(str(config_path))
    assert cfg.enc.mono_2bit_drop1bit_fill_gray_level == 200


def test_load_config_parses_drop1bit_neighbor_k(tmp_path):
    config_path = _write_min_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "  max_iter: 20",
            "  max_iter: 20\n  mono_2bit_drop1bit_neighbor_k: 3",
        ),
        encoding="utf-8",
    )

    cfg = load_config(str(config_path))
    assert cfg.enc.mono_2bit_drop1bit_neighbor_k == 3


@pytest.mark.parametrize("field_name", ["mono_2bit_mixed_two_bit_run", "mono_2bit_mixed_one_bit_run"])
def test_load_config_rejects_non_positive_mixed_mono_template_fields(tmp_path, field_name):
    config_path = _write_min_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "  max_iter: 20",
            f"  max_iter: 20\n  {field_name}: 0",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=field_name):
        load_config(str(config_path))


@pytest.mark.parametrize("raw_value", [-1, 10])
def test_load_config_rejects_invalid_zlib_level(tmp_path, raw_value):
    config_path = _write_min_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "  max_iter: 20",
            f"  max_iter: 20\n  zlib_level: {raw_value}",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="zlib_level"):
        load_config(str(config_path))


@pytest.mark.parametrize("raw_value", [-1, 256])
def test_load_config_rejects_invalid_drop1bit_fill_gray_level(tmp_path, raw_value):
    config_path = _write_min_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "  max_iter: 20",
            f"  max_iter: 20\n  mono_2bit_drop1bit_fill_gray_level: {raw_value}",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="mono_2bit_drop1bit_fill_gray_level"):
        load_config(str(config_path))


@pytest.mark.parametrize("raw_value", [0, -1])
def test_load_config_rejects_invalid_drop1bit_neighbor_k(tmp_path, raw_value):
    config_path = _write_min_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "  max_iter: 20",
            f"  max_iter: 20\n  mono_2bit_drop1bit_neighbor_k: {raw_value}",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="mono_2bit_drop1bit_neighbor_k"):
        load_config(str(config_path))


def test_load_config_defaults_input_catalog_sampling_to_uniform(tmp_path):
    config_path = _write_min_config(tmp_path)
    cfg = load_config(str(config_path))
    assert cfg.io.input_catalog_sampling == "uniform"


def test_load_config_defaults_log_feeder_events_to_false(tmp_path):
    config_path = _write_min_config(tmp_path)
    cfg = load_config(str(config_path))
    assert cfg.image_feeder.log_feeder_events is False


def test_load_config_defaults_write_json_logs_to_true(tmp_path):
    config_path = _write_min_config(tmp_path)
    cfg = load_config(str(config_path))
    assert cfg.io.write_json_logs is True


def test_load_config_parses_write_json_logs_false(tmp_path):
    config_path = _write_min_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "  pre_comp_det_filename: pre_comp_det.json",
            "  pre_comp_det_filename: pre_comp_det.json\n  write_json_logs: false",
        ),
        encoding="utf-8",
    )

    cfg = load_config(str(config_path))
    assert cfg.io.write_json_logs is False


def test_load_config_parses_log_feeder_events_true(tmp_path):
    config_path = _write_min_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8") + "\nimage_feeder:\n  log_feeder_events: true\n",
        encoding="utf-8",
    )

    cfg = load_config(str(config_path))
    assert cfg.image_feeder.log_feeder_events is True


def test_load_config_parses_input_catalog_sampling(tmp_path):
    config_path = _write_min_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "  pre_comp_det_filename: pre_comp_det.json",
            "  pre_comp_det_filename: pre_comp_det.json\n  input_catalog_sampling: proportional",
        ),
        encoding="utf-8",
    )

    cfg = load_config(str(config_path))
    assert cfg.io.input_catalog_sampling == "proportional"


def test_load_config_rejects_invalid_input_catalog_sampling(tmp_path):
    config_path = _write_min_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "  pre_comp_det_filename: pre_comp_det.json",
            "  pre_comp_det_filename: pre_comp_det.json\n  input_catalog_sampling: random",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="input_catalog_sampling"):
        load_config(str(config_path))


def test_load_config_defaults_adaptive_pipeline_thresholds(tmp_path):
    config_path = _write_min_config(tmp_path)

    cfg = load_config(str(config_path))

    assert cfg.pipeline_manager.queue_backlog_threshold_1 == 5
    assert cfg.pipeline_manager.queue_backlog_threshold_2 == 10
    assert cfg.pipeline_manager.queue_backlog_threshold_3 == 15
    assert cfg.pipeline_manager.fast_full_hysteresis_exit == pytest.approx(7.5)
    assert cfg.pipeline_manager.skip_obj_hysteresis_exit == pytest.approx(12.5)
    assert cfg.pipeline_manager.adaptive_compression_rate_warmup_frames == 10
    assert cfg.pipeline_manager.adaptive_compression_rate_max == pytest.approx(300.0)
    assert cfg.pipeline_manager.adaptive_compression_rate_boost_factor == pytest.approx(1.5)
    assert cfg.pipeline_manager.adaptive_compression_rate_method == "moving_average"
    assert cfg.pipeline_manager.adaptive_compression_rate_target_margin_ratio == pytest.approx(0.2)
    assert cfg.pipeline_manager.adaptive_compression_rate_ema_alpha == pytest.approx(0.2)
    assert cfg.pipeline_manager.large_dim_tile_threshold_px == 1280


def test_load_config_parses_adaptive_pipeline_thresholds(tmp_path):
    config_path = _write_min_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "decoder:\n  avif_timeout_sec: 120",
            "pipeline_manager:\n  queue_backlog_threshold_1: 9\n  queue_backlog_threshold_2: 12\n  queue_backlog_threshold_3: 20\n  fast_full_hysteresis_exit: 10.0\n  skip_obj_hysteresis_exit: 17.0\n  adaptive_compression_rate_warmup_frames: 4\n  adaptive_compression_rate_max: 222.0\n  adaptive_compression_rate_boost_factor: 1.8\n  adaptive_compression_rate_method: ema\n  adaptive_compression_rate_target_margin_ratio: 0.35\n  adaptive_compression_rate_ema_alpha: 0.4\n  large_dim_tile_threshold_px: 1400\ndecoder:\n  avif_timeout_sec: 120",
        ),
        encoding="utf-8",
    )

    cfg = load_config(str(config_path))

    assert cfg.pipeline_manager.queue_backlog_threshold_1 == 9
    assert cfg.pipeline_manager.queue_backlog_threshold_2 == 12
    assert cfg.pipeline_manager.queue_backlog_threshold_3 == 20
    assert cfg.pipeline_manager.fast_full_hysteresis_exit == pytest.approx(10.0)
    assert cfg.pipeline_manager.skip_obj_hysteresis_exit == pytest.approx(17.0)
    assert cfg.pipeline_manager.adaptive_compression_rate_warmup_frames == 4
    assert cfg.pipeline_manager.adaptive_compression_rate_max == pytest.approx(222.0)
    assert cfg.pipeline_manager.adaptive_compression_rate_boost_factor == pytest.approx(1.8)
    assert cfg.pipeline_manager.adaptive_compression_rate_method == "ema"
    assert cfg.pipeline_manager.adaptive_compression_rate_target_margin_ratio == pytest.approx(0.35)
    assert cfg.pipeline_manager.adaptive_compression_rate_ema_alpha == pytest.approx(0.4)
    assert cfg.pipeline_manager.large_dim_tile_threshold_px == 1400


@pytest.mark.parametrize(
    "field_name,raw_value",
    [
        ("queue_backlog_threshold_1", -1),
        ("queue_backlog_threshold_2", -1),
        ("queue_backlog_threshold_3", -1),
        ("adaptive_compression_rate_warmup_frames", -1),
        ("large_dim_tile_threshold_px", -1),
    ],
)
def test_load_config_rejects_negative_adaptive_pipeline_thresholds(tmp_path, field_name, raw_value):
    config_path = _write_min_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "decoder:\n  avif_timeout_sec: 120",
            f"pipeline_manager:\n  {field_name}: {raw_value}\ndecoder:\n  avif_timeout_sec: 120",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=field_name):
        load_config(str(config_path))


def test_load_config_rejects_non_positive_adaptive_compression_rate_max(tmp_path):
    config_path = _write_min_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "decoder:\n  avif_timeout_sec: 120",
            "pipeline_manager:\n  adaptive_compression_rate_max: 0\ndecoder:\n  avif_timeout_sec: 120",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="adaptive_compression_rate_max"):
        load_config(str(config_path))


def test_load_config_rejects_non_positive_adaptive_compression_rate_boost_factor(tmp_path):
    config_path = _write_min_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "decoder:\n  avif_timeout_sec: 120",
            "pipeline_manager:\n  adaptive_compression_rate_boost_factor: 0\ndecoder:\n  avif_timeout_sec: 120",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="adaptive_compression_rate_boost_factor"):
        load_config(str(config_path))


def test_load_config_rejects_invalid_adaptive_compression_rate_method(tmp_path):
    config_path = _write_min_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "decoder:\n  avif_timeout_sec: 120",
            "pipeline_manager:\n  adaptive_compression_rate_method: unsupported\ndecoder:\n  avif_timeout_sec: 120",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="adaptive_compression_rate_method"):
        load_config(str(config_path))


def test_load_config_rejects_out_of_range_adaptive_compression_rate_target_margin_ratio(tmp_path):
    config_path = _write_min_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "decoder:\n  avif_timeout_sec: 120",
            "pipeline_manager:\n  adaptive_compression_rate_target_margin_ratio: 1.1\ndecoder:\n  avif_timeout_sec: 120",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="adaptive_compression_rate_target_margin_ratio"):
        load_config(str(config_path))


def test_load_config_rejects_out_of_range_adaptive_compression_rate_ema_alpha(tmp_path):
    config_path = _write_min_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "decoder:\n  avif_timeout_sec: 120",
            "pipeline_manager:\n  adaptive_compression_rate_ema_alpha: 1.5\ndecoder:\n  avif_timeout_sec: 120",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="adaptive_compression_rate_ema_alpha"):
        load_config(str(config_path))


def test_load_config_rejects_invalid_queue_backlog_threshold_order(tmp_path):
    config_path = _write_min_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "decoder:\n  avif_timeout_sec: 120",
            "pipeline_manager:\n  queue_backlog_threshold_1: 7\n  queue_backlog_threshold_2: 7\n  queue_backlog_threshold_3: 9\ndecoder:\n  avif_timeout_sec: 120",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="queue_backlog_threshold_1"):
        load_config(str(config_path))


def test_load_config_parses_new_canny_mode_and_deriche_fields(tmp_path):
    config_path = _write_min_config(
        tmp_path,
        img_process_extra="""
  canny_mode: new
  canny_deriche_bilateral_d: 9
  canny_deriche_bilateral_sigma_color: 45
  canny_deriche_bilateral_sigma_space: 46
  canny_deriche_gaussian_sigma: 1.9
  canny_deriche_morph_close_kernel: 5
  canny_deriche_morph_close_iterations: 2
""".rstrip(),
    )

    cfg = load_config(str(config_path))

    assert cfg.img_process.canny_mode == "new"
    assert cfg.img_process.canny_deriche_bilateral_d == 9
    assert cfg.img_process.canny_deriche_bilateral_sigma_color == pytest.approx(45.0)
    assert cfg.img_process.canny_deriche_bilateral_sigma_space == pytest.approx(46.0)
    assert cfg.img_process.canny_deriche_gaussian_sigma == pytest.approx(1.9)
    assert cfg.img_process.canny_deriche_morph_close_kernel == 5
    assert cfg.img_process.canny_deriche_morph_close_iterations == 2


def test_load_config_rejects_invalid_canny_mode(tmp_path):
    config_path = _write_min_config(
        tmp_path,
        img_process_extra="""
  canny_mode: unsupported
""".rstrip(),
    )

    with pytest.raises(ValueError, match="canny_mode"):
        load_config(str(config_path))


def test_load_config_parses_mono_skel_tuning_fields(tmp_path):
    config_path = _write_min_config(
        tmp_path,
        img_process_extra="""
  mono_skel_max_segments: 18
  mono_skel_min_segment_length: 3
  mono_skel_hough_threshold: 9
  mono_skel_max_segment_gap: 4
  mono_skel_work_max_dim: 192
  mono_skel_stitch_angle_tol_deg: 25.0
""".rstrip(),
    )

    cfg = load_config(str(config_path))

    assert cfg.img_process.mono_skel_max_segments == 18
    assert cfg.img_process.mono_skel_min_segment_length == 3
    assert cfg.img_process.mono_skel_hough_threshold == 9
    assert cfg.img_process.mono_skel_max_segment_gap == 4
    assert cfg.img_process.mono_skel_work_max_dim == 192
    assert cfg.img_process.mono_skel_stitch_angle_tol_deg == pytest.approx(25.0)


@pytest.mark.parametrize(
    "field_name, raw_value",
    [
        ("mono_skel_max_segments", 0),
        ("mono_skel_min_segment_length", 0),
        ("mono_skel_hough_threshold", 0),
        ("mono_skel_work_max_dim", 0),
        ("mono_skel_stitch_angle_tol_deg", 0),
    ],
)
def test_load_config_rejects_non_positive_mono_skel_fields(tmp_path, field_name, raw_value):
    config_path = _write_min_config(
        tmp_path,
        img_process_extra=f"  {field_name}: {raw_value}",
    )

    with pytest.raises(ValueError, match=field_name):
        load_config(str(config_path))


def test_load_config_parses_mono_shape_v1_tuning_fields(tmp_path):
    config_path = _write_min_config(
        tmp_path,
        img_process_extra="""
  mono_shape_max_points: 80
  mono_shape_epsilon_ratio: 0.01
""".rstrip(),
    )

    cfg = load_config(str(config_path))

    assert cfg.img_process.mono_shape_max_points == 80
    assert cfg.img_process.mono_shape_epsilon_ratio == pytest.approx(0.01)


@pytest.mark.parametrize(
    "field_name, raw_value",
    [
        ("mono_shape_max_points", 0),
        ("mono_shape_epsilon_ratio", 0),
        ("mono_shape_max_points", -1),
        ("mono_shape_epsilon_ratio", -0.5),
    ],
)
def test_load_config_rejects_non_positive_mono_shape_v1_fields(tmp_path, field_name, raw_value):
    config_path = _write_min_config(
        tmp_path,
        img_process_extra=f"  {field_name}: {raw_value}",
    )

    with pytest.raises(ValueError, match=field_name):
        load_config(str(config_path))


def _with_model_extra(config_path: Path, model_extra: str) -> Path:
    """Append extra `model:` section keys to a config written by `_write_min_config`."""
    text = config_path.read_text(encoding="utf-8")
    anchor = "  valid_obj_categories:\n"
    assert anchor in text, "expected _write_min_config's model section to end with valid_obj_categories"
    config_path.write_text(text.replace(anchor, anchor + model_extra.rstrip("\n") + "\n", 1), encoding="utf-8")
    return config_path


def test_load_default_config_uses_sets_values_for_dlstreamer_detector_backend():
    """configs/default.yaml opts into the DL Streamer Pipeline Server detector by default."""
    cfg = load_config()

    assert cfg.model.dlstreamer_pipeline_name == "star_image_object_detection"
    assert cfg.model.dlstreamer_exchange_input_dir == Path("/app/data")
    assert cfg.model.dlstreamer_exchange_output_dir == Path("/app/output")
    assert cfg.model.dlstreamer_poll_interval_sec == pytest.approx(0.2)
    assert cfg.model.dlstreamer_timeout_sec == pytest.approx(30.0)


def test_load_config_detector_backend_defaults_to_yolo_when_omitted(tmp_path):
    """A config predating this field (no `detector_backend` key) keeps the legacy YOLO path."""
    config_path = _write_min_config(tmp_path)

    cfg = load_config(str(config_path))

    assert cfg.model.detector_backend == "yolo"


def test_load_config_parses_dlstreamer_backend_fields(tmp_path):
    config_path = _write_min_config(tmp_path)
    _with_model_extra(
        config_path,
        """
  detector_backend: dlstreamer
  dlstreamer_base_url: http://localhost:9090
  dlstreamer_pipeline_name: custom_object_detection
  dlstreamer_exchange_input_dir: /tmp/exchange/input
  dlstreamer_exchange_output_dir: /tmp/exchange/output
  dlstreamer_poll_interval_sec: 0.5
  dlstreamer_timeout_sec: 45.0
""",
    )

    cfg = load_config(str(config_path))

    assert cfg.model.detector_backend == "dlstreamer"
    assert cfg.model.dlstreamer_base_url == "http://localhost:9090"
    assert cfg.model.dlstreamer_pipeline_name == "custom_object_detection"
    assert cfg.model.dlstreamer_exchange_input_dir == Path("/tmp/exchange/input")  # nosec B108 - asserting a config value, not creating a temp file
    assert cfg.model.dlstreamer_exchange_output_dir == Path("/tmp/exchange/output")  # nosec B108 - asserting a config value, not creating a temp file
    assert cfg.model.dlstreamer_poll_interval_sec == pytest.approx(0.5)
    assert cfg.model.dlstreamer_timeout_sec == pytest.approx(45.0)


def test_load_config_detector_backend_is_case_insensitive(tmp_path):
    config_path = _write_min_config(tmp_path)
    _with_model_extra(config_path, "  detector_backend: DLStreamer\n")

    cfg = load_config(str(config_path))

    assert cfg.model.detector_backend == "dlstreamer"


def test_load_config_rejects_invalid_detector_backend(tmp_path):
    config_path = _write_min_config(tmp_path)
    _with_model_extra(config_path, "  detector_backend: tensorflow\n")

    with pytest.raises(ValueError, match="detector_backend"):
        load_config(str(config_path))


def test_load_config_rejects_dlstreamer_backend_with_non_positive_timeout(tmp_path):
    config_path = _write_min_config(tmp_path)
    _with_model_extra(
        config_path,
        """
  detector_backend: dlstreamer
  dlstreamer_timeout_sec: 0
""",
    )

    with pytest.raises(ValueError, match="dlstreamer_timeout_sec"):
        load_config(str(config_path))


def test_load_config_rejects_dlstreamer_backend_with_non_positive_poll_interval(tmp_path):
    config_path = _write_min_config(tmp_path)
    _with_model_extra(
        config_path,
        """
  detector_backend: dlstreamer
  dlstreamer_poll_interval_sec: -0.1
""",
    )

    with pytest.raises(ValueError, match="dlstreamer_poll_interval_sec"):
        load_config(str(config_path))


def test_load_config_allows_yolo_backend_with_blank_dlstreamer_base_url(tmp_path):
    """dlstreamer_* fields are only validated when detector_backend=dlstreamer is active."""
    config_path = _write_min_config(tmp_path)
    _with_model_extra(
        config_path,
        """
  detector_backend: yolo
  dlstreamer_base_url: ""
""",
    )

    cfg = load_config(str(config_path))

    assert cfg.model.detector_backend == "yolo"


def test_load_default_config_includes_mux_frame_and_crop_limits():
    cfg = load_config()
    assert cfg.mux_cfg.max_frame_len == 64 * 1024 * 1024
    assert cfg.mux_cfg.default_max_crops == 255


def test_load_config_defaults_mux_frame_and_crop_limits_when_omitted(tmp_path):
    config_path = _write_min_config(tmp_path)

    cfg = load_config(str(config_path))

    assert cfg.mux_cfg.max_frame_len == 64 * 1024 * 1024
    assert cfg.mux_cfg.default_max_crops == 255


def test_load_config_parses_mux_frame_and_crop_limits(tmp_path):
    config_path = _write_min_config(
        tmp_path,
        mux_cfg_extra="""
  max_frame_len: 1048576
  default_max_crops: 32
""",
    )

    cfg = load_config(str(config_path))

    assert cfg.mux_cfg.max_frame_len == 1048576
    assert cfg.mux_cfg.default_max_crops == 32


@pytest.mark.parametrize(
    "field_name, raw_value",
    [
        ("max_frame_len", -1),
        ("default_max_crops", -1),
    ],
)
def test_load_config_rejects_negative_mux_frame_and_crop_limits(tmp_path, field_name, raw_value):
    config_path = _write_min_config(
        tmp_path,
        mux_cfg_extra=f"\n  {field_name}: {raw_value}\n",
    )

    with pytest.raises(ValueError, match=">= 0"):
        load_config(str(config_path))


def test_load_default_config_includes_service_max_body_bytes():
    cfg = load_config()
    assert cfg.enc.max_body_bytes == 25 * 1024 * 1024
    assert cfg.dec.max_body_bytes == 25 * 1024 * 1024


def test_load_config_defaults_service_max_body_bytes_when_omitted(tmp_path):
    config_path = _write_min_config(tmp_path)

    cfg = load_config(str(config_path))

    assert cfg.enc.max_body_bytes == 25 * 1024 * 1024
    assert cfg.dec.max_body_bytes == 25 * 1024 * 1024


def test_load_config_parses_service_max_body_bytes(tmp_path):
    config_path = _write_min_config(
        tmp_path,
        encoder_extra="  max_body_bytes: 1048576\n",
        decoder_extra="  max_body_bytes: 2097152\n",
    )

    cfg = load_config(str(config_path))

    assert cfg.enc.max_body_bytes == 1048576
    assert cfg.dec.max_body_bytes == 2097152


@pytest.mark.parametrize("section", ["encoder_extra", "decoder_extra"])
def test_load_config_rejects_negative_service_max_body_bytes(tmp_path, section):
    config_path = _write_min_config(tmp_path, **{section: "  max_body_bytes: -1\n"})

    with pytest.raises(ValueError, match=">= 0"):
        load_config(str(config_path))
