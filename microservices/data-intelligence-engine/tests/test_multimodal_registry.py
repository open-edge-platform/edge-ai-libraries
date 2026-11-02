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

XCLIP_ID = "microsoft/xclip-base-patch16-zero-shot"
GME_ID = "Alibaba-NLP/gme-Qwen2-VL-2B-Instruct"


def _xclip_dir(root, name="xclip-base-patch16-zero-shot", frames=32, ir=True):
    path = root / name
    (path / "openvino").mkdir(parents=True)
    (path / "config.json").write_text(
        json.dumps({"model_type": "xclip", "vision_config": {"num_frames": frames}})
    )
    (path / "tokenizer_config.json").write_text('{}')
    (path / "tokenizer.json").write_text('{}')
    if ir:
        from inference.multimodal.xclip_openvino import TEXT_IR, VIDEO_IR

        for name in (VIDEO_IR, TEXT_IR):
            artifact = path / "openvino" / name
            artifact.write_text("<xml/>")
            artifact.with_suffix(".bin").touch()
    return path


def _gme_dir(root, name="gme-Qwen2-VL-2B-Instruct-OV"):
    path = root / name
    path.mkdir(parents=True)
    (path / "gme_openvino_config.json").write_text(json.dumps({"precisions": {}}))
    return path


# --- recognition ----------------------------------------------------------------


def test_a_model_is_recognized_by_what_its_directory_holds(tmp_path):
    """The directory can be named anything; the contents are what count."""
    oddly_named = _xclip_dir(tmp_path, name="some-video-model")
    assert registry.lookup(None, str(oddly_named)).name == "xclip"
    assert registry.lookup(None, str(_gme_dir(tmp_path))).name == "gme_qwen2vl"


def test_an_id_prefix_recognizes_a_model_that_is_not_on_disk():
    assert registry.lookup(XCLIP_ID, None).name == "xclip"
    assert registry.lookup(GME_ID, None).name == "gme_qwen2vl"


def test_a_text_model_is_recognized_as_none_of_these(tmp_path):
    assert registry.lookup("BAAI/bge-small-en-v1.5", None) is None
    plain = tmp_path / "bge-small-en-v1.5"
    plain.mkdir()
    assert registry.lookup(None, str(plain)) is None


def test_recognized_models_state_their_roles_without_being_loaded():
    roles = {model.name: model.supported_roles for model in registry.MODELS}
    assert roles["xclip"] == frozenset({"short_video", "l1_segment"})
    assert {"image", "doc_image", "l2_caption", "l2_transcript", "l3_wiki"} <= roles[
        "gme_qwen2vl"
    ]
    kinds = {model.name: model.supported_kinds for model in registry.MODELS}
    assert kinds["xclip"] == frozenset({"video"})
    # Audio through its transcripts: GME embeds them, X-CLIP does not.
    assert kinds["gme_qwen2vl"] == frozenset({"image", "text", "audio"})


# --- the default an asset scope and representation imply ------------------------


@pytest.mark.parametrize("selectors, name", [
    (["video"], "xclip"), (["mp4"], "xclip"), (["video/mp4"], "xclip"),
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
    assert registry.default_for(["video"], []).name == "xclip"


# --- resolving a source's options -------------------------------------------------


def test_resolve_records_a_portable_path_for_a_model_in_the_model_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
    path = _xclip_dir(tmp_path)
    resolved = registry.resolve({"asset_types": ["video"], "embedding_model": path.name})

    assert resolved.model.name == "xclip"
    assert resolved.model_path == "xclip-base-patch16-zero-shot"


def test_frozen_profile_keeps_loading_an_absolute_path_outside_the_model_dir(tmp_path, monkeypatch):
    path = _gme_dir(tmp_path)
    model = registry.lookup(None, str(path))
    built = []
    monkeypatch.setattr(model.__class__, "is_ready", lambda self, path: True)
    monkeypatch.setattr(model.__class__, "build", lambda self, path, device, params: built.append(path))

    registry.load({"name": "gme_qwen2vl", "path": str(path)}, {})

    assert built == [path]


def test_resolve_by_id_with_asset_scope_derives_the_path_from_the_id():
    resolved = registry.resolve({"asset_types": ["video"], "embedding_model": XCLIP_ID})

    assert resolved.model.name == "xclip"
    assert resolved.model_id == XCLIP_ID
    assert resolved.model_path == "xclip-base-patch16-zero-shot"


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
            "embedding_model_path": value, "embedding_model": XCLIP_ID,
            "asset_types": scope,
        })


