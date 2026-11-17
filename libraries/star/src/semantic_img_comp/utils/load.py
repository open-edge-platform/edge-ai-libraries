# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: utils/load.py
Version: 0.2
Authors: Omid Semiari, Hosein Nikopour
Date: 2026-04-10
Description: loads image path and yolo model.
"""

from pathlib import Path
import random

import yaml


VALID_EXTENSIONS = {".jpg", ".jpeg", ".png"}
VALID_CATALOG_SAMPLING_MODES = {"uniform", "proportional"}


def _load_image_paths_from_dir(input_dir: Path) -> list[Path]:
    if not input_dir.exists() or not input_dir.is_dir():
        raise FileNotFoundError(f"Input data directory does not exist: {input_dir}")

    return sorted(
        p for p in input_dir.iterdir()
        if p.suffix.lower() in VALID_EXTENSIONS and p.is_file()
    )


def _parse_catalog_dirs(catalog_raw, *, catalog_path: Path) -> tuple[list[Path], int | None]:
    if isinstance(catalog_raw, list):
        entries = catalog_raw
        random_seed = None
    elif isinstance(catalog_raw, dict):
        entries = catalog_raw.get("input_dirs")
        if entries is None:
            entries = catalog_raw.get("directories")
        if entries is None:
            raise ValueError(
                f"Catalog YAML must contain 'input_dirs' (or 'directories'): {catalog_path}"
            )
        random_seed = catalog_raw.get("random_seed")
    else:
        raise ValueError(
            f"Catalog YAML must be a list or dict, got {type(catalog_raw).__name__}: {catalog_path}"
        )

    if not isinstance(entries, list) or not entries:
        raise ValueError(f"Catalog input directory list must be non-empty: {catalog_path}")

    resolved_dirs: list[Path] = []
    base_dir = catalog_path.parent
    for entry in entries:
        candidate = Path(entry)
        if not candidate.is_absolute():
            candidate = (base_dir / candidate).resolve()
        if not candidate.exists() or not candidate.is_dir():
            raise FileNotFoundError(f"Catalog directory does not exist: {candidate}")
        resolved_dirs.append(candidate)

    if random_seed is not None:
        try:
            random_seed = int(random_seed)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Catalog random_seed must be an integer, got {random_seed!r}") from exc

    return resolved_dirs, random_seed


def _load_paths_from_catalog(catalog_path: Path, *, sampling_mode: str = "uniform") -> list[Path]:
    with open(catalog_path, "r", encoding="utf-8") as f:
        catalog_raw = yaml.safe_load(f)

    if catalog_raw is None:
        raise ValueError(f"Catalog YAML is empty: {catalog_path}")

    mode = str(sampling_mode).strip().lower()
    if mode not in VALID_CATALOG_SAMPLING_MODES:
        raise ValueError(
            f"Unsupported catalog sampling mode: {sampling_mode!r}. "
            f"Expected one of {sorted(VALID_CATALOG_SAMPLING_MODES)}"
        )

    directories, random_seed = _parse_catalog_dirs(catalog_raw, catalog_path=catalog_path)

    rng = random.Random(random_seed)  # nosec B311 - deterministic dataset shuffling, not security/crypto related
    by_dir: dict[Path, list[Path]] = {}
    total_count = 0
    for input_dir in directories:
        paths = _load_image_paths_from_dir(input_dir)
        if paths:
            rng.shuffle(paths)
            by_dir[input_dir] = paths
            total_count += len(paths)

    if total_count == 0:
        raise ValueError(f"No supported images found across catalog directories: {catalog_path}")

    # Draw from active directories using the configured policy.
    mixed_paths: list[Path] = []
    while by_dir:
        active_dirs = [directory for directory, paths in by_dir.items() if paths]
        if not active_dirs:
            break
        if mode == "uniform":
            weights = [1] * len(active_dirs)
        else:
            weights = [len(by_dir[directory]) for directory in active_dirs]
        selected_dir = rng.choices(active_dirs, weights=weights, k=1)[0]
        mixed_paths.append(by_dir[selected_dir].pop())
        if not by_dir[selected_dir]:
            del by_dir[selected_dir]

    return mixed_paths


def load_paths_with_context(input_path, *, catalog_sampling_mode: str = "uniform") -> tuple[list[Path], dict[str, object]]:
    """Load image paths and return basic source metadata for reproducibility/logging."""
    input_path = Path(input_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input path does not exist: {input_path}")

    if input_path.is_dir():
        return _load_image_paths_from_dir(input_path), {
            "source_type": "directory",
            "catalog_random_seed": None,
            "catalog_sampling_mode": None,
        }

    if input_path.is_file() and input_path.suffix.lower() in {".yml", ".yaml"}:
        with open(input_path, "r", encoding="utf-8") as f:
            catalog_raw = yaml.safe_load(f)

        if catalog_raw is None:
            raise ValueError(f"Catalog YAML is empty: {input_path}")

        _, random_seed = _parse_catalog_dirs(catalog_raw, catalog_path=input_path)
        return _load_paths_from_catalog(input_path, sampling_mode=catalog_sampling_mode), {
            "source_type": "catalog",
            "catalog_random_seed": random_seed,
            "catalog_sampling_mode": str(catalog_sampling_mode).strip().lower(),
        }

    raise ValueError(
        f"Unsupported input path: {input_path}. Expected a directory or YAML catalog file (.yml/.yaml)."
    )

# ------------------------------
# BUILD IMAGE LIST
# ------------------------------
def load_paths(input_path, *, catalog_sampling_mode: str = "uniform"):
    """
    Load sorted list of image paths from a directory.

    Args:
        input_path: Path to directory (str or Path object)

    Returns:
        Sorted list of Path objects for valid image files
    """
    paths, _ = load_paths_with_context(input_path, catalog_sampling_mode=catalog_sampling_mode)
    return paths

# ------------------------------
# LOAD YOLO MODEL
# ------------------------------
def load_yolo_model(model_path=None, model_name="yolov8m.pt", device=None):
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise ImportError(
            "ultralytics is required to load YOLO models. Install encoder dependencies or run with --skip-obj-detction."
        ) from exc

    if model_path is None:
        model_path = Path(f'/obj_det_models/{model_name}')
    else:
        model_path = Path(model_path)

    if model_path.is_file():
        # PyTorch (.pt)
        if model_path.suffix.lower() != ".pt":
            raise ValueError(f"Unsupported model file: {model_path}")
        model = YOLO(str(model_path), task="detect")

        print(f"\nLoaded YOLO model: {model_path}")
        print("===================================\n")


    elif model_path.is_dir():
        # OpenVINO
        xmls = list(model_path.glob("*.xml"))
        bins = list(model_path.glob("*.bin"))

        if not xmls or not bins:
            raise FileNotFoundError(
                f"Invalid OpenVINO model directory: {model_path}"
            )

        # pass directory or xml path
        model = YOLO(str(model_path), task="detect")

        print(f"\nLoaded OpenVINO quantized YOLO model: {model_path}")
        print("===================================\n")

    else:
        raise FileNotFoundError(f"Model path does not exist: {model_path}")

    if device is not None:
        import numpy as np
        model.predict(np.zeros((32, 32, 3), dtype="uint8"), device=device, verbose=False)

    # YOLO class names (index → name)
    yolo_names = model.names
    if isinstance(yolo_names, list):
        yolo_names = {i: n for i, n in enumerate(yolo_names)}

    return model, yolo_names

