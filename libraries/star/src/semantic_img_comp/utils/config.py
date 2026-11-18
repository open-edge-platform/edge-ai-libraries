# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: utils/config.py
Version: 0.2
Authors: Omid Semiari, Hosein Nikopour
Date: 2026-04-10
Description: config loader. It uses default parameter values which can be overwritten by yaml config file.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple
from pathlib import Path
from types import SimpleNamespace

import math
import os
import yaml
import struct



ROOT_DIR = Path(__file__).resolve().parents[3]  # parent[3] points to the root directory of the repo
DEFAULT_CONFIG_PATH = ROOT_DIR / "configs" / "default.yaml"
VALID_CATALOG_SAMPLING_MODES = frozenset({"uniform", "proportional"})
VALID_CANNY_MODES = frozenset({"old", "new"})
VALID_DETECTOR_BACKENDS = frozenset({"yolo", "dlstreamer"})
LEGACY_SCALING_KEYS = (
    "bg_scaling_min1",
    "bg_scaling_min2",
    "bg_scaling_max",
    "obj_scaling_min",
    "obj_scaling_max",
)
DEFAULT_ENCODERS_TAG = {
    "color-avif": 0,
    "mono-avif-high": 1,
    "mono-avif-mid": 2,
    "mono-avif-low": 3,
    "mono-28bit": 4,
    "mono-2bit": 5,
    "mono-mask-1bit": 6,
    "mono-skel-v1": 8,
    "mono-shape-v1": 9,
    "airplane-symbol-v1": 10,
    "mono-2bit-mixed-n1bit": 11,
    "mono-2bit-template-drop1bit": 12,
    "mono-8bit-template-drop1bit": 13,
}
# Data classes for structure
# --------------------------

@dataclass
class AppConfig:
    name: str = "semantic compression"
    log_level: str = "INFO"  # SILENT, DEBUG, INFO, WARNING, ERROR, CRITICAL
    device: str = "cpu"  # "cpu", "cuda:0"
    # Stable identity the TCP encoder sends to the decoder at the start of its connection,
    # so per-client frame sequencing in SemanticCodecBridge survives encoder reconnects
    # (a raw socket address changes on every reconnect). Overridable via --client-id.
    client_id: str = "default"


@dataclass
class ModelConfig:
    enc_yolo_model_path: Path = ROOT_DIR / "models/obj_det_models/yolov8m_int8_openvino_model"
    pre_comp_conf: float = 0.25
    iou_threshold: float = 0.45
    tile_nms_iou: float = 0.45
    merge_tile_detections: bool = True
    max_detections: int = 300
    valid_obj_categories: Optional[set[int]] = None
    symbol_category_ids: set[int] = None
    tile_size: Optional[int] = None
    tile_overlap: Optional[int] = None
    tile_batch_size: int = 8  # 1 preserves legacy per-tile predict behavior
    # Object detection backend: "yolo" runs a local ultralytics/OpenVINO model;
    # "dlstreamer" delegates detection to a running DL Streamer Pipeline Server
    # instance (gvadetect) over its REST API instead of loading a model locally.
    detector_backend: str = "yolo"  # yolo | dlstreamer
    dlstreamer_base_url: str = "http://dlstreamer-pipeline-server:8080"
    dlstreamer_pipeline_name: str = "star_image_object_detection"
    # Same absolute path in both the encoder container and the DL Streamer Pipeline
    # Server container (see docker-compose.yml) -- bind-mounting the shared host
    # directory at an identical mount point in both containers means one path
    # value works for local file I/O (this process) and for the `file://` URI
    # sent to the pipeline server, instead of needing two separate fields.
    dlstreamer_exchange_input_dir: Path = Path("/app/data")
    dlstreamer_exchange_output_dir: Path = Path("/app/output")
    dlstreamer_poll_interval_sec: float = 0.2
    dlstreamer_timeout_sec: float = 30.0


@dataclass
class IOConfig:
    input_dir: Path = Path("/app/data")
    output_dir: Path = Path("/app/output")
    annot_file: Optional[Path] = None
    save_visualizations: bool = True
    draw_bboxes: bool = True
    print_runtime_logs: bool = True
    write_json_logs: bool = True
    input_catalog_sampling: str = "uniform"        # YAML catalog multi-dir sampling mode: uniform | proportional


@dataclass
class ImageFeederConfig:
    target_input_rate_mbps: Optional[float] = None  # Target data rate in Mbps; None = no rate limit
    run_duration_sec: Optional[float] = None        # Stop feeder after this many seconds; None = run until all images are sent
    log_feeder_events: bool = False                 # Emit feeder_rate_limited / feeder_enqueued events
    mode: Optional[str] = None                      # http or tcp


@dataclass
class PerformanceConfig:
    image_size: int = 640


@dataclass
class EncConfig:
    min_bg_bytes: int = 10
    min_bg_pixels: int = 10_000
    min_bytes_for_budget_allocation: int = 50
    min_obj_pixels: int = 5000
    min_bytes_for_encoded_data: int = 500
    avif_quality: int = 0
    avif_speed: int = 6
    avif_jobs: int = 0  # 0 disables explicit --jobs flag; >0 sets avifenc --jobs
    avif_codec: Optional[str] = None  # e.g. "aom", "rav1e", "svt"
    avif_timeout_sec: int = 120
    compression_rate: float = 100.0
    compression_levels: Optional[dict] = None  # level_1 and level_2 rates
    obj_budget_ratio: float = 0.9
    object_budget_soft: bool = True
    max_iter_bg: int = 0         # bg scale search iterations; 0 = fixed scale (min1/min2), no search
    max_iter_obj: int = 1        # obj scale search iterations
    scale_search_step_size: int = 1  # Step size for binary search when finding scale for budget
    zlib_level: int = 9
    # Mapping from encoder name to AVIF quality for mono-avif variants
    avif_mono_quality_map: Optional[dict] = None
    mono_2bit_mixed_two_bit_run: int = 4
    mono_2bit_mixed_one_bit_run: int = 1
    mono_2bit_drop1bit_neighbor_k: int = 2
    mono_2bit_drop1bit_fill_gray_level: int = 128
    # SDL443/T-004: reject encoder-service request bodies larger than this before buffering them.
    max_body_bytes: int = 25 * 1024 * 1024  # 25 MiB, generous upper bound for one raw JPEG frame


@dataclass
class PipelineManagerConfig:
    queue_backlog_threshold_1: int = 5
    queue_backlog_threshold_2: int = 10
    queue_backlog_threshold_3: int = 15
    compression_level: int = 1
    fast_full_hysteresis_exit: float = 7.5
    skip_obj_hysteresis_exit: float = 12.5
    adaptive_compression_rate_warmup_frames: int = 10
    adaptive_compression_rate_max: float = 300.0
    adaptive_compression_rate_boost_factor: float = 1.5
    adaptive_compression_rate_method: str = "moving_average"
    adaptive_compression_rate_target_margin_ratio: float = 0.2
    adaptive_compression_rate_ema_alpha: float = 0.2
    large_dim_tile_threshold_px: int = 1280

