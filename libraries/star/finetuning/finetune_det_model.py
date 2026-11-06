# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: finetune_det_model.py
Version: 0.2
Authors: Omid Semiari, Hosein Nikopour
Date: 2026-07-07
Description: Module to finetune the Yolo model using custom dataset.
"""

from collections import Counter
from pathlib import Path

import yaml
from ultralytics import YOLO


def _resolve_data_yaml_path(data_yaml: str) -> Path:
    data_yaml_path = Path(data_yaml)
    if data_yaml_path.is_absolute():
        return data_yaml_path.resolve()

    if data_yaml_path.exists():
        return data_yaml_path.resolve()

    return (Path(__file__).resolve().parent / data_yaml_path).resolve()


def _image_dir_to_label_dir(image_dir: Path) -> Path:
    parts = list(image_dir.parts)
    if "images" in parts:
        idx = parts.index("images")
        parts[idx] = "labels"
        return Path(*parts)
    return image_dir


def _count_train_class_instances(data_yaml: str):
    data_yaml_path = _resolve_data_yaml_path(data_yaml)
    with data_yaml_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    dataset_root = Path(cfg.get("path", "."))
    if not dataset_root.is_absolute():
        dataset_root = (data_yaml_path.parent / dataset_root).resolve()

    train_entries = cfg.get("train", [])
    if isinstance(train_entries, str):
        train_entries = [train_entries]

    counts = Counter()
    for train_entry in train_entries:
        image_dir = Path(train_entry)
        if not image_dir.is_absolute():
            image_dir = dataset_root / image_dir

        label_dir = _image_dir_to_label_dir(image_dir).resolve()
        if not label_dir.exists():
            continue

        for label_file in label_dir.rglob("*.txt"):
            for row in label_file.read_text(encoding="utf-8").splitlines():
                parts = row.strip().split()
                if not parts:
                    continue
                try:
                    cls_id = int(float(parts[0]))
                except ValueError:
                    continue
                counts[cls_id] += 1

    names = cfg.get("names", {})
    return counts, int(cfg.get("nc", 0)), names


def _print_class_counts(data_yaml: str):
    counts, nc, names = _count_train_class_instances(data_yaml)
    print("\nTraining class instance counts:")
    for cls_id in range(nc):
        if isinstance(names, dict):
            class_name = names.get(cls_id, names.get(str(cls_id), f"class_{cls_id}"))
        elif isinstance(names, list) and cls_id < len(names):
            class_name = names[cls_id]
        else:
            class_name = f"class_{cls_id}"
        print(f"  {cls_id}: {class_name} -> {counts.get(cls_id, 0)}")


def train(
    model_path="../models/yolov8m.pt",
    data_yaml="data_nrl.yaml",
    total_epochs=100,
    imgsz=640,
    batch=128,
    device='0,1,2,3,4,5,6,7',
):
    """
    Fine-tune YOLOv8 on custom dataset
    with all layers unfrozen (single-phase training).
    """

    # Load pretrained YOLOv8 model
    model = YOLO(model_path)

    _print_class_counts(data_yaml)

    model.train(
        data=data_yaml,
        epochs=total_epochs,
        imgsz=imgsz,
        batch=batch,
        device=device,

        freeze=0,          # ✅ train all layers from start
        lr0=0.001,         # ✅ conservative LR for stability

        # Augmentations
        hsv_h=0.0, hsv_s=0.0, hsv_v=0.2,
        degrees=5.0, translate=0.1, scale=0.5, shear=2.0, perspective=0.0,
        fliplr=0.5, flipud=0.0,
        mosaic=0.5, mixup=0.1,
        erasing=0.2,

        # Performance
        workers=4,
        cache=False,
        pretrained=True,
    )


if __name__ == "__main__":
    train()