# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: utils/logging_helpers.py
Version: 0.2
Authors: Omid Semiari, Hosein Nikopour
Date: 2026-04-10
Description: set up the logger that writes to stdout and optionally to a JSON file.
"""

import json
import os
import math
from typing import Any, Dict
import logging
import sys
from pathlib import Path

def setup_logger(
    name: str,
    cfg: Any,
    *,
    level: int | None = None,
    log_path: Path | None = None,
    enable_stdout: bool | None = None,
    propagate: bool | None = None,
) -> logging.Logger:
    """
    Setup a logger that writes to stdout and optionally to a JSON file.
    The log file is cleared on each run.

    :param name: Logger name
    :param cfg: Config object; supplies defaults for any of level/enable_stdout/propagate/log_path left as None
    :param level: Logging level
    :param log_path: Optional Path to log file
    :param enable_stdout: Whether to mirror logs to stdout in addition to file logging
    :param propagate: Whether to propagate records to the root logger (e.g. app.log)
    :return: Configured Logger
    """
    cfg_log_level_name = str(cfg.app.log_level).upper()
    if level is None:
        level = resolve_log_level(cfg.app.log_level)
    if enable_stdout is None:
        enable_stdout = bool(cfg.io.print_runtime_logs) and cfg_log_level_name != "SILENT"
    if propagate is None:
        propagate = cfg_log_level_name in {"INFO", "DEBUG"}
    if log_path is None and bool(getattr(cfg.io, "write_json_logs", True)):
        log_path = Path(cfg.io.output_dir) / "log" / f"{name}_log.json"

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = propagate

    # Clear existing handlers to avoid duplicate logs
    logger.handlers.clear()

    formatter = logging.Formatter("%(message)s")

    # --- StreamHandler (stdout) ---
    if enable_stdout:
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(formatter)
        logger.addHandler(sh)

    # --- FileHandler (optional) ---
    if log_path is not None:
        # Ensure directory exists
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path_str = str(log_path.resolve())

        # Remove existing file to start fresh
        if os.path.exists(log_path_str):
            os.remove(log_path_str)

        fh = logging.FileHandler(log_path_str, mode="w", encoding="utf-8")
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    return logger


def resolve_log_level(level_name: str | int) -> int:
    """Resolve textual or numeric logging levels with INFO fallback."""
    if isinstance(level_name, int):
        return level_name
    level_map = {
        "SILENT": logging.CRITICAL + 1,  # Above CRITICAL to suppress all logging
        "CRITICAL": logging.CRITICAL,
        "ERROR": logging.ERROR,
        "WARNING": logging.WARNING,
        "INFO": logging.INFO,
        "DEBUG": logging.DEBUG,
    }
    return level_map.get(str(level_name).upper(), logging.INFO)


def _round_floats(obj: Any, ndigits: int = 2) -> Any:
    """Recursively round all float values in a nested structure to *ndigits* decimal places."""
    if isinstance(obj, float):
        return round(obj, ndigits)
    if isinstance(obj, dict):
        return {k: _round_floats(v, ndigits) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        rounded = [_round_floats(v, ndigits) for v in obj]
        return type(obj)(rounded)
    return obj


def log_json(logger: logging.Logger, record: Dict[str, Any]) -> None:
    """
    Emit a JSON log line. Keeps payload compact and serializable.
    Float values are rounded to 2 decimal places before serialization.
    """
    logger.info(json.dumps(_round_floats(record), ensure_ascii=False, separators=(",", ":"), default=str))


def compute_compression_rate(
    input_bytes: int | float | None,
    payload_bytes: int | float | None,
) -> float | None:
    """Return input/payload compression rate when the denominator is positive."""
    if input_bytes is None or payload_bytes is None:
        return None
    if payload_bytes <= 0:
        return None
    return float(input_bytes) / float(payload_bytes)


def build_encoder_log_record(
    *,
    frame_id: int,
    img_data: Any,
    size_log: Dict[str, Any],
    file_name: str | None = None,
    timing_ms: Dict[str, float] | None = None,
    bg_quota_bytes: int | None = None,
    obj_quota_bytes: int | None = None,
    aggregated_comp_rate: float | None = None,
    tar_comp_rate: float | None = None,
    symbol_encoder_index: int | None = None,
) -> Dict[str, Any]:
    """Build a structured encoder log record shared across encoder entrypoints."""

    crops = list(getattr(img_data, "crops", None) or [])
    bg = getattr(img_data, "bg", None)
    total_payload_bytes = float(sum(size_log.values()))
    orig_jpeg_bytes = getattr(img_data, "org_jpeg_bytes", 0)

    objects_total_pixels = sum(
        crop.obj_size[0] * crop.obj_size[1]
        for crop in crops
        if getattr(crop, "obj_size", None)
    )
    obj_scaling_factors = [getattr(crop, "scaling_factor", None) for crop in crops]
    scaled_total_pixels_per_crop = [
        None
        if (
            symbol_encoder_index is not None
            and getattr(crop, "encoder_index", None) == symbol_encoder_index
            and getattr(crop, "scaling_factor", None) is None
        )
        else (math.prod(crop.obj_size_scaled) if getattr(crop, "obj_size_scaled", None) else None)
        for crop in crops
    ]
    scaled_min_dim_per_crop = [
        None
        if (
            symbol_encoder_index is not None
            and getattr(crop, "encoder_index", None) == symbol_encoder_index
            and getattr(crop, "scaling_factor", None) is None
        )
        else (min(crop.obj_size_scaled) if getattr(crop, "obj_size_scaled", None) else None)
        for crop in crops
    ]

    record: Dict[str, Any] = {
        "event": "payloads_multiplexed",
        "frame_id": frame_id,
        "img_id": getattr(img_data, "img_idx", None),
        "image": {
            "orig_size_wh": getattr(img_data, "org_img_size", None),
            "orig_jpeg_bytes": orig_jpeg_bytes,
        },
        "payload": {
            "bytes_by_bucket": size_log,
            "total_bytes": total_payload_bytes,
        },
        "runtime_ms": {},
        "background": {
            "enc_idx": None,
            "scale_factor": None,
            "total_pixels": None,
            "quota_bytes": bg_quota_bytes,
        },
        "objects": {
            "count": len(crops),
            "total_pixels": objects_total_pixels,
            "quota_bytes": obj_quota_bytes,
            "enc_idx": [getattr(crop, "encoder_index", None) for crop in crops],
            "scaling_factor": obj_scaling_factors,
            "scaled_total_pixels_per_crop": scaled_total_pixels_per_crop,
            "scaled_min_dim_per_crop": scaled_min_dim_per_crop,
            "orig_min_dim_per_crop": [
                min(crop.obj_size) if getattr(crop, "obj_size", None) else None
                for crop in crops
            ],
        },
    }

    # Rate metrics are logged under the frame_sent event.
    _ = aggregated_comp_rate
    _ = tar_comp_rate

    if isinstance(file_name, str) and file_name.strip():
        record["file_name"] = file_name
    if timing_ms:
        record["runtime_ms"] = {key: round(value, 2) for key, value in timing_ms.items()}

    if bg is not None:
        record["background"]["scale_factor"] = getattr(bg, "scaling_factor", None)
        record["background"]["enc_idx"] = getattr(bg, "encoder_index", None)
        if getattr(bg, "scaled_size", None):
            record["background"]["total_pixels"] = math.prod(bg.scaled_size)

    if len(crops) == 0:
        record["objects"] = {"count": 0}
        return record

    # Drop sparse object-scale arrays when they contain no usable values for this image.
    objects_record = record["objects"]
    for key in (
        "scaling_factor",
        "scaled_total_pixels_per_crop",
        "scaled_min_dim_per_crop",
    ):
        values = objects_record.get(key)
        if isinstance(values, list) and not any(value is not None for value in values):
            objects_record.pop(key, None)

    return record
