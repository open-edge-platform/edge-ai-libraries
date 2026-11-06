# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: utils/runtime.py
Version: 0.2
Authors: Omid Semiari, Hosein Nikopour
Date: 2026-04-10
Description: creates plots out of encoder decoder logs

#############################
Summarize newline-delimited JSON (NDJSON) encoder/decoder logs and optionally
create plots.

The module accepts one JSON object per line and emits one summary JSON object
per valid log entry. Encoder and decoder records are handled separately:

- Encoder summaries include compression, payload, pixel, and runtime metrics.
- Decoder summaries include total decode runtime.

By default, the CLI prints a short completion message. Summaries may be written
to an output file, and optional plots can be shown or saved to disk.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence
import numpy as np
from semantic_img_comp.utils.config import load_config


# ---------------------------------------------------------------------------
# Accepted input keys
# ---------------------------------------------------------------------------
ORIG_BYTES_KEYS = ("orig_jpeg_bytes", "image.orig_jpeg_bytes")
ORIG_PIXEL_SIZE_KEYS = ("orig_img_size_wh", "orig_img_size_pixels", "orig_img_size", "image.orig_size_wh")
PAYLOAD_BYTES_KEYS = ("total_payload_bytes", "payload.total_bytes")
AGGREGATED_COMP_RATE_KEYS = ("aggregated_comp_rate", "metrics.aggregated_comp_rate")
FRAME_SENT_AGGREGATED_COMP_RATE_KEYS = ("metrics.aggregated_comp_rate", "aggregated_comp_rate")

NUM_DETECTED_OBJS_KEYS = ("num_detected_objs", "objects.count")
OBJECTS_TOTAL_PIXELS_KEYS = ("objects_total_pixels", "objects.total_pixels")

PAYLOAD_BREAKDOWN_KEYS = ("payload_size_bytes_by_bucket", "payload_size_bytes", "payload.bytes_by_bucket")
PAYLOAD_BACKGROUND_KEY = "background"
PAYLOAD_OBJECTS_KEY = "objects"
PAYLOAD_METADATA_KEY = "metadata"

RUNTIME_BREAKDOWN_KEYS = ("timing_ms", "runtime_ms")
RUNTIME_YOLO_KEY = "yolo"
RUNTIME_ENC_TOTAL_KEY = "enc_total"
RUNTIME_DEC_TOTAL_KEYS = ("decode_time_ms",)
BG_ENC_IDX_KEYS = ("bg_enc_idx", "background.enc_idx")
OBJS_ENC_IDX_KEYS = ("objs_enc_idx", "objects.enc_idx")
BG_SCALE_FACTOR_KEYS = ("bg_scale_factor", "background.scale_factor")
OBJS_SCALING_FACTOR_KEYS = ("objs_scaling_factor", "objects.scaling_factor")
OBJS_ORIG_MIN_DIM_PER_CROP_KEYS = ("objs_orig_min_dim_per_crop", "objects.orig_min_dim_per_crop")
FAST_PATH_BG_SELECTED_KEYS = ("fast_path_bg_selected", "fast_path.bg_selected")
FAST_PATH_OBJ_SELECTED_KEYS = ("fast_path_obj_selected", "fast_path.obj_selected")
OBJ_DETECTION_SKIPPED_KEYS = ("obj_detection_skipped", "objects.detection_skipped")

ENCODER_SUMMARY_KEYS = (
    "orig_jpeg_bytes",
    "total_payload_bytes",
    "comp_rate",
    "aggregated_comp_rate",
    "orig_total_pixels",
    "num_detected_objs",
    "objects_total_pixels",
    "payload_background_bytes",
    "bg_payload_ratio",
    "obj_payload_ratio",
    "bg_origjpeg_ratio",
    "obj_origjpeg_ratio",
    "obj_orig_pixels_ratio",
    "runtime_yolo_ms",
    "runtime_enc_total_ms",
    "bg_enc_idx",
    "objs_enc_idx",
    "bg_scale_factor",
    "objs_scaling_factor",
    "objs_orig_min_dim_per_crop",
    "fast_path_bg_selected",
    "fast_path_obj_selected",
    "obj_detection_skipped",
)
DECODER_SUMMARY_KEYS = ("runtime_dec_total_ms",)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------
def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def _to_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and np.isfinite(value):
        return bool(value)
    if isinstance(value, str):
        stripped = value.strip().lower()
        if stripped in {"true", "1", "yes", "y", "on"}:
            return True
        if stripped in {"false", "0", "no", "n", "off"}:
            return False
    return None


