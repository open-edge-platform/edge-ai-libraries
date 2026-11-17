# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
File: finetune_det_model.py
Version: 0.2
Authors: Omid Semiari, Hosein Nikopour
Date: 2026-07-07
Description: Module to split the data into train/val/test subsets and remap class IDs.
"""


import argparse
import json
import random
import shutil
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from tqdm import tqdm

IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def parse_mapping(mapping_text: str) -> Dict[int, int]:
    """Parse a class-id mapping string like: '0:0,1:0,2:1'."""
    mapping: Dict[int, int] = {}
    chunks = [chunk.strip() for chunk in mapping_text.split(",") if chunk.strip()]
    if not chunks:
        raise ValueError("Mapping is empty. Example: --mapping 0:0,1:0,2:1")

    for chunk in chunks:
        if ":" not in chunk:
            raise ValueError(f"Invalid mapping entry '{chunk}'. Expected old:new format.")
        old_raw, new_raw = chunk.split(":", 1)
        old_cls = int(old_raw.strip())
        new_cls = int(new_raw.strip())
        if old_cls < 0 or new_cls < 0:
            raise ValueError("Class IDs must be >= 0.")
        mapping[old_cls] = new_cls

    return mapping


def load_mapping(mapping: str, mapping_file: Path | None) -> Dict[int, int]:
    if mapping and mapping_file is not None:
        raise ValueError("Use either --mapping or --mapping-file, not both.")

    if mapping:
        return parse_mapping(mapping)

    if mapping_file is None:
        raise ValueError("One mapping source is required: --mapping or --mapping-file")

    payload = json.loads(mapping_file.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Mapping file must be a JSON object, e.g. {\"0\": 0, \"1\": 0}")

    out: Dict[int, int] = {}
    for key, value in payload.items():
        old_cls = int(key)
        new_cls = int(value)
        if old_cls < 0 or new_cls < 0:
            raise ValueError("Class IDs must be >= 0.")
        out[old_cls] = new_cls

    if not out:
        raise ValueError("Mapping file produced an empty mapping.")
    return out


def parse_ratios(ratios_raw: str) -> Tuple[float, float, float]:
    """Parse ratio text like '80,10,10' or '0.8,0.1,0.1'."""
    try:
        vals = [float(x.strip()) for x in ratios_raw.split(",")]
    except ValueError as exc:
        raise ValueError("Ratios must be numeric values like 80,10,10") from exc

    if len(vals) != 3:
        raise ValueError("Ratios must have 3 comma-separated values: train,val,test")
    if any(v < 0 for v in vals):
        raise ValueError("Ratios must be non-negative")

    total = sum(vals)
    if total == 0:
        raise ValueError("Ratio sum must be > 0")

    # Allow either percentages (sum ~= 100) or direct fractions (sum ~= 1).
    if abs(total - 100.0) < 1e-6:
        vals = [v / 100.0 for v in vals]
    else:
        vals = [v / total for v in vals]

    return vals[0], vals[1], vals[2]


def list_images(images_dir: Path) -> List[Path]:
    if not images_dir.exists():
        raise FileNotFoundError(f"Images directory not found: {images_dir}")
    images = [p for p in sorted(images_dir.iterdir()) if p.suffix.lower() in IMG_EXTS]
    if not images:
        raise ValueError(f"No images found in: {images_dir}")
    return images


def split_items(items: Sequence[Path], train_r: float, val_r: float, seed: int) -> Tuple[List[Path], List[Path], List[Path]]:
    shuffled = list(items)
    random.Random(seed).shuffle(shuffled)

    n = len(shuffled)
    n_train = int(round(n * train_r))
    n_val = int(round(n * val_r))

    # Make sure slices always sum exactly to n.
    if n_train > n:
        n_train = n
    if n_train + n_val > n:
        n_val = max(0, n - n_train)

    train_items = shuffled[:n_train]
    val_items = shuffled[n_train : n_train + n_val]
    test_items = shuffled[n_train + n_val :]
    return train_items, val_items, test_items


def remap_label_lines(
    lines: Iterable[str],
    mapping: Dict[int, int],
    unmapped: str,
    strict_lines: bool,
) -> List[str]:
    out: List[str] = []

    for idx, line in enumerate(lines, start=1):
        raw = line.strip()
        if not raw:
            continue

        parts = raw.split()
        if len(parts) != 5:
            if strict_lines:
                raise ValueError(f"Invalid YOLO line at row {idx}: '{line.rstrip()}'")
            continue

        cls = int(parts[0])
        if cls in mapping:
            new_cls = mapping[cls]
            out.append(f"{new_cls} {parts[1]} {parts[2]} {parts[3]} {parts[4]}\n")
            continue

        if unmapped == "keep":
            out.append(f"{cls} {parts[1]} {parts[2]} {parts[3]} {parts[4]}\n")
        elif unmapped == "drop":
            continue
        else:
            raise ValueError(f"Unmapped class id: {cls}")

    return out


def write_sample(
    image_path: Path,
    labels_dir: Path,
    out_root: Path,
    split: str,
    mapping: Dict[int, int],
    action: str,
    unmapped: str,
    strict_lines: bool,
    create_empty_labels: bool,
) -> None:
    dst_img_dir = out_root / "images" / split
    dst_lbl_dir = out_root / "labels" / split
    dst_img_dir.mkdir(parents=True, exist_ok=True)
    dst_lbl_dir.mkdir(parents=True, exist_ok=True)

    dst_img = dst_img_dir / image_path.name
    if action == "symlink":
        if not dst_img.exists():
            dst_img.symlink_to(image_path.resolve())
    elif action == "move":
        shutil.move(str(image_path), str(dst_img))
    else:
        shutil.copy2(image_path, dst_img)

    src_lbl = labels_dir / f"{image_path.stem}.txt"
    dst_lbl = dst_lbl_dir / f"{image_path.stem}.txt"
    if src_lbl.exists():
        txt = src_lbl.read_text(encoding="utf-8")
        remapped = remap_label_lines(
            txt.splitlines(),
            mapping=mapping,
            unmapped=unmapped,
            strict_lines=strict_lines,
        )
        dst_lbl.write_text("".join(remapped), encoding="utf-8")
        if action == "move":
            src_lbl.unlink(missing_ok=True)
    elif create_empty_labels:
        # Keep negative samples explicit in YOLO format.
        dst_lbl.write_text("", encoding="utf-8")


def run(
    src: Path,
    dst: Path,
    mapping: Dict[int, int],
    ratios: Tuple[float, float, float],
    seed: int,
    action: str,
    unmapped: str,
    strict_lines: bool,
    create_empty_labels: bool,
    images_subdir: str,
    labels_subdir: str,
) -> None:
    images_dir = src / images_subdir
    labels_dir = src / labels_subdir
    if not labels_dir.exists():
        raise FileNotFoundError(f"Labels directory not found: {labels_dir}")

    images = list_images(images_dir)
    train_items, val_items, test_items = split_items(images, ratios[0], ratios[1], seed)

    if dst.exists() and any(dst.iterdir()):
        raise ValueError(f"Destination must be empty or non-existent: {dst}")
    dst.mkdir(parents=True, exist_ok=True)

    split_map = {
        "train": train_items,
        "val": val_items,
        "test": test_items,
    }

    for split_name, split_items_list in split_map.items():
        for img in tqdm(split_items_list, desc=f"{split_name} ({len(split_items_list)})"):
            write_sample(
                image_path=img,
                labels_dir=labels_dir,
                out_root=dst,
                split=split_name,
                mapping=mapping,
                action=action,
                unmapped=unmapped,
                strict_lines=strict_lines,
                create_empty_labels=create_empty_labels,
            )

    print("Done.")
    print(f"Source images: {len(images)}")
    print(f"train/val/test: {len(train_items)}/{len(val_items)}/{len(test_items)}")
    print(f"Output dataset: {dst}")


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Split YOLO dataset into train/val/test and remap class IDs.",
    )
    ap.add_argument("--src", required=True, help="Dataset root containing images/ and labels/")
    ap.add_argument("--dst", required=True, help="Output dataset root")
    ap.add_argument(
        "--ratios",
        default="80,10,10",
        help="Split ratios as train,val,test. Examples: 80,10,10 or 0.8,0.1,0.1",
    )
    ap.add_argument("--seed", type=int, default=42, help="Random seed for deterministic split")
    ap.add_argument(
        "--mapping",
        default="",
        help="Class remap spec in old:new list format, e.g. 0:0,1:0,2:1",
    )
    ap.add_argument(
        "--mapping-file",
        type=Path,
        default=None,
        help="JSON file containing mapping, e.g. {'0': 0, '1': 0, '2': 1}",
    )
    ap.add_argument(
        "--images-subdir",
        default="images",
        help="Images subdirectory under --src (default: images)",
    )
    ap.add_argument(
        "--labels-subdir",
        default="labels",
        help="Labels subdirectory under --src (default: labels)",
    )
    ap.add_argument(
        "--action",
        choices=["copy", "symlink", "move"],
        default="copy",
        help="How to place images in output split folders",
    )
    ap.add_argument(
        "--unmapped",
        choices=["error", "drop", "keep"],
        default="error",
        help="How to handle class IDs not present in mapping",
    )
    ap.add_argument(
        "--strict-lines",
        action="store_true",
        help="Fail on malformed YOLO annotation rows (default: skip malformed lines)",
    )
    ap.add_argument(
        "--no-empty-labels",
        action="store_true",
        help="Do not create empty .txt labels when an image has no label file",
    )
    return ap


def main() -> None:
    args = build_arg_parser().parse_args()

    mapping = load_mapping(args.mapping, args.mapping_file)
    ratios = parse_ratios(args.ratios)

    run(
        src=Path(args.src),
        dst=Path(args.dst),
        mapping=mapping,
        ratios=ratios,
        seed=args.seed,
        action=args.action,
        unmapped=args.unmapped,
        strict_lines=args.strict_lines,
        create_empty_labels=not args.no_empty_labels,
        images_subdir=args.images_subdir,
        labels_subdir=args.labels_subdir,
    )


if __name__ == "__main__":
    main()

