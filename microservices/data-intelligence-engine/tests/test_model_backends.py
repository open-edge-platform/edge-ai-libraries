# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# pyright: reportMissingImports=false

import json

import pytest

import config
from core import embedding
from inference import models
import core.postprocessor as postprocessor


@pytest.mark.parametrize(
    ("legacy", "canonical"),
    [
        ("openvino", "llamaindex_openvino"),
        ("openai", "openai_compatible"),
        ("gme", "native_openvino_gme"),
    ],
)
def test_legacy_model_backend_names_are_normalized(legacy, canonical):
    assert config.normalize_model_backend(legacy) == canonical


def test_embedding_and_reranker_report_one_shared_backend_list(monkeypatch):
    def no_workspace_models(model_type=None):
        del model_type
        return []

    monkeypatch.setattr(models, "workspace_models", no_workspace_models)

    embedding = models.model_options(models.EMBEDDING)
    reranker = models.model_options(models.RERANKER)

    assert embedding["backends"] == list(config.MODEL_BACKENDS)
    assert reranker["backends"] == list(config.MODEL_BACKENDS)


def test_layout_reports_its_own_backend_list(monkeypatch):
    monkeypatch.setattr(models, "workspace_models", lambda model_type=None: [])

    layout = models.model_options(models.LAYOUT)

    assert layout["backend"] == config.LAYOUT_BACKEND
    assert layout["backends"] == list(config.LAYOUT_BACKENDS)
    assert layout["model_id"] == config.LAYOUT_MODEL_ID


def test_workspace_scan_separates_layout_and_ocr_from_embeddings(tmp_path):
    layout_dir = tmp_path / "detector"
    layout_dir.mkdir()
    (layout_dir / "config.json").write_text(
        json.dumps({"model_type": "pp_doclayout_v3"}), encoding="utf-8"
    )
    (tmp_path / "tesseract-ocr").mkdir()

    found = {entry["name"]: entry["model_type"] for entry in models._scan(str(tmp_path))}

    assert found == {
        "tesseract-ocr": models.OCR,
        "detector": models.LAYOUT,
    }