def _read_nested(obj: Dict[str, Any], dotted_key: str) -> Any:
    current: Any = obj
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _first_present(obj: Dict[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in obj:
            return obj[key]
        if "." in key:
            nested_value = _read_nested(obj, key)
            if nested_value is not None:
                return nested_value
    return None


def _safe_divide(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _sum_optional(*values: Optional[float]) -> Optional[float]:
    filtered = [value for value in values if value is not None]
    if not filtered:
        return None
    return float(sum(filtered))


def _parse_pixels_total(value: Any) -> Optional[float]:
    """Return total pixels from width/height-like inputs."""
    if value is None:
        return None

    if isinstance(value, (list, tuple)) and len(value) >= 2:
        width = _to_float(value[0])
        height = _to_float(value[1])
        if width is None or height is None:
            return None
        return width * height

    if isinstance(value, dict):
        for width_key, height_key in (("w", "h"), ("width", "height"), ("x", "y")):
            if width_key in value and height_key in value:
                width = _to_float(value.get(width_key))
                height = _to_float(value.get(height_key))
                if width is None or height is None:
                    return None
                return width * height
        return None

    return _to_float(value)


def _iter_ndjson_records(path: str | Path, *, strict_json: bool = True) -> Iterator[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                if strict_json:
                    raise ValueError(f"Invalid JSON on line {line_number}") from exc
                continue

            if isinstance(record, dict):
                yield record


def _parse_decoder_summary(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    runtime_dec_total_ms = _to_float(_first_present(record, RUNTIME_DEC_TOTAL_KEYS))
    if runtime_dec_total_ms is None:
        return None
    return {"runtime_dec_total_ms": runtime_dec_total_ms}


def _normalize_codec_idx(value: Any) -> Optional[int]:
    parsed = _to_float(value)
    if parsed is None or not np.isfinite(parsed):
        return None
    return int(parsed)


def _normalize_codec_idx_list(value: Any) -> List[int]:
    if isinstance(value, (list, tuple)):
        raw_values = value
    else:
        raw_values = [value]

    out: List[int] = []
    for raw in raw_values:
        normalized = _normalize_codec_idx(raw)
        if normalized is not None:
            out.append(normalized)
    return out


def _normalize_float_list(value: Any) -> List[float]:
    if isinstance(value, (list, tuple)):
        raw_values = value
    else:
        raw_values = [value]

    out: List[float] = []
    for raw in raw_values:
        parsed = _to_float(raw)
        if parsed is None or not np.isfinite(parsed):
            continue
        out.append(float(parsed))
    return out


def _load_codec_idx_to_name_map() -> Dict[int, str]:
    """Load encoder-index to codec-name mapping from config; fallback to empty on error."""
    try:
        cfg = load_config()
        legacy_tags = getattr(cfg.img_process, "encoders_tag", None) or {}
        level_tags = {
            **(getattr(cfg.img_process, "encoders_tag_bg_level_1", None) or {}),
            **(getattr(cfg.img_process, "encoders_tag_objs_level_1", None) or {}),
            **(getattr(cfg.img_process, "encoders_tag_bg_level_2", None) or {}),
            **(getattr(cfg.img_process, "encoders_tag_objs_level_2", None) or {}),
        }
        encoders_tag = {**level_tags, **legacy_tags}
    except Exception:
        return {}

    idx_to_name: Dict[int, str] = {}
    for codec_name, codec_idx in encoders_tag.items():
        normalized = _normalize_codec_idx(codec_idx)
        if normalized is not None:
            idx_to_name[normalized] = str(codec_name)
    return idx_to_name


def _count_codec_usage(
    rows: Iterable[Dict[str, Any]],
    key: str,
    idx_to_name: Dict[int, str],
) -> Dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        for codec_idx in _normalize_codec_idx_list(row.get(key)):
            codec_label = idx_to_name.get(codec_idx, f"unknown:{codec_idx}")
            counts[codec_label] += 1
    return dict(counts)


def _compute_image_flag_ratios(rows: Sequence[Dict[str, Any]]) -> Dict[str, float]:
    total_images = len(rows)
    if total_images == 0:
        return {
            "fast_path_bg_only_selected": 0.0,
            "fast_path_obj_only_selected": 0.0,
            "obj_detection_skipped": 0.0,
            "both_fast_path_bg_and_obj_selected": 0.0,
            "no_fast_path_selected": 0.0,
        }

    fast_path_bg_only_count = 0
    fast_path_obj_only_count = 0
    obj_detection_skipped_count = 0
    both_fast_path_count = 0
    no_fast_path_count = 0

    for row in rows:
        bg_selected = bool(row.get("fast_path_bg_selected"))
        obj_selected = bool(row.get("fast_path_obj_selected"))

        if bg_selected and obj_selected:
            both_fast_path_count += 1
        elif bg_selected:
            fast_path_bg_only_count += 1
        elif obj_selected:
            fast_path_obj_only_count += 1
        else:
            no_fast_path_count += 1

        if bool(row.get("obj_detection_skipped")):
            obj_detection_skipped_count += 1

    return {
        "fast_path_bg_only_selected": fast_path_bg_only_count / total_images,
        "fast_path_obj_only_selected": fast_path_obj_only_count / total_images,
        "obj_detection_skipped": obj_detection_skipped_count / total_images,
        "both_fast_path_bg_and_obj_selected": both_fast_path_count / total_images,
        "no_fast_path_selected": no_fast_path_count / total_images,
    }


def _parse_encoder_summary(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    orig_bytes = _to_float(_first_present(record, ORIG_BYTES_KEYS))
    payload_bytes = _to_float(_first_present(record, PAYLOAD_BYTES_KEYS))
    if orig_bytes is None or payload_bytes is None or payload_bytes <= 0:
        return None

    pixels_total = _parse_pixels_total(_first_present(record, ORIG_PIXEL_SIZE_KEYS))
    orig_total_megapixels = pixels_total / 1e6 if pixels_total is not None else None

    num_detected_objs = _to_float(_first_present(record, NUM_DETECTED_OBJS_KEYS))
    objects_total_pixels = _to_float(_first_present(record, OBJECTS_TOTAL_PIXELS_KEYS))
    aggregated_comp_rate = _to_float(_first_present(record, AGGREGATED_COMP_RATE_KEYS))

    runtime_yolo_ms = None
    runtime_enc_total_ms = None
    runtime_breakdown_ms: Dict[str, float] = {}
    runtime_breakdown = _first_present(record, RUNTIME_BREAKDOWN_KEYS)
    if isinstance(runtime_breakdown, dict):
        for runtime_key, runtime_value in runtime_breakdown.items():
            parsed = _to_float(runtime_value)
            if parsed is None or not np.isfinite(parsed):
                continue
            runtime_breakdown_ms[str(runtime_key)] = float(parsed)

        runtime_yolo_ms = runtime_breakdown_ms.get(RUNTIME_YOLO_KEY)
        runtime_enc_total_ms = runtime_breakdown_ms.get(RUNTIME_ENC_TOTAL_KEY)

    payload_background_bytes = None
    bg_payload_ratio = None
    obj_payload_ratio = None
    bg_origjpeg_ratio = None
    obj_origjpeg_ratio = None

    payload_breakdown = _first_present(record, PAYLOAD_BREAKDOWN_KEYS)
    if isinstance(payload_breakdown, dict):
        payload_background_bytes = _to_float(payload_breakdown.get(PAYLOAD_BACKGROUND_KEY))
        payload_obj_bytes = _to_float(payload_breakdown.get(PAYLOAD_OBJECTS_KEY))
        payload_metadata_bytes = _to_float(payload_breakdown.get(PAYLOAD_METADATA_KEY))
        obj_payload_bytes = _sum_optional(payload_obj_bytes, payload_metadata_bytes)

        bg_payload_ratio = _safe_divide(payload_background_bytes, payload_bytes)
        obj_payload_ratio = _safe_divide(obj_payload_bytes, payload_bytes)
        bg_origjpeg_ratio = _safe_divide(payload_background_bytes, orig_bytes)
        obj_origjpeg_ratio = _safe_divide(obj_payload_bytes, orig_bytes)

    bg_enc_idx = _normalize_codec_idx(_first_present(record, BG_ENC_IDX_KEYS))
    objs_enc_idx = _normalize_codec_idx_list(_first_present(record, OBJS_ENC_IDX_KEYS))
    bg_scale_factor = _to_float(_first_present(record, BG_SCALE_FACTOR_KEYS))
    # These three fields are omitted from logs when all per-crop values were None;
    # treat a missing key as an empty list so downstream aggregations are safe.
    _objs_scaling_raw = _first_present(record, OBJS_SCALING_FACTOR_KEYS)
    objs_scaling_factor = _normalize_float_list(_objs_scaling_raw) if _objs_scaling_raw is not None else []
    objs_orig_min_dim_per_crop = _normalize_float_list(_first_present(record, OBJS_ORIG_MIN_DIM_PER_CROP_KEYS))
    fast_path_bg_selected = _to_bool(_first_present(record, FAST_PATH_BG_SELECTED_KEYS))
    fast_path_obj_selected = _to_bool(_first_present(record, FAST_PATH_OBJ_SELECTED_KEYS))
    obj_detection_skipped = _to_bool(_first_present(record, OBJ_DETECTION_SKIPPED_KEYS))

    return {
        "orig_jpeg_bytes": orig_bytes,
        "total_payload_bytes": payload_bytes,
        "comp_rate": orig_bytes / payload_bytes,
        "aggregated_comp_rate": aggregated_comp_rate,
        "orig_total_pixels": orig_total_megapixels,
        "num_detected_objs": num_detected_objs,
        "objects_total_pixels": objects_total_pixels,
        "payload_background_bytes": payload_background_bytes,
        "bg_payload_ratio": bg_payload_ratio,
        "obj_payload_ratio": obj_payload_ratio,
        "bg_origjpeg_ratio": bg_origjpeg_ratio,
        "obj_origjpeg_ratio": obj_origjpeg_ratio,
        "obj_orig_pixels_ratio": _safe_divide(objects_total_pixels, pixels_total),
        "runtime_yolo_ms": runtime_yolo_ms,
        "runtime_enc_total_ms": runtime_enc_total_ms,
        "runtime_breakdown_ms": runtime_breakdown_ms,
        "bg_enc_idx": bg_enc_idx,
        "objs_enc_idx": objs_enc_idx,
        "bg_scale_factor": bg_scale_factor,
        "objs_scaling_factor": objs_scaling_factor,
        "objs_orig_min_dim_per_crop": objs_orig_min_dim_per_crop,
        "fast_path_bg_selected": fast_path_bg_selected,
        "fast_path_obj_selected": fast_path_obj_selected,
        "obj_detection_skipped": obj_detection_skipped,
    }


def _collect_runtime_breakdown_series(rows: Iterable[Dict[str, Any]]) -> Dict[str, List[float]]:
    series: Dict[str, List[float]] = {}
    for row in rows:
        row_runtime_keys: set[str] = set()
        runtime_breakdown = row.get("runtime_breakdown_ms")
        if isinstance(runtime_breakdown, dict):
            for runtime_key, runtime_value in runtime_breakdown.items():
                parsed = _to_float(runtime_value)
                if parsed is None or not np.isfinite(parsed):
                    continue
                normalized_key = str(runtime_key)
                if parsed <= 0:
                    continue
                row_runtime_keys.add(normalized_key)
                series.setdefault(normalized_key, []).append(float(parsed))

        # Keep backward compatibility when only the legacy runtime fields are present.
        for fallback_key, runtime_key in (
            ("runtime_yolo_ms", RUNTIME_YOLO_KEY),
            ("runtime_enc_total_ms", RUNTIME_ENC_TOTAL_KEY),
        ):
            parsed = _to_float(row.get(fallback_key))
            if parsed is None or not np.isfinite(parsed):
                continue
            if parsed <= 0:
                continue
            if runtime_key in row_runtime_keys:
                continue
            series.setdefault(runtime_key, []).append(float(parsed))

    return {key: series[key] for key in sorted(series)}


def _parse_summary(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    decoder_summary = _parse_decoder_summary(record)
    if decoder_summary is not None:
        return decoder_summary
    return _parse_encoder_summary(record)


def _merge_frame_sent_metrics(
    summary: Dict[str, Any],
    frame_sent_metrics: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """Backfill rate metrics from frame_sent when payload rows do not carry them."""
    if not isinstance(frame_sent_metrics, dict):
        return summary

    if summary.get("aggregated_comp_rate") is None:
        summary["aggregated_comp_rate"] = _to_float(
            _first_present(frame_sent_metrics, FRAME_SENT_AGGREGATED_COMP_RATE_KEYS)
        )
    return summary


def iter_summaries(path: str | Path, *, strict_json: bool = True) -> Iterator[Dict[str, Any]]:
    """Yield one summary dict per valid NDJSON entry."""
    pending_payload_summaries: Dict[int, Dict[str, Any]] = {}
    frame_sent_metrics_by_id: Dict[int, Dict[str, Any]] = {}

    for record in _iter_ndjson_records(path, strict_json=strict_json):
        event_name = record.get("event")
        frame_id_raw = record.get("frame_id")
        frame_id = int(frame_id_raw) if isinstance(frame_id_raw, int) else None

        if event_name == "frame_sent" and frame_id is not None:
            frame_sent_metrics = record.get("metrics")
            if isinstance(frame_sent_metrics, dict):
                frame_sent_metrics_by_id[frame_id] = frame_sent_metrics
                pending = pending_payload_summaries.pop(frame_id, None)
                if pending is not None:
                    yield _merge_frame_sent_metrics(pending, frame_sent_metrics)
            continue

        summary = _parse_summary(record)
        if summary is None:
            continue

        if event_name == "payloads_multiplexed" and frame_id is not None:
            metrics = frame_sent_metrics_by_id.get(frame_id)
            if metrics is not None:
                yield _merge_frame_sent_metrics(summary, metrics)
            else:
                pending_payload_summaries[frame_id] = summary
            continue

        yield summary

    for frame_id in sorted(pending_payload_summaries):
        yield pending_payload_summaries[frame_id]


# ---------------------------------------------------------------------------
# Plot helpers
# ---------------------------------------------------------------------------
def _numeric_series(rows: Iterable[Dict[str, Any]], key: str, *, positive_only: bool = False) -> List[float]:
    values: List[float] = []
    for row in rows:
        value = _to_float(row.get(key))
        if value is None or not np.isfinite(value):
            continue
        if positive_only and value <= 0:
            continue
        values.append(float(value))
    return values


def _paired_series(
    rows: Iterable[Dict[str, Any]],
    x_key: str,
    y_key: str,
    *,
    positive_x: bool = False,
    positive_y: bool = False,
) -> tuple[List[float], List[float]]:
    xs: List[float] = []
    ys: List[float] = []
    for row in rows:
        x_value = _to_float(row.get(x_key))
        y_value = _to_float(row.get(y_key))
        if x_value is None or y_value is None:
            continue
        if not np.isfinite(x_value) or not np.isfinite(y_value):
            continue
        if positive_x and x_value <= 0:
            continue
        if positive_y and y_value <= 0:
            continue
        xs.append(float(x_value))
        ys.append(float(y_value))
    return xs, ys


def _plot_cdf(
    values: Sequence[float],
    *,
    ax,
    xlabel: str,
    log_scale: bool = True,
    lower_percentile: float = 5.0,
) -> None:
    xs = np.asarray(values, dtype=float)
    xs = xs[np.isfinite(xs)]
    if log_scale:
        xs = xs[xs > 0]
    xs = np.sort(xs)
    if xs.size == 0:
        ax.set_xlabel(xlabel)
        ax.set_ylabel("CDF")
        ax.grid(True, alpha=0.2)
        return

    ys = np.arange(1, xs.size + 1) / xs.size
    p_low = float(np.percentile(xs, lower_percentile))
    p50 = float(np.percentile(xs, 50))
    p95 = float(np.percentile(xs, 95))
    mean = float(np.mean(xs))

    ax.plot(xs, ys, linewidth=2)
    ax.axvline(p_low, color="C1", linestyle="--", linewidth=2, label=f"p{lower_percentile:g} = {p_low:.3g}")
    ax.axvline(p95, color="C2", linestyle="--", linewidth=2, label=f"p95 = {p95:.3g}")
    ax.axvline(p50, color="C3", linestyle="--", linewidth=2, label=f"median = {p50:.3g}")
    ax.axvline(mean, color="C4", linestyle="--", linewidth=2, label=f"mean = {mean:.3g}")
    ax.set_ylim(0.0, 1.0)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("CDF")
    if log_scale:
        ax.set_xscale("log", base=10)
    ax.grid(True, alpha=0.2)
    ax.legend()


def _plot_histogram(ax, values: Sequence[float], *, xlabel: str, density: bool = True, log_scale: bool = True) -> None:
    xs = np.asarray(values, dtype=float)
    xs = xs[np.isfinite(xs)]
    if log_scale:
        xs = xs[xs > 0]

    ax.set_xlabel(xlabel)
    ax.set_ylabel("Probability density" if density else "Count")
    ax.grid(True, alpha=0.2)
    if xs.size == 0:
        return

    ax.hist(xs, bins=50, density=density)

    mean = float(np.mean(xs))
    p5 = float(np.percentile(xs, 5))
    p50 = float(np.percentile(xs, 50))
    p95 = float(np.percentile(xs, 95))
    ax.axvline(mean, linestyle="--", color="C4", label=f"Mean: {mean:.2f}")
    ax.axvline(p5, linestyle="--", color="C1", label=f"p5: {p5:.2f}")
    ax.axvline(p95, linestyle="--", color="C2", label=f"p95: {p95:.2f}")
    ax.axvline(p50, linestyle="--", color="C3", label=f"Median: {p50:.2f}")
    if log_scale:
        ax.set_xscale("log", base=10)
    ax.legend()


def _plot_scatter_with_summary(
    plt_module,
    x_values: Sequence[float],
    y_values: Sequence[float],
    *,
    xlabel: str,
    ylabel: str,
    title: str,
    filename: str,
    save_dir: Optional[str],
    x_log_scale: bool = True,
    y_log_scale: bool = True,
    x_mean_label: Optional[str] = None,
    x_mean_scale: float = 1.0,
    y_mean_label: str = "Mean",
    y_median_label: str = "Median",
) -> None:
    plt_module.figure()
    if x_values and y_values:
        plt_module.scatter(x_values, y_values, s=10, alpha=0.6)
        if x_log_scale:
            plt_module.xscale("log", base=10)
        if y_log_scale:
            plt_module.yscale("log", base=10)

        y_mean = float(np.mean(y_values))
        y_median = float(np.median(y_values))
        plt_module.axhline(y_mean, linestyle="--", linewidth=2, label=f"{y_mean_label} = {y_mean:.1f}")
        plt_module.axhline(y_median, linestyle="-.", linewidth=2, color="red", label=f"{y_median_label} = {y_median:.1f}")

        if x_mean_label is not None:
            x_mean = float(np.mean(x_values))
            plt_module.axvline(
                x_mean,
                linestyle=":",
                linewidth=2,
                color="black",
                label=x_mean_label.format(mean=x_mean * x_mean_scale),
            )

        plt_module.legend()

    plt_module.xlabel(xlabel)
    plt_module.ylabel(ylabel)
    plt_module.title(title)
    plt_module.grid(True, alpha=0.2)
    _save_or_show(plt_module, save_dir, filename)


def _save_or_show(plt_module, save_dir: Optional[str], filename: str) -> None:
    plt_module.tight_layout()
    if save_dir:
        output_path = Path(save_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        plt_module.savefig(output_path / filename, dpi=150)
        plt_module.close()
        return
    plt_module.show()


def _plot_codec_usage_counts(ax, counts: Dict[str, int], *, title: str) -> None:
    labels = list(counts.keys())
    values = [counts[label] for label in labels]

    if not labels:
        ax.set_title(title)
        ax.set_xlabel("Codec")
        ax.set_ylabel("Count")
        ax.grid(True, alpha=0.2)
        return

    ax.bar(labels, values)
    ax.set_title(title)
    ax.set_xlabel("Codec")
    ax.set_ylabel("Count")
    ax.grid(True, axis="y", alpha=0.2)
    ax.tick_params(axis="x", rotation=30)


def _plot_image_flag_ratios(ax, rows: Sequence[Dict[str, Any]]) -> None:
    ratios = _compute_image_flag_ratios(rows)
    labels = [
        "bg-only fast path",
        "obj-only fast path",
        "obj_detection_skipped",
        "both bg+obj fast path",
        "fast_path_selected = false",
    ]
    values = [
        ratios["fast_path_bg_only_selected"],
        ratios["fast_path_obj_only_selected"],
        ratios["obj_detection_skipped"],
        ratios["both_fast_path_bg_and_obj_selected"],
        ratios["no_fast_path_selected"],
    ]

    bars = ax.bar(labels, values)
    ax.set_ylim(0.0, 1.0)
    ax.set_ylabel("Ratio of images")
    ax.set_title(f"Fast-path and object-detection ratios (total images = {len(rows)})")
    ax.grid(True, axis="y", alpha=0.2)
    ax.tick_params(axis="x", rotation=20)

    for bar, value in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value,
            f"{value:.1%}",
            ha="center",
            va="bottom",
        )


def _make_dec_plots(rows: List[Dict[str, Any]], *, save_dir: Optional[str] = None) -> None:
    import matplotlib.pyplot as plt

    decoder_rows = [row for row in rows if any(key in row for key in DECODER_SUMMARY_KEYS)]
    runtime_dec_total_ms = _numeric_series(decoder_rows, "runtime_dec_total_ms")
    if not runtime_dec_total_ms:
        return

    _, ax = plt.subplots(figsize=(12, 8))
    _plot_cdf(runtime_dec_total_ms, ax=ax, xlabel="Total decoding runtime (ms)", log_scale=False)
    _save_or_show(plt, save_dir, "decoder_runtime_cdf_plot.png")


def _make_enc_plots(rows: List[Dict[str, Any]], *, save_dir: Optional[str] = None) -> None:
    import matplotlib.pyplot as plt

    encoder_rows = [row for row in rows if any(key in row for key in ENCODER_SUMMARY_KEYS)]
    if not encoder_rows:
        return

    orig_b = _numeric_series(encoder_rows, "orig_jpeg_bytes", positive_only=True)
    pay_b = _numeric_series(encoder_rows, "total_payload_bytes", positive_only=True)
    bg_pay_ratio = _numeric_series(encoder_rows, "bg_payload_ratio", positive_only=True)
    obj_pay_ratio = _numeric_series(encoder_rows, "obj_payload_ratio", positive_only=True)
    bg_orig_ratio = _numeric_series(encoder_rows, "bg_origjpeg_ratio", positive_only=True)
    obj_orig_ratio = _numeric_series(encoder_rows, "obj_origjpeg_ratio", positive_only=True)
    obj_orig_pixels_ratio = _numeric_series(encoder_rows, "obj_orig_pixels_ratio", positive_only=True)
    num_det_objs = _numeric_series(encoder_rows, "num_detected_objs")
    runtime_breakdown_series = _collect_runtime_breakdown_series(encoder_rows)
    bg_scaling_factor = _numeric_series(encoder_rows, "bg_scale_factor", positive_only=True)
    objs_scaling_factor: List[float] = []
    objs_orig_min_dim_per_crop: List[float] = []
    for row in encoder_rows:
        objs_scaling_factor.extend(v for v in _normalize_float_list(row.get("objs_scaling_factor")) if v > 0)
        objs_orig_min_dim_per_crop.extend(
            v for v in _normalize_float_list(row.get("objs_orig_min_dim_per_crop")) if v > 0
        )

    orig_b_scatter_x, orig_b_scatter_y = _paired_series(
        encoder_rows,
        "orig_jpeg_bytes",
        "comp_rate",
        positive_x=True,
        positive_y=True,
    )
    pay_b_scatter_x, pay_b_scatter_y = _paired_series(
        encoder_rows,
        "total_payload_bytes",
        "comp_rate",
        positive_x=True,
        positive_y=True,
    )
    px_scatter_x, px_scatter_y = _paired_series(
        encoder_rows,
        "orig_total_pixels",
        "comp_rate",
        positive_x=True,
        positive_y=True,
    )

    _plot_scatter_with_summary(
        plt,
        orig_b_scatter_x,
        orig_b_scatter_y,
        xlabel="Original image size (bytes)",
        ylabel="Compression rate (orig_bytes / payload_bytes)",
        title="Compression rate vs original image bytes",
        filename="scatter_comp_vs_orig_bytes.png",
        save_dir=save_dir,
        x_mean_label="Mean image size [KB] = {mean:.1f}",
        x_mean_scale=1 / 1000,
    )

    _plot_scatter_with_summary(
        plt,
        pay_b_scatter_x,
        pay_b_scatter_y,
        xlabel="Total payload size (bytes)",
        ylabel="Compression rate (orig_bytes / payload_bytes)",
        title="Compression rate vs total payload bytes",
        filename="scatter_comp_vs_payload_bytes.png",
        save_dir=save_dir,
        x_mean_label=None,
        y_mean_label="Mean CR",
        y_median_label="Median CR",
    )

    _plot_scatter_with_summary(
        plt,
        px_scatter_x,
        px_scatter_y,
        xlabel="original image total pixels",
        ylabel="Compression rate (orig_bytes / payload_bytes)",
        title="Compression rate vs original image megapixels",
        filename="scatter_comp_vs_num_pixels.png",
        save_dir=save_dir,
        y_mean_label="Mean CR",
        y_median_label="Median CR",
    )

    _, axs = plt.subplots(2, 2, figsize=(10, 8))
    _plot_histogram(axs[0, 0], _numeric_series(encoder_rows, "orig_total_pixels", positive_only=True), xlabel="Total megapixels per image")
    _plot_histogram(axs[0, 1], orig_b, xlabel="Original image size (bytes)")
    _plot_histogram(axs[1, 0], pay_b, xlabel="Total payload size (bytes)")
    _plot_histogram(axs[1, 1], num_det_objs, xlabel="Number of detected objects", density=False, log_scale=False)
    _save_or_show(plt, save_dir, "histograms.png")

    _, axs = plt.subplots(2, 3, figsize=(12, 8))
    _plot_cdf(pay_b, ax=axs[0, 0], xlabel="Total payload size (bytes)")
    _plot_cdf(bg_pay_ratio, ax=axs[0, 1], xlabel="Bg to payload ratio")
    _plot_cdf(bg_orig_ratio, ax=axs[0, 2], xlabel="Bg to input img ratio")
    _plot_cdf(obj_orig_pixels_ratio, ax=axs[1, 0], xlabel="ROI to orig pixels ratio")
    _plot_cdf(obj_pay_ratio, ax=axs[1, 1], xlabel="ROI to payload ratio")
    _plot_cdf(obj_orig_ratio, ax=axs[1, 2], xlabel="ROI to input img ratio")
    _save_or_show(plt, save_dir, "cdf_plots.png")

    if runtime_breakdown_series:
        n_plots = len(runtime_breakdown_series)
        n_cols = 2 if n_plots > 1 else 1
        n_rows = math.ceil(n_plots / n_cols)
        _, axs = plt.subplots(n_rows, n_cols, figsize=(6 * n_cols, 4 * n_rows))
        axs_flat = np.asarray(axs).reshape(-1)

        for idx, (runtime_key, values) in enumerate(runtime_breakdown_series.items()):
            label = runtime_key.replace("_", " ").strip().title() or runtime_key
            _plot_cdf(values, ax=axs_flat[idx], xlabel=f"{label} runtime (ms)", log_scale=False)

        for idx in range(n_plots, len(axs_flat)):
            axs_flat[idx].axis("off")

        _save_or_show(plt, save_dir, "runtime_cdf_plots.png")

    _, axs = plt.subplots(1, 2, figsize=(12, 8))
    _plot_cdf(
        bg_scaling_factor,
        ax=axs[0],
        xlabel="Background scaling factor",
        log_scale=False,
        lower_percentile=55,
    )
    _plot_cdf(
        objs_scaling_factor,
        ax=axs[1],
        xlabel="Objects scaling factor",
        log_scale=False,
        lower_percentile=55,
    )
    _save_or_show(plt, save_dir, "scaling_factor_cdf_plots.png")

    _, ax = plt.subplots(figsize=(12, 8))
    _plot_cdf(
        objs_orig_min_dim_per_crop,
        ax=ax,
        xlabel="Original object min dimension per crop (pixels)",
        log_scale=False,
        lower_percentile=5,
    )
    _save_or_show(plt, save_dir, "objs_orig_min_dim_cdf_plot.png")

    codec_idx_to_name = _load_codec_idx_to_name_map()
    bg_codec_counts = _count_codec_usage(encoder_rows, "bg_enc_idx", codec_idx_to_name)
    obj_codec_counts = _count_codec_usage(encoder_rows, "objs_enc_idx", codec_idx_to_name)
    if bg_codec_counts or obj_codec_counts:
        _, axs = plt.subplots(2, 1, figsize=(12, 8))
        _plot_codec_usage_counts(axs[0], bg_codec_counts, title="Background codec usage count")
        _plot_codec_usage_counts(axs[1], obj_codec_counts, title="Object codec usage count")
        _save_or_show(plt, save_dir, "codec_usage_counts.png")

    _, ax = plt.subplots(figsize=(12, 8))
    _plot_image_flag_ratios(ax, encoder_rows)
    _save_or_show(plt, save_dir, "image_flag_ratios.png")


def _infer_plot_modes(path: str | Path, rows: Sequence[Dict[str, Any]]) -> List[str]:
    has_encoder_rows = any("comp_rate" in row for row in rows)
    has_decoder_rows = any("runtime_dec_total_ms" in row for row in rows)

    modes: List[str] = []
    if has_encoder_rows:
        modes.append("encoder")
    if has_decoder_rows:
        modes.append("decoder")
    if modes:
        return modes

    path_str = str(path).lower()
    return ["encoder"] if "enc" in path_str else ["decoder"]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="Path to NDJSON log file (one JSON object per line)")
    parser.add_argument("--output", help="Write per-entry summary dicts as NDJSON to this file.")
    parser.add_argument("--plots", action="store_true", help="Generate plots (requires matplotlib).")
    parser.add_argument(
        "--save-plots-dir",
        help="If set, save plots into this directory instead of showing interactive windows.",
    )
    parser.add_argument(
        "--skip-bad-json",
        action="store_true",
        help="Skip malformed JSON lines instead of failing.",
    )
    args = parser.parse_args()

    rows = list(iter_summaries(args.path, strict_json=not args.skip_bad_json))

    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n")

    if args.plots:
        for mode in _infer_plot_modes(args.path, rows):
            if mode == "encoder":
                _make_enc_plots(rows, save_dir=args.save_plots_dir)
            elif mode == "decoder":
                _make_dec_plots(rows, save_dir=args.save_plots_dir)

    if args.plots:
        print("Log is processed and plots are ready.")
        return

    print("Log is processed and summaries are ready.")


if __name__ == "__main__":
    main()






