# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""G13--G16/G18 integration without real models, downloads or running services."""

import ast
import gc
import json
import os
import runpy
import threading
import weakref
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pytest
import yaml

import config
from core import embedding
from core.multimodal import registry
from core.multimodal import embeddings as media_embeddings
from inference import gme_runtime, models
from inference.multimodal.gme_qwen2vl import GmeQwen2VLEmbedding


ROOT = Path(__file__).resolve().parents[1]
GME_ID = "Alibaba-NLP/gme-Qwen2-VL-2B-Instruct"
XCLIP_ID = "microsoft/xclip-base-patch16-zero-shot"


def _package(path):
    path.mkdir(parents=True)
    metadata = {
        "embedding_dim": 1536,
        "default_precision": "int8",
        "precisions": {
            "int8": {"language": "language.xml", "visual": "visual.xml"},
        },
        "processor": {
            "min_image_tokens": 4, "max_image_tokens": 1024,
            "max_length": 1800, "padding_side": "right",
        },
    }
    (path / "gme_openvino_config.json").write_text(json.dumps(metadata))
    # What export_gme_ov.py writes: the IR pairs and the Hugging Face processor
    # files the Python runtime tokenizes with (no tokenizer IR).
    for name in ("language.xml", "language.bin", "visual.xml", "visual.bin",
                 "tokenizer.json", "preprocessor_config.json"):
        (path / name).touch()
    return path


@pytest.fixture
def fake_runtime(monkeypatch):
    built = []

    class FakeRuntime:
        def __init__(self, model_dir, device, precision, **options):
            self.model_dir = Path(model_dir)
            self.device = device
            self.precision = precision
            self.embedding_dim = 1536
            self.calls = []
            self.options = options
            built.append(self)

        def _vectors(self, method, values, **options):
            self.calls.append((method, list(values), options))
            return np.asarray([[0.6, 0.8]] * len(values))

        def get_text_embeddings(self, texts, **options):
            return self._vectors("text", texts, **options)

        def get_image_embeddings(self, images, **options):
            return self._vectors("image", images, **options)

        def get_fused_embeddings(self, texts, images, **options):
            return self._vectors("fused", texts, images=list(images), **options)

    monkeypatch.setattr(gme_runtime, "GmeOpenVINO", FakeRuntime)
    monkeypatch.setattr(embedding, "_CACHE", embedding.ModelCache())
    monkeypatch.setattr(embedding, "_GME_RUNTIMES", embedding.ModelCache())
    monkeypatch.setattr(media_embeddings, "_CACHE", embedding.ModelCache())
    return built


@pytest.mark.parametrize("media_first", [False, True])
def test_g13_main_and_registry_share_runtime_identity(tmp_path, monkeypatch, fake_runtime, media_first):
    package = _package(tmp_path / "package")
    alias = tmp_path / "alias"
    alias.symlink_to(package, target_is_directory=True)
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
    record = {"name": "gme_qwen2vl", "id": GME_ID, "path": "alias"}

    def text_model():
        return embedding.build_embedding(
            backend="native_openvino_gme", model_path=str(package), device="CPU"
        )

    def media_model():
        return media_embeddings.build_multimodal_embedding(
            record, {"embedding_device": "cpu"}
        )

    if media_first:
        media, text = media_model(), text_model()
    else:
        text, media = text_model(), media_model()

    assert text._runtime is media._runtime is fake_runtime[0]
    assert len(fake_runtime) == 1
    assert fake_runtime[0].model_dir == package.resolve()
    assert text.get_query_embedding("query") == [0.6, 0.8]
    assert text.get_text_embedding("document") == [0.6, 0.8]
    assert text.get_fused_embeddings(["caption"], ["image"]) == [[0.6, 0.8]]
    assert media.embed_text(["query"]) == [[0.6, 0.8]]
    assert media.embed_documents(["transcript"]) == [[0.6, 0.8]]
    assert media.embed_image(["image"]) == [[0.6, 0.8]]
    assert [call[2]["is_query"] for call in fake_runtime[0].calls] == [
        True, False, False, True, False, False
    ]


def test_g13_concurrent_builds_compile_once_per_canonical_path_device(tmp_path, fake_runtime):
    package = _package(tmp_path / "package")
    barrier = threading.Barrier(8, timeout=5)

    def build(_):
        barrier.wait()
        return embedding.build_gme_runtime(str(package), "CPU")

    with ThreadPoolExecutor(8) as pool:
        runtimes = list(pool.map(build, range(8)))

    assert all(runtime is runtimes[0] for runtime in runtimes)
    assert len(fake_runtime) == 1
    other_device = embedding.build_gme_runtime(str(package), "GPU")
    assert other_device is not runtimes[0]
    assert len(fake_runtime) == 2


