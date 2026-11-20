# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""A profile says what produced a source's records, and changes when that does."""

import json
import re

import pytest

import config
from assetlib.sources.profile import build_profile, default_collection_name
from core.file_asset_library import describe_vector_source
from core.multimodal import registry

VICLIP_ID = "viclip-b-fp16"


@pytest.fixture(autouse=True)
def prepared_video_defaults(monkeypatch, tmp_path):
    root = tmp_path / "models"
    package = root / VICLIP_ID
    package.mkdir(parents=True)
    artifacts = {
        "video_encoder": ["video_encoder.xml", "video_encoder.bin"],
        "text_encoder": ["text_encoder.xml", "text_encoder.bin"],
        "tokenizer": ["vocab.json", "merges.txt", "tokenizer_config.json", "special_tokens_map.json"],
    }
    for files in artifacts.values():
        for name in files:
            (package / name).write_text("{}" if name.endswith(".json") else "test artifact")
    (package / "video_embedding.json").write_text(json.dumps({
        "format": 1, "name": "viclip-b", "model_id": "OpenGVLab/ViCLIP-B-16-hf",
        "preprocessing": "viclip", "dimension": 512, "context_length": 32,
        "tokenizer_type": "clip_bpe", "frames": 8, "image_size": 224,
        "precision": "fp16", "parameter_count": 1, "artifacts": artifacts,
    }))
    for key in ("MODEL_DIR", "LEGACY_MODEL_DIR", "SHARED_MODEL_DIR"):
        monkeypatch.setattr(config, key, str(root))
    monkeypatch.setattr(config, "VIDEO_EMBEDDING_MODEL_ID", VICLIP_ID)
    monkeypatch.setattr(config, "VIDEO_EMBEDDING_BACKEND", config.LOCAL_OPENVINO)
    assert registry.lookup(VICLIP_ID, None).is_ready(package)
    return package


def test_a_parameter_that_changes_vectors_changes_the_hash():
    # GME's processor limit is configurable; ViCLIP's eight-frame input is not.
    small = describe_vector_source({"asset_types": ["image"], "max_image_tokens": 256})
    large = describe_vector_source({
        "asset_types": ["image"], "max_image_tokens": 512,
    })
    assert small["encoder_kind"] == large["encoder_kind"] == "multimodal"
    assert small["multimodal_model"] == large["multimodal_model"]
    assert small["params"]["max_image_tokens"] == 256
    assert large["params"]["max_image_tokens"] == 512
    assert small["profile_hash"] != large["profile_hash"]


def test_viclip_rejects_a_frame_count_that_conflicts_with_its_package(prepared_video_defaults):
    model = registry.lookup(VICLIP_ID, None)
    assert model.fixed_params(prepared_video_defaults) == {"frames_per_clip": 8}
    profile = describe_vector_source({"asset_types": ["video"], "frames_per_clip": 8})
    assert profile["supported_roles"] == ["l1_segment", "short_video"]
    with pytest.raises(ValueError, match="frames_per_clip=16.*model's 8"):
        registry.load(profile["multimodal_model"], {**profile["params"], "frames_per_clip": 16})


def test_the_device_is_shown_but_not_hashed():
    cpu = build_profile("text", "openvino", "bge", {"chunk_size": 512}, device="CPU")
    gpu = build_profile("text", "openvino", "bge", {"chunk_size": 512}, device="GPU")
    assert cpu["profile_hash"] == gpu["profile_hash"]


def test_a_text_source_resolves_engine_defaults():
    profile = describe_vector_source({})
    assert profile["encoder_kind"] == "text"
    assert profile["model"] and profile["params"]["chunk_size"] > 0


def test_routing_is_part_of_the_profile():
    everything = describe_vector_source({"asset_types": ["image", "audio"]})
    asr_only = describe_vector_source({
        "asset_types": ["image", "audio"], "block_roles": ["l2_transcript"],
    })
    assert everything["profile_hash"] != asr_only["profile_hash"]


def test_a_derived_collection_name_is_safe_for_milvus():
    name = default_collection_name("my library", "video-viclip f16")
    assert re.fullmatch(r"[A-Za-z_][0-9A-Za-z_]*", name)
    assert name.startswith("my_library_video_viclip_f16_")


def test_a_misspelt_role_is_refused():
    with pytest.raises(ValueError, match="Unknown block_roles transcript"):
        describe_vector_source({"asset_types": ["audio"], "block_roles": ["transcript"]})


