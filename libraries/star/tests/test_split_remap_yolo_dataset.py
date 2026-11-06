# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[1]
    mod_path = repo_root / "finetuning" / "split_remap_yolo_dataset.py"
    spec = spec_from_file_location("split_remap_yolo_dataset", mod_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_sample_dataset(root: Path, count: int = 10) -> None:
    img_dir = root / "images"
    lbl_dir = root / "labels"
    img_dir.mkdir(parents=True)
    lbl_dir.mkdir(parents=True)

    for i in range(count):
        (img_dir / f"img_{i:03d}.jpg").write_bytes(b"fake")
        cls = i % 4  # 0,1,2,3 repeating
        (lbl_dir / f"img_{i:03d}.txt").write_text(
            f"{cls} 0.5 0.5 0.2 0.2\n",
            encoding="utf-8",
        )


def test_split_and_remap_end_to_end(tmp_path):
    mod = _load_module()

    src = tmp_path / "src"
    dst = tmp_path / "dst"
    _write_sample_dataset(src, count=10)

    mod.run(
        src=src,
        dst=dst,
        mapping={0: 0, 1: 0, 2: 1, 3: 2},
        ratios=(0.8, 0.1, 0.1),
        seed=7,
        action="copy",
        unmapped="error",
        strict_lines=True,
        create_empty_labels=True,
        images_subdir="images",
        labels_subdir="labels",
    )

    assert len(list((dst / "images" / "train").glob("*.jpg"))) == 8
    assert len(list((dst / "images" / "val").glob("*.jpg"))) == 1
    assert len(list((dst / "images" / "test").glob("*.jpg"))) == 1

    all_labels = list((dst / "labels").rglob("*.txt"))
    assert len(all_labels) == 10
    for label_path in all_labels:
        txt = label_path.read_text(encoding="utf-8").strip()
        if not txt:
            continue
        cls = int(txt.split()[0])
        assert cls in {0, 1, 2}


def test_parse_mapping_and_ratios():
    mod = _load_module()

    mapping = mod.parse_mapping("0:0,1:0,2:1,3:2")
    assert mapping == {0: 0, 1: 0, 2: 1, 3: 2}

    ratios = mod.parse_ratios("80,10,10")
    assert abs(sum(ratios) - 1.0) < 1e-9
    assert ratios[0] > ratios[1] > 0

