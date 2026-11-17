# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Backend and runtime reporting, strict backend names, legacy profile upgrade."""

import pytest

import config
from assetlib.sources.profile import upgrade_legacy_backends
from inference import meta as ib


def _classes():
    from core.multimodal.asr import WhisperOpenVINO
    from core.postprocessor import _RemoteReranker
    from inference import ov_adapter
    from inference.multimodal.cosmos_openvino import CosmosOpenVINOEmbedding
    from inference.multimodal.viclip_openvino import ViClipOpenVINOEmbedding
    from inference.remote_adapter import _remote_embedding_class

    LO, RE = config.LOCAL_OPENVINO, config.REMOTE_OPENAI_COMPATIBLE
    return [
        (ov_adapter.OpenVINOGenAIEmbedding, LO, ib.RUNTIME_OV_GENAI, False),
        (ov_adapter.OpenVINOGenAIReranking, LO, ib.RUNTIME_OV_GENAI, False),
        (ov_adapter.MultimodalOVEmbedding, LO, ib.RUNTIME_OV_GME, True),
        (ov_adapter.OpenVINOVLReranker, LO, ib.RUNTIME_OV_CORE, True),
        (ov_adapter.OpenVINOLayoutDetector, LO, ib.RUNTIME_OV_CORE, None),
        (ov_adapter._serialized_openvino_embedding_class(), LO, ib.RUNTIME_OV_LLAMAINDEX, False),
        (ov_adapter._llamaindex_rerank_class(), LO, ib.RUNTIME_OV_LLAMAINDEX, False),
        (ViClipOpenVINOEmbedding, LO, ib.RUNTIME_OV_CORE, True),
        (CosmosOpenVINOEmbedding, LO, ib.RUNTIME_OV_CORE, True),
        (WhisperOpenVINO, LO, ib.RUNTIME_OV_OPTIMUM, None),
        (_RemoteReranker, RE, "", False),
        (_remote_embedding_class(), RE, "", False),
    ]


def test_every_model_class_reports_backend_and_runtime():
    for cls, backend, runtime, multimodal in _classes():
        assert issubclass(cls, ib.InferenceMeta), cls
        assert cls.BACKEND == backend, cls
        assert cls.RUNTIME == runtime, cls
        assert cls.SUPPORT_MULTIMODAL is multimodal, cls
        instance = object.__new__(cls)
        assert instance.get_backend() == backend
        assert instance.get_runtime() == runtime
        assert instance.get_support_multimodal() is multimodal


@pytest.mark.parametrize(
    "old", ["llamaindex_openvino", "openvino_genai", "native_openvino_gme",
            "openai_compatible", "openvino", "openai", "gme", "openvino_vl"],
)
def test_old_backend_names_are_rejected(old):
    with pytest.raises(ValueError, match="model backend must be one of"):
        config.normalize_model_backend(old)


def test_only_the_two_backends_are_valid():
    assert config.MODEL_BACKENDS == ("local_openvino", "remote_openai_compatible")
    assert config.normalize_model_backend("LOCAL_OPENVINO") == "local_openvino"


@pytest.mark.parametrize(
    "old, backend, runtime, fused",
    [
        ("llamaindex_openvino", "local_openvino", "ov_llamaindex", False),
        ("openvino_genai", "local_openvino", "ov_genai", False),
        ("native_openvino_gme", "local_openvino", "ov_gme", True),
        ("openai_compatible", "remote_openai_compatible", "", False),
    ],
)
def test_a_stored_text_profile_is_upgraded_with_its_runtime(old, backend, runtime, fused):
    profile, options = upgrade_legacy_backends(
        {"encoder_kind": "text", "backend": old, "profile_hash": "abc"},
        {"embedding_backend": old},
    )
    assert profile["backend"] == backend and options["embedding_backend"] == backend
    assert profile["runtime"] == runtime and profile["fused"] is fused
    assert profile["profile_hash"] == "abc"


def test_a_stored_media_profile_gets_no_runtime_from_its_old_label():
    profile, _ = upgrade_legacy_backends(
        {"encoder_kind": "multimodal", "backend": "llamaindex_openvino"}, {}
    )
    assert profile["backend"] == "local_openvino" and "runtime" not in profile


def test_new_profiles_are_left_alone():
    profile = {"encoder_kind": "text", "backend": "local_openvino", "runtime": "ov_genai"}
    assert upgrade_legacy_backends(profile, {})[0] == profile


def test_source_records_are_upgraded_when_read():
    from assetlib.contracts import Source

    source = Source.from_record({
        "source_id": "s", "name": "n", "source_type": "sql",
        "collection": {"table": "t"}, "operator_options": {"embedding_backend": "openvino_genai"},
        "profile": {"encoder_kind": "text", "backend": "openvino_genai"},
    })
    assert source.profile["backend"] == "local_openvino"
    assert source.profile["runtime"] == "ov_genai"
    assert source.configuration["embedding_backend"] == "local_openvino"


def test_support_multimodal_defaults_to_na():
    assert ib.InferenceMeta.SUPPORT_MULTIMODAL is None


def test_a_text_model_is_not_multimodal_and_a_gme_package_is(tmp_path, monkeypatch):
    from core import embedding

    gme = tmp_path / "gme"
    gme.mkdir()
    (gme / "gme_openvino_config.json").write_text("{}")
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
    local = config.LOCAL_OPENVINO
    assert embedding.embedding_is_fused(local, "gme") is True
    assert embedding.embedding_is_fused(local, "bge-small") is False
    assert embedding.embedding_is_fused(config.REMOTE_OPENAI_COMPATIBLE, "gme") is False


def test_a_vl_export_is_the_media_reranker(tmp_path, monkeypatch):
    from core import postprocessor

    vl = tmp_path / "vl"
    vl.mkdir()
    (vl / "reranker_text.xml").write_text("")
    (vl / "reranker_text.bin").write_text("")
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
    assert postprocessor.is_media_reranker("vl") is True
    assert postprocessor.is_media_reranker("bge-reranker") is False
    assert postprocessor.reranker_class(config.REMOTE_OPENAI_COMPATIBLE, "vl").SUPPORT_MULTIMODAL is False