@dataclass
class DecConfig:
    avif_timeout_sec: int = 120
    smooth_sigma: float = 0.0
    bg_max_level: int = 150  # Maximum grayscale level for background low-bit codecs (mono-2bit, mono-mask-1bit)
    # SDL443/T-004: reject decoder-service request bodies larger than this before buffering them.
    max_body_bytes: int = 25 * 1024 * 1024  # 25 MiB, generous upper bound for one mux payload

@dataclass
class ImgProcessingConfig:
    bg_scaling_min1_level_1: int = 20   # percent of original bg size when no object detected
    bg_scaling_min2_level_1: int = 5    # percent of original bg size when objects are detected
    bg_scaling_max_level_1: int = 100
    obj_scaling_min_level_1: int = 30   # percent of original object size
    obj_scaling_max_level_1: int = 100
    bg_scaling_min1_level_2: int = 10
    bg_scaling_min2_level_2: int = 3
    bg_scaling_max_level_2: int = 60
    obj_scaling_min_level_2: int = 20
    obj_scaling_max_level_2: int = 80
    active_bg_scaling_min1: Optional[int] = None
    active_bg_scaling_min2: Optional[int] = None
    active_bg_scaling_max: Optional[int] = None
    active_obj_scaling_min: Optional[int] = None
    active_obj_scaling_max: Optional[int] = None
    additional_crop_margin: float = 0.0
    paste_feather_ratio: float = 0.5
    paste_feather_min_px: int = 1
    skip_object_bboxes_in_background: bool = False
    canny_mode: str = "old"  # old | new
    canny_sigma: float = 1.0
    canny_low: int = 12
    canny_high: int = 45
    canny_deriche_bilateral_d: int = 9
    canny_deriche_bilateral_sigma_color: float = 60.0
    canny_deriche_bilateral_sigma_space: float = 60.0
    canny_deriche_gaussian_sigma: float = 2.0
    canny_deriche_morph_close_kernel: int = 7
    canny_deriche_morph_close_iterations: int = 2
    mono_skel_max_segments: int = 8
    mono_skel_min_segment_length: int = 5
    mono_skel_hough_threshold: int = 20
    mono_skel_max_segment_gap: int = 2
    mono_skel_work_max_dim: int = 128
    mono_skel_stitch_angle_tol_deg: float = 20.0
    mono_shape_max_points: int = 120
    mono_shape_epsilon_ratio: float = 0.01
    vessel_theta_offset_deg: float = 90.0
    encoders_tag_bg_level_1: Optional[dict] = None  # Level 1 background encoder tags
    encoders_tag_objs_level_1: Optional[dict] = None  # Level 1 object encoder tags
    encoders_tag_bg_level_2: Optional[dict] = None  # Level 2 background encoder tags
    encoders_tag_objs_level_2: Optional[dict] = None  # Level 2 object encoder tags
    active_encoders_tag_bg: Optional[dict] = None  # per-image runtime-selected background encoder tags
    active_encoders_tag_objs: Optional[dict] = None  # per-image runtime-selected object encoder tags
    # Unified registry used by decoder/log tools across all levels.
    encoders_tag: Optional[dict] = None


@dataclass(frozen=True)
class MuxStructConfig:
    """
    All binary layout decisions live here.

    Change these format strings to change the wire format without touching mux logic.
    Note: struct formats are standard Python `struct` format strings.
    """
    endian: str = ">"  # ">" big-endian, "<" little-endian, "!" network, etc.

    # Frame/header
    fmt_payload_len: str = "!I"  # 4-byte length

    # Image sizes
    fmt_hw: str = "2H"            # convenience for packing (h, w)

    # Length prefixes
    fmt_len_bg: str = "I"         # e.g. uint32
    fmt_len_obj: str = "I"        # e.g. uint32

    # Counts
    fmt_crops_count: str = "B"    # uint8 (max 255 objects per frame)

    # BBoxes
    fmt_bbox: str = "4H"          # e.g. 4x uint16 — used for expanded_bbox only

    # Crop metadata
    fmt_encoder_index: str = "B"  # uint8 (max 255 codec tags)

    # SDL443/T-003: upper bound on a single length-prefixed TCP frame before it is allocated into a receive buffer.
    max_frame_len: int = 64 * 1024 * 1024  # 64 MiB

    # SDL443/T-009: fallback cap on num_crops when no model-derived limit is supplied.
    # Matches the wire format's own uint8 ceiling for fmt_crops_count ("B" -> 0-255).
    default_max_crops: int = 255

    def fmt(self, code: str) -> str:
        """Prefixes endian to a non-endian struct code."""
        # If caller mistakenly passes something already endian-prefixed, keep it as-is.
        if code and code[0] in "@=<>!":
            return code
        return f"{self.endian}{code}"

    def header_fields_total_bytes(self) -> Tuple[int, int]:
        fields_bg = [
            self.fmt_hw,
            self.fmt_len_bg,
            self.fmt_hw,
            self.fmt_encoder_index,
            self.fmt_crops_count,
        ]

        fields_per_crop = [
            self.fmt_len_obj,
            self.fmt_bbox,        # expanded_bbox
            self.fmt_hw,
            self.fmt_encoder_index
        ]

        # Prefix endian once; calcsize then gives the total bytes for the combined format.
        return struct.calcsize(self.endian + "".join(fields_bg)), struct.calcsize(self.endian + "".join(fields_per_crop))


@dataclass
class Config:
    app: AppConfig
    model: ModelConfig
    io: IOConfig
    image_feeder: ImageFeederConfig
    performance: PerformanceConfig
    enc: EncConfig
    pipeline_manager: PipelineManagerConfig
    dec: DecConfig
    img_process: ImgProcessingConfig
    mux_cfg: MuxStructConfig


# --------------------------
# YAML loading + validation
# --------------------------


def _read_yaml(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Config file not found: {path}\n"
            f"Tip: make sure you're running from repo root or pass --config <path>."
        )

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if data is None:
        raise ValueError(f"Config file is empty: {path}")

    if not isinstance(data, dict):
        raise ValueError(f"Config must be a YAML dict at top-level. Got: {type(data)}")

    return data


def _require_section(cfg: Dict[str, Any], key: str) -> Dict[str, Any]:
    """Ensure config section exists and is a dict."""
    if key not in cfg:
        raise KeyError(
            f"Missing required section '{key}' in config. "
            f"Expected something like:\n\n{key}:\n  ...\n"
        )

    if not isinstance(cfg[key], dict):
        raise TypeError(f"Config section '{key}' must be a dict. Got: {type(cfg[key])}")

    return cfg[key]


def _get(cfg_section: Dict[str, Any], key: str, default: Any) -> Any:
    """Get key from section, treating empty strings as missing."""
    value = cfg_section.get(key, default)
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return default
    return value


