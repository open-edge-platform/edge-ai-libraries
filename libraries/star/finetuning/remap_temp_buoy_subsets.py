# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

import yaml

IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
SPLIT_KEYS = ("train", "val", "test")
DEFAULT_OUTPUT_DIR_NAME = "temp_buoy_single_class"
DEFAULT_OUTPUT_YAML_NAME = "temp_buoy_single_class.yaml"
DEFAULT_CLASS_NAME = "buoy"
DEFAULT_MODEL = "yolov8m.pt"


class OutOfRangeClassIdError(ValueError):
    """Raised when a label row contains a class id outside the source YAML range."""


def _normalize_names(raw_names: object) -> List[str]:
    if isinstance(raw_names, list):
        return [str(name) for name in raw_names]

    if isinstance(raw_names, dict):
        ordered_items = sorted(raw_names.items(), key=lambda item: int(item[0]))
        return [str(name) for _, name in ordered_items]

    raise ValueError("Dataset YAML must define 'names' as a list or mapping.")


def load_dataset_yaml(yaml_path: Path) -> dict:
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Dataset YAML must be a mapping: {yaml_path}")

    missing = [key for key in ("names", "nc", *SPLIT_KEYS) if key not in data]
    if missing:
        raise ValueError(f"Dataset YAML is missing required keys: {missing}")

    names = _normalize_names(data["names"])
    nc = int(data["nc"])
    if len(names) != nc:
        raise ValueError(f"'nc' ({nc}) does not match number of class names ({len(names)}).")

    data["names"] = names
    data["nc"] = nc
    return data


def resolve_dataset_dir(yaml_path: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = (yaml_path.parent / path).resolve()
    return path


def infer_labels_dir(images_dir: Path) -> Path:
    if images_dir.name != "images":
        raise ValueError(f"Expected an images directory ending with 'images': {images_dir}")

    labels_dir = images_dir.parent / "labels"
    if not labels_dir.exists():
        raise FileNotFoundError(f"Labels directory not found for images directory {images_dir}: {labels_dir}")
    return labels_dir


def list_images(images_dir: Path) -> List[Path]:
    if not images_dir.exists():
        raise FileNotFoundError(f"Images directory not found: {images_dir}")

    images = [path for path in sorted(images_dir.iterdir()) if path.is_file() and path.suffix.lower() in IMG_EXTS]
    if not images:
        raise ValueError(f"No images found in: {images_dir}")
    return images


def build_single_class_mapping(
    names: Sequence[str],
    class_name: str = DEFAULT_CLASS_NAME,
) -> tuple[List[str], Dict[int, int], int]:
    if not names:
        raise ValueError("Source dataset must define at least one class.")

    class_name = class_name.strip()
    if not class_name:
        raise ValueError("class_name must not be empty.")

    mapping = {source_id: 0 for source_id in range(len(names))}
    return [class_name], mapping, 0


def remap_label_lines(
    lines: Iterable[str],
    mapping: Dict[int, int],
    max_source_class_id: int,
    strict_lines: bool,
) -> List[str]:
    out: List[str] = []

    for idx, line in enumerate(lines, start=1):
        raw = line.strip()
        if not raw:
            continue

        parts = raw.split()
        is_detection = len(parts) == 5
        is_segmentation = len(parts) > 5 and (len(parts) - 1) % 2 == 0 and (len(parts) - 1) >= 6
        if not (is_detection or is_segmentation):
            if strict_lines:
                raise ValueError(f"Invalid YOLO line at row {idx}: '{line.rstrip()}'")
            continue

        try:
            cls = int(parts[0])
        except ValueError as exc:
            raise ValueError(f"Invalid class id at row {idx}: '{parts[0]}'") from exc

        if cls < 0 or cls > max_source_class_id:
            raise OutOfRangeClassIdError(
                f"Class id {cls} at row {idx} is outside the source range 0..{max_source_class_id}."
            )

        # Validate all coordinate tokens for both detection and segmentation formats.
        try:
            for token in parts[1:]:
                float(token)
        except ValueError as exc:
            if strict_lines:
                raise ValueError(f"Invalid numeric token at row {idx}: '{line.rstrip()}'") from exc
            continue

        new_cls = mapping.get(cls, cls)
        out.append(f"{new_cls} {' '.join(parts[1:])}\n")

    return out


def _copy_image(src: Path, dst: Path, action: str) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)

    if action == "symlink":
        if dst.exists() or dst.is_symlink():
            dst.unlink()
        dst.symlink_to(src.resolve())
    elif action == "move":
        shutil.move(str(src), str(dst))
    else:
        shutil.copy2(src, dst)


