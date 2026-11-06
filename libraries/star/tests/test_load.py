# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
import random

import pytest

from semantic_img_comp.utils.load import load_paths
from semantic_img_comp.utils.load import load_paths_with_context


def _make_image(path: Path) -> None:
    path.write_bytes(b"fake")


def test_load_paths_from_catalog_supports_population_proportional_mixing(tmp_path: Path):
    dir_a = tmp_path / "dir_a"
    dir_b = tmp_path / "dir_b"
    dir_a.mkdir()
    dir_b.mkdir()

    for idx in range(3):
        _make_image(dir_a / f"a_{idx}.jpg")
    _make_image(dir_b / "b_0.jpg")

    catalog_path = tmp_path / "inputs.yaml"
    catalog_path.write_text(
        f"""
input_dirs:
  - {dir_a.as_posix()}
  - {dir_b.as_posix()}
random_seed: 7
""".strip(),
        encoding="utf-8",
    )

    paths = load_paths(catalog_path)

    assert len(paths) == 4
    assert sum(1 for p in paths if p.parent == dir_a) == 3
    assert sum(1 for p in paths if p.parent == dir_b) == 1


def test_load_paths_from_catalog_same_seed_produces_same_order(tmp_path: Path):
    dir_a = tmp_path / "dir_a"
    dir_b = tmp_path / "dir_b"
    dir_a.mkdir()
    dir_b.mkdir()

    for idx in range(3):
        _make_image(dir_a / f"a_{idx}.jpg")
        _make_image(dir_b / f"b_{idx}.jpg")

    catalog_path = tmp_path / "inputs.yaml"
    catalog_path.write_text(
        f"""
input_dirs:
  - {dir_a.as_posix()}
  - {dir_b.as_posix()}
random_seed: 11
""".strip(),
        encoding="utf-8",
    )

    first = load_paths(catalog_path)
    second = load_paths(catalog_path)

    assert first == second


def test_load_paths_with_context_reports_catalog_seed(tmp_path: Path):
    dir_a = tmp_path / "dir_a"
    dir_b = tmp_path / "dir_b"
    dir_a.mkdir()
    dir_b.mkdir()
    _make_image(dir_a / "a_0.jpg")
    _make_image(dir_b / "b_0.jpg")

    catalog_path = tmp_path / "inputs.yaml"
    catalog_path.write_text(
        f"""
input_dirs:
  - {dir_a.as_posix()}
  - {dir_b.as_posix()}
random_seed: 17
""".strip(),
        encoding="utf-8",
    )

    paths, ctx = load_paths_with_context(catalog_path)

    assert len(paths) == 2
    assert ctx == {
        "source_type": "catalog",
        "catalog_random_seed": 17,
        "catalog_sampling_mode": "uniform",
    }


def test_load_paths_catalog_defaults_to_uniform_sampling(tmp_path: Path, monkeypatch):
    dir_a = tmp_path / "dir_a"
    dir_b = tmp_path / "dir_b"
    dir_a.mkdir()
    dir_b.mkdir()
    for idx in range(3):
        _make_image(dir_a / f"a_{idx}.jpg")
    _make_image(dir_b / "b_0.jpg")

    catalog_path = tmp_path / "inputs.yaml"
    catalog_path.write_text(
        f"""
input_dirs:
  - {dir_a.as_posix()}
  - {dir_b.as_posix()}
random_seed: 7
""".strip(),
        encoding="utf-8",
    )

    weights_seen = []
    original_choices = random.Random.choices

    def _spy_choices(self, population, weights=None, k=1):
        weights_seen.append(tuple(weights) if weights is not None else None)
        return original_choices(self, population, weights=weights, k=k)

    monkeypatch.setattr(random.Random, "choices", _spy_choices)

    load_paths(catalog_path)

    assert (1, 1) in weights_seen


def test_load_paths_catalog_supports_proportional_sampling_mode(tmp_path: Path, monkeypatch):
    dir_a = tmp_path / "dir_a"
    dir_b = tmp_path / "dir_b"
    dir_a.mkdir()
    dir_b.mkdir()
    for idx in range(3):
        _make_image(dir_a / f"a_{idx}.jpg")
    _make_image(dir_b / "b_0.jpg")

    catalog_path = tmp_path / "inputs.yaml"
    catalog_path.write_text(
        f"""
input_dirs:
  - {dir_a.as_posix()}
  - {dir_b.as_posix()}
random_seed: 7
""".strip(),
        encoding="utf-8",
    )

    weights_seen = []
    original_choices = random.Random.choices

    def _spy_choices(self, population, weights=None, k=1):
        weights_seen.append(tuple(weights) if weights is not None else None)
        return original_choices(self, population, weights=weights, k=k)

    monkeypatch.setattr(random.Random, "choices", _spy_choices)

    load_paths(catalog_path, catalog_sampling_mode="proportional")

    assert (3, 1) in weights_seen


def test_load_paths_catalog_rejects_invalid_sampling_mode(tmp_path: Path):
    dir_a = tmp_path / "dir_a"
    dir_a.mkdir()
    _make_image(dir_a / "a_0.jpg")

    catalog_path = tmp_path / "inputs.yaml"
    catalog_path.write_text(
        f"""
input_dirs:
  - {dir_a.as_posix()}
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="sampling mode"):
        load_paths(catalog_path, catalog_sampling_mode="by_size")


def test_load_paths_from_catalog_supports_relative_dirs(tmp_path: Path):
    inputs_root = tmp_path / "inputs"
    inputs_root.mkdir()
    dir_a = inputs_root / "a"
    dir_b = inputs_root / "b"
    dir_a.mkdir()
    dir_b.mkdir()

    _make_image(dir_a / "a_0.png")
    _make_image(dir_b / "b_0.jpeg")

    catalog_path = tmp_path / "inputs.yaml"
    catalog_path.write_text(
        """
input_dirs:
  - ./inputs/a
  - ./inputs/b
""".strip(),
        encoding="utf-8",
    )

    paths = load_paths(catalog_path)

    assert {p.parent for p in paths} == {dir_a.resolve(), dir_b.resolve()}


def test_load_paths_from_catalog_rejects_missing_input_dirs_key(tmp_path: Path):
    catalog_path = tmp_path / "inputs.yaml"
    catalog_path.write_text("random_seed: 1", encoding="utf-8")

    with pytest.raises(ValueError, match="input_dirs"):
        load_paths(catalog_path)