def _get_bool(cfg_section: Dict[str, Any], key: str, default: bool) -> bool:
    """Parse a boolean config value with support for common string forms."""
    value = _get(cfg_section, key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    raise ValueError(f"Config value '{key}' must be a boolean. Got: {value!r}")


def _optional_path(value: Any) -> Optional[Path]:
    """Normalize optional path-like values to Path while preserving None."""
    if value is None:
        return None
    return Path(value)


def _get_non_negative_float(cfg_section: Dict[str, Any], key: str, default: float) -> float:
    """Parse a numeric config value, normalizing ints/floats to a finite non-negative float."""
    value = _get(cfg_section, key, default)
    if isinstance(value, bool):
        raise ValueError(f"Config value '{key}' must be a number, got boolean {value!r}")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Config value '{key}' must be a number. Got: {value!r}") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"Config value '{key}' must be finite. Got: {value!r}")
    if parsed < 0:
        raise ValueError(f"Config value '{key}' must be >= 0. Got: {value!r}")
    return parsed


def _get_non_negative_int(cfg_section: Dict[str, Any], key: str, default: int) -> int:
    """Parse an integer config value and validate it is non-negative."""
    value = _get(cfg_section, key, default)
    if isinstance(value, bool):
        raise ValueError(f"Config value '{key}' must be an integer, got boolean {value!r}")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Config value '{key}' must be an integer. Got: {value!r}") from exc
    if parsed < 0:
        raise ValueError(f"Config value '{key}' must be >= 0. Got: {value!r}")
    return parsed


def _get_catalog_sampling_mode(cfg_section: Dict[str, Any], key: str, default: str) -> str:
    """Parse catalog sampling mode for multi-directory YAML inputs."""
    value = _get(cfg_section, key, default)
    mode = str(value).strip().lower()
    if mode not in VALID_CATALOG_SAMPLING_MODES:
        raise ValueError(
            f"Config value '{key}' must be one of {sorted(VALID_CATALOG_SAMPLING_MODES)}. Got: {value!r}"
        )
    return mode


def _get_canny_mode(cfg_section: Dict[str, Any], key: str, default: str) -> str:
    """Parse edge detector mode and normalize aliases to old/new."""
    value = _get(cfg_section, key, default)
    mode = str(value).strip().lower()
    aliases = {
        "legacy": "old",
        "canny": "old",
        "deriche": "new",
        "canny_deriche": "new",
    }
    mode = aliases.get(mode, mode)
    if mode not in VALID_CANNY_MODES:
        raise ValueError(
            f"Config value '{key}' must be one of {sorted(VALID_CANNY_MODES)}. Got: {value!r}"
        )
    return mode


def _get_detector_backend(cfg_section: Dict[str, Any], key: str, default: str) -> str:
    """Parse the object-detection backend selector (yolo | dlstreamer)."""
    value = _get(cfg_section, key, default)
    backend = str(value).strip().lower()
    if backend not in VALID_DETECTOR_BACKENDS:
        raise ValueError(
            f"Config value '{key}' must be one of {sorted(VALID_DETECTOR_BACKENDS)}. Got: {value!r}"
        )
    return backend


def _parse_encoder_tag_map(value: Any, *, key: str, default: Dict[str, int]) -> Dict[str, int]:
    """Parse and validate encoder-tag mappings from config values."""
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return dict(default)
    if not isinstance(value, dict):
        raise ValueError(f"Config value '{key}' must be a dictionary. Got: {type(value)}")

    parsed: Dict[str, int] = {}
    for codec_name, codec_idx in value.items():
        codec_name_str = str(codec_name)
        if codec_name_str.strip() == "":
            raise ValueError(f"Config value '{key}' has an empty codec name")
        if isinstance(codec_idx, bool):
            raise ValueError(f"Config value '{key}.{codec_name_str}' must be an integer")
        try:
            parsed_idx = int(codec_idx)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Config value '{key}.{codec_name_str}' must be an integer. Got: {codec_idx!r}"
            ) from exc
        if parsed_idx < 0:
            raise ValueError(f"Config value '{key}.{codec_name_str}' must be >= 0. Got: {parsed_idx}")
        parsed[codec_name_str] = parsed_idx

    if not parsed:
        raise ValueError(f"Config value '{key}' must not be empty")
    return parsed


def _parse_optional_encoder_tag_map(value: Any, *, key: str) -> Optional[Dict[str, int]]:
    """Parse an optional encoder-tag mapping, preserving None when unset."""
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return None
    return _parse_encoder_tag_map(value, key=key, default={"_unused": 0})


def _parse_avif_mono_quality_map(value: Any, *, key: str) -> Dict[str, int]:
    """Parse and validate AVIF monochrome quality mappings from config values.

    Expects a dictionary mapping encoder names (e.g., 'mono-avif-high') to quality values (0-63).
    """
    if value is None or (isinstance(value, str) and value.strip() == ""):
        # Return default quality mapping for mono-avif variants
        return {
            "mono-avif-high": 0,    # highest quality
            "mono-avif-mid": 32,    # mid quality
            "mono-avif-low": 55,    # low quality (high compression)
        }
    if not isinstance(value, dict):
        raise ValueError(f"Config value '{key}' must be a dictionary. Got: {type(value)}")

    parsed: Dict[str, int] = {}
    for encoder_name, quality in value.items():
        encoder_name_str = str(encoder_name)
        if encoder_name_str.strip() == "":
            raise ValueError(f"Config value '{key}' has an empty encoder name")
        if isinstance(quality, bool):
            raise ValueError(f"Config value '{key}.{encoder_name_str}' must be an integer")
        try:
            quality_int = int(quality)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Config value '{key}.{encoder_name_str}' must be an integer. Got: {quality!r}"
            ) from exc
        if quality_int < 0 or quality_int > 63:
            raise ValueError(f"Config value '{key}.{encoder_name_str}' must be in range [0, 63]. Got: {quality_int}")
        parsed[encoder_name_str] = quality_int

    return parsed


def _dict_to_namespace(d: Optional[Dict[str, Any]]) -> Optional[SimpleNamespace]:
    """Convert a dict to SimpleNamespace, or return None if dict is empty/None."""
    if not d:
        return None
    return SimpleNamespace(**d)


