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
from inference.ov_adapter import MultimodalOVEmbedding


ROOT = Path(__file__).resolve().parents[1]
GME_ID = "gme-Qwen2-VL-2B-Instruct-OV"
VICLIP_ID = "viclip-b-fp16"
VICLIP_OFFICIAL_ID = "OpenGVLab/ViCLIP-B-16-hf"


def _video_package(path, name="viclip-b"):
    """Satisfy the runtime's prepared-package contract without compiling IR."""
    path.mkdir(parents=True)
    dimension, preprocessing, context_length, tokenizer_type, model_id = {
        "viclip-b": (512, "viclip", 32, "clip_bpe", VICLIP_OFFICIAL_ID),
        "viclip-l": (768, "viclip", 32, "clip_bpe", "OpenGVLab/ViCLIP-L-14-hf"),
        "cosmos-224p": (256, "cosmos", 128, "bert", "nvidia/Cosmos-Embed1-224p"),
    }[name]
    tokenizer = ["tokenizer_config.json", "special_tokens_map.json"]
    tokenizer += ["vocab.txt"] if name == "cosmos-224p" else ["vocab.json", "merges.txt"]
    artifacts = {
        "video_encoder": ["video_encoder.xml", "video_encoder.bin"],
        "text_encoder": ["text_encoder.xml", "text_encoder.bin"],
        "tokenizer": tokenizer,
    }
    for files in artifacts.values():
        for filename in files:
            (path / filename).write_text("{}" if filename.endswith(".json") else "test artifact")
    (path / "video_embedding.json").write_text(json.dumps({
        "format": 1, "name": name, "model_id": model_id,
        "preprocessing": preprocessing, "dimension": dimension, "context_length": context_length,
        "tokenizer_type": tokenizer_type, "frames": 8, "image_size": 224,
        "precision": "fp16", "parameter_count": 1, "artifacts": artifacts,
    }))
    model = registry.lookup(path.name, str(path))
    assert model.name == name and model.is_ready(path)
    return path


