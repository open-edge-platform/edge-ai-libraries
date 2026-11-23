# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import sys
from pathlib import Path

import matplotlib
import pytest

from semantic_img_comp.utils import summarize_logs


matplotlib.use("Agg")


def _write_ndjson(path: Path, records) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            if isinstance(record, str):
                handle.write(record + "\n")
            else:
                handle.write(json.dumps(record) + "\n")


def test_parse_pixels_total_supports_common_shapes():
    assert summarize_logs._parse_pixels_total([8, 6]) == 48.0
    assert summarize_logs._parse_pixels_total({"width": 8, "height": 6}) == 48.0
    assert summarize_logs._parse_pixels_total({"w": "8", "h": "6"}) == 48.0
    assert summarize_logs._parse_pixels_total(123) == 123.0


def test_iter_summaries_parses_current_encoder_log_shape(tmp_path: Path):
    log_path = tmp_path / "encoder_log.json"
    _write_ndjson(
        log_path,
        [
            {
                "event": "payloads_multiplexed",
                "orig_jpeg_bytes": 2000,
                "total_payload_bytes": 500,
                "aggregated_comp_rate": 3.25,
                "orig_img_size_wh": [10, 20],
                "num_detected_objs": 2,
                "objects_total_pixels": 40,
                "payload_size_bytes_by_bucket": {
                    "background": 300,
                    "objects": 150,
                    "metadata": 50,
                },
                "timing_ms": {
                    "yolo": 3.5,
                    "enc_total": 8.5,
                },
                "fast_path_bg_selected": True,
                "fast_path_obj_selected": False,
                "obj_detection_skipped": True,
            }
        ],
    )

    rows = list(summarize_logs.iter_summaries(log_path))

    assert len(rows) == 1
    row = rows[0]
    assert row["orig_jpeg_bytes"] == 2000.0
    assert row["total_payload_bytes"] == 500.0
    assert row["comp_rate"] == 4.0
    assert row["aggregated_comp_rate"] == 3.25
    assert row["orig_total_pixels"] == pytest.approx(0.0002)
    assert row["payload_background_bytes"] == 300.0
    assert row["bg_payload_ratio"] == 0.6
    assert row["obj_payload_ratio"] == 0.4
    assert row["bg_origjpeg_ratio"] == 0.15
    assert row["obj_origjpeg_ratio"] == 0.1
    assert row["obj_orig_pixels_ratio"] == pytest.approx(40 / 200)
    assert row["runtime_yolo_ms"] == 3.5
    assert row["runtime_enc_total_ms"] == 8.5
    assert row["runtime_breakdown_ms"] == {"yolo": 3.5, "enc_total": 8.5}
    assert row["fast_path_bg_selected"] is True
    assert row["fast_path_obj_selected"] is False
    assert row["obj_detection_skipped"] is True


def test_iter_summaries_parses_organized_encoder_log_shape(tmp_path: Path):
    log_path = tmp_path / "encoder_log_organized.json"
    _write_ndjson(
        log_path,
        [
            {
                "event": "payloads_multiplexed",
                "image": {
                    "orig_jpeg_bytes": 2000,
                    "orig_size_wh": [10, 20],
                },
                "payload": {
                    "total_bytes": 500,
                    "bytes_by_bucket": {
                        "background": 300,
                        "objects": 150,
                        "metadata": 50,
                    },
                },
                "metrics": {"aggregated_comp_rate": 3.25},
                "objects": {
                    "count": 2,
                    "total_pixels": 40,
                    "enc_idx": [1, 2],
                    "scaling_factor": [0.8, 0.6],
                    "orig_min_dim_per_crop": [5, 9],
                    "detection_skipped": 0,
                },
                "background": {
                    "enc_idx": 2,
                    "scale_factor": 0.5,
                },
                "fast_path": {
                    "bg_selected": True,
                    "obj_selected": "true",
                },
                "runtime_ms": {
                    "yolo": 3.5,
                    "enc_total": 8.5,
                },
            }
        ],
    )

    rows = list(summarize_logs.iter_summaries(log_path))

    assert len(rows) == 1
    row = rows[0]
    assert row["orig_jpeg_bytes"] == 2000.0
    assert row["total_payload_bytes"] == 500.0
    assert row["comp_rate"] == 4.0
    assert row["aggregated_comp_rate"] == 3.25
    assert row["orig_total_pixels"] == pytest.approx(0.0002)
    assert row["payload_background_bytes"] == 300.0
    assert row["bg_payload_ratio"] == 0.6
    assert row["obj_payload_ratio"] == 0.4
    assert row["bg_origjpeg_ratio"] == 0.15
    assert row["obj_origjpeg_ratio"] == 0.1
    assert row["obj_orig_pixels_ratio"] == pytest.approx(40 / 200)
    assert row["runtime_yolo_ms"] == 3.5
    assert row["runtime_enc_total_ms"] == 8.5
    assert row["bg_enc_idx"] == 2
    assert row["objs_enc_idx"] == [1, 2]
    assert row["bg_scale_factor"] == 0.5
    assert row["objs_scaling_factor"] == [0.8, 0.6]
    assert row["objs_orig_min_dim_per_crop"] == [5.0, 9.0]
    assert row["fast_path_bg_selected"] is True
    assert row["fast_path_obj_selected"] is True
    assert row["obj_detection_skipped"] is False