def load_config(config_path: Optional[str] = None) -> Config:
    """
    Load a YAML config file and return a typed Config object.

    Priority order:
    1) `config_path` argument (if passed)
    2) environment variable CONFIG_PATH
    3) DEFAULT_CONFIG_PATH
    """
    final_path = config_path or os.getenv("CONFIG_PATH") or DEFAULT_CONFIG_PATH
    raw = _read_yaml(final_path)

    # Required sections
    app_raw = _require_section(raw, "app")
    model_raw = _require_section(raw, "model")
    io_raw = _require_section(raw, "io")
    perf_raw = _require_section(raw, "performance")
    enc_raw = _require_section(raw, "encoder")
    dec_raw = _require_section(raw, "decoder")
    pipeline_mgr_raw = raw.get("pipeline_manager")
    if pipeline_mgr_raw is None:
        pipeline_mgr_raw = {}
    elif not isinstance(pipeline_mgr_raw, dict):
        raise TypeError(f"Config section 'pipeline_manager' must be a dict. Got: {type(pipeline_mgr_raw)}")
    image_feeder_raw = raw.get("image_feeder")
    if image_feeder_raw is None:
        image_feeder_raw = {}
    elif not isinstance(image_feeder_raw, dict):
        raise TypeError(f"Config section 'image_feeder' must be a dict. Got: {type(image_feeder_raw)}")
    img_proc_raw = _require_section(raw, "img_process")
    mux_cfg_raw = _require_section(raw, "mux_cfg")

    for removed_key in ("encoders_tag_bg", "encoders_tag_objs"):
        removed_value = img_proc_raw.get(removed_key)
        if removed_value is not None and not (isinstance(removed_value, str) and removed_value.strip() == ""):
            raise ValueError(
                f"img_process.{removed_key} has been removed; use level-specific encoder maps instead"
            )

    for removed_key in LEGACY_SCALING_KEYS:
        removed_value = img_proc_raw.get(removed_key)
        if removed_value is not None and not (isinstance(removed_value, str) and removed_value.strip() == ""):
            raise ValueError(
                f"img_process.{removed_key} has been removed; use level-specific scaling keys instead"
            )

    valid_obj_categories_raw = _get(model_raw, "valid_obj_categories", None)
    valid_obj_categories = None
    if valid_obj_categories_raw is not None:
        if not isinstance(valid_obj_categories_raw, (list, tuple, set)):
            raise ValueError("model.valid_obj_categories must be a list/tuple/set of non-negative integers")
        valid_obj_categories = set()
        for cat in valid_obj_categories_raw:
            if not isinstance(cat, int) or cat < 0:
                raise ValueError("model.valid_obj_categories entries must be non-negative integers")
            valid_obj_categories.add(cat)

    symbol_category_ids_raw = _get(model_raw, "symbol_category_ids", [4, 8])
    if not isinstance(symbol_category_ids_raw, (list, tuple, set)):
        raise ValueError("model.symbol_category_ids must be a list/tuple/set of non-negative integers")
    symbol_category_ids: set[int] = set()
    for cat in symbol_category_ids_raw:
        if not isinstance(cat, int) or cat < 0:
            raise ValueError("model.symbol_category_ids entries must be non-negative integers")
        symbol_category_ids.add(cat)
    if not symbol_category_ids:
        raise ValueError("model.symbol_category_ids must not be empty")

    # Build typed config with defaults
    # Prefer the new key name, but keep legacy fallback for existing configs.
    enc_model_path_raw = _get(model_raw, "enc_yolo_model_path", None)
    if enc_model_path_raw is None:
        enc_model_path_raw = _get(model_raw, "pre_comp_model_path", ModelConfig.enc_yolo_model_path)

    legacy_encoders_tag_raw = img_proc_raw.get("encoders_tag")
    legacy_encoders_tag = _parse_encoder_tag_map(
        value=legacy_encoders_tag_raw,
        key="img_process.encoders_tag",
        default=DEFAULT_ENCODERS_TAG,
    )
    encoders_tag_bg_level_1 = _parse_optional_encoder_tag_map(
        img_proc_raw.get("encoders_tag_bg_level_1"),
        key="img_process.encoders_tag_bg_level_1",
    )
    encoders_tag_objs_level_1 = _parse_optional_encoder_tag_map(
        img_proc_raw.get("encoders_tag_objs_level_1"),
        key="img_process.encoders_tag_objs_level_1",
    )
    encoders_tag_bg_level_2 = _parse_optional_encoder_tag_map(
        img_proc_raw.get("encoders_tag_bg_level_2"),
        key="img_process.encoders_tag_bg_level_2",
    )
    encoders_tag_objs_level_2 = _parse_optional_encoder_tag_map(
        img_proc_raw.get("encoders_tag_objs_level_2"),
        key="img_process.encoders_tag_objs_level_2",
    )
    merged_encoders_tag = {
        **(encoders_tag_bg_level_1 or {}),
        **(encoders_tag_objs_level_1 or {}),
        **(encoders_tag_bg_level_2 or {}),
        **(encoders_tag_objs_level_2 or {}),
    }
    # Prefer explicit unified map when provided; otherwise derive from split maps.
    unified_encoders_tag = (
        legacy_encoders_tag
        if not (legacy_encoders_tag_raw is None or (isinstance(legacy_encoders_tag_raw, str) and legacy_encoders_tag_raw.strip() == ""))
        else (merged_encoders_tag or legacy_encoders_tag)
    )

    queue_threshold_1 = _get_non_negative_int(
        pipeline_mgr_raw,
        "queue_backlog_threshold_1",
        PipelineManagerConfig.queue_backlog_threshold_1,
    )
    queue_threshold_2 = _get_non_negative_int(
        pipeline_mgr_raw,
        "queue_backlog_threshold_2",
        max(queue_threshold_1 + 1, PipelineManagerConfig.queue_backlog_threshold_2),
    )
    queue_threshold_3 = _get_non_negative_int(
        pipeline_mgr_raw,
        "queue_backlog_threshold_3",
        max(queue_threshold_2 + 1, PipelineManagerConfig.queue_backlog_threshold_3),
    )
    fast_full_hysteresis_exit = _get_non_negative_float(
        pipeline_mgr_raw,
        "fast_full_hysteresis_exit",
        (queue_threshold_1 + queue_threshold_2) / 2.0,
    )
    skip_obj_hysteresis_exit = _get_non_negative_float(
        pipeline_mgr_raw,
        "skip_obj_hysteresis_exit",
        (queue_threshold_2 + queue_threshold_3) / 2.0,
    )

    cfg = Config(
        app=AppConfig(
            log_level=_get(app_raw, "log_level", AppConfig.log_level),
            device=_get(app_raw, "device", AppConfig.device),
            client_id=_get(app_raw, "client_id", AppConfig.client_id),
        ),
        model=ModelConfig(
            enc_yolo_model_path=Path(enc_model_path_raw),
            pre_comp_conf=float(_get(model_raw, "pre_comp_conf", ModelConfig.pre_comp_conf)),
            iou_threshold=float(_get(model_raw, "iou_threshold", ModelConfig.iou_threshold)),
            tile_nms_iou=float(_get(model_raw, "tile_nms_iou", ModelConfig.tile_nms_iou)),
            merge_tile_detections=_get_bool(
                model_raw,
                "merge_tile_detections",
                ModelConfig.merge_tile_detections,
            ),
            max_detections=int(_get(model_raw, "max_detections", ModelConfig.max_detections)),
            valid_obj_categories=valid_obj_categories,
            symbol_category_ids=symbol_category_ids,
            tile_size=_get(model_raw, "tile_size", ModelConfig.tile_size),
            tile_overlap=_get(model_raw, "tile_overlap", ModelConfig.tile_overlap),
            tile_batch_size=_get_non_negative_int(
                model_raw,
                "tile_batch_size",
                ModelConfig.tile_batch_size,
            ),
            detector_backend=_get_detector_backend(
                model_raw,
                "detector_backend",
                ModelConfig.detector_backend,
            ),
            dlstreamer_base_url=str(_get(model_raw, "dlstreamer_base_url", ModelConfig.dlstreamer_base_url)),
            dlstreamer_pipeline_name=str(_get(model_raw, "dlstreamer_pipeline_name", ModelConfig.dlstreamer_pipeline_name)),
            dlstreamer_exchange_input_dir=Path(_get(model_raw, "dlstreamer_exchange_input_dir", ModelConfig.dlstreamer_exchange_input_dir)),
            dlstreamer_exchange_output_dir=Path(_get(model_raw, "dlstreamer_exchange_output_dir", ModelConfig.dlstreamer_exchange_output_dir)),
            dlstreamer_poll_interval_sec=_get_non_negative_float(
                model_raw,
                "dlstreamer_poll_interval_sec",
                ModelConfig.dlstreamer_poll_interval_sec,
            ),
            dlstreamer_timeout_sec=_get_non_negative_float(
                model_raw,
                "dlstreamer_timeout_sec",
                ModelConfig.dlstreamer_timeout_sec,
            ),
        ),
        io=IOConfig(
            input_dir=Path(_get(io_raw, "input_dir", IOConfig.input_dir)),
            annot_file=_optional_path(_get(io_raw, "annot_file", IOConfig.annot_file)),
            output_dir=Path(_get(io_raw, "output_dir", IOConfig.output_dir)),
            save_visualizations=_get_bool(io_raw, "save_visualizations", IOConfig.save_visualizations),
            draw_bboxes=_get_bool(io_raw, "draw_bboxes", IOConfig.draw_bboxes),
            print_runtime_logs=_get_bool(io_raw, "print_runtime_logs", IOConfig.print_runtime_logs),
            write_json_logs=_get_bool(io_raw, "write_json_logs", IOConfig.write_json_logs),
            input_catalog_sampling=_get_catalog_sampling_mode(
                io_raw,
                "input_catalog_sampling",
                IOConfig.input_catalog_sampling,
            ),
        ),
        image_feeder=ImageFeederConfig(
            target_input_rate_mbps=_get(
                image_feeder_raw, "target_input_rate_mbps", ImageFeederConfig.target_input_rate_mbps
            ),
            run_duration_sec=_get(image_feeder_raw, "run_duration_sec", ImageFeederConfig.run_duration_sec),
            log_feeder_events=_get_bool(
                image_feeder_raw, "log_feeder_events", ImageFeederConfig.log_feeder_events
            ),
            mode=_get(image_feeder_raw, "mode", ImageFeederConfig.mode),
        ),
        performance=PerformanceConfig(
            image_size=int(_get(perf_raw, "image_size", PerformanceConfig.image_size)),
        ),
        enc=EncConfig(
            min_bg_bytes=int(_get(enc_raw, "min_bg_bytes", EncConfig.min_bg_bytes)),
            min_bg_pixels = int(_get(enc_raw, "min_bg_pixels", EncConfig.min_bg_pixels)),
            min_bytes_for_budget_allocation=int(_get(enc_raw, "min_bytes_for_budget_allocation", EncConfig.min_bytes_for_budget_allocation)),
            min_obj_pixels=int(_get(enc_raw, "min_obj_pixels", EncConfig.min_obj_pixels)),
            min_bytes_for_encoded_data=int(_get(enc_raw, "min_bytes_for_encoded_data", EncConfig.min_bytes_for_encoded_data)),
            avif_quality=int(_get(enc_raw, "avif_quality", EncConfig.avif_quality)),
            avif_speed=int(_get(enc_raw, "avif_speed", EncConfig.avif_speed)),
            avif_jobs=_get_non_negative_int(
                enc_raw,
                "avif_jobs",
                int(os.getenv("AVIF_JOBS", EncConfig.avif_jobs)),
            ),
            avif_codec=_get(enc_raw, "avif_codec", EncConfig.avif_codec),
            avif_timeout_sec=int(_get(enc_raw, "avif_timeout_sec", EncConfig.avif_timeout_sec)),
            compression_rate=float(_get(enc_raw, "compression_rate", EncConfig.compression_rate)),
            compression_levels=_dict_to_namespace(enc_raw.get("compression_levels", {})),
            obj_budget_ratio=float(_get(enc_raw, "obj_budget_ratio", EncConfig.obj_budget_ratio)),
            object_budget_soft=_get_bool(enc_raw, "object_budget_soft", EncConfig.object_budget_soft),
            max_iter_bg=int(_get(enc_raw, "max_iter_bg", EncConfig.max_iter_bg)),
            max_iter_obj=int(_get(enc_raw, "max_iter_obj", EncConfig.max_iter_obj)),
            scale_search_step_size=int(_get(enc_raw, "scale_search_step_size", EncConfig.scale_search_step_size)),
            zlib_level=_get_non_negative_int(enc_raw, "zlib_level", EncConfig.zlib_level),
            avif_mono_quality_map=_parse_avif_mono_quality_map(
                enc_raw.get("avif_mono_quality_map"),
                key="encoder.avif_mono_quality_map",
            ),
            mono_2bit_mixed_two_bit_run=_get_non_negative_int(
                enc_raw,
                "mono_2bit_mixed_two_bit_run",
                EncConfig.mono_2bit_mixed_two_bit_run,
            ),
            mono_2bit_mixed_one_bit_run=_get_non_negative_int(
                enc_raw,
                "mono_2bit_mixed_one_bit_run",
                EncConfig.mono_2bit_mixed_one_bit_run,
            ),
            mono_2bit_drop1bit_fill_gray_level=_get_non_negative_int(
                enc_raw,
                "mono_2bit_drop1bit_fill_gray_level",
                EncConfig.mono_2bit_drop1bit_fill_gray_level,
            ),
            mono_2bit_drop1bit_neighbor_k=_get_non_negative_int(
                enc_raw,
                "mono_2bit_drop1bit_neighbor_k",
                EncConfig.mono_2bit_drop1bit_neighbor_k,
            ),
            max_body_bytes=_get_non_negative_int(enc_raw, "max_body_bytes", EncConfig.max_body_bytes),
        ),
        pipeline_manager=PipelineManagerConfig(
            queue_backlog_threshold_1=queue_threshold_1,
            queue_backlog_threshold_2=queue_threshold_2,
            queue_backlog_threshold_3=queue_threshold_3,
            compression_level=int(_get(pipeline_mgr_raw, "compression_level", PipelineManagerConfig.compression_level)),
            fast_full_hysteresis_exit=fast_full_hysteresis_exit,
            skip_obj_hysteresis_exit=skip_obj_hysteresis_exit,
            adaptive_compression_rate_warmup_frames=_get_non_negative_int(
                pipeline_mgr_raw,
                "adaptive_compression_rate_warmup_frames",
                PipelineManagerConfig.adaptive_compression_rate_warmup_frames,
            ),
            adaptive_compression_rate_max=_get_non_negative_float(
                pipeline_mgr_raw,
                "adaptive_compression_rate_max",
                PipelineManagerConfig.adaptive_compression_rate_max,
            ),
            adaptive_compression_rate_boost_factor=_get_non_negative_float(
                pipeline_mgr_raw,
                "adaptive_compression_rate_boost_factor",
                PipelineManagerConfig.adaptive_compression_rate_boost_factor,
            ),
            adaptive_compression_rate_method=str(
                _get(
                    pipeline_mgr_raw,
                    "adaptive_compression_rate_method",
                    PipelineManagerConfig.adaptive_compression_rate_method,
                )
            ).strip().lower(),
            adaptive_compression_rate_target_margin_ratio=_get_non_negative_float(
                pipeline_mgr_raw,
                "adaptive_compression_rate_target_margin_ratio",
                PipelineManagerConfig.adaptive_compression_rate_target_margin_ratio,
            ),
            adaptive_compression_rate_ema_alpha=_get_non_negative_float(
                pipeline_mgr_raw,
                "adaptive_compression_rate_ema_alpha",
                PipelineManagerConfig.adaptive_compression_rate_ema_alpha,
            ),
            large_dim_tile_threshold_px=_get_non_negative_int(
                pipeline_mgr_raw,
                "large_dim_tile_threshold_px",
                PipelineManagerConfig.large_dim_tile_threshold_px,
            ),
        ),
        dec=DecConfig(
            avif_timeout_sec=int(_get(dec_raw, "avif_timeout_sec", DecConfig.avif_timeout_sec)),
            smooth_sigma=float(_get(dec_raw, "smooth_sigma", DecConfig.smooth_sigma)),
            max_body_bytes=_get_non_negative_int(dec_raw, "max_body_bytes", DecConfig.max_body_bytes),
        ),
        img_process=ImgProcessingConfig(
            bg_scaling_min1_level_1=_get_non_negative_int(
                img_proc_raw,
                "bg_scaling_min1_level_1",
                ImgProcessingConfig.bg_scaling_min1_level_1,
            ),
            bg_scaling_min2_level_1=_get_non_negative_int(
                img_proc_raw,
                "bg_scaling_min2_level_1",
                ImgProcessingConfig.bg_scaling_min2_level_1,
            ),
            bg_scaling_max_level_1=_get_non_negative_int(
                img_proc_raw,
                "bg_scaling_max_level_1",
                ImgProcessingConfig.bg_scaling_max_level_1,
            ),
            obj_scaling_min_level_1=_get_non_negative_int(
                img_proc_raw,
                "obj_scaling_min_level_1",
                ImgProcessingConfig.obj_scaling_min_level_1,
            ),
            obj_scaling_max_level_1=_get_non_negative_int(
                img_proc_raw,
                "obj_scaling_max_level_1",
                ImgProcessingConfig.obj_scaling_max_level_1,
            ),
            bg_scaling_min1_level_2=_get_non_negative_int(
                img_proc_raw,
                "bg_scaling_min1_level_2",
                ImgProcessingConfig.bg_scaling_min1_level_2,
            ),
            bg_scaling_min2_level_2=_get_non_negative_int(
                img_proc_raw,
                "bg_scaling_min2_level_2",
                ImgProcessingConfig.bg_scaling_min2_level_2,
            ),
            bg_scaling_max_level_2=_get_non_negative_int(
                img_proc_raw,
                "bg_scaling_max_level_2",
                ImgProcessingConfig.bg_scaling_max_level_2,
            ),
            obj_scaling_min_level_2=_get_non_negative_int(
                img_proc_raw,
                "obj_scaling_min_level_2",
                ImgProcessingConfig.obj_scaling_min_level_2,
            ),
            obj_scaling_max_level_2=_get_non_negative_int(
                img_proc_raw,
                "obj_scaling_max_level_2",
                ImgProcessingConfig.obj_scaling_max_level_2,
            ),
            active_bg_scaling_min1=None,
            active_bg_scaling_min2=None,
            active_bg_scaling_max=None,
            active_obj_scaling_min=None,
            active_obj_scaling_max=None,
            additional_crop_margin=_get_non_negative_float(
                img_proc_raw,
                "additional_crop_margin",
                ImgProcessingConfig.additional_crop_margin,
            ),
            paste_feather_ratio=_get_non_negative_float(
                img_proc_raw,
                "paste_feather_ratio",
                ImgProcessingConfig.paste_feather_ratio,
            ),
            paste_feather_min_px=_get_non_negative_int(
                img_proc_raw,
                "paste_feather_min_px",
                ImgProcessingConfig.paste_feather_min_px,
            ),
            skip_object_bboxes_in_background=_get_bool(
                img_proc_raw,
                "skip_object_bboxes_in_background",
                ImgProcessingConfig.skip_object_bboxes_in_background,
            ),
            canny_mode=_get_canny_mode(
                img_proc_raw,
                "canny_mode",
                ImgProcessingConfig.canny_mode,
            ),
            canny_sigma=float(_get(img_proc_raw, "canny_sigma", ImgProcessingConfig.canny_sigma)),
            canny_low=int(_get(img_proc_raw, "canny_low", ImgProcessingConfig.canny_low)),
            canny_high=int(_get(img_proc_raw, "canny_high", ImgProcessingConfig.canny_high)),
            canny_deriche_bilateral_d=_get_non_negative_int(
                img_proc_raw,
                "canny_deriche_bilateral_d",
                ImgProcessingConfig.canny_deriche_bilateral_d,
            ),
            canny_deriche_bilateral_sigma_color=_get_non_negative_float(
                img_proc_raw,
                "canny_deriche_bilateral_sigma_color",
                ImgProcessingConfig.canny_deriche_bilateral_sigma_color,
            ),
            canny_deriche_bilateral_sigma_space=_get_non_negative_float(
                img_proc_raw,
                "canny_deriche_bilateral_sigma_space",
                ImgProcessingConfig.canny_deriche_bilateral_sigma_space,
            ),
            canny_deriche_gaussian_sigma=_get_non_negative_float(
                img_proc_raw,
                "canny_deriche_gaussian_sigma",
                ImgProcessingConfig.canny_deriche_gaussian_sigma,
            ),
            canny_deriche_morph_close_kernel=_get_non_negative_int(
                img_proc_raw,
                "canny_deriche_morph_close_kernel",
                ImgProcessingConfig.canny_deriche_morph_close_kernel,
            ),
            canny_deriche_morph_close_iterations=_get_non_negative_int(
                img_proc_raw,
                "canny_deriche_morph_close_iterations",
                ImgProcessingConfig.canny_deriche_morph_close_iterations,
            ),
            mono_skel_max_segments=_get_non_negative_int(
                img_proc_raw,
                "mono_skel_max_segments",
                ImgProcessingConfig.mono_skel_max_segments,
            ),
            mono_skel_min_segment_length=_get_non_negative_int(
                img_proc_raw,
                "mono_skel_min_segment_length",
                ImgProcessingConfig.mono_skel_min_segment_length,
            ),
            mono_skel_hough_threshold=_get_non_negative_int(
                img_proc_raw,
                "mono_skel_hough_threshold",
                ImgProcessingConfig.mono_skel_hough_threshold,
            ),
            mono_skel_max_segment_gap=_get_non_negative_int(
                img_proc_raw,
                "mono_skel_max_segment_gap",
                ImgProcessingConfig.mono_skel_max_segment_gap,
            ),
            mono_skel_work_max_dim=_get_non_negative_int(
                img_proc_raw,
                "mono_skel_work_max_dim",
                ImgProcessingConfig.mono_skel_work_max_dim,
            ),
             mono_skel_stitch_angle_tol_deg=_get_non_negative_float(
                 img_proc_raw,
                 "mono_skel_stitch_angle_tol_deg",
                 ImgProcessingConfig.mono_skel_stitch_angle_tol_deg,
             ),
             mono_shape_max_points=_get_non_negative_int(
                 img_proc_raw,
                 "mono_shape_max_points",
                 ImgProcessingConfig.mono_shape_max_points,
             ),
             mono_shape_epsilon_ratio=_get_non_negative_float(
                 img_proc_raw,
                 "mono_shape_epsilon_ratio",
                 ImgProcessingConfig.mono_shape_epsilon_ratio,
             ),
             vessel_theta_offset_deg=float(
                 _get(img_proc_raw, "vessel_theta_offset_deg", ImgProcessingConfig.vessel_theta_offset_deg)
             ),
             encoders_tag_bg_level_1=encoders_tag_bg_level_1,
             encoders_tag_objs_level_1=encoders_tag_objs_level_1,
             encoders_tag_bg_level_2=encoders_tag_bg_level_2,
             encoders_tag_objs_level_2=encoders_tag_objs_level_2,
             active_encoders_tag_bg=None,
             active_encoders_tag_objs=None,
             encoders_tag=unified_encoders_tag,
        ),
        mux_cfg=MuxStructConfig(
            endian=_get(mux_cfg_raw, "endian", MuxStructConfig.endian),
            fmt_payload_len=_get(mux_cfg_raw, "fmt_payload_len", MuxStructConfig.fmt_payload_len),
            fmt_hw=_get(mux_cfg_raw, "fmt_hw", MuxStructConfig.fmt_hw),
            fmt_len_bg=_get(mux_cfg_raw, "fmt_len_bg", MuxStructConfig.fmt_len_bg),
            fmt_len_obj=_get(mux_cfg_raw, "fmt_len_obj", MuxStructConfig.fmt_len_obj),
            fmt_crops_count=_get(mux_cfg_raw, "fmt_crops_count", MuxStructConfig.fmt_crops_count),
            fmt_bbox=_get(mux_cfg_raw, "fmt_bbox", MuxStructConfig.fmt_bbox),
            fmt_encoder_index=_get(mux_cfg_raw, "fmt_encoder_index", MuxStructConfig.fmt_encoder_index),
            max_frame_len=_get_non_negative_int(mux_cfg_raw, "max_frame_len", MuxStructConfig.max_frame_len),
            default_max_crops=_get_non_negative_int(mux_cfg_raw, "default_max_crops", MuxStructConfig.default_max_crops),
        )
    )

    # Minimal validation checks (add more if needed)
    if cfg.model.pre_comp_conf < 0 or cfg.model.pre_comp_conf > 1:
        raise ValueError("model.pre_comp_conf must be between 0 and 1")

    if cfg.model.tile_batch_size < 1:
        raise ValueError("model.tile_batch_size must be >= 1 (use 1 for legacy per-tile mode)")

    if cfg.model.tile_nms_iou < 0 or cfg.model.tile_nms_iou > 1:
        raise ValueError("model.tile_nms_iou must be between 0 and 1")

    if cfg.model.detector_backend not in VALID_DETECTOR_BACKENDS:
        raise ValueError(f"model.detector_backend must be one of {sorted(VALID_DETECTOR_BACKENDS)}")

    if cfg.model.detector_backend == "dlstreamer":
        if not str(cfg.model.dlstreamer_base_url).strip():
            raise ValueError("model.dlstreamer_base_url must be set when model.detector_backend=dlstreamer")
        if not str(cfg.model.dlstreamer_pipeline_name).strip():
            raise ValueError("model.dlstreamer_pipeline_name must be set when model.detector_backend=dlstreamer")
        if cfg.model.dlstreamer_timeout_sec <= 0:
            raise ValueError("model.dlstreamer_timeout_sec must be > 0")
        if cfg.model.dlstreamer_poll_interval_sec <= 0:
            raise ValueError("model.dlstreamer_poll_interval_sec must be > 0")


    if cfg.performance.image_size <= 0:
        raise ValueError("performance.image_size must be > 0")

    if cfg.enc.compression_rate <= 0:
        raise ValueError("encoder.compression_rate must be > 0")

    if cfg.enc.obj_budget_ratio <= 0 or cfg.enc.obj_budget_ratio > 1:
        raise ValueError("encoder.obj_budget_ratio must be in (0, 1]")

    if cfg.enc.min_bytes_for_budget_allocation <= 0:
        raise ValueError("encoder.min_bytes_for_budget_allocation must be > 0")

    if cfg.enc.avif_timeout_sec <= 0:
        raise ValueError("encoder.avif_timeout_sec must be > 0")

    if cfg.enc.avif_jobs < 0:
        raise ValueError("encoder.avif_jobs must be >= 0")

    if cfg.enc.avif_codec is not None and not str(cfg.enc.avif_codec).strip():
        cfg.enc.avif_codec = None

    if cfg.enc.min_bytes_for_encoded_data <= 0:
        raise ValueError("encoder.min_bytes_for_encoded_data must be > 0")

    if cfg.enc.scale_search_step_size <= 0:
        raise ValueError("encoder.scale_search_step_size must be > 0")


    if cfg.pipeline_manager.queue_backlog_threshold_1 < 0:
        raise ValueError("pipeline_manager.queue_backlog_threshold_1 must be >= 0")

    if cfg.pipeline_manager.queue_backlog_threshold_2 < 0:
        raise ValueError("pipeline_manager.queue_backlog_threshold_2 must be >= 0")

    if cfg.pipeline_manager.queue_backlog_threshold_3 < 0:
        raise ValueError("pipeline_manager.queue_backlog_threshold_3 must be >= 0")

    if cfg.pipeline_manager.compression_level not in (1, 2):
        raise ValueError("pipeline_manager.compression_level must be 1 or 2")

    if cfg.pipeline_manager.fast_full_hysteresis_exit < 0:
        raise ValueError("pipeline_manager.fast_full_hysteresis_exit must be >= 0")

    if cfg.pipeline_manager.skip_obj_hysteresis_exit < 0:
        raise ValueError("pipeline_manager.skip_obj_hysteresis_exit must be >= 0")

    if cfg.pipeline_manager.adaptive_compression_rate_warmup_frames < 0:
        raise ValueError("pipeline_manager.adaptive_compression_rate_warmup_frames must be >= 0")

    if cfg.pipeline_manager.adaptive_compression_rate_max <= 0:
        raise ValueError("pipeline_manager.adaptive_compression_rate_max must be > 0")

    if cfg.pipeline_manager.adaptive_compression_rate_boost_factor <= 0:
        raise ValueError("pipeline_manager.adaptive_compression_rate_boost_factor must be > 0")

    if cfg.pipeline_manager.adaptive_compression_rate_method not in ("moving_average", "ema"):
        raise ValueError("pipeline_manager.adaptive_compression_rate_method must be 'moving_average' or 'ema'")

    if cfg.pipeline_manager.adaptive_compression_rate_target_margin_ratio < 0:
        raise ValueError("pipeline_manager.adaptive_compression_rate_target_margin_ratio must be >= 0")

    if cfg.pipeline_manager.adaptive_compression_rate_target_margin_ratio > 1:
        raise ValueError("pipeline_manager.adaptive_compression_rate_target_margin_ratio must be <= 1")

    if cfg.pipeline_manager.adaptive_compression_rate_ema_alpha <= 0:
        raise ValueError("pipeline_manager.adaptive_compression_rate_ema_alpha must be > 0")

    if cfg.pipeline_manager.adaptive_compression_rate_ema_alpha > 1:
        raise ValueError("pipeline_manager.adaptive_compression_rate_ema_alpha must be <= 1")

    if not (
        cfg.pipeline_manager.queue_backlog_threshold_1
        < cfg.pipeline_manager.queue_backlog_threshold_2
        < cfg.pipeline_manager.queue_backlog_threshold_3
    ):
        raise ValueError(
            "pipeline_manager queue thresholds must satisfy queue_backlog_threshold_1 < queue_backlog_threshold_2 < queue_backlog_threshold_3"
        )

    if cfg.pipeline_manager.large_dim_tile_threshold_px < 0:
        raise ValueError("pipeline_manager.large_dim_tile_threshold_px must be >= 0")

    if cfg.enc.zlib_level < 0 or cfg.enc.zlib_level > 9:
        raise ValueError("encoder.zlib_level must be in [0, 9]")

    if cfg.enc.mono_2bit_mixed_two_bit_run <= 0:
        raise ValueError("encoder.mono_2bit_mixed_two_bit_run must be > 0")

    if cfg.enc.mono_2bit_mixed_one_bit_run <= 0:
        raise ValueError("encoder.mono_2bit_mixed_one_bit_run must be > 0")

    if cfg.enc.mono_2bit_drop1bit_fill_gray_level < 0 or cfg.enc.mono_2bit_drop1bit_fill_gray_level > 255:
        raise ValueError("encoder.mono_2bit_drop1bit_fill_gray_level must be in [0, 255]")

    if cfg.enc.mono_2bit_drop1bit_neighbor_k <= 0:
        raise ValueError("encoder.mono_2bit_drop1bit_neighbor_k must be > 0")

    if cfg.dec.avif_timeout_sec <= 0:
        raise ValueError("decoder.avif_timeout_sec must be > 0")

    if cfg.dec.smooth_sigma < 0:
        raise ValueError("decoder.smooth_sigma must be >= 0")

    for level in (1, 2):
        bg_min1 = int(getattr(cfg.img_process, f"bg_scaling_min1_level_{level}"))
        bg_min2 = int(getattr(cfg.img_process, f"bg_scaling_min2_level_{level}"))
        bg_max = int(getattr(cfg.img_process, f"bg_scaling_max_level_{level}"))
        obj_min = int(getattr(cfg.img_process, f"obj_scaling_min_level_{level}"))
        obj_max = int(getattr(cfg.img_process, f"obj_scaling_max_level_{level}"))

        if bg_max <= 0:
            raise ValueError(f"img_process.bg_scaling_max_level_{level} must be > 0")

        if obj_max <= 0:
            raise ValueError(f"img_process.obj_scaling_max_level_{level} must be > 0")

        if bg_min1 > bg_max:
            raise ValueError(
                f"img_process.bg_scaling_min1_level_{level} must be <= img_process.bg_scaling_max_level_{level}"
            )

        if bg_min2 > bg_max:
            raise ValueError(
                f"img_process.bg_scaling_min2_level_{level} must be <= img_process.bg_scaling_max_level_{level}"
            )

        if obj_min > obj_max:
            raise ValueError(
                f"img_process.obj_scaling_min_level_{level} must be <= img_process.obj_scaling_max_level_{level}"
            )

    if cfg.img_process.canny_mode not in VALID_CANNY_MODES:
        raise ValueError(f"img_process.canny_mode must be one of {sorted(VALID_CANNY_MODES)}")

    if cfg.img_process.mono_skel_max_segments <= 0:
        raise ValueError("img_process.mono_skel_max_segments must be > 0")

    if cfg.img_process.mono_skel_min_segment_length <= 0:
        raise ValueError("img_process.mono_skel_min_segment_length must be > 0")

    if cfg.img_process.mono_skel_hough_threshold <= 0:
        raise ValueError("img_process.mono_skel_hough_threshold must be > 0")

    if cfg.img_process.mono_skel_work_max_dim <= 0:
        raise ValueError("img_process.mono_skel_work_max_dim must be > 0")

    if cfg.img_process.mono_skel_stitch_angle_tol_deg <= 0:
        raise ValueError("img_process.mono_skel_stitch_angle_tol_deg must be > 0")

    if cfg.img_process.mono_shape_max_points <= 0:
        raise ValueError("img_process.mono_shape_max_points must be > 0")

    if cfg.img_process.mono_shape_epsilon_ratio <= 0:
        raise ValueError("img_process.mono_shape_epsilon_ratio must be > 0")

    if not math.isfinite(float(cfg.img_process.vessel_theta_offset_deg)):
        raise ValueError("img_process.vessel_theta_offset_deg must be finite")

    if not cfg.img_process.encoders_tag:
        raise ValueError("img_process.encoders_tag must not be empty")

    unified_indices = list(cfg.img_process.encoders_tag.values())
    if len(set(unified_indices)) != len(unified_indices):
        raise ValueError("img_process.encoders_tag must map each encoder name to a unique index")

    known_indices = set(unified_indices)
    for split_key, split_map in (
        ("img_process.encoders_tag_bg_level_1", cfg.img_process.encoders_tag_bg_level_1 or {}),
        ("img_process.encoders_tag_objs_level_1", cfg.img_process.encoders_tag_objs_level_1 or {}),
        ("img_process.encoders_tag_bg_level_2", cfg.img_process.encoders_tag_bg_level_2 or {}),
        ("img_process.encoders_tag_objs_level_2", cfg.img_process.encoders_tag_objs_level_2 or {}),
    ):
        missing_indices = sorted({idx for idx in split_map.values() if idx not in known_indices})
        if missing_indices:
            raise ValueError(
                f"{split_key} contains indices not present in img_process.encoders_tag: {missing_indices}"
            )


    if cfg.image_feeder.target_input_rate_mbps is not None:
        try:
            rate = float(cfg.image_feeder.target_input_rate_mbps)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"image_feeder.target_input_rate_mbps must be a number, got {cfg.image_feeder.target_input_rate_mbps!r}"
            ) from exc
        if rate <= 0:
            raise ValueError(f"image_feeder.target_input_rate_mbps must be > 0, got {rate}")

    if cfg.image_feeder.run_duration_sec is not None:
        try:
            dur = float(cfg.image_feeder.run_duration_sec)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"image_feeder.run_duration_sec must be a number, got {cfg.image_feeder.run_duration_sec!r}"
            ) from exc
        if dur <= 0:
            raise ValueError(f"image_feeder.run_duration_sec must be > 0, got {dur}")

    return cfg