def process_split(
    images_dir: Path,
    out_root: Path,
    mapping: Dict[int, int],
    max_source_class_id: int,
    action: str,
    strict_lines: bool,
    create_empty_labels: bool,
) -> str:
    labels_dir = infer_labels_dir(images_dir)
    images = list_images(images_dir)
    subset_name = images_dir.parent.name

    dst_images_dir = out_root / subset_name / "images"
    dst_labels_dir = out_root / subset_name / "labels"
    dst_images_dir.mkdir(parents=True, exist_ok=True)
    dst_labels_dir.mkdir(parents=True, exist_ok=True)

    for image_path in images:
        src_label = labels_dir / f"{image_path.stem}.txt"
        dst_label = dst_labels_dir / f"{image_path.stem}.txt"
        if src_label.exists():
            try:
                remapped = remap_label_lines(
                    src_label.read_text(encoding="utf-8").splitlines(),
                    mapping=mapping,
                    max_source_class_id=max_source_class_id,
                    strict_lines=strict_lines,
                )
            except OutOfRangeClassIdError:
                # Skip the full sample when any row has an out-of-range class id.
                continue

            _copy_image(image_path, dst_images_dir / image_path.name, action)
            dst_label.write_text("".join(remapped), encoding="utf-8")
            if action == "move":
                src_label.unlink(missing_ok=True)
        elif create_empty_labels:
            _copy_image(image_path, dst_images_dir / image_path.name, action)
            dst_label.write_text("", encoding="utf-8")
        else:
            _copy_image(image_path, dst_images_dir / image_path.name, action)

    return subset_name


def _infer_default_output_root(yaml_path: Path, data: dict, output_dir_name: str) -> Path:
    subset_roots = [resolve_dataset_dir(yaml_path, str(data[key])).parent for key in SPLIT_KEYS]
    common_root = Path(os.path.commonpath([str(path) for path in subset_roots]))
    return common_root / output_dir_name


def _relative_path(from_dir: Path, to_path: Path) -> str:
    return os.path.relpath(to_path, start=from_dir)


def build_single_class_dataset_yaml(
    source_data: dict,
    yaml_paths: Dict[str, str],
    class_name: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "names": [class_name],
        "nc": 1,
    }

    for key, value in source_data.items():
        if key not in {"names", "nc", "path", *SPLIT_KEYS}:
            payload[key] = value

    for split_key in SPLIT_KEYS:
        payload[split_key] = yaml_paths[split_key]

    return payload


def write_dataset_yaml(output_yaml: Path, payload: dict) -> Path:
    output_yaml.parent.mkdir(parents=True, exist_ok=True)
    output_yaml.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return output_yaml.resolve()


def build_yolov8_train_command(
    dataset_yaml: Path,
    model: str = DEFAULT_MODEL,
    epochs: int = 100,
    imgsz: int = 640,
    batch: int = 16,
    device: str | None = None,
) -> str:
    command_parts = [
        "yolo detect train",
        f'model="{model}"',
        f'data="{dataset_yaml}"',
        f"epochs={epochs}",
        f"imgsz={imgsz}",
        f"batch={batch}",
    ]
    if device:
        command_parts.append(f'device="{device}"')
    return " ".join(command_parts)


def run_yolov8_training(
    dataset_yaml: Path,
    model: str = DEFAULT_MODEL,
    epochs: int = 100,
    imgsz: int = 640,
    batch: int = 16,
    device: str | None = None,
    project: str | None = None,
    name: str | None = None,
    exist_ok: bool = False,
) -> Any:
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise ImportError(
            "Ultralytics is required for --train. Install it in the active environment first."
        ) from exc

    model_handle = YOLO(model)
    train_kwargs: dict[str, Any] = {
        "data": str(dataset_yaml),
        "epochs": epochs,
        "imgsz": imgsz,
        "batch": batch,
    }
    if device:
        train_kwargs["device"] = device
    if project:
        train_kwargs["project"] = project
    if name:
        train_kwargs["name"] = name
    if exist_ok:
        train_kwargs["exist_ok"] = True

    return model_handle.train(**train_kwargs)


