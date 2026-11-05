# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Runtime models are local, already exported, and never fetched on first use."""

import ast
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

import config
from core import embedding, layout, postprocessor
from core.multimodal import asr, registry
from inference import ov_adapter
from inference.multimodal import xclip_openvino


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("backend", ["llamaindex_openvino", "openvino_genai"])
@pytest.mark.parametrize("kind", ["embedding", "reranker"])
@pytest.mark.parametrize("incomplete", [False, True])
def test_missing_or_incomplete_openvino_models_fail_before_loading(
    tmp_path, backend, kind, incomplete
):
    model_path = tmp_path / "unprepared"
    if incomplete:
        model_path.mkdir()
        (model_path / "openvino_model.xml").touch()

    with pytest.raises(FileNotFoundError, match="[Pp]repare"):
        if kind == "embedding":
            embedding._build(backend, "remote/model", str(model_path), "CPU", "")
        else:
            postprocessor._build(backend, 3, "remote/model", str(model_path), "CPU", "")
    assert not model_path.exists() or sorted(path.name for path in model_path.iterdir()) == [
        "openvino_model.xml"
    ]


def _prepared_model(path):
    path.mkdir()
    for name in ("openvino_model.xml", "openvino_model.bin"):
        (path / name).touch()
    return str(path)


def test_prepared_embedding_uses_the_local_adapter_without_export(tmp_path, monkeypatch):
    path = _prepared_model(tmp_path / "embedding")
    monkeypatch.setattr(ov_adapter, "serialized_openvino_embedding", lambda **options: options)

    options = embedding._build("llamaindex_openvino", "remote/model", path, "CPU", "")

    assert options["model_id_or_path"] == path
    assert options["model_kwargs"]["local_files_only"] is True
    assert options["model_kwargs"]["export"] is False


def test_serialized_embedding_injects_a_local_only_tokenizer(tmp_path, monkeypatch):
    path = _prepared_model(tmp_path / "embedding")
    calls = []
    tokenizer = object()
    module = ModuleType("transformers")
    module.AutoTokenizer = SimpleNamespace(
        from_pretrained=lambda path, **options: calls.append((path, options)) or tokenizer
    )
    monkeypatch.setitem(sys.modules, "transformers", module)
    monkeypatch.setattr(ov_adapter, "_serialized_openvino_embedding_class", lambda: lambda **options: options)

    options = ov_adapter.serialized_openvino_embedding(
        model_id_or_path=path, model_kwargs={"export": True, "local_files_only": False}
    )

    assert calls == [(path, {"local_files_only": True})]
    assert options["tokenizer"] is tokenizer
    assert options["model_kwargs"] == {"export": False, "local_files_only": True}


def test_prepared_reranker_disables_hub_access_and_export(tmp_path, monkeypatch):
    path = _prepared_model(tmp_path / "reranker")
    module = ModuleType("llama_index.postprocessor.openvino_rerank")
    module.OpenVINORerank = lambda **options: options
    monkeypatch.setitem(sys.modules, module.__name__, module)

    processor = postprocessor._build("llamaindex_openvino", 3, "remote/model", path, "CPU", "")

    assert processor.model["model_id_or_path"] == path
    assert processor.model["model_kwargs"]["local_files_only"] is True
    assert processor.model["model_kwargs"]["export"] is False


@pytest.mark.parametrize("family", ["xclip", "gme_qwen2vl"])
def test_missing_multimodal_model_is_never_prepared_by_the_registry(tmp_path, family):
    path = tmp_path / family
    with pytest.raises(FileNotFoundError, match="[Pp]repare"):
        registry.load({"name": family, "id": "remote/model", "path": str(path)}, {})
    assert not path.exists()


@pytest.mark.parametrize("asset_type, model_id", [
    ("video", "microsoft/xclip-base-patch16-zero-shot"),
    ("image", "Alibaba-NLP/gme-Qwen2-VL-2B-Instruct"),
    ("audio", "Alibaba-NLP/gme-Qwen2-VL-2B-Instruct"),
])
def test_asset_scoped_source_resolution_does_not_prepare_its_missing_model(
    tmp_path, monkeypatch, asset_type, model_id,
):
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
    path = tmp_path / model_id.rsplit("/", 1)[-1]
    options = {
        "asset_types": [asset_type], "embedding_model": model_id,
    }
    resolved = registry.resolve(options)

    assert resolved.params["asset_types"] == [asset_type]
    assert not path.exists(), "creating a source resolves its identity, not its artifacts"
    with pytest.raises(FileNotFoundError, match="[Pp]repare"):
        registry.load(resolved.record(), resolved.params)
    assert not path.exists()


@pytest.mark.parametrize("checkpoint", [False, True])
def test_whisper_requires_preexported_ir_instead_of_downloading_or_exporting(tmp_path, checkpoint):
    if checkpoint:
        (tmp_path / "config.json").write_text('{"model_type":"whisper"}')
    with pytest.raises(FileNotFoundError, match="[Pp]repare"):
        asr.WhisperOpenVINO(str(tmp_path), model_id="openai/whisper-small")
    assert not (tmp_path / "openvino").exists()


def test_asr_and_xclip_require_weights_as_well_as_xml(tmp_path):
    ir_dir = tmp_path / "openvino"
    ir_dir.mkdir()
    for name in (
        "openvino_encoder_model.xml", "openvino_decoder_model.xml",
        xclip_openvino.TEXT_IR, xclip_openvino.VIDEO_IR,
    ):
        (ir_dir / name).touch()

    assert asr.find_ir_dir(str(tmp_path)) is None
    assert xclip_openvino.find_ir_dir(str(tmp_path)) is None