@pytest.fixture
def prepared_video_root(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
    _video_package(tmp_path / VICLIP_ID)
    # Official checkpoint identity resolves its own directory, never an alias
    # to the default precision package or a remote checkpoint.
    _video_package(tmp_path / VICLIP_OFFICIAL_ID.rsplit("/", 1)[-1])
    return tmp_path


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
        def __init__(self, model_dir, device, **options):
            self.model_dir = Path(model_dir)
            self.device = device
            self.max_image_tokens = options.get("max_image_tokens", 1024)
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


def _media(package):
    return media_embeddings.build_multimodal_embedding(
        {"name": "gme_qwen2vl", "id": package.name}, {}
    )


@pytest.mark.parametrize("media_first", [False, True])
def test_g13_main_and_registry_share_runtime_identity(tmp_path, monkeypatch, fake_runtime, media_first):
    package = _package(tmp_path / "package")
    alias = tmp_path / "alias"
    alias.symlink_to(package, target_is_directory=True)
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
    record = {"name": "gme_qwen2vl", "id": "alias"}

    def text_model():
        return embedding.build_embedding(
            backend=config.LOCAL_OPENVINO, model_id="package", device="CPU"
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
    assert media.get_query_embedding("query") == [0.6, 0.8]
    assert media.get_text_embedding_batch(["transcript"]) == [[0.6, 0.8]]
    assert media.get_image_embeddings(["image"]) == [[0.6, 0.8]]
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


def test_g13_runtime_cache_releases_after_both_adapters_are_dropped(tmp_path, monkeypatch, fake_runtime):
    package = _package(tmp_path / "package")
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
    text = embedding.build_embedding(
        backend=config.LOCAL_OPENVINO, model_id="package", device="CPU"
    )
    media = _media(package)
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
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
    runtime = embedding.build_gme_runtime(str(package), "CPU")
    runtime.embedding_dim = 42

    with pytest.raises(ValueError, match="expected 1536"):
        _media(package)


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
    ):
        path = ROOT / "src" / relative
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.module != "core.embeddings", str(path)
            elif isinstance(node, ast.Import):
                assert all(alias.name != "core.embeddings" for alias in node.names), str(path)


def test_g14_all_model_options_expose_each_package_once_as_embedding(tmp_path, monkeypatch):
    _package(tmp_path / "gme")
    for family in ("viclip-b", "viclip-l", "cosmos-224p"):
        _video_package(tmp_path / f"{family}-fp16", family)
    whisper = tmp_path / "whisper"
    whisper.mkdir()
    (whisper / "config.json").write_text('{"model_type": "whisper"}')
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
    monkeypatch.setattr(config, "EMBEDDING_BACKEND", config.LOCAL_OPENVINO)
    options = models.all_model_options()
    names = {
        kind: [entry["name"] for entry in option["models"]]
        for kind, option in options.items()
    }

    assert tuple(options) == (models.EMBEDDING, models.RERANKER, models.LAYOUT, models.ASR)
    assert names[models.EMBEDDING] == ["cosmos-224p-fp16", "gme", "viclip-b-fp16", "viclip-l-fp16"]
    assert models.MULTIMODAL not in options
    assert names[models.ASR] == ["whisper"]
    assert models.LAYOUT in options
    assert options[models.ASR]["backends"] == [config.LOCAL_OPENVINO]
    assert all(entry["ready"] for entry in options[models.EMBEDDING]["models"])
    assert {
        entry["name"]: entry["supported_kinds"] for entry in options[models.EMBEDDING]["models"]
    } == {
        "cosmos-224p-fp16": ["video"], "gme": ["audio", "image", "text"],
        "viclip-b-fp16": ["video"], "viclip-l-fp16": ["video"],
    }
    assert {
        entry["name"]: (entry["supported_asset_types"], entry["supported_roles"])
        for entry in options[models.EMBEDDING]["models"]
    } == {
        "cosmos-224p-fp16": (["video"], ["l1_segment", "short_video"]),
        "gme": (["audio", "document", "image"],
                ["doc_image", "image", "l2_caption", "l2_transcript", "l3_wiki"]),
        "viclip-b-fp16": (["video"], ["l1_segment", "short_video"]),
        "viclip-l-fp16": (["video"], ["l1_segment", "short_video"]),
    }
    assert options[models.ASR]["models"] == [{
        "name": "whisper", "path": str(whisper), "ready": False, "model_type": models.ASR,
    }]
    assert models.model_options(models.MULTIMODAL)["models"] == options[models.EMBEDDING]["models"]


def test_g14_incomplete_gme_is_one_embedding_with_compatibility_view(tmp_path, monkeypatch):
    package = _package(tmp_path / "gme")
    (package / "visual.bin").unlink()
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))

    entries = models.workspace_models()

    assert len(entries) == 1
    assert entries[0]["model_type"] == models.EMBEDDING
    assert entries[0]["supported_kinds"] == ["audio", "image", "text"]
    assert entries[0]["supported_asset_types"] == ["audio", "document", "image"]
    assert entries[0]["supported_roles"] == ["doc_image", "image", "l2_caption", "l2_transcript", "l3_wiki"]
    assert models.workspace_models(models.MULTIMODAL) == entries
    assert not any(entry["ready"] for entry in entries)
    assert registry.lookup(None, str(package)).is_ready(package) is False


@pytest.mark.parametrize("model_id,asset_type", [
    (GME_ID, "image"), (VICLIP_ID, "video"), (VICLIP_OFFICIAL_ID, "video"),
])
@pytest.mark.parametrize("backend", [None, config.LOCAL_OPENVINO])
def test_g18_registry_accepts_prepared_models_on_local_openvino(prepared_video_root, model_id, asset_type, backend):
    options = {"asset_types": [asset_type], "embedding_model": model_id}
    if backend:
        options["embedding_backend"] = backend
    resolved = registry.resolve(options)

    assert resolved.backend == config.LOCAL_OPENVINO
    assert resolved.model_id == model_id
    assert resolved.params["asset_types"] == [asset_type]
    if asset_type == "video":
        assert resolved.model.name == "viclip-b"
        assert "path" not in resolved.record()
        assert resolved.model.is_ready(prepared_video_root / model_id.rsplit("/", 1)[-1])