def test_asset_types_alone_infer_the_default_model_for_that_family():
    video = describe_vector_source({"asset_types": ["video"]})
    assert video["encoder_kind"] == "multimodal"
    assert video["model"] == VICLIP_ID
    assert video["multimodal_model"]["name"] == "viclip-b"
    image = describe_vector_source({"asset_types": ["image"]})
    assert image["multimodal_model"]["name"] == "gme_qwen2vl"
    assert describe_vector_source({"block_kinds": ["text"]})["encoder_kind"] == "text"
    assert describe_vector_source({})["encoder_kind"] == "text"


@pytest.mark.parametrize("kind", ["video", "image", "audio"])
def test_legacy_block_kind_only_media_sources_are_rejected(kind):
    with pytest.raises(ValueError, match="asset_types"):
        describe_vector_source({"block_kinds": [kind]})


def test_asset_families_no_single_default_model_embeds_are_refused():
    with pytest.raises(ValueError, match="one model"):
        describe_vector_source({"asset_types": ["image", "video"]})
    with pytest.raises(ValueError, match="one model"):
        describe_vector_source({"asset_types": ["video", "audio"]})


def test_audio_is_a_gme_source_through_its_transcripts():
    profile = describe_vector_source({"asset_types": ["audio"]})

    assert profile["encoder_kind"] == "multimodal"
    assert profile["multimodal_model"]["name"] == "gme_qwen2vl"
    assert "l2_transcript" in profile["supported_roles"]


def test_a_model_is_checked_against_the_kinds_it_is_asked_to_take():
    describe_vector_source({
        "asset_types": ["video"], "embedding_model": VICLIP_ID, "block_kinds": ["video"],
    })
    with pytest.raises(ValueError, match="block_kinds"):
        describe_vector_source({
            "asset_types": ["video"], "embedding_model": VICLIP_ID, "block_kinds": ["image"],
        })


def test_a_backend_that_is_not_the_models_runtime_is_refused():
    with pytest.raises(ValueError, match="not 'remote_openai_compatible'"):
        describe_vector_source({
            "asset_types": ["video"], "embedding_model": VICLIP_ID, "embedding_backend": config.REMOTE_OPENAI_COMPATIBLE,
        })


def test_the_model_is_pinned_in_the_profile_by_id_without_a_path():
    profile = describe_vector_source({"asset_types": ["video"]})
    record = profile["multimodal_model"]
    assert record["id"] == VICLIP_ID
    # The id names a directory under the model dir; no path is stored.
    assert "path" not in record


@pytest.mark.parametrize("family, kinds, roles", [
    ("image", ["image"], ["image"]),
    ("audio", ["text"], ["l2_transcript"]),
    ("video", ["video"], ["l1_segment", "long_video", "short_video"]),
])
def test_default_routing_is_frozen_in_the_profile(family, kinds, roles):
    profile = describe_vector_source({"asset_types": [family]})

    assert profile["params"] == {
        "asset_types": [family], "block_kinds": kinds, "block_roles": roles,
    }
    if family == "video":
        assert "long_video" not in profile["supported_roles"]


@pytest.mark.parametrize("key", ["block_kinds", "block_roles"])
def test_explicit_empty_block_filters_are_frozen_and_change_the_profile(key):
    default = describe_vector_source({"asset_types": ["video"]})
    unfiltered = describe_vector_source({"asset_types": ["video"], key: []})

    assert unfiltered["params"][key] == []
    assert unfiltered["profile_hash"] != default["profile_hash"]
    assert unfiltered["multimodal_model"] == default["multimodal_model"]


def test_video_captions_have_a_gme_profile_with_text_routing():
    profile = describe_vector_source({"asset_types": ["video"], "block_roles": ["l2_caption"]})

    assert profile["encoder_kind"] == "multimodal"
    assert profile["multimodal_model"]["name"] == "gme_qwen2vl"
    assert profile["params"] == {
        "asset_types": ["video"], "block_roles": ["l2_caption"], "block_kinds": ["text"],
    }


def test_extension_scope_is_preserved_in_the_profile_and_its_hash():
    mp4 = describe_vector_source({"asset_types": [".MP4"]})
    video = describe_vector_source({"asset_types": ["video"]})

    assert mp4["params"]["asset_types"] == ["mp4"]
    assert mp4["multimodal_model"] == video["multimodal_model"]
    assert mp4["profile_hash"] != video["profile_hash"]