def test_g13_shared_runtime_rejects_conflicting_processor_settings(tmp_path, fake_runtime):
    package = _package(tmp_path / "package")
    runtime = embedding.build_gme_runtime(str(package), "CPU")

    assert embedding.build_gme_runtime(
        str(package), "cpu", max_image_tokens=1024
    ) is runtime
    with pytest.raises(ValueError, match="already in use"):
        embedding.build_gme_runtime(str(package), "CPU", max_image_tokens=512)
    assert len(fake_runtime) == 1


def test_separate_prepared_model_ids_use_separate_runtimes(tmp_path, monkeypatch, fake_runtime):
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
    first = _package(tmp_path / "gme-int8")
    second = _package(tmp_path / "gme-int4")
    metadata = json.loads((second / "gme_openvino_config.json").read_text())
    metadata["default_precision"] = "int4"
    metadata["precisions"] = {"int4": metadata["precisions"]["int8"]}
    (second / "gme_openvino_config.json").write_text(json.dumps(metadata))
    adapters = []
    for package in (first, second):
        resolved = registry.resolve({"asset_types": ["image"], "embedding_model": package.name})
        adapters.append(registry.load(resolved.record(), resolved.params))

    assert adapters[0]._runtime is not adapters[1]._runtime
    assert [runtime.model_dir for runtime in fake_runtime] == [first, second]
    assert [runtime.precision for runtime in fake_runtime] == ["int8", "int4"]


def test_g13_runtime_cache_releases_after_both_adapters_are_dropped(tmp_path, fake_runtime):
    package = _package(tmp_path / "package")
    text = embedding.build_embedding(
        backend="native_openvino_gme", model_path=str(package), device="CPU"
    )
    media = GmeQwen2VLEmbedding(str(package))
    reference = weakref.ref(text._runtime)
    fake_runtime.clear()
    del text
    gc.collect()
    assert reference() is media._runtime
    del media
    gc.collect()

    assert reference() is None
    assert len(embedding._GME_RUNTIMES) == 0


def test_g13_runtime_serializes_preprocessing_not_just_infer_requests(monkeypatch):
    runtime = object.__new__(gme_runtime.GmeOpenVINO)
    runtime._lock = threading.Lock()
    entered = threading.Event()
    release = threading.Event()

    def encode(*args):
        assert runtime._lock.locked()
        entered.set()
        assert release.wait(timeout=5)
        return np.asarray([[1.0]])

    monkeypatch.setattr(runtime, "_embed", encode)
    with ThreadPoolExecutor(1) as pool:
        task = pool.submit(runtime.embed, ["text"])
        try:
            assert entered.wait(timeout=5)
            assert not runtime._lock.acquire(blocking=False)
        finally:
            release.set()
        assert task.result().tolist() == [[1.0]]


def test_g13_media_adapter_rejects_incorrect_declared_width(tmp_path, monkeypatch, fake_runtime):
    package = _package(tmp_path / "package")
    runtime = embedding.build_gme_runtime(str(package), "CPU")
    runtime.embedding_dim = 42

    with pytest.raises(ValueError, match="expected 1536"):
        GmeQwen2VLEmbedding(str(package))


def test_g15_embedding_cache_releases_unreferenced_models(monkeypatch):
    class Model:
        pass

    monkeypatch.setattr(embedding, "_CACHE", embedding.ModelCache())
    monkeypatch.setattr(embedding, "_build", lambda *args: Model())
    model = embedding.build_embedding(model_id="fake")
    assert embedding.build_embedding(model_id="fake") is model
    reference = weakref.ref(model)
    del model
    gc.collect()

    assert reference() is None
    assert len(embedding._CACHE) == 0


def test_g15_no_obsolete_embedding_module_or_imports():
    assert not (ROOT / "src/core/embeddings.py").exists()
    for relative in (
        "core/embedding.py", "inference/models.py", "core/multimodal/registry.py",
        "inference/multimodal/gme_qwen2vl.py",
    ):
        path = ROOT / "src" / relative
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.module != "core.embeddings", str(path)
            elif isinstance(node, ast.Import):
                assert all(alias.name != "core.embeddings" for alias in node.names), str(path)


