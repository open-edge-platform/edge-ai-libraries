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
    "legacy",
    ["openvino", "openai", "gme", "llamaindex_openvino", "openvino_genai",
     "openai_compatible", "native_openvino_gme", "openvino_vl"],
)
def test_legacy_model_backend_names_are_rejected(legacy):
    with pytest.raises(ValueError, match="model backend must be one of"):
        config.normalize_model_backend(legacy)


@pytest.mark.parametrize("backend", config.MODEL_BACKENDS)
def test_canonical_model_backend_names_are_accepted(backend):
    assert config.normalize_model_backend(backend.upper()) == backend


def test_reranker_reports_media_defaults(monkeypatch):
    def no_workspace_models(model_type=None):
        del model_type
        return []

    monkeypatch.setattr(models, "workspace_models", no_workspace_models)

    embedding = models.model_options(models.EMBEDDING)
    reranker = models.model_options(models.RERANKER)

    assert embedding["backends"] == list(config.MODEL_BACKENDS)
    assert reranker["backends"] == list(config.MODEL_BACKENDS)
    from schemas import ModelOptions
    response = ModelOptions(**reranker).model_dump()
    expected_models = [] if config.RERANK_BACKEND == config.LOCAL_OPENVINO else [{
        "name": config.RERANK_MODEL_ID, "path": config.RERANK_API_BASE,
        "ready": True, "model_type": models.RERANKER,
    }]
    assert reranker == {
        "model_type": models.RERANKER,
        "backend": config.RERANK_BACKEND,
        "backends": list(config.MODEL_BACKENDS),
        "device": config.RERANK_DEVICE,
        "model_id": config.RERANK_MODEL_ID,
        "media_model_id": config.MEDIA_RERANK_MODEL_ID,
        "media_backend": config.MEDIA_RERANK_BACKEND,
        "media_device": config.MEDIA_RERANK_DEVICE,
        "api_base": config.RERANK_API_BASE,
        "workspace": config.MODEL_DIR,
        "models": expected_models,
    }
    assert response == {
        **reranker, "models": [{**model, "media": False} for model in expected_models],
    }


def test_layout_reports_its_own_backend_list(monkeypatch):
    monkeypatch.setattr(models, "workspace_models", lambda model_type=None: [])

    layout = models.model_options(models.LAYOUT)

    assert layout["backend"] == config.LAYOUT_BACKEND
    assert layout["backends"] == [config.LOCAL_OPENVINO]
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


@pytest.mark.parametrize("nested", (False, True))
@pytest.mark.parametrize("name, kind, kinds, asset_types", (
    ("unrecognized-package", models.EMBEDDING, ["text"], ["document"]),
    ("unrecognized-reranker", models.RERANKER, ["text"], ["audio", "document"]),
    ("unrecognized-layout", models.LAYOUT, ["image"], ["document", "image"]),
    ("unrecognized-ocr", models.OCR, [], []),
))
def test_unprepared_scan_retains_only_type_capabilities(
    tmp_path, nested, name, kind, kinds, asset_types,
):
    directory = tmp_path / "vendor" / name if nested else tmp_path / name
    directory.mkdir(parents=True)

    assert models._scan(str(tmp_path)) == [{
        "name": f"vendor/{name}" if nested else name,
        "path": str(directory), "ready": False, "model_type": kind,
        "supported_kinds": kinds, "supported_asset_types": asset_types, "supported_roles": [],
    }]


@pytest.mark.parametrize("artifacts, vl_ready", (
    ((), False), (("reranker_text.xml",), False),
    (("reranker_text.xml", "reranker_text.bin"), True),
))
def test_vl_capabilities_require_recognized_ir_not_a_model_id(tmp_path, artifacts, vl_ready):
    directory = tmp_path / "independent-reranker"
    directory.mkdir()
    for artifact in artifacts:
        (directory / artifact).touch()
    expected = {
        "name": directory.name, "path": str(directory), "ready": vl_ready,
        "model_type": models.RERANKER,
        "supported_kinds": ["image", "text", "video"] if vl_ready else ["text"],
        "supported_asset_types": ["audio", "document", "image", "video"] if vl_ready else ["audio", "document"],
        "supported_roles": [],
    }
    if vl_ready:
        expected["media"] = True

    assert models._scan(str(tmp_path)) == [expected]


def test_unknown_capability_type_does_not_invent_support():
    assert models._capabilities("future", media=True) == {
        "supported_kinds": [], "supported_asset_types": [], "supported_roles": [],
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
            "model_type": models.EMBEDDING,
            "supported_kinds": ["audio", "image", "text"],
            "supported_asset_types": ["audio", "document", "image"],
            "supported_roles": ["doc_image", "image", "l2_caption", "l2_transcript", "l3_wiki"],
        }
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


@pytest.mark.parametrize("canonical", config.MODEL_BACKENDS)
def test_embedding_dispatches_with_canonical_name(monkeypatch, canonical):
    configured = canonical
    def capture_backend(backend, *configuration):
        del configuration
        return backend

    monkeypatch.setattr(embedding, "_CACHE", embedding.ModelCache())
    monkeypatch.setattr(embedding, "_build", capture_backend)

    assert embedding.build_embedding(
        backend=configured, model_id=f"test-{configured}"
    ) == canonical


@pytest.mark.parametrize("legacy", ["native_openvino_gme", "openvino_genai", "openai_compatible"])
def test_legacy_backend_is_rejected_by_both_factories(legacy):
    with pytest.raises(ValueError, match="model backend must be one of"):
        embedding.build_embedding(backend=legacy, model_id="m")
    with pytest.raises(ValueError, match="model backend must be one of"):
        postprocessor.build_reranker(backend=legacy, model_id="m")


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

    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
    monkeypatch.setattr(ov_adapter, "OpenVINOGenAIEmbedding", lambda **options: options)
    model_dir = tmp_path / "dense"
    (model_dir / "1_Pooling").mkdir(parents=True)
    (model_dir / "tokenizer_config.json").write_text(json.dumps({"model_max_length": 256}))
    (model_dir / "1_Pooling" / "config.json").write_text(json.dumps({"pooling_mode_mean_tokens": True}))
    for name in ("openvino_model.xml", "openvino_model.bin"):
        (model_dir / name).touch()

    options = embedding._build(config.LOCAL_OPENVINO, "dense", "CPU", "")

    assert (options["max_length"], options["pooling"]) == (256, "mean")


def test_genai_input_length_is_capped_and_pooling_defaults_to_cls(tmp_path):
    (tmp_path / "tokenizer_config.json").write_text(json.dumps({"model_max_length": 8192}))

    assert config.embedding_max_length(str(tmp_path)) == config.EMBEDDING_MAX_LENGTH
    assert config.embedding_pooling(str(tmp_path)) == "cls"