def test_g18_registry_accepts_gme_for_image_assets():
    resolved = registry.resolve({
        "asset_types": ["image"], "embedding_model": GME_ID,
        "embedding_backend": config.LOCAL_OPENVINO,
    })

    assert resolved.backend == config.LOCAL_OPENVINO
    assert resolved.model.name == "gme_qwen2vl"
    assert resolved.params == {
        "asset_types": ["image"], "block_kinds": ["image"], "block_roles": ["image"],
    }


def test_g18_registry_rejects_the_retired_gme_checkpoint_id():
    with pytest.raises(ValueError, match="no longer accepted"):
        registry.resolve({
            "asset_types": ["image"], "embedding_model": "Alibaba-NLP/gme-Qwen2-VL-2B-Instruct",
        })


@pytest.mark.parametrize("model_id,asset_type", [(GME_ID, "image"), (VICLIP_ID, "video")])
def test_g18_media_models_do_not_run_on_a_remote_backend(prepared_video_root, model_id, asset_type):
    with pytest.raises(ValueError, match="runs on"):
        registry.resolve({
            "asset_types": [asset_type], "embedding_model": model_id,
            "embedding_backend": config.REMOTE_OPENAI_COMPATIBLE,
        })


@pytest.mark.parametrize("backend", [
    "openvino", "llamaindex_openvino", "native_openvino_gme", "openai_compatible", "openvino_genai",
])
def test_g18_retired_backend_names_are_rejected(prepared_video_root, backend):
    with pytest.raises(ValueError, match="model backend must be one of"):
        config.normalize_model_backend(backend)
    with pytest.raises(ValueError):
        registry.resolve({
            "asset_types": ["video"], "embedding_model": VICLIP_ID,
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
        ENGINE_ASR_BACKEND="ignored",
    )

    assert values["ASR_PROMPT"] == prompt
    assert values["ASR_SEGMENT_SECONDS"] == 30.0
    assert values["SHORT_VIDEO_MAX_SECONDS"] == 60.0
    assert values["BACKFILL_BATCH_SIZE"] == 32
    assert values["VIDEO_SUMMARY_TASK"] == "summary"
    assert values["VIDEO_SUMMARY_TIMEOUT"] == 300.0
    assert values["ASR_BACKEND"] == values["LOCAL_OPENVINO"]


def test_g16_multimodal_environment_defaults_and_overrides(monkeypatch, tmp_path):
    values = _config(
        monkeypatch, tmp_path,
        ENGINE_VIDEO_EMBEDDING_BACKEND="local_openvino",
        ENGINE_IMAGE_EMBEDDING_BACKEND="local_openvino",
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

    assert values["MODEL_DIR"] == str(tmp_path / "shared-models")
    assert not any(name.endswith("_MODEL_PATH") for name in values)
    assert values["VIDEO_EMBEDDING_MODEL_ID"] == "example/video"
    assert values["IMAGE_EMBEDDING_MODEL_ID"] == "example/image"
    assert values["ASR_MODEL_ID"] == "example/speech"
    assert values["VIDEO_EMBEDDING_BACKEND"] == values["LOCAL_OPENVINO"]
    assert values["IMAGE_EMBEDDING_BACKEND"] == values["LOCAL_OPENVINO"]
    assert values["VIDEO_EMBEDDING_DEVICE"] == "GPU"
    assert values["IMAGE_EMBEDDING_DEVICE"] == "GPU.0"
    assert values["ASR_DEVICE"] == "GPU"
    assert values["ASR_ENABLED"] is False
    assert values["VIDEO_SUMMARY_BASE_URL"] == "http://captions.internal"


def test_g16_empty_model_root_keeps_the_prepared_package_defaults(monkeypatch, tmp_path):
    values = _config(
        monkeypatch, tmp_path, ENGINE_MODEL_ROOT_PATH="",
    )

    assert values["MODEL_DIR"] == str(tmp_path / "workspace/models")
    for prefix, leaf in (
        ("VIDEO_EMBEDDING", "viclip-b-fp16"),
        ("IMAGE_EMBEDDING", "gme-Qwen2-VL-2B-Instruct-OV"),
        ("ASR", "whisper-small"),
    ):
        assert values[f"{prefix}_MODEL_ID"] == leaf
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