# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Finding an exported GME package, and which of its weights to load."""

import json

import pytest

from inference.multimodal.gme_qwen2vl import choose_precision, find_package

PRECISIONS = {
    name: {"language": f"gme_language_{name}.xml", "visual": f"gme_visual_{name}.xml"}
    for name in ("fp32", "int8", "int4")
}


def _package(path, shipped=("int8",), default="int4"):
    path.mkdir(parents=True)
    (path / "gme_openvino_config.json").write_text(
        json.dumps({"precisions": PRECISIONS, "default_precision": default, "embedding_dim": 1536})
    )
    for name in shipped:
        for part in ("language", "visual"):
            ir = path / PRECISIONS[name][part]
            ir.write_text("")
            ir.with_suffix(".bin").write_bytes(b"")
    return path


def test_a_package_unpacked_one_level_down_is_found(tmp_path):
    inner = _package(tmp_path / "gme-OV" / "gme-OV")
    assert find_package(str(tmp_path / "gme-OV")) == inner


def test_a_directory_without_a_package_is_refused_by_path(tmp_path):
    with pytest.raises(FileNotFoundError, match=str(tmp_path)):
        find_package(str(tmp_path))


def test_a_default_whose_weights_are_missing_falls_back_to_what_is_there(tmp_path):
    package = _package(tmp_path / "p", shipped=("int8",), default="int4")
    assert choose_precision(package) == "int8"


def test_the_default_is_used_when_it_is_there(tmp_path):
    package = _package(tmp_path / "p", shipped=("int8", "int4"), default="int4")
    assert choose_precision(package) == "int4"


def test_a_runtime_precision_override_is_not_an_adapter_input(tmp_path):
    package = _package(tmp_path / "p", shipped=("int8",))
    with pytest.raises(TypeError):
        choose_precision(package, "fp32")


def test_xml_without_weights_does_not_count_as_a_shipped_precision(tmp_path):
    package = _package(tmp_path / "p", shipped=("int8",))
    (package / "gme_language_int8.bin").unlink()

    with pytest.raises(FileNotFoundError, match="no complete"):
        choose_precision(package)


def test_multiple_precisions_without_the_default_remain_ambiguous(tmp_path):
    package = _package(tmp_path / "p", shipped=("fp32", "int8"), default="int4")

    with pytest.raises(ValueError, match="default_precision"):
        choose_precision(package)