def test_model_params_are_recorded_and_other_options_are_not():
    resolved = registry.resolve({
        "asset_types": ["video"], "embedding_model": XCLIP_ID,
        "frames_per_clip": 16, "embedding_device": "GPU",
        "chunk_size": 128,
    })
    assert resolved.params == {
        "frames_per_clip": 16, "asset_types": ["video"],
        "block_kinds": ["video"],
        "block_roles": ["l1_segment", "long_video", "short_video"],
    }


@pytest.mark.parametrize("factory, scope", [(_xclip_dir, "video"), (_gme_dir, "image")])
def test_prepared_local_variant_is_selected_by_id_under_model_root(tmp_path, monkeypatch, factory, scope):
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
    path = factory(tmp_path, name="custom-prepared-variant")
    resolved = registry.resolve({"asset_types": [scope], "embedding_model": path.name})

    assert resolved.model_id == path.name
    assert resolved.model_path == path.name
    assert resolved.model.matches_dir(path)
    assert "precision" not in resolved.params


@pytest.mark.parametrize("value", ["fp16", "int4", None])
def test_source_precision_is_rejected_instead_of_ignored(value):
    with pytest.raises(ValueError, match="precision.*embedding_model"):
        registry.resolve({"asset_types": ["video"], "precision": value})
    with pytest.raises(ValueError, match="precision.*embedding_model"):
        registry.load({"name": "xclip", "path": "not-read"}, {"precision": value})
    assert "precision" not in registry.MODEL_PARAMS


def test_the_env_default_fills_only_what_the_source_omits(monkeypatch):
    """Precedence: what the source says, else ENGINE_*_EMBEDDING_*, else the
    built-in default -- the same pattern a text source follows."""
    monkeypatch.setattr(config, "VIDEO_EMBEDDING_MODEL_ID", "microsoft/xclip-custom")

    assert (
        registry.resolve({"asset_types": ["video"]}).model_id == "microsoft/xclip-custom"
    )
    assert (
        registry.resolve(
            {"asset_types": ["video"], "embedding_model": XCLIP_ID}
        ).model_id
        == XCLIP_ID
    )