def test_g14_all_model_options_expose_gme_in_both_pickers_only(tmp_path, monkeypatch):
    _package(tmp_path / "gme")
    xclip = tmp_path / "xclip"
    xclip.mkdir()
    (xclip / "config.json").write_text('{"model_type": "xclip"}')
    whisper = tmp_path / "whisper"
    whisper.mkdir()
    (whisper / "config.json").write_text('{"model_type": "whisper"}')
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
    monkeypatch.setattr(config, "EMBEDDING_BACKEND", "native_openvino_gme")
    options = models.all_model_options()
    names = {
        kind: [entry["name"] for entry in option["models"]]
        for kind, option in options.items()
    }

    assert names[models.EMBEDDING] == ["gme"]
    assert names[models.MULTIMODAL] == ["gme", "xclip"]
    assert names[models.ASR] == ["whisper"]
    assert models.LAYOUT in options
    assert options[models.ASR]["backends"] == ["openvino"]
    assert all(entry["ready"] for entry in options[models.EMBEDDING]["models"])


def test_g14_incomplete_gme_is_listed_in_both_pickers_but_not_ready(tmp_path, monkeypatch):
    package = _package(tmp_path / "gme")
    (package / "visual.bin").unlink()
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))

    entries = models.workspace_models()

    assert {entry["model_type"] for entry in entries} == {models.EMBEDDING, models.MULTIMODAL}
    assert not any(entry["ready"] for entry in entries)
    assert registry.lookup(None, str(package)).is_ready(package) is False


@pytest.mark.parametrize("model_id,asset_type", [(GME_ID, "image"), (XCLIP_ID, "video")])
@pytest.mark.parametrize("backend", ["openvino", "llamaindex_openvino"])
def test_g18_registry_accepts_alias_and_main_canonical_backend(model_id, asset_type, backend):
    resolved = registry.resolve({
        "asset_types": [asset_type], "embedding_model": model_id, "embedding_backend": backend,
    })

    assert resolved.backend == "llamaindex_openvino"
    assert resolved.model_id == model_id
    assert resolved.params["asset_types"] == [asset_type]


def test_g18_registry_accepts_native_gme_for_image_assets():
    resolved = registry.resolve({
        "asset_types": ["image"], "embedding_model": GME_ID,
        "embedding_backend": "native_openvino_gme",
    })

    assert resolved.backend == "native_openvino_gme"
    assert resolved.model.name == "gme_qwen2vl"
    assert resolved.params == {
        "asset_types": ["image"], "block_kinds": ["image"], "block_roles": ["image"],
    }


def test_g18_registry_still_rejects_native_gme_for_xclip():
    with pytest.raises(ValueError, match="runs on"):
        registry.resolve({
            "asset_types": ["video"], "embedding_model": XCLIP_ID,
            "embedding_backend": "native_openvino_gme",
        })


@pytest.mark.parametrize("model_id,asset_type", [(GME_ID, "image"), (XCLIP_ID, "video")])
@pytest.mark.parametrize("backend", ["openai_compatible", "openvino_genai"])
def test_g18_registry_does_not_redesign_main_providers(model_id, asset_type, backend):
    assert config.normalize_model_backend(backend) == backend
    with pytest.raises(ValueError, match="runs on"):
        registry.resolve({
            "asset_types": [asset_type], "embedding_model": model_id,
            "embedding_backend": backend,
        })


