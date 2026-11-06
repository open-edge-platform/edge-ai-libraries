# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import yaml


def _load_module():
    repo_root = Path(__file__).resolve().parents[1]
    mod_path = repo_root / "finetuning" / "remap_temp_buoy_subsets.py"
    spec = spec_from_file_location("remap_temp_buoy_subsets", mod_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_split_sample(root: Path, subset_name: str, samples: list[tuple[str, int]]) -> None:
    images_dir = root / subset_name / "images"
    labels_dir = root / subset_name / "labels"
    images_dir.mkdir(parents=True)
    labels_dir.mkdir(parents=True)

    for stem, cls in samples:
        (images_dir / f"{stem}.jpg").write_bytes(b"fake")
        (labels_dir / f"{stem}.txt").write_text(
            f"{cls} 0.5 0.5 0.2 0.2\n",
            encoding="utf-8",
        )


def test_remap_from_yaml_preserves_subsets_and_writes_single_class_yaml(tmp_path):
    mod = _load_module()

    finetuning_dir = tmp_path / "finetuning"
    finetuning_dir.mkdir()
    _write_split_sample(tmp_path, "train", [("train_buoy", 0), ("train_target", 2)])
    _write_split_sample(tmp_path, "valid", [("val_red_pole", 10)])
    _write_split_sample(tmp_path, "test", [("test_target", 12)])

    source_yaml = finetuning_dir / "temp_buoy.yaml"
    source_yaml.write_text(
        yaml.safe_dump(
            {
                "names": [
                    "black_buoy",
                    "black_cross",
                    "black_target_boat",
                    "black_triangle",
                    "blue_buoy",
                    "green_buoy",
                    "green_light_buoy",
                    "green_pole_buoy",
                    "red_buoy",
                    "red_light_buoy",
                    "red_pole_buoy",
                    "yellow_buoy",
                    "yellow_target_boat",
                ],
                "nc": 13,
                "train": "../train/images",
                "val": "../valid/images",
                "test": "../test/images",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    summary = mod.remap_from_yaml(source_yaml=source_yaml)

    output_root = tmp_path / "temp_buoy_single_class"
    assert summary["output_root"] == output_root.resolve()
    assert summary["dataset_yaml"] == (finetuning_dir / "temp_buoy_single_class.yaml").resolve()
    assert summary["new_class_id"] == 0
    assert summary["class_name"] == "buoy"
    assert summary["new_names"] == ["buoy"]
    assert summary["mapping"] == {idx: 0 for idx in range(13)}
    assert summary["yaml_paths"] == {
        "train": "../temp_buoy_single_class/train/images",
        "val": "../temp_buoy_single_class/valid/images",
        "test": "../temp_buoy_single_class/test/images",
    }
    assert 'model="yolov8m.pt"' in summary["train_command"]
    assert f'data="{summary["dataset_yaml"]}"' in summary["train_command"]

    assert len(list((output_root / "train" / "images").glob("*.jpg"))) == 2
    assert len(list((output_root / "valid" / "images").glob("*.jpg"))) == 1
    assert len(list((output_root / "test" / "images").glob("*.jpg"))) == 1

    assert (output_root / "train" / "labels" / "train_buoy.txt").read_text(encoding="utf-8").startswith("0 ")
    assert (output_root / "valid" / "labels" / "val_red_pole.txt").read_text(encoding="utf-8").startswith("0 ")
    assert (output_root / "train" / "labels" / "train_target.txt").read_text(encoding="utf-8").startswith("0 ")
    assert (output_root / "test" / "labels" / "test_target.txt").read_text(encoding="utf-8").startswith("0 ")

    generated_yaml = yaml.safe_load(summary["dataset_yaml"].read_text(encoding="utf-8"))
    assert generated_yaml["nc"] == 1
    assert generated_yaml["names"] == ["buoy"]
    assert generated_yaml["train"] == "../temp_buoy_single_class/train/images"
    assert generated_yaml["val"] == "../temp_buoy_single_class/valid/images"
    assert generated_yaml["test"] == "../temp_buoy_single_class/test/images"


def test_build_single_class_mapping_collapses_all_source_classes():
    mod = _load_module()

    names = [
        "black_buoy",
        "black_cross",
        "blue_buoy",
        "yellow_target_boat",
    ]
    updated_names, mapping, new_class_id = mod.build_single_class_mapping(names)

    assert updated_names == ["buoy"]
    assert new_class_id == 0
    assert mapping == {0: 0, 1: 0, 2: 0, 3: 0}


def test_remap_label_lines_accepts_segmentation_polygon_rows():
    mod = _load_module()

    polygon_row = (
        "11 0.3701923078125 0.5264423078125 0.37139423125 0.5488782046875 "
        "0.3798076921875 0.5280448703125 0.375 0.5216346140625 0.3701923078125 0.5264423078125"
    )
    out = mod.remap_label_lines(
        [polygon_row],
        mapping={i: 0 for i in range(13)},
        max_source_class_id=12,
        strict_lines=True,
    )

    assert len(out) == 1
    assert out[0].startswith("0 ")
    assert "0.3701923078125" in out[0]


def test_remap_label_lines_rejects_malformed_polygon_rows_when_strict():
    mod = _load_module()

    malformed_row = "11 0.1 0.2 0.3"
    try:
        mod.remap_label_lines(
            [malformed_row],
            mapping={i: 0 for i in range(13)},
            max_source_class_id=12,
            strict_lines=True,
        )
    except ValueError as exc:
        assert "Invalid YOLO line" in str(exc)
    else:
        raise AssertionError("Expected ValueError for malformed polygon row in strict mode")


def test_process_split_skips_sample_with_out_of_range_class_id(tmp_path):
    mod = _load_module()

    images_dir = tmp_path / "train" / "images"
    labels_dir = tmp_path / "train" / "labels"
    images_dir.mkdir(parents=True)
    labels_dir.mkdir(parents=True)

    (images_dir / "good.jpg").write_bytes(b"fake")
    (labels_dir / "good.txt").write_text("1 0.5 0.5 0.2 0.2\n", encoding="utf-8")

    (images_dir / "bad.jpg").write_bytes(b"fake")
    (labels_dir / "bad.txt").write_text("25 0.5 0.5 0.2 0.2\n", encoding="utf-8")

    out_root = tmp_path / "out"
    subset_name = mod.process_split(
        images_dir=images_dir,
        out_root=out_root,
        mapping={0: 0, 1: 0, 2: 0},
        max_source_class_id=2,
        action="copy",
        strict_lines=True,
        create_empty_labels=True,
    )

    assert subset_name == "train"
    assert (out_root / "train" / "images" / "good.jpg").exists()
    assert (out_root / "train" / "labels" / "good.txt").exists()
    assert not (out_root / "train" / "images" / "bad.jpg").exists()
    assert not (out_root / "train" / "labels" / "bad.txt").exists()