def test_prepared_layout_is_reported_ready_without_export(tmp_path, monkeypatch):
    from inference import models

    model = tmp_path / "PP-DocLayoutV3"
    model.mkdir()
    Path(layout.pp_doclayout_v3_onnx_path(str(model))).touch()
    monkeypatch.setattr(models.config, "MODEL_DIR", str(tmp_path))

    assert models.workspace_models(models.LAYOUT) == [
        {"name": model.name, "path": str(model), "ready": True, "model_type": models.LAYOUT}
    ]


@pytest.mark.parametrize("backend", ["openvino", "torch"])
def test_layout_does_not_fetch_or_export_a_missing_model(tmp_path, backend):
    detector = layout._build(backend, "remote/layout", str(tmp_path / "missing"), "CPU", 0.3)
    with pytest.raises(FileNotFoundError, match="[Pp]repare"):
        detector._ensure_loaded()
    assert not (tmp_path / "missing").exists()


def test_whisper_loaders_are_explicitly_local_only(tmp_path, monkeypatch):
    ir_dir = tmp_path / "openvino"
    ir_dir.mkdir()
    for name in ("openvino_encoder_model", "openvino_decoder_model"):
        for suffix in ("xml", "bin"):
            (ir_dir / f"{name}.{suffix}").touch()
    calls = []

    def load(name):
        def from_pretrained(path, **options):
            calls.append((name, path, options))
            return SimpleNamespace(tokenizer=object(), feature_extractor=object())
        return SimpleNamespace(from_pretrained=from_pretrained)

    optimum = ModuleType("optimum.intel")
    optimum.OVModelForSpeechSeq2Seq = load("model")
    transformers = ModuleType("transformers")
    transformers.AutoProcessor = load("processor")
    transformers.pipeline = lambda *args, **options: object()
    monkeypatch.setitem(sys.modules, "optimum.intel", optimum)
    monkeypatch.setitem(sys.modules, "transformers", transformers)

    asr.WhisperOpenVINO(str(tmp_path))

    assert {name for name, _, _ in calls} == {"processor", "model"}
    assert all(path == str(ir_dir) and options["local_files_only"] for _, path, options in calls)
    assert next(options for name, _, options in calls if name == "model")["export"] is False


def test_xclip_tokenizer_is_loaded_only_from_the_prepared_local_directory(tmp_path, monkeypatch):
    calls = []
    module = ModuleType("transformers")
    module.AutoTokenizer = SimpleNamespace(
        from_pretrained=lambda path, **options: calls.append((path, options)) or object()
    )
    monkeypatch.setitem(sys.modules, "transformers", module)
    model = object.__new__(xclip_openvino.XClipOpenVinoEmbedding)
    model.model_path = str(tmp_path)
    model._tokenizer = None
    import threading
    model._tokenizer_lock = threading.Lock()

    assert model.tokenizer is model.tokenizer
    assert calls == [(str(tmp_path), {"local_files_only": True})]


def test_sentence_splitting_never_initializes_the_nltk_downloader(monkeypatch):
    from core.node_parser import build_node_parser
    from llama_index.core.utils import globals_helper
    from nltk.tokenize import PunktSentenceTokenizer
    from llama_index.core.node_parser.text.utils import split_by_sentence_tokenizer_internal

    def forbidden():
        raise AssertionError("runtime attempted to initialize the NLTK downloader")

    monkeypatch.setattr(globals_helper, "wait_for_nltk_check", forbidden)
    parser = build_node_parser(16, 0)
    text = "A person enters the room. Another person leaves. " * 30

    assert parser._chunking_tokenizer_fn(text) == split_by_sentence_tokenizer_internal(
        text, PunktSentenceTokenizer()
    )
    assert len(parser.split_text(text)) > 1


@pytest.mark.parametrize("content", [None, b"corrupt vocabulary"])
def test_missing_or_corrupt_token_count_cache_fails_without_downloading(tmp_path, monkeypatch, content):
    import hashlib
    import llama_index.core
    from core.node_parser import _local_tokenizer
    from llama_index.core import utils

    monkeypatch.setattr(llama_index.core, "global_tokenizer", None)
    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", str(tmp_path))
    key = hashlib.sha1(
        b"https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken"
    ).hexdigest()
    if content is not None:
        (tmp_path / key).write_bytes(content)

    def forbidden():
        raise AssertionError("tokenizer loader reached its download fallback")

    monkeypatch.setattr(utils, "get_tokenizer", forbidden)
    with pytest.raises(FileNotFoundError, match="[Pp]repare"):
        _local_tokenizer()


def test_runtime_source_contains_no_model_download_or_export_fallbacks():
    forbidden = {
        "snapshot_download", "hf_hub_download", "create_and_save_openvino_model",
        "export_pp_doclayout_v3", "save_pretrained",
    }
    for path in (ROOT / "src").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                assert name not in forbidden, f"{path}: runtime call to {name}"
                if name == "from_pretrained":
                    options = {keyword.arg: keyword.value for keyword in node.keywords}
                    assert isinstance(options.get("local_files_only"), ast.Constant), str(path)
                    assert options["local_files_only"].value is True, str(path)
                    assert not (isinstance(options.get("export"), ast.Constant) and options["export"].value), str(path)