def remap_from_yaml(
    source_yaml: Path,
    output_root: Path | None = None,
    output_yaml: Path | None = None,
    class_name: str = DEFAULT_CLASS_NAME,
    action: str = "copy",
    strict_lines: bool = True,
    create_empty_labels: bool = True,
    model: str = DEFAULT_MODEL,
    epochs: int = 100,
    imgsz: int = 640,
    batch: int = 16,
    device: str | None = None,
    train: bool = False,
    project: str | None = None,
    name: str | None = None,
    exist_ok: bool = False,
) -> dict:
    data = load_dataset_yaml(source_yaml)
    output_root = output_root or _infer_default_output_root(source_yaml, data, DEFAULT_OUTPUT_DIR_NAME)
    output_root = output_root.resolve()
    output_yaml = (output_yaml or source_yaml.with_name(DEFAULT_OUTPUT_YAML_NAME)).resolve()

    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError(f"Output root must be empty or not exist: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)

    updated_names, mapping, new_class_id = build_single_class_mapping(
        data["names"],
        class_name=class_name,
    )

    subset_dirs: Dict[str, str] = {}
    for split_key in SPLIT_KEYS:
        images_dir = resolve_dataset_dir(source_yaml, str(data[split_key]))
        subset_name = process_split(
            images_dir=images_dir,
            out_root=output_root,
            mapping=mapping,
            max_source_class_id=data["nc"] - 1,
            action=action,
            strict_lines=strict_lines,
            create_empty_labels=create_empty_labels,
        )
        subset_dirs[split_key] = subset_name

    yaml_paths = {
        split_key: _relative_path(source_yaml.parent.resolve(), output_root / subset_name / "images")
        for split_key, subset_name in subset_dirs.items()
    }

    dataset_yaml = write_dataset_yaml(
        output_yaml,
        build_single_class_dataset_yaml(
            source_data=data,
            yaml_paths=yaml_paths,
            class_name=class_name,
        ),
    )

    train_command = build_yolov8_train_command(
        dataset_yaml=dataset_yaml,
        model=model,
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        device=device,
    )

    train_result = None
    if train:
        train_result = run_yolov8_training(
            dataset_yaml=dataset_yaml,
            model=model,
            epochs=epochs,
            imgsz=imgsz,
            batch=batch,
            device=device,
            project=project,
            name=name,
            exist_ok=exist_ok,
        )

    return {
        "output_root": output_root,
        "dataset_yaml": dataset_yaml,
        "new_class_id": new_class_id,
        "new_names": updated_names,
        "class_name": class_name,
        "mapping": mapping,
        "yaml_paths": yaml_paths,
        "train_command": train_command,
        "train_result": train_result,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Preserve the train/val/test subsets defined in a YOLO dataset YAML, collapse every source "
            "class into a single buoy class, and write a YOLOv8m-ready dataset YAML."
        )
    )
    parser.add_argument(
        "--source-yaml",
        type=Path,
        default=Path(__file__).with_name("temp_buoy.yaml"),
        help="Source dataset YAML to read (default: finetuning/temp_buoy.yaml)",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Output dataset root. Defaults to a sibling directory named temp_buoy_single_class.",
    )
    parser.add_argument(
        "--output-yaml",
        type=Path,
        default=None,
        help="Output YAML path. Defaults to finetuning/temp_buoy_single_class.yaml.",
    )
    parser.add_argument(
        "--class-name",
        default=DEFAULT_CLASS_NAME,
        help="Name of the single consolidated class (default: buoy)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="YOLO model checkpoint to fine-tune after remapping (default: yolov8m.pt)",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=100,
        help="Epochs to include in the suggested training command (default: 100)",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="Image size to include in the suggested training command (default: 640)",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=16,
        help="Batch size to include in the suggested training command (default: 16)",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Optional device string to include in the suggested training command",
    )
    parser.add_argument(
        "--train",
        action="store_true",
        help="Launch YOLOv8 training immediately after writing the remapped dataset YAML.",
    )
    parser.add_argument(
        "--project",
        default=None,
        help="Optional Ultralytics project directory to use when --train is set.",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Optional Ultralytics run name to use when --train is set.",
    )
    parser.add_argument(
        "--exist-ok",
        action="store_true",
        help="Allow reusing an existing Ultralytics run directory when --train is set.",
    )
    parser.add_argument(
        "--action",
        choices=["copy", "symlink", "move"],
        default="copy",
        help="How to materialize images in the remapped dataset",
    )
    parser.add_argument(
        "--non-strict-lines",
        action="store_true",
        help="Skip malformed YOLO annotation rows instead of failing.",
    )
    parser.add_argument(
        "--no-empty-labels",
        action="store_true",
        help="Do not create empty label files when a source image has no annotation file.",
    )
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    summary = remap_from_yaml(
        source_yaml=args.source_yaml.resolve(),
        output_root=args.output_root.resolve() if args.output_root else None,
        output_yaml=args.output_yaml.resolve() if args.output_yaml else None,
        class_name=args.class_name,
        action=args.action,
        strict_lines=not args.non_strict_lines,
        create_empty_labels=not args.no_empty_labels,
        model=args.model,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        train=args.train,
        project=args.project,
        name=args.name,
        exist_ok=args.exist_ok,
    )

    print("Remap complete.")
    print(f"Output root: {summary['output_root']}")
    print(f"Dataset YAML: {summary['dataset_yaml']}")
    print(f"Consolidated class id: {summary['new_class_id']}")
    print(f"Consolidated class name: {summary['class_name']}")
    print(f"Mapped source ids -> {summary['new_class_id']}: {sorted(summary['mapping'])}")
    print("YAML subset entries:")
    for split_key in SPLIT_KEYS:
        print(f"  {split_key}: {summary['yaml_paths'][split_key]}")
    print("Suggested YOLOv8m training command:")
    print(summary["train_command"])
    if summary["train_result"] is not None:
        print("YOLOv8 training run completed.")


if __name__ == "__main__":
    main()