def test_iter_summaries_backfills_aggregated_comp_rate_from_frame_sent_metrics(tmp_path: Path):
    log_path = tmp_path / "encoder_log_split_metrics.json"
    _write_ndjson(
        log_path,
        [
            {
                "event": "payloads_multiplexed",
                "frame_id": 7,
                "image": {
                    "orig_jpeg_bytes": 2000,
                    "orig_size_wh": [10, 20],
                },
                "payload": {
                    "total_bytes": 500,
                    "bytes_by_bucket": {
                        "background": 300,
                        "objects": 150,
                        "metadata": 50,
                    },
                },
            },
            {
                "event": "frame_sent",
                "frame_id": 7,
                "queue_backlog": 0,
                "metrics": {
                    "aggregated_comp_rate": 3.25,
                    "comp_rate": 4.0,
                    "tar_comp_rate": 120.0,
                    "comp_level": 2,
                },
            },
        ],
    )

    rows = list(summarize_logs.iter_summaries(log_path))

    assert len(rows) == 1
    assert rows[0]["comp_rate"] == 4.0
    assert rows[0]["aggregated_comp_rate"] == 3.25


def test_collect_runtime_breakdown_series_supports_dynamic_timing_keys():
    rows = [
        {
            "runtime_breakdown_ms": {
                "yolo": 3.0,
                "enc_total": 8.0,
                "payload_pack": 1.2,
                "bad": "nan",
            }
        },
        {
            "runtime_breakdown_ms": {
                "payload_pack": "1.8",
            }
        },
        {
            "runtime_yolo_ms": 4.0,
            "runtime_enc_total_ms": 9.0,
        },
    ]

    assert summarize_logs._collect_runtime_breakdown_series(rows) == {
        "enc_total": [8.0, 9.0],
        "payload_pack": [1.2, 1.8],
        "yolo": [3.0, 4.0],
    }


def test_collect_runtime_breakdown_series_skips_zero_yolo_runtime_values():
    rows = [
        {
            "runtime_breakdown_ms": {
                "yolo": 0.0,
                "enc_total": 0.0,
            }
        },
        {
            "runtime_yolo_ms": 0.0,
            "runtime_enc_total_ms": 9.0,
        },
        {
            "runtime_breakdown_ms": {
                "yolo": 3.5,
                "enc_total": 8.0,
            }
        },
    ]

    assert summarize_logs._collect_runtime_breakdown_series(rows) == {
        "enc_total": [9.0, 8.0],
        "yolo": [3.5],
    }


def test_iter_summaries_parses_decoder_log_shape(tmp_path: Path):
    log_path = tmp_path / "decoder_log.json"
    _write_ndjson(log_path, [{"event": "frame_decoded", "decode_time_ms": 17.25}])

    rows = list(summarize_logs.iter_summaries(log_path))

    assert rows == [{"runtime_dec_total_ms": 17.25}]


