# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""X-CLIP exports are self-contained without real weights or conversion."""

import json
from pathlib import Path
import runpy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import config
from core.multimodal import registry
from inference.multimodal.xclip_openvino import find_ir_dir


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "xclip" / "convert.py"


@pytest.fixture
def converter(monkeypatch):
    namespace = runpy.run_path(str(SCRIPT))
    model = Mock()
    model.config = SimpleNamespace(
        vision_config=SimpleNamespace(num_frames=32, image_size=2),
        text_config=SimpleNamespace(max_position_embeddings=4),
    )
    load = Mock(return_value=model)
    monkeypatch.setattr(namespace["XCLIPModel"], "from_pretrained", load)
    monkeypatch.setattr(namespace["ov"], "convert_model", Mock(return_value=object()))
    saved = []

    def save(model, path, *, compress_to_fp16):
        saved.append((path, compress_to_fp16))
        Path(path).write_text("<xml/>")
        Path(path).with_suffix(".bin").touch()

    monkeypatch.setattr(namespace["ov"], "save_model", save)
    return SimpleNamespace(convert=namespace["convert"], load=load, saved=saved)


def _checkpoint(path, *, fast_tokenizer=True):
    path.mkdir()
    files = {
        "config.json": json.dumps({"model_type": "xclip", "vision_config": {"num_frames": 32}}),
        "tokenizer_config.json": '{"tokenizer_class":"CLIPTokenizer"}',
        "special_tokens_map.json": '{}',
        "added_tokens.json": '{}',
        "preprocessor_config.json": '{"image_mean":[0.485,0.456,0.406]}',
    }
    if fast_tokenizer:
        files["tokenizer.json"] = '{}'
    else:
        files.update({"vocab.json": '{}', "merges.txt": '#version: 0.2\n'})
    for name, content in files.items():
        (path / name).write_text(content)
    (path / "model.safetensors").touch()
    return files


@pytest.mark.parametrize("precision", ["fp32", "fp16"])
@pytest.mark.parametrize("explicit_output", [False, True])
@pytest.mark.parametrize("fast_tokenizer", [False, True])
def test_conversion_output_is_an_independent_package(
    tmp_path, monkeypatch, converter, precision, explicit_output, fast_tokenizer,
):
    checkpoint = tmp_path / "checkpoint"
    files = _checkpoint(checkpoint, fast_tokenizer=fast_tokenizer)
    output = tmp_path / f"video-{precision}" if explicit_output else checkpoint / "openvino" / precision
    converter.convert(str(checkpoint), str(output) if explicit_output else None, precision=precision)

    assert len(converter.saved) == 2
    assert all(compressed == (precision == "fp16") for _, compressed in converter.saved)
    assert converter.load.call_args.kwargs["local_files_only"] is True
    assert not (output / "model.safetensors").exists()
    for name, content in files.items():
        assert (output / name).read_text() == content
        assert (checkpoint / name).read_text() == content
    assert find_ir_dir(str(output)) == str(output)
    model = registry.lookup(None, str(output))
    assert model.name == "xclip" and model.is_ready(output)
    if explicit_output:
        monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
        resolved = registry.resolve({"asset_types": ["video"], "embedding_model": output.name})
        assert resolved.model_id == resolved.model_path == output.name


@pytest.mark.parametrize("missing", ["config.json", "tokenizer_config.json", "tokenizer.json"])
def test_missing_local_assets_fail_before_conversion(tmp_path, converter, missing):
    checkpoint = tmp_path / "checkpoint"
    _checkpoint(checkpoint)
    (checkpoint / missing).unlink()
    output = tmp_path / "output"

    with pytest.raises(FileNotFoundError, match=missing):
        converter.convert(str(checkpoint), str(output))

    converter.load.assert_not_called()
    assert converter.saved == []
    assert not output.exists()


def test_exporting_into_checkpoint_keeps_existing_metadata(tmp_path, converter):
    checkpoint = tmp_path / "checkpoint"
    files = _checkpoint(checkpoint)

    converter.convert(str(checkpoint), str(checkpoint), precision="fp16")

    for name, content in files.items():
        assert (checkpoint / name).read_text() == content
    assert registry.lookup(None, str(checkpoint)).is_ready(checkpoint)


def test_frame_mismatch_fails_before_writing_package(tmp_path, converter):
    checkpoint = tmp_path / "checkpoint"
    _checkpoint(checkpoint)
    output = tmp_path / "output"

    with pytest.raises(ValueError, match="expects 32 frames"):
        converter.convert(str(checkpoint), str(output), frames=16)

    assert converter.saved == []
    assert not output.exists()