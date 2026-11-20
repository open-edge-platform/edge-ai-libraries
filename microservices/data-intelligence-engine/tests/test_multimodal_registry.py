# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""The multimodal registry: which models are multimodal, and how they get ready.

A source names its model the same way whether it embeds text or media. What
makes it multimodal is that the name -- a directory's contents first, an id's
prefix second -- is recognized here. Everything this module asserts hangs off
that recognition: the defaults an `asset_types` scope implies, the point at
which a missing model fails, and the inputs a model fixes for itself.
"""

import json

import pytest

import config
from core.multimodal import registry
from tests.video_package import VIDEO_FAMILIES, video_package

VIDEO_ID = "viclip-b-fp16"
GME_ID = "gme-Qwen2-VL-2B-Instruct-OV"
RETIRED_GME_ID = "Alibaba-NLP/gme-Qwen2-VL-2B-Instruct"


def _gme_dir(root, name="gme-Qwen2-VL-2B-Instruct-OV"):
    path = root / name
    path.mkdir(parents=True)
    (path / "gme_openvino_config.json").write_text(json.dumps({"precisions": {}}))
    return path


@pytest.fixture(autouse=True)
def _model_dir(tmp_path, monkeypatch):
    """Frozen records are located by id under the model dir."""
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))


# --- recognition ----------------------------------------------------------------


@pytest.mark.parametrize("family", VIDEO_FAMILIES)
def test_a_model_is_recognized_by_what_its_directory_holds(tmp_path, family):
    """The directory can be named anything; the contents are what count."""
    oddly_named = video_package(tmp_path, name="some-video-model", family=family)
    assert registry.lookup(None, str(oddly_named)).name == family
    assert registry.lookup(None, str(_gme_dir(tmp_path))).name == "gme_qwen2vl"


@pytest.mark.parametrize("family, model_id", [
    (family, model_id)
    for family, ids in (
        ("viclip-b", ("viclip-b", "OpenGVLab/ViCLIP-B-16-hf", "ViCLIP-B-16-hf")),
        ("viclip-l", ("viclip-l", "OpenGVLab/ViCLIP-L-14-hf", "ViCLIP-L-14-hf")),
        ("cosmos-224p", ("cosmos-224p", "nvidia/Cosmos-Embed1-224p", "Cosmos-Embed1-224p")),
    )
    for model_id in (*ids, f"{family}-fp16", f"{family}-fp32")
])
def test_exact_video_identity_recognizes_a_model_that_is_not_on_disk(family, model_id):
    assert registry.lookup(model_id, None).name == family


def test_a_gme_id_prefix_recognizes_a_model_that_is_not_on_disk():
    assert registry.lookup(GME_ID, None).name == "gme_qwen2vl"


def test_the_old_huggingface_gme_id_is_no_longer_accepted():
    with pytest.raises(ValueError, match="no longer accepted"):
        registry.lookup(RETIRED_GME_ID, None)


@pytest.mark.parametrize("model_id", [
    "viclip-b-custom", "viclip-l-int8", "cosmos-224p-custom",
    "OpenGVLab/ViCLIP-B-16-hf-other", "nvidia/Cosmos-Embed1-224p-other",
])
def test_video_ids_are_exact_identities_not_family_prefixes(tmp_path, monkeypatch, model_id):
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
    assert registry.lookup(model_id, None) is None
    with pytest.raises(ValueError, match="embedding_model"):
        registry.resolve({"asset_types": ["video"], "embedding_model": model_id})
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("model_id", [
    "microsoft/xclip-base-patch16-zero-shot", "xclip-base-patch16-zero-shot-fp16", "x-clip-custom",
])
def test_retired_xclip_ids_are_rejected_even_with_a_supported_package(tmp_path, model_id):
    path = video_package(tmp_path)
    with pytest.raises(ValueError, match="Unsupported production video model"):
        registry.lookup(model_id, str(path))


@pytest.mark.parametrize("record", [
    {"name": "xclip"},
    {"name": "viclip-b", "id": "microsoft/xclip-base-patch16-zero-shot"},
    {"name": "x-clip-custom", "id": VIDEO_ID},
])
def test_retired_xclip_profiles_are_rejected_before_path_or_default_resolution(monkeypatch, record):
    monkeypatch.setattr(registry, "local_path", lambda *args: pytest.fail("must reject frozen identity first"))
    with pytest.raises(ValueError, match="Unsupported production video model"):
        registry.load(record, {})


@pytest.mark.parametrize("identity", ["directory", "config", "root-ir", "nested-ir"])
def test_retired_local_video_packages_are_not_accepted_or_listed_as_text(tmp_path, monkeypatch, identity):
    from inference import models

    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
    path = tmp_path / ("xclip-base-patch16-zero-shot" if identity == "directory" else "custom-video")
    path.mkdir()
    if identity == "config":
        (path / "config.json").write_text('{"model_type":"xclip"}')
    elif identity in ("root-ir", "nested-ir"):
        ir = path if identity == "root-ir" else path / "openvino" / "fp16"
        ir.mkdir(parents=True, exist_ok=True)
        for tower in ("xclip_video", "xclip_text"):
            (ir / f"{tower}.xml").write_text("<xml/>")
            (ir / f"{tower}.bin").write_bytes(b"\x00")
    before = sorted(path.rglob("*"))

    with pytest.raises(ValueError, match="Unsupported production video model"):
        registry.lookup(None, str(path))
    with pytest.raises(ValueError, match="Unsupported production video model"):
        registry.resolve({"asset_types": ["video"], "embedding_model": path.name})
    assert models.workspace_models() == []
    assert sorted(path.rglob("*")) == before


def test_a_text_model_is_recognized_as_none_of_these(tmp_path):
    assert registry.lookup("BAAI/bge-small-en-v1.5", None) is None
    plain = tmp_path / "bge-small-en-v1.5"
    plain.mkdir()
    assert registry.lookup(None, str(plain)) is None


def test_recognized_models_state_their_roles_without_being_loaded():
    roles = {model.name: model.supported_roles for model in registry.MODELS}
    for family in VIDEO_FAMILIES:
        assert roles[family] == frozenset({"short_video", "l1_segment"})
    assert {"image", "doc_image", "l2_caption", "l2_transcript", "l3_wiki"} <= roles[
        "gme_qwen2vl"
    ]
    kinds = {model.name: model.supported_kinds for model in registry.MODELS}
    for family in VIDEO_FAMILIES:
        assert kinds[family] == frozenset({"video"})
    # Audio through its transcripts: GME embeds them, video encoders do not.
    assert kinds["gme_qwen2vl"] == frozenset({"image", "text", "audio"})
    assets = {model.name: model.supported_asset_types for model in registry.MODELS}
    for family in VIDEO_FAMILIES:
        assert assets[family] == frozenset({"video"})
    # Catalog adds ordinary documents for text-capable models without mutating
    # the registry's representation-based capabilities.
    assert assets["gme_qwen2vl"] == frozenset({"audio", "image"})


@pytest.mark.parametrize("roles, expected", [
    ({"l2_caption", "l3_wiki"}, set()),
    ({"l2_transcript"}, {"audio"}),
    ({"image", "doc_image", "l2_caption"}, {"image"}),
    ({"short_video", "l1_segment"}, {"video"}),
    ({"image", "l2_transcript", "short_video"}, {"image", "audio", "video"}),
])
def test_asset_support_requires_default_representation_not_optional_captions(roles, expected):
    class FutureModel(registry.MultimodalModel):
        def implementation(self):
            class Capabilities:
                supported_roles = frozenset(roles)
            return Capabilities

    model = FutureModel("future-family", "future-category", ("future-package",))
    assert model.supported_asset_types == frozenset(expected)
    assert model.supported_roles == frozenset(roles)


# --- the default an asset scope and representation imply ------------------------


@pytest.mark.parametrize("selectors, name", [
    (["video"], "viclip-b"), (["mp4"], "viclip-b"), (["video/mp4"], "viclip-b"),
    (["image"], "gme_qwen2vl"), (["jpg"], "gme_qwen2vl"),
    (["image/png"], "gme_qwen2vl"), (["audio"], "gme_qwen2vl"),
    (["wav"], "gme_qwen2vl"), (["audio/wav"], "gme_qwen2vl"),
])
def test_default_for_media_assets_is_the_category_default(selectors, name):
    assert registry.default_for(selectors).name == name


def test_images_and_audio_transcripts_can_share_one_default_model():
    assert registry.default_for(["image", "audio"]).name == "gme_qwen2vl"


@pytest.mark.parametrize("selectors", [[], ["pdf"], ["application/pdf"], ["document"]])
def test_default_for_documents_or_nothing_is_the_document_default(selectors):
    assert registry.default_for(selectors) is None


def test_default_for_assets_no_single_model_embeds_is_an_error():
    with pytest.raises(ValueError, match="one model"):
        registry.default_for(["image", "video"])
    with pytest.raises(ValueError, match="one model"):
        registry.default_for(["video", "audio"])


def test_explicit_roles_select_the_representation_before_the_default_model():
    assert registry.default_for(["video"], ["l2_caption"]).name == "gme_qwen2vl"
    assert registry.default_for(["video"], []).name == "viclip-b"


# --- resolving a source's options -------------------------------------------------


@pytest.mark.parametrize("family", VIDEO_FAMILIES)
def test_resolve_records_the_id_and_no_path_for_a_model_in_the_model_dir(tmp_path, monkeypatch, family):
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
    path = video_package(tmp_path, family=family)
    resolved = registry.resolve({"asset_types": ["video"], "embedding_model": path.name})

    assert resolved.model.name == family
    assert resolved.record() == {
        "name": family, "category": "video", "id": f"{family}-fp16",
    }


def test_frozen_profile_is_loaded_by_id_under_the_model_dir(tmp_path, monkeypatch):
    path = _gme_dir(tmp_path)
    model = registry.lookup(None, str(path))
    built = []
    monkeypatch.setattr(model.__class__, "is_ready", lambda self, path: True)
    monkeypatch.setattr(model.__class__, "build", lambda self, path, device, params: built.append(path))

    registry.load({"name": "gme_qwen2vl", "id": path.name}, {})

    assert built == [path]


@pytest.mark.parametrize("family", VIDEO_FAMILIES)
def test_resolve_by_id_with_asset_scope_records_the_id(family):
    model_id = f"{family}-fp16"
    resolved = registry.resolve({"asset_types": ["video"], "embedding_model": model_id})

    assert resolved.model.name == family
    assert resolved.model_id == model_id
    assert "path" not in resolved.record()


def test_a_frozen_record_without_an_id_is_refused():
    with pytest.raises(ValueError, match="no model id"):
        registry.load({"name": "viclip-b"}, {})


def test_a_frozen_record_whose_id_is_not_in_the_model_dir_fails_as_unprepared():
    with pytest.raises(FileNotFoundError, match="[Pp]repare"):
        registry.load({"name": "viclip-b", "id": "viclip-b-fp16"}, {})


def test_an_unrecognized_model_id_for_media_is_an_error_not_a_download(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="embedding_model"):
        registry.resolve({"embedding_model": empty.name, "asset_types": ["video"]})
    assert list(empty.iterdir()) == []


def test_an_unrecognized_model_id_for_text_is_just_a_text_source(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
    empty = tmp_path / "empty"
    empty.mkdir()
    assert (
        registry.resolve({"embedding_model": empty.name, "block_kinds": ["text"]})
        is None
    )


@pytest.mark.parametrize("value", [None, "", "/explicit/model", "relative/model"])
@pytest.mark.parametrize("scope", [["video"], ["image"], ["pdf"]])
def test_public_model_path_is_rejected_even_with_a_model_id(value, scope):
    with pytest.raises(ValueError, match="embedding_model_path.*embedding_model"):
        registry.resolve({
            "embedding_model_path": value, "embedding_model": VIDEO_ID,
            "asset_types": scope,
        })


def test_model_params_are_recorded_and_other_options_are_not():
    resolved = registry.resolve({
        "asset_types": ["video"], "embedding_model": VIDEO_ID,
        "frames_per_clip": 8, "embedding_device": "GPU",
        "chunk_size": 128,
    })
    assert resolved.params == {
        "frames_per_clip": 8, "asset_types": ["video"],
        "block_kinds": ["video"],
        "block_roles": ["l1_segment", "long_video", "short_video"],
    }


@pytest.mark.parametrize("factory, scope", [(video_package, "video"), (_gme_dir, "image")])
def test_prepared_local_variant_is_selected_by_id_under_model_root(tmp_path, monkeypatch, factory, scope):
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
    path = factory(tmp_path, name="custom-prepared-variant")
    resolved = registry.resolve({"asset_types": [scope], "embedding_model": path.name})

    assert resolved.model_id == path.name
    assert "path" not in resolved.record()
    assert resolved.model.matches_dir(path)
    assert "precision" not in resolved.params


@pytest.mark.parametrize("value", ["fp16", "int4", None])
def test_source_precision_is_rejected_instead_of_ignored(value):
    with pytest.raises(ValueError, match="precision.*embedding_model"):
        registry.resolve({"asset_types": ["video"], "precision": value})
    with pytest.raises(ValueError, match="precision.*embedding_model"):
        registry.load({"name": "viclip-b", "id": "viclip-b-fp16"}, {"precision": value})
    assert "precision" not in registry.MODEL_PARAMS


def test_the_env_default_fills_only_what_the_source_omits(monkeypatch):
    """Precedence: what the source says, else ENGINE_*_EMBEDDING_*, else the
    built-in default -- the same pattern a text source follows."""
    monkeypatch.setattr(config, "VIDEO_EMBEDDING_MODEL_ID", "viclip-l-fp32")

    assert (
        registry.resolve({"asset_types": ["video"]}).model_id == "viclip-l-fp32"
    )
    assert (
        registry.resolve(
            {"asset_types": ["video"], "embedding_model": VIDEO_ID}
        ).model_id
        == VIDEO_ID
    )


@pytest.mark.parametrize("asset_types, name, kinds, roles", [
    (["video"], "viclip-b", ["video"], ["l1_segment", "long_video", "short_video"]),
    (["image"], "gme_qwen2vl", ["image"], ["image"]),
    (["audio"], "gme_qwen2vl", ["text"], ["l2_transcript"]),
    (["image", "audio"], "gme_qwen2vl", ["image", "text"], ["image", "l2_transcript"]),
])
def test_resolve_freezes_effective_routing_without_expanding_model_capabilities(
    asset_types, name, kinds, roles,
):
    options = {"asset_types": asset_types}
    resolved = registry.resolve(options)

    assert resolved.model.name == name
    assert resolved.params == {
        "asset_types": sorted(asset_types), "block_kinds": kinds, "block_roles": roles,
    }
    assert options == {"asset_types": asset_types}, "defaults must not rewrite user options"
    assert "long_video" not in resolved.model.supported_roles


@pytest.mark.parametrize("selectors, expected", [
    ([".MP4", "mp4"], ["mp4"]), (["image/PNG"], ["image/png"]),
    ([".WAV"], ["wav"]),
])
def test_effective_asset_selectors_are_normalized_not_broadened(selectors, expected):
    assert registry.resolve({"asset_types": selectors}).params["asset_types"] == expected


def test_a_video_caption_source_uses_gme_and_text_not_video_blocks():
    resolved = registry.resolve({"asset_types": ["video"], "block_roles": ["l2_caption"]})

    assert resolved.model.name == "gme_qwen2vl"
    assert resolved.params == {
        "asset_types": ["video"], "block_kinds": ["text"], "block_roles": ["l2_caption"],
    }


@pytest.mark.parametrize("filters", [
    {"block_kinds": []}, {"block_roles": []}, {"block_kinds": [], "block_roles": []},
])
def test_explicit_empty_block_filters_are_preserved(filters):
    resolved = registry.resolve({"asset_types": ["video"], **filters})

    assert resolved.model.name == "viclip-b"
    for key, value in filters.items():
        assert resolved.params[key] == value


@pytest.mark.parametrize("options", [
    {"block_kinds": ["video"]}, {"block_kinds": ["image"]},
    {"block_kinds": ["audio"]},
    {"block_roles": ["l2_caption"]},
])
def test_block_filters_alone_cannot_select_a_media_source(options):
    with pytest.raises(ValueError, match="asset_types"):
        registry.resolve(options)


def test_document_prose_and_figure_filters_do_not_select_a_media_model():
    assert registry.resolve({'block_kinds': ['image', 'text']}) is None
    assert registry.resolve({'asset_types': ['pdf'], 'block_roles': ['doc_image']}) is None


@pytest.mark.parametrize("model_id", [*(f"{family}-fp16" for family in VIDEO_FAMILIES), GME_ID])
@pytest.mark.parametrize("scope", [{}, {"asset_types": None}, {"asset_types": []}])
def test_an_explicit_media_model_does_not_replace_required_asset_scope(model_id, scope):
    with pytest.raises(ValueError, match="asset_types"):
        registry.resolve({"embedding_model": model_id, **scope})


@pytest.mark.parametrize("factory", [video_package, _gme_dir])
def test_a_recognized_local_media_id_still_requires_asset_scope(tmp_path, monkeypatch, factory):
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="asset_types"):
        registry.resolve({"embedding_model": factory(tmp_path).name})


@pytest.mark.parametrize("asset_types", ["video", [""], [3], ["video", "pdf"]])
def test_invalid_or_mixed_document_media_scope_is_rejected(asset_types):
    with pytest.raises(ValueError, match="asset_types"):
        registry.resolve({"asset_types": asset_types})


@pytest.mark.parametrize("options, message", [
        ({"asset_types": ["video"], "embedding_model": VIDEO_ID,
      "block_roles": ["l2_caption"]}, "block_roles"),
        ({"asset_types": ["image"], "embedding_model": VIDEO_ID}, "block_roles"),
    ({"asset_types": ["video"], "embedding_model": GME_ID}, "block_roles"),
    ({"asset_types": ["video"], "embedding_model": "BAAI/bge-small-en-v1.5"}, "embedding_model"),
    ({"asset_types": ["video"], "block_roles": ["l2_caption"],
      "block_kinds": ["video"]}, "block_kinds"),
    ({"asset_types": ["image"], "block_roles": ["doc_image"]}, "asset_types"),
])
def test_explicit_models_and_filters_must_match_the_selected_representation(options, message):
    with pytest.raises(ValueError, match=message):
        registry.resolve(options)


def test_explicit_gme_can_embed_video_captions_but_not_raw_video():
    resolved = registry.resolve({
        "asset_types": ["video"], "embedding_model": GME_ID, "block_roles": ["l2_caption"],
    })
    assert resolved.model.name == "gme_qwen2vl"
    assert resolved.params["block_kinds"] == ["text"]


# --- getting a model ready --------------------------------------------------------


@pytest.mark.parametrize("family", VIDEO_FAMILIES)
@pytest.mark.parametrize("precision", ["fp16", "fp32"])
def test_complete_root_video_package_counts_as_ready(tmp_path, family, precision):
    path = video_package(tmp_path, family=family, precision=precision)
    model = registry.lookup(None, str(path))

    assert model.name == family
    assert model.is_ready(path)
    metadata = model.implementation().package_metadata(path, expected_name=family)
    assert metadata["precision"] == precision
    assert metadata["frames"] == 8


@pytest.mark.parametrize("family", VIDEO_FAMILIES)
@pytest.mark.parametrize("field, value", [
    ("format", 2), ("frames", 16), ("image_size", 256), ("dimension", 1),
    ("context_length", 1), ("preprocessing", "xclip"), ("tokenizer_type", "unknown"),
    ("precision", "int8"), ("model_id", "wrong/model"),
    ("parameter_count", None), ("parameter_count", 0), ("parameter_count", True),
    ("artifacts", {}), ("artifacts", {"video_encoder": ["video_encoder.xml"]}),
])
def test_invalid_manifest_is_rejected_before_build(tmp_path, monkeypatch, family, field, value):
    path = video_package(tmp_path, family=family)
    manifest = path / "video_embedding.json"
    metadata = json.loads(manifest.read_text())
    metadata[field] = value
    manifest.write_text(json.dumps(metadata))
    model = registry.lookup(None, str(path))
    monkeypatch.setattr(model.__class__, "build", lambda *args: pytest.fail("invalid package must not compile"))

    assert not model.is_ready(path)
    with pytest.raises(FileNotFoundError, match="Prepare"):
        registry.load(_record(path, name=family), {})


@pytest.mark.parametrize("family", VIDEO_FAMILIES)
@pytest.mark.parametrize("mutation", ["empty", "symlink", "traversal"])
def test_unsafe_or_empty_artifacts_are_rejected_before_build(tmp_path, monkeypatch, family, mutation):
    path = video_package(tmp_path, family=family)
    artifact = path / "text_encoder.bin"
    if mutation == "empty":
        artifact.write_bytes(b"")
    else:
        target = tmp_path / "outside.bin"
        target.write_bytes(b"\x00")
        if mutation == "symlink":
            artifact.unlink()
            artifact.symlink_to(target)
        else:
            manifest = path / "video_embedding.json"
            metadata = json.loads(manifest.read_text())
            metadata["artifacts"]["tokenizer"].append("../outside.bin")
            manifest.write_text(json.dumps(metadata))
    model = registry.lookup(None, str(path))
    monkeypatch.setattr(model.__class__, "build", lambda *args: pytest.fail("unsafe package must not compile"))

    assert not model.is_ready(path)
    with pytest.raises(FileNotFoundError, match="unsafe package artifact"):
        registry.load(_record(path, name=family), {})


@pytest.mark.parametrize("family", VIDEO_FAMILIES)
def test_manifest_precision_must_match_the_directory_suffix(tmp_path, family):
    path = video_package(tmp_path, name=f"{family}-fp32", family=family, precision="fp16")
    model = registry.lookup(None, str(path))

    assert not model.is_ready(path)
    with pytest.raises(FileNotFoundError, match="directory precision conflicts"):
        registry.load(_record(path, name=family), {})


@pytest.mark.parametrize("family, other", [("viclip-b", "viclip-l"), ("viclip-l", "cosmos-224p"),
                                         ("cosmos-224p", "viclip-b")])
def test_explicit_and_frozen_identity_cannot_silently_change_embedding_space(tmp_path, monkeypatch, family, other):
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
    path = video_package(tmp_path, name=f"{family}-fp16", family=other)
    model = registry.lookup(f"{family}-fp16", str(path))
    monkeypatch.setattr(model.__class__, "build", lambda *args: pytest.fail("identity conflict must not compile"))

    assert model.name == family
    assert not model.is_ready(path)
    with pytest.raises(FileNotFoundError, match="mismatched video package"):
        registry.load(_record(path, name=family), {})
    video_package(tmp_path, name=f"{other}-fp16", family=other)
    with pytest.raises(ValueError, match="Frozen model.*conflicts"):
        registry.load(_record(path, model_id=f"{other}-fp16", name=family), {})


@pytest.mark.parametrize("family", VIDEO_FAMILIES)
def test_precision_variants_are_selected_by_id_not_by_directory_preference(tmp_path, monkeypatch, family):
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
    for precision in ("fp16", "fp32"):
        path = video_package(tmp_path, family=family, precision=precision)
        model = registry.lookup(None, str(path))
        assert model.is_ready(path)
    built = []
    monkeypatch.setattr(model.__class__, "build", lambda self, p, device, params: built.append(p))

    for precision in ("fp16", "fp32"):
        model_id = f"{family}-{precision}"
        resolved = registry.resolve({"asset_types": ["video"], "embedding_model": model_id})
        registry.load(resolved.record(), resolved.params)

    assert built == [tmp_path / f"{family}-{precision}" for precision in ("fp16", "fp32")]


@pytest.mark.parametrize("family", VIDEO_FAMILIES)
@pytest.mark.parametrize("directory", ["openvino", "openvino/fp16", "openvino/fp32"])
def test_nested_ir_is_not_a_substitute_for_the_selected_root_package(tmp_path, family, directory):
    path = video_package(tmp_path, family=family)
    nested = path / directory
    nested.mkdir(parents=True)
    for filename in ("video_encoder.xml", "video_encoder.bin", "text_encoder.xml", "text_encoder.bin"):
        (path / filename).rename(nested / filename)
    model = registry.lookup(None, str(path))

    assert not model.is_ready(path)
    # Validation iterates a set: either missing tower may be reported first.
    with pytest.raises(FileNotFoundError, match=r"package artifact: (video|text)_encoder\.(xml|bin)"):
        registry.load(_record(path, name=family), {})


@pytest.mark.parametrize("family", VIDEO_FAMILIES)
def test_local_ir_only_variant_reports_missing_manifest_without_mutating_package(tmp_path, monkeypatch, family):
    from inference import models

    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
    path = video_package(tmp_path, family=family)
    (path / "video_embedding.json").unlink()
    before = sorted(path.iterdir())
    resolved = registry.resolve({"asset_types": ["video"], "embedding_model": path.name})

    assert resolved.model.name == family
    assert resolved.model_id == path.name
    assert not resolved.model.is_ready(path)
    with pytest.raises(FileNotFoundError, match="video_embedding.json"):
        registry.load(resolved.record(), resolved.params)
    assert models.workspace_models() == [{
        "name": path.name, "path": str(path), "ready": False,
        "model_type": models.EMBEDDING, "supported_kinds": ["video"],
        "supported_asset_types": ["video"], "supported_roles": ["l1_segment", "short_video"],
    }]
    assert sorted(path.iterdir()) == before


@pytest.mark.parametrize("family", VIDEO_FAMILIES)
def test_complete_root_package_with_any_local_id_loads_that_exact_package(tmp_path, monkeypatch, family):
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
    path = video_package(tmp_path, name="my-prepared-video-variant", family=family)
    resolved = registry.resolve({"asset_types": ["video"], "embedding_model": path.name})
    model = resolved.model
    built = []
    monkeypatch.setattr(model.__class__, "build", lambda self, p, device, params: built.append((p, dict(params))))

    registry.load(resolved.record(), resolved.params)

    assert model.is_ready(path)
    assert resolved.model.name == family
    assert built == [(path, {"frames_per_clip": 8})]


@pytest.mark.parametrize("family", VIDEO_FAMILIES)
@pytest.mark.parametrize("missing", [
    "video_embedding.json", "tokenizer_config.json", "special_tokens_map.json",
    "video_encoder.xml", "video_encoder.bin", "text_encoder.xml", "text_encoder.bin",
])
def test_video_readiness_requires_package_artifacts_before_build(tmp_path, monkeypatch, family, missing):
    path = video_package(tmp_path, family=family)
    (path / missing).unlink()
    model = registry.lookup(f"{family}-fp16", str(path))
    monkeypatch.setattr(model.__class__, "build", lambda *args: pytest.fail("must validate before compiling"))

    assert not model.is_ready(path)
    with pytest.raises(FileNotFoundError, match=missing):
        registry.load(_record(path, name=family), {})


@pytest.mark.parametrize("family, missing", [
    ("viclip-b", "vocab.json"), ("viclip-b", "merges.txt"),
    ("viclip-l", "vocab.json"), ("viclip-l", "merges.txt"),
    ("cosmos-224p", "vocab.txt"),
])
def test_family_tokenizer_files_cannot_be_replaced_by_tokenizer_json(tmp_path, family, missing):
    path = video_package(tmp_path, family=family)
    (path / missing).unlink()
    (path / "tokenizer.json").write_text("{}")
    model = registry.lookup(None, str(path))

    assert not model.is_ready(path)
    with pytest.raises(FileNotFoundError, match=missing):
        registry.load(_record(path, name=family), {})


@pytest.mark.parametrize("family", VIDEO_FAMILIES)
@pytest.mark.parametrize("checkpoint", [False, True])
def test_an_unprepared_video_model_is_refused_without_downloading_or_converting(tmp_path, family, checkpoint):
    path = video_package(tmp_path, family=family, ir=False) if checkpoint else tmp_path / "missing"
    before = sorted(path.iterdir()) if path.exists() else []

    with pytest.raises(FileNotFoundError, match="[Pp]repare"):
        registry.load(_record(path, name=family), {})
    assert not path.exists() or sorted(path.iterdir()) == before


def test_gme_requires_a_prepared_package(tmp_path):
    with pytest.raises(FileNotFoundError, match="[Pp]repare"):
        registry.load(_record(tmp_path / "gme", GME_ID, "gme_qwen2vl"), {})


# --- building from a profile's record ----------------------------------------------


def _record(path, model_id=None, name="viclip-b"):
    return {"name": name, "id": model_id or path.name}


@pytest.mark.parametrize("family", VIDEO_FAMILIES)
def test_load_builds_a_ready_model_without_preparing(tmp_path, monkeypatch, family):
    path = video_package(tmp_path, family=family)
    built = []
    model = registry.lookup(None, str(path))
    monkeypatch.setattr(
        model.__class__, "build",
        lambda self, p, device, params: built.append((p, device, dict(params))),
    )

    registry.load(_record(path, name=family), {})

    assert built == [(path, "CPU", {"frames_per_clip": 8})]


@pytest.mark.parametrize("family", VIDEO_FAMILIES)
def test_a_fixed_input_the_source_restated_identically_is_accepted(tmp_path, monkeypatch, family):
    path = video_package(tmp_path, family=family)
    model = registry.lookup(None, str(path))
    built = []
    monkeypatch.setattr(
        model.__class__, "build",
        lambda self, p, device, params: built.append(dict(params)),
    )

    registry.load(_record(path, name=family), {"frames_per_clip": 8})

    assert built == [{"frames_per_clip": 8}]


@pytest.mark.parametrize("family", VIDEO_FAMILIES)
def test_a_fixed_input_the_source_disagrees_with_fails_at_mount(tmp_path, family):
    path = video_package(tmp_path, family=family)
    with pytest.raises(ValueError, match="frames_per_clip=16 does not match"):
        registry.load(_record(path, name=family), {"frames_per_clip": 16})


@pytest.mark.parametrize("family", VIDEO_FAMILIES)
def test_the_model_comes_from_the_record_not_todays_defaults(tmp_path, monkeypatch, family):
    """Changing ENGINE_VIDEO_EMBEDDING_* after creation must not retarget an
    existing source; the profile's record is what is loaded."""
    path = video_package(tmp_path, family=family)
    monkeypatch.setattr(config, "VIDEO_EMBEDDING_MODEL_ID", "viclip-l-fp32")
    model = registry.lookup(None, str(path))
    built = []
    monkeypatch.setattr(
        model.__class__, "build",
        lambda self, p, device, params: built.append(str(p)),
    )

    registry.load(_record(path, name=family), {})

    assert built == [str(path)]