def test_workspace_scan_reports_complete_gme_package_ready(tmp_path, monkeypatch):
    model_dir = tmp_path / "gme-Qwen2-VL-2B-Instruct-OV"
    model_dir.mkdir()
    (model_dir / "gme_openvino_config.json").write_text(
        json.dumps(
            {
                "tokenizer_model": "openvino_tokenizer.xml",
                "precisions": {
                    "int8": {
                        "language": "gme_language_int8.xml",
                        "visual": "gme_visual_int8.xml",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    for name in (
        "openvino_tokenizer.xml",
        "gme_language_int8.xml",
        "gme_language_int8.bin",
        "gme_visual_int8.xml",
        "gme_visual_int8.bin",
    ):
        (model_dir / name).touch()

    found = models._scan(str(tmp_path))

    assert found == [
        {
            "name": "gme-Qwen2-VL-2B-Instruct-OV",
            "path": str(model_dir),
            "ready": True,
            "model_type": kind,
        }
        for kind in (models.EMBEDDING, models.MULTIMODAL)
    ]


@pytest.mark.parametrize("tokenizer_files,ready", [
    (("tokenizer.json",), True),
    (("vocab.json", "merges.txt"), True),
    ((), False),
])
def test_a_gme_package_as_exported_for_the_python_runtime_is_ready(tmp_path, tokenizer_files, ready):
    """export_gme_ov.py writes the Hugging Face processor files the Python
    runtime loads, and no tokenizer IR; that package is complete."""
    model_dir = tmp_path / "gme-Qwen2-VL-2B-Instruct-OV"
    model_dir.mkdir()
    (model_dir / "gme_openvino_config.json").write_text(json.dumps({
        "precisions": {"int8": {"language": "gme_language_int8.xml", "visual": "gme_visual_int8.xml"}},
        "default_precision": "int8",
    }), encoding="utf-8")
    for name in ("gme_language_int8.xml", "gme_language_int8.bin", "gme_visual_int8.xml",
                 "gme_visual_int8.bin", "preprocessor_config.json", *tokenizer_files):
        (model_dir / name).touch()

    assert {entry["ready"] for entry in models._scan(str(tmp_path))} == {ready}


@pytest.mark.parametrize(
    ("configured", "canonical"),
    [
        ("openvino", "llamaindex_openvino"),
        ("openai", "openai_compatible"),
        ("gme", "native_openvino_gme"),
        ("openvino_genai", "openvino_genai"),
    ],
)
def test_embedding_dispatches_with_canonical_name(
    monkeypatch, configured, canonical
):
    def capture_backend(backend, *configuration):
        del configuration
        return backend

    monkeypatch.setattr(embedding, "_CACHE", embedding.ModelCache())
    monkeypatch.setattr(embedding, "_build", capture_backend)

    assert embedding.build_embedding(
        backend=configured, model_id=f"test-{configured}"
    ) == canonical


def test_gme_provider_is_rejected_only_when_building_a_reranker():
    assert "native_openvino_gme" in config.MODEL_BACKENDS

    with pytest.raises(ValueError, match="no factory implementation"):
        postprocessor._build(
            "native_openvino_gme", 3, "gme", "gme", "CPU", ""
        )


def _gme_package(model_dir, shipped, default="int4"):
    """A package whose config lists every precision but ships only `shipped`."""
    model_dir.mkdir()
    metadata = {
        "default_precision": default,
        "precisions": {
            name: {"language": f"gme_language_{name}.xml", "visual": f"gme_visual_{name}.xml"}
            for name in ("fp32", "int8", "int4")
        },
    }
    for name in shipped:
        for part in ("language", "visual"):
            for suffix in ("xml", "bin"):
                (model_dir / f"gme_{part}_{name}.{suffix}").touch()
    return metadata


@pytest.mark.parametrize(
    ("shipped", "expected"),
    [(["int8"], "int8"), (["fp32"], "fp32"), (["fp32", "int8", "int4"], "int4")],
)
def test_gme_precision_is_the_one_the_package_ships(tmp_path, shipped, expected):
    runtime = pytest.importorskip("inference.gme_runtime", exc_type=ImportError)
    metadata = _gme_package(tmp_path / "gme", shipped)

    precision, language, visual = runtime.package_ir_files(tmp_path / "gme", metadata)

    assert precision == expected
    assert (language, visual) == (f"gme_language_{expected}.xml", f"gme_visual_{expected}.xml")


@pytest.mark.parametrize(("shipped", "error"), [([], FileNotFoundError), (["fp32", "int8"], ValueError)])
def test_gme_precision_must_be_unambiguous(tmp_path, shipped, error):
    runtime = pytest.importorskip("inference.gme_runtime", exc_type=ImportError)
    metadata = _gme_package(tmp_path / "gme", shipped)

    with pytest.raises(error):
        runtime.package_ir_files(tmp_path / "gme", metadata)


def test_genai_options_are_parsed_from_the_model_directory(tmp_path, monkeypatch):
    from inference import ov_adapter

    monkeypatch.setattr(ov_adapter, "OpenVINOGenAIEmbedding", lambda **options: options)
    model_dir = tmp_path / "dense"
    (model_dir / "1_Pooling").mkdir(parents=True)
    (model_dir / "tokenizer_config.json").write_text(json.dumps({"model_max_length": 256}))
    (model_dir / "1_Pooling" / "config.json").write_text(json.dumps({"pooling_mode_mean_tokens": True}))
    for name in ("openvino_model.xml", "openvino_model.bin"):
        (model_dir / name).touch()

    options = embedding._build("openvino_genai", "dense", str(model_dir), "CPU", "")

    assert (options["max_length"], options["pooling"]) == (256, "mean")


def test_genai_input_length_is_capped_and_pooling_defaults_to_cls(tmp_path):
    (tmp_path / "tokenizer_config.json").write_text(json.dumps({"model_max_length": 8192}))

    assert config.embedding_max_length(str(tmp_path)) == config.EMBEDDING_MAX_LENGTH
    assert config.embedding_pooling(str(tmp_path)) == "cls"
