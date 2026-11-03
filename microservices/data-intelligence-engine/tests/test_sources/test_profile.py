# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""A profile says what produced a source's records, and changes when that does."""

import re

import pytest

from assetlib.sources.profile import build_profile, default_collection_name
from core.file_asset_library import describe_vector_source

XCLIP_ID = "microsoft/xclip-base-patch16-zero-shot"


def test_a_parameter_that_changes_vectors_changes_the_hash():
    f8 = describe_vector_source({"asset_types": ["video"], "frames_per_clip": 8})
    f16 = describe_vector_source({
        "asset_types": ["video"], "embedding_model": XCLIP_ID, "frames_per_clip": 16,
    })
    assert f8["encoder_kind"] == f16["encoder_kind"] == "multimodal"
    assert f8["supported_roles"] == ["l1_segment", "short_video"]
    assert f8["profile_hash"] != f16["profile_hash"]


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
    name = default_collection_name("my library", "video-xclip f16")
    assert re.fullmatch(r"[A-Za-z_][0-9A-Za-z_]*", name)
    assert name.startswith("my_library_video_xclip_f16_")


def test_a_misspelt_role_is_refused():
    with pytest.raises(ValueError, match="Unknown block_roles transcript"):
        describe_vector_source({"asset_types": ["audio"], "block_roles": ["transcript"]})


def test_asset_types_alone_infer_the_default_model_for_that_family():
    video = describe_vector_source({"asset_types": ["video"]})
    assert video["encoder_kind"] == "multimodal"
    assert video["model"] == XCLIP_ID
    assert video["multimodal_model"]["name"] == "xclip"
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
        "asset_types": ["video"], "embedding_model": XCLIP_ID, "block_kinds": ["video"],
    })
    with pytest.raises(ValueError, match="block_kinds"):
        describe_vector_source({
            "asset_types": ["video"], "embedding_model": XCLIP_ID, "block_kinds": ["image"],
        })


def test_a_backend_that_is_not_the_models_runtime_is_refused():
    with pytest.raises(ValueError, match="not 'openai_compatible'"):
        describe_vector_source({
            "asset_types": ["video"], "embedding_model": XCLIP_ID, "embedding_backend": "openai",
        })


def test_the_model_is_pinned_in_the_profile_with_a_portable_path():
    profile = describe_vector_source({"asset_types": ["video"]})
    record = profile["multimodal_model"]
    assert record["id"] == XCLIP_ID
    # Inside the model dir, so the library can move with its workspace.
    assert record["path"] == "xclip-base-patch16-zero-shot"


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