@pytest.mark.parametrize("family", VIDEO_FAMILIES)
def test_the_device_follows_todays_default_when_the_source_said_none(tmp_path, monkeypatch, family):
    path = video_package(tmp_path, family=family)
    monkeypatch.setattr(config, "VIDEO_EMBEDDING_DEVICE", "GPU")
    model = registry.lookup(None, str(path))
    built = []
    monkeypatch.setattr(
        model.__class__, "build",
        lambda self, p, device, params: built.append(device),
    )

    registry.load(_record(path, name=family), {})
    registry.load(_record(path, name=family), {"embedding_device": "CPU"})

    assert built == ["GPU", "CPU"]


# --- the model list ------------------------------------------------------------------


def test_workspace_models_classifies_media_as_embeddings_with_capabilities(tmp_path, monkeypatch):
    """Embedding packages appear once; Whisper remains a separate capability."""
    from inference import models

    for family in VIDEO_FAMILIES:
        video_package(tmp_path, family=family)
    _gme_dir(tmp_path)
    bge = tmp_path / "bge-small-en-v1.5"
    bge.mkdir()
    whisper = tmp_path / "whisper-small"
    (whisper / "openvino").mkdir(parents=True)
    (whisper / "config.json").write_text('{"model_type": "whisper"}')
    for name in ("openvino_encoder_model.xml", "openvino_decoder_model.xml"):
        artifact = whisper / "openvino" / name
        artifact.write_text("")
        artifact.with_suffix(".bin").touch()
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))

    by_type = {}
    for entry in models.workspace_models():
        by_type.setdefault(entry["model_type"], []).append(entry["name"])

    assert models.MULTIMODAL not in by_type
    assert by_type[models.EMBEDDING] == [
        "bge-small-en-v1.5",
        "cosmos-224p-fp16",
        "gme-Qwen2-VL-2B-Instruct-OV",
        "viclip-b-fp16",
        "viclip-l-fp16",
    ]
    assert [entry["name"] for entry in models.workspace_models(models.MULTIMODAL)] == [
        "cosmos-224p-fp16", "gme-Qwen2-VL-2B-Instruct-OV", "viclip-b-fp16", "viclip-l-fp16",
    ]
    assert {
        entry["name"]: entry["supported_kinds"] for entry in models.workspace_models(models.EMBEDDING)
    } == {
        "bge-small-en-v1.5": ["text"],
        "cosmos-224p-fp16": ["video"],
        "gme-Qwen2-VL-2B-Instruct-OV": ["audio", "image", "text"],
        "viclip-b-fp16": ["video"],
        "viclip-l-fp16": ["video"],
    }
    assert by_type[models.ASR] == ["whisper-small"]
    assert next(e for e in models.workspace_models(models.ASR))["ready"] is True
    assert all(
        entry["ready"] for entry in models.workspace_models(models.MULTIMODAL)
        if entry["name"] != "gme-Qwen2-VL-2B-Instruct-OV"
    )