@pytest.mark.parametrize("asset_types, name, kinds, roles", [
    (["video"], "xclip", ["video"], ["l1_segment", "long_video", "short_video"]),
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

    assert resolved.model.name == "xclip"
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


@pytest.mark.parametrize("model_id", [XCLIP_ID, GME_ID])
@pytest.mark.parametrize("scope", [{}, {"asset_types": None}, {"asset_types": []}])
def test_an_explicit_media_model_does_not_replace_required_asset_scope(model_id, scope):
    with pytest.raises(ValueError, match="asset_types"):
        registry.resolve({"embedding_model": model_id, **scope})


@pytest.mark.parametrize("factory", [_xclip_dir, _gme_dir])
def test_a_recognized_local_media_id_still_requires_asset_scope(tmp_path, monkeypatch, factory):
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="asset_types"):
        registry.resolve({"embedding_model": factory(tmp_path).name})


@pytest.mark.parametrize("asset_types", ["video", [""], [3], ["video", "pdf"]])
def test_invalid_or_mixed_document_media_scope_is_rejected(asset_types):
    with pytest.raises(ValueError, match="asset_types"):
        registry.resolve({"asset_types": asset_types})


@pytest.mark.parametrize("options, message", [
    ({"asset_types": ["video"], "embedding_model": XCLIP_ID,
      "block_roles": ["l2_caption"]}, "block_roles"),
    ({"asset_types": ["image"], "embedding_model": XCLIP_ID}, "block_roles"),
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


def test_hand_converted_ir_in_a_precision_folder_counts_as_ready(tmp_path):
    path = _xclip_dir(tmp_path, ir=False)
    from inference.multimodal.xclip_openvino import TEXT_IR, VIDEO_IR

    ir = path / "openvino" / "fp16"
    ir.mkdir(parents=True)
    (ir / VIDEO_IR).write_text("<xml/>")
    (ir / TEXT_IR).write_text("<xml/>")
    (ir / VIDEO_IR).with_suffix(".bin").touch()
    (ir / TEXT_IR).with_suffix(".bin").touch()

    assert registry.lookup(XCLIP_ID, None).is_ready(path)


def test_fp32_is_preferred_when_several_precisions_are_on_disk(tmp_path):
    from inference.multimodal.xclip_openvino import TEXT_IR, VIDEO_IR, find_ir_dir

    path = _xclip_dir(tmp_path, ir=False)
    for precision in ("fp16", "fp32"):
        ir = path / "openvino" / precision
        ir.mkdir(parents=True)
        (ir / VIDEO_IR).write_text("<xml/>")
        (ir / TEXT_IR).write_text("<xml/>")
        (ir / VIDEO_IR).with_suffix(".bin").touch()
        (ir / TEXT_IR).with_suffix(".bin").touch()

    assert find_ir_dir(str(path)) == str(path / "openvino" / "fp32")


def test_an_existing_bare_openvino_dir_counts_as_fp32(tmp_path):
    """Legacy bare `openvino/` fp32 exports still load without conversion."""
    from inference.multimodal.xclip_openvino import find_ir_dir

    path = _xclip_dir(tmp_path)

    assert find_ir_dir(str(path)) == str(path / "openvino")


def _root_xclip_ir(path):
    from inference.multimodal.xclip_openvino import TEXT_IR, VIDEO_IR

    path.mkdir(parents=True, exist_ok=True)
    for name in (VIDEO_IR, TEXT_IR):
        artifact = path / name
        artifact.write_text('<xml/>')
        artifact.with_suffix('.bin').touch()


def test_local_ir_only_variant_is_video_but_reports_missing_package_metadata(tmp_path, monkeypatch):
    from inference import models

    monkeypatch.setattr(config, 'MODEL_DIR', str(tmp_path))
    path = tmp_path / 'xclip-base-patch16-zero-shot-fp16'
    _root_xclip_ir(path)
    before = sorted(path.iterdir())
    resolved = registry.resolve({'asset_types': ['video'], 'embedding_model': path.name})

    assert resolved.model.name == 'xclip'
    assert resolved.model_id == resolved.model_path == path.name
    assert not resolved.model.is_ready(path)
    with pytest.raises(FileNotFoundError, match='config.json.*tokenizer_config.json.*tokenizer.json'):
        registry.load(resolved.record(), resolved.params)
    assert models.workspace_models() == [{
        'name': path.name, 'path': str(path), 'ready': False, 'model_type': models.MULTIMODAL,
    }]
    assert sorted(path.iterdir()) == before


def test_complete_root_ir_package_with_any_local_id_loads_that_exact_package(tmp_path, monkeypatch):
    from inference.multimodal.xclip_openvino import find_ir_dir

    monkeypatch.setattr(config, 'MODEL_DIR', str(tmp_path))
    path = _xclip_dir(tmp_path, name='my-prepared-video-variant', frames=16, ir=False)
    _root_xclip_ir(path)
    resolved = registry.resolve({'asset_types': ['video'], 'embedding_model': path.name})
    model = resolved.model
    built = []
    monkeypatch.setattr(model.__class__, 'build', lambda self, p, device, params: built.append((p, dict(params))))

    registry.load(resolved.record(), resolved.params)

    assert model.is_ready(path)
    assert find_ir_dir(str(path)) == str(path)
    assert built == [(path, {'frames_per_clip': 16})]


@pytest.mark.parametrize('missing', ['config.json', 'tokenizer_config.json', 'tokenizer.json'])
def test_xclip_readiness_requires_package_metadata_before_build(tmp_path, monkeypatch, missing):
    path = _xclip_dir(tmp_path)
    (path / missing).unlink()
    model = registry.lookup(None, str(path))
    monkeypatch.setattr(model.__class__, 'build', lambda *args: pytest.fail('must validate before compiling'))

    assert not model.is_ready(path)
    with pytest.raises(FileNotFoundError, match=missing):
        registry.load(_record(path), {})


def test_xclip_accepts_local_vocab_and_merges_instead_of_tokenizer_json(tmp_path):
    path = _xclip_dir(tmp_path)
    (path / 'tokenizer.json').unlink()
    (path / 'vocab.json').write_text('{}')
    (path / 'merges.txt').write_text('')

    assert registry.lookup(None, str(path)).is_ready(path)


@pytest.mark.parametrize("checkpoint", [False, True])
def test_an_unprepared_xclip_is_refused_without_downloading_or_converting(tmp_path, checkpoint):
    path = _xclip_dir(tmp_path, ir=False) if checkpoint else tmp_path / "missing"

    with pytest.raises(FileNotFoundError, match="[Pp]repare"):
        registry.load(_record(path), {})
    assert not path.exists() or list((path / "openvino").iterdir()) == []


def test_gme_requires_a_prepared_package(tmp_path):
    with pytest.raises(FileNotFoundError, match="[Pp]repare"):
        registry.load(_record(tmp_path / "gme", GME_ID, "gme_qwen2vl"), {})


# --- building from a profile's record ----------------------------------------------


def _record(path, model_id=XCLIP_ID, name="xclip"):
    return {"name": name, "id": model_id, "path": str(path)}


def test_load_builds_a_ready_model_without_preparing(tmp_path, monkeypatch):
    path = _xclip_dir(tmp_path)
    built = []
    model = registry.lookup(None, str(path))
    monkeypatch.setattr(
        model.__class__, "build",
        lambda self, p, device, params: built.append((p, device, dict(params))),
    )

    registry.load(_record(path), {})

    assert built == [(path, "CPU", {"frames_per_clip": 32})]


def test_a_fixed_input_the_source_restated_identically_is_accepted(tmp_path, monkeypatch):
    path = _xclip_dir(tmp_path)
    model = registry.lookup(None, str(path))
    built = []
    monkeypatch.setattr(
        model.__class__, "build",
        lambda self, p, device, params: built.append(dict(params)),
    )

    registry.load(_record(path), {"frames_per_clip": 32})

    assert built == [{"frames_per_clip": 32}]


def test_a_fixed_input_the_source_disagrees_with_fails_at_mount(tmp_path):
    path = _xclip_dir(tmp_path)
    with pytest.raises(ValueError, match="frames_per_clip=16 does not match"):
        registry.load(_record(path), {"frames_per_clip": 16})


def test_the_model_comes_from_the_record_not_todays_defaults(tmp_path, monkeypatch):
    """Changing ENGINE_VIDEO_EMBEDDING_* after creation must not retarget an
    existing source; the profile's record is what is loaded."""
    path = _xclip_dir(tmp_path)
    monkeypatch.setattr(config, "VIDEO_EMBEDDING_MODEL_ID", "microsoft/xclip-large")
    monkeypatch.setattr(config, "VIDEO_EMBEDDING_MODEL_PATH", "/somewhere/else")
    model = registry.lookup(None, str(path))
    built = []
    monkeypatch.setattr(
        model.__class__, "build",
        lambda self, p, device, params: built.append(str(p)),
    )

    registry.load(_record(path), {})

    assert built == [str(path)]


def test_the_device_follows_todays_default_when_the_source_said_none(tmp_path, monkeypatch):
    path = _xclip_dir(tmp_path)
    monkeypatch.setattr(config, "VIDEO_EMBEDDING_DEVICE", "GPU")
    model = registry.lookup(None, str(path))
    built = []
    monkeypatch.setattr(
        model.__class__, "build",
        lambda self, p, device, params: built.append(device),
    )

    registry.load(_record(path), {})
    registry.load(_record(path), {"embedding_device": "CPU"})

    assert built == ["GPU", "CPU"]


# --- the model list ------------------------------------------------------------------


def test_workspace_models_classifies_multimodal_directories_apart(tmp_path, monkeypatch):
    """GME serves both paths; X-CLIP and Whisper must not enter text pickers."""
    from inference import models

    _xclip_dir(tmp_path)
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

    assert sorted(by_type[models.MULTIMODAL]) == [
        "gme-Qwen2-VL-2B-Instruct-OV",
        "xclip-base-patch16-zero-shot",
    ]
    assert by_type[models.EMBEDDING] == [
        "bge-small-en-v1.5", "gme-Qwen2-VL-2B-Instruct-OV"
    ], "X-CLIP and Whisper are not text models"
    assert by_type[models.ASR] == ["whisper-small"]
    assert next(e for e in models.workspace_models(models.ASR))["ready"] is True