def _config(monkeypatch, tmp_path, **environment):
    for name in tuple(os.environ):
        if name.startswith("ENGINE_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("ENGINE_WORKSPACE", str(tmp_path / "workspace"))
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    return runpy.run_path(str(ROOT / "src/config.py"))


@pytest.mark.parametrize("language,prompt", [("zh", "以下是普通话的句子。"), ("en", ""), ("", "")])
def test_g16_asr_prompt_follows_language_and_tuning_is_constant(monkeypatch, tmp_path, language, prompt):
    values = _config(
        monkeypatch, tmp_path, ENGINE_ASR_LANGUAGE=language,
        ENGINE_ASR_PROMPT="ignored", ENGINE_ASR_SEGMENT_SECONDS="999",
        ENGINE_SHORT_VIDEO_MAX_SECONDS="999", ENGINE_BACKFILL_BATCH_SIZE="999",
        ENGINE_VIDEO_SUMMARY_TASK="ignored", ENGINE_VIDEO_SUMMARY_TIMEOUT="999",
        ENGINE_ASR_BACKEND="llamaindex_openvino",
    )

    assert values["ASR_PROMPT"] == prompt
    assert values["ASR_SEGMENT_SECONDS"] == 30.0
    assert values["SHORT_VIDEO_MAX_SECONDS"] == 60.0
    assert values["BACKFILL_BATCH_SIZE"] == 32
    assert values["VIDEO_SUMMARY_TASK"] == "summary"
    assert values["VIDEO_SUMMARY_TIMEOUT"] == 300.0
    assert values["ASR_BACKEND"] == "openvino"


def test_g16_multimodal_environment_defaults_and_overrides(monkeypatch, tmp_path):
    values = _config(
        monkeypatch, tmp_path,
        ENGINE_VIDEO_EMBEDDING_BACKEND="openvino",
        ENGINE_IMAGE_EMBEDDING_BACKEND="openvino",
        ENGINE_VIDEO_EMBEDDING_MODEL_ID="example/video",
        ENGINE_IMAGE_EMBEDDING_MODEL_ID="example/image",
        ENGINE_ASR_MODEL_ID="example/speech",
        ENGINE_MODEL_ROOT_PATH=str(tmp_path / "shared-models"),
        ENGINE_VIDEO_EMBEDDING_DEVICE="GPU",
        ENGINE_IMAGE_EMBEDDING_DEVICE="GPU.0",
        ENGINE_ASR_DEVICE="GPU",
        ENGINE_ASR_ENABLED="false",
        ENGINE_VIDEO_SUMMARY_BASE_URL="http://captions.internal",
    )

    for prefix, leaf in (("VIDEO_EMBEDDING", "video"), ("IMAGE_EMBEDDING", "image"), ("ASR", "speech")):
        assert values[f"{prefix}_MODEL_PATH"] == str(tmp_path / "shared-models" / leaf)
    assert values["VIDEO_EMBEDDING_BACKEND"] == "llamaindex_openvino"
    assert values["IMAGE_EMBEDDING_BACKEND"] == "llamaindex_openvino"
    assert values["VIDEO_EMBEDDING_DEVICE"] == "GPU"
    assert values["IMAGE_EMBEDDING_DEVICE"] == "GPU.0"
    assert values["ASR_DEVICE"] == "GPU"
    assert values["ASR_ENABLED"] is False
    assert values["VIDEO_SUMMARY_BASE_URL"] == "http://captions.internal"


def test_g16_empty_model_root_keeps_the_prepared_package_defaults(monkeypatch, tmp_path):
    values = _config(
        monkeypatch, tmp_path, ENGINE_MODEL_ROOT_PATH="",
    )

    for prefix, leaf in (
        ("VIDEO_EMBEDDING", "xclip-base-patch16-zero-shot"),
        ("IMAGE_EMBEDDING", "gme-Qwen2-VL-2B-Instruct-OV"),
        ("ASR", "whisper-small"),
    ):
        assert values[f"{prefix}_MODEL_PATH"] == str(tmp_path / "workspace/models" / leaf)
    assert values["ASR_LANGUAGE"] == "zh"
    assert values["ASR_ENABLED"] is True


@pytest.mark.parametrize("prefix", ["VIDEO_EMBEDDING", "IMAGE_EMBEDDING"])
def test_g16_invalid_media_backend_names_the_setting(monkeypatch, tmp_path, prefix):
    variable = f"ENGINE_{prefix}_BACKEND"
    with pytest.raises(ValueError, match=variable):
        _config(monkeypatch, tmp_path, **{variable: "unknown"})


def test_g16_compose_forwards_multimodal_deployment_settings_with_defaults():
    compose = yaml.safe_load((ROOT / "deployment/docker/docker-compose.yml").read_text())
    environment = compose["services"]["engine"]["environment"]
    names = {
        f"ENGINE_{prefix}_{suffix}"
        for prefix in ("VIDEO_EMBEDDING", "IMAGE_EMBEDDING")
        for suffix in ("BACKEND", "MODEL_ID", "DEVICE")
    } | {
        f"ENGINE_ASR_{suffix}"
        for suffix in ("MODEL_ID", "DEVICE", "LANGUAGE", "ENABLED")
    } | {"ENGINE_VIDEO_SUMMARY_BASE_URL", "ENGINE_MODEL_ROOT_PATH"}

    assert all(
        environment[name].startswith(
            "${" + name + ("-" if name == "ENGINE_ASR_LANGUAGE" else ":-")
        )
        for name in names
    )
    assert "ENGINE_ASR_BACKEND" not in environment


def test_milvus_preserves_main_chainguard_initialization_and_healthcheck():
    compose = yaml.safe_load((ROOT / "deployment/docker/docker-compose-milvus.yml").read_text())
    services = compose["services"]
    minio = services["minio"]

    assert "chainguard/minio@sha256:" in minio["image"]
    assert minio["depends_on"]["minio-init"]["condition"] == "service_completed_successfully"
    assert minio["command"][0] == "server"
    assert minio["healthcheck"]["test"] == ["CMD", "mc", "--config-dir", "/tmp/.mc", "ready", "local"]
    assert minio["environment"]["MINIO_ROOT_USER"] == services["milvus-standalone"]["environment"]["MINIO_ACCESS_KEY_ID"]