def test_iter_summaries_skips_bad_json_when_requested(tmp_path: Path):
    log_path = tmp_path / "mixed.json"
    _write_ndjson(
        log_path,
        [
            "{not-json}",
            {
                "orig_jpeg_bytes": 1000,
                "total_payload_bytes": 250,
            },
        ],
    )

    rows = list(summarize_logs.iter_summaries(log_path, strict_json=False))

    assert len(rows) == 1
    assert rows[0]["comp_rate"] == 4.0


def test_iter_summaries_raises_on_bad_json_in_strict_mode(tmp_path: Path):
    log_path = tmp_path / "broken.json"
    _write_ndjson(log_path, ["{not-json}"])

    with pytest.raises(ValueError, match="Invalid JSON on line 1"):
        list(summarize_logs.iter_summaries(log_path, strict_json=True))


def test_iter_summaries_skips_invalid_encoder_rows(tmp_path: Path):
    log_path = tmp_path / "encoder_log.json"
    _write_ndjson(
        log_path,
        [
            {"orig_jpeg_bytes": 1000, "total_payload_bytes": 0},
            {"orig_jpeg_bytes": 1000},
            {"event": "unrelated"},
        ],
    )

    assert list(summarize_logs.iter_summaries(log_path)) == []


def test_infer_plot_modes_prefers_row_content_over_filename():
    rows = [{"comp_rate": 4.0}, {"runtime_dec_total_ms": 10.0}]

    assert summarize_logs._infer_plot_modes("decoder_log.json", rows) == ["encoder", "decoder"]


def test_iter_summaries_parses_codec_index_fields(tmp_path: Path):
    log_path = tmp_path / "enc_with_codec_idx.json"
    _write_ndjson(
        log_path,
        [
            {
                "orig_jpeg_bytes": 2000,
                "total_payload_bytes": 500,
                "bg_enc_idx": 2,
                "objs_enc_idx": [1, "2", None, "bad"],
            }
        ],
    )

    rows = list(summarize_logs.iter_summaries(log_path))
    assert len(rows) == 1
    assert rows[0]["bg_enc_idx"] == 2
    assert rows[0]["objs_enc_idx"] == [1, 2]


def test_iter_summaries_parses_scaling_factor_fields(tmp_path: Path):
    log_path = tmp_path / "enc_with_scaling_factors.json"
    _write_ndjson(
        log_path,
        [
            {
                "orig_jpeg_bytes": 2000,
                "total_payload_bytes": 500,
                "bg_scale_factor": "0.75",
                "objs_scaling_factor": [1, "0.5", None, "bad"],
            }
        ],
    )

    rows = list(summarize_logs.iter_summaries(log_path))
    assert len(rows) == 1
    assert rows[0]["bg_scale_factor"] == 0.75
    assert rows[0]["objs_scaling_factor"] == [1.0, 0.5]


def test_iter_summaries_parses_orig_min_dim_per_crop_field(tmp_path: Path):
    log_path = tmp_path / "enc_with_orig_min_dim.json"
    _write_ndjson(
        log_path,
        [
            {
                "orig_jpeg_bytes": 2000,
                "total_payload_bytes": 500,
                "objs_orig_min_dim_per_crop": [12, "7", None, "bad", 0, -3],
            }
        ],
    )

    rows = list(summarize_logs.iter_summaries(log_path))
    assert len(rows) == 1
    assert rows[0]["objs_orig_min_dim_per_crop"] == [12.0, 7.0, 0.0, -3.0]


def test_count_codec_usage_maps_indices_to_names():
    rows = [
        {"bg_enc_idx": 1, "objs_enc_idx": [1, 3]},
        {"bg_enc_idx": 3, "objs_enc_idx": [3, 99]},
    ]
    mapping = {1: "mono-avif", 3: "mono-mask-1bit"}

    bg_counts = summarize_logs._count_codec_usage(rows, "bg_enc_idx", mapping)
    obj_counts = summarize_logs._count_codec_usage(rows, "objs_enc_idx", mapping)

    assert bg_counts == {"mono-avif": 1, "mono-mask-1bit": 1}
    assert obj_counts == {"mono-avif": 1, "mono-mask-1bit": 2, "unknown:99": 1}


def test_compute_image_flag_ratios_uses_total_image_count():
    rows = [
        {
            "fast_path_bg_selected": True,
            "fast_path_obj_selected": True,
            "obj_detection_skipped": False,
        },
        {
            "fast_path_bg_selected": True,
            "fast_path_obj_selected": False,
            "obj_detection_skipped": True,
        },
        {
            "fast_path_bg_selected": False,
            "fast_path_obj_selected": False,
            "obj_detection_skipped": False,
        },
        {},
    ]

    assert summarize_logs._compute_image_flag_ratios(rows) == {
        "fast_path_bg_only_selected": 0.25,
        "fast_path_obj_only_selected": 0.0,
        "obj_detection_skipped": 0.25,
        "both_fast_path_bg_and_obj_selected": 0.25,
        "no_fast_path_selected": 0.5,
    }


def test_plot_image_flag_ratios_has_five_bars():
    import matplotlib.pyplot as plt

    rows = [
        {"fast_path_bg_selected": True, "fast_path_obj_selected": False, "obj_detection_skipped": False},
        {"fast_path_bg_selected": False, "fast_path_obj_selected": True, "obj_detection_skipped": False},
        {"fast_path_bg_selected": True, "fast_path_obj_selected": True, "obj_detection_skipped": False},
        {"fast_path_bg_selected": False, "fast_path_obj_selected": False, "obj_detection_skipped": True},
    ]

    _, ax = plt.subplots()
    summarize_logs._plot_image_flag_ratios(ax, rows)

    assert len(ax.patches) == 5
    plt.close()


def test_make_enc_plots_writes_image_flag_ratio_barplot(tmp_path: Path):
    rows = [
        {
            "comp_rate": 4.0,
            "orig_jpeg_bytes": 1000.0,
            "total_payload_bytes": 250.0,
            "fast_path_bg_selected": True,
            "fast_path_obj_selected": True,
            "obj_detection_skipped": False,
        },
        {
            "comp_rate": 5.0,
            "orig_jpeg_bytes": 1200.0,
            "total_payload_bytes": 240.0,
            "fast_path_bg_selected": False,
            "fast_path_obj_selected": True,
            "obj_detection_skipped": True,
        },
    ]

    summarize_logs._make_enc_plots(rows, save_dir=str(tmp_path))

    assert (tmp_path / "image_flag_ratios.png").exists()


def test_iter_summaries_handles_missing_scaling_factor_field(tmp_path: Path):
    """Records missing objects.scaling_factor should parse without error and yield empty list."""
    log_path = tmp_path / "enc_no_scaling.json"
    _write_ndjson(
        log_path,
        [
            {
                "event": "payloads_multiplexed",
                "image": {
                    "orig_jpeg_bytes": 1000,
                    "orig_size_wh": [8, 6],
                },
                "payload": {
                    "total_bytes": 200,
                    "bytes_by_bucket": {"background": 200},
                },
                # No objects.scaling_factor, no objects.scaled_* keys
                "objects": {
                    "count": 2,
                    "total_pixels": 100,
                    "enc_idx": [5, 5],
                    "orig_min_dim_per_crop": [10, 8],
                },
            }
        ],
    )

    rows = list(summarize_logs.iter_summaries(log_path))
    assert len(rows) == 1
    assert rows[0]["objs_scaling_factor"] == []
    assert rows[0]["num_detected_objs"] == 2.0


def test_main_prints_single_status_line_instead_of_summary_rows(tmp_path: Path, monkeypatch, capsys):
    log_path = tmp_path / "encoder_log.json"
    _write_ndjson(
        log_path,
        [
            {
                "orig_jpeg_bytes": 2000,
                "total_payload_bytes": 500,
                "fast_path_bg_selected": True,
                "fast_path_obj_selected": False,
                "obj_detection_skipped": False,
            }
        ],
    )

    monkeypatch.setattr(sys, "argv", ["summarize_logs.py", str(log_path)])

    summarize_logs.main()

    captured = capsys.readouterr()
    assert captured.out.strip() == "Log is processed and summaries are ready."
    assert '"orig_jpeg_bytes"' not in captured.out


