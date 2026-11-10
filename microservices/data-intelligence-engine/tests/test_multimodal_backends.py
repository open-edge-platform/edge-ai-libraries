# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Choosing the model, and what happens when the chosen one is not written yet.

A multimodal source is an ordinary vector source -- same type, same adapter,
same kind of collection. Only the configured model differs, named the way a
text source names its model: `embedding_model` under the shared model root, with
`embedding_backend` staying the runtime. The registry
(`core/multimodal/registry.py`) is what recognizes the model; its own tests
are in `test_multimodal_registry.py`.

The requirement running through this file is that a misconfigured model fails
loudly at the moment the source is built. A source that quietly accepted media
and embedded none of it would look exactly like a working one from the outside
-- the pool would go `ready`, the asset would be listed, and nothing would
ever be found.
"""

import pytest

import config
from core.file_asset_library import _is_multimodal
from core.multimodal.embeddings import build_multimodal_embedding
from tests.video_package import VIDEO_FAMILIES

VIDEO_ID = "viclip-b-fp16"
GME_ID = "gme-Qwen2-VL-2B-Instruct-OV"


# --- which indexer a source gets -----------------------------------------------


@pytest.mark.parametrize("family", VIDEO_FAMILIES)
def test_a_source_is_multimodal_when_its_model_is(family):
    assert _is_multimodal({"asset_types": ["video"], "embedding_model": f"{family}-fp16"})
    assert _is_multimodal({
        "asset_types": ["image"], "embedding_model": GME_ID, "embedding_backend": config.LOCAL_OPENVINO,
    })
    assert not _is_multimodal({"embedding_model": GME_ID, "embedding_backend": config.LOCAL_OPENVINO})


@pytest.mark.parametrize("kind", ["video", "image", "audio"])
def test_asset_types_alone_can_make_a_source_multimodal(kind):
    assert _is_multimodal({"asset_types": [kind]})


@pytest.mark.parametrize("kind", ["video", "image", "audio"])
def test_block_kinds_alone_cannot_make_a_source_multimodal(kind):
    with pytest.raises(ValueError, match="asset_types"):
        _is_multimodal({"block_kinds": [kind]})


@pytest.mark.parametrize("kind", ["image", "audio"])
@pytest.mark.parametrize("backend", [config.LOCAL_OPENVINO, config.LOCAL_OPENVINO.upper()])
def test_native_gme_media_uses_the_multimodal_pipeline(kind, backend):
    assert _is_multimodal({
        "asset_types": [kind], "embedding_model": GME_ID, "embedding_backend": backend,
    })


@pytest.mark.parametrize("backend", [None, config.LOCAL_OPENVINO])
@pytest.mark.parametrize("family", VIDEO_FAMILIES)
def test_video_without_asset_scope_is_invalid_even_with_an_explicit_model(backend, family):
    options = {"embedding_model": f"{family}-fp16"}
    if backend:
        options["embedding_backend"] = backend
    with pytest.raises(ValueError, match="asset_types"):
        _is_multimodal(options)


def test_an_ordinary_text_source_is_not():
    assert not _is_multimodal({"embedding_backend": config.LOCAL_OPENVINO})
    assert not _is_multimodal({"embedding_backend": config.REMOTE_OPENAI_COMPATIBLE})
    assert not _is_multimodal({"embedding_model": "BAAI/bge-small-en-v1.5"})
    assert not _is_multimodal({}), "no model and no media scope is the document default"


# --- the factory ---------------------------------------------------------------


def test_a_record_naming_no_known_model_is_rejected():
    with pytest.raises(ValueError, match="Unknown multimodal model"):
        build_multimodal_embedding({"name": "clip-but-imaginary", "path": "/x"})


@pytest.mark.parametrize("scope", [{}, {"asset_types": ["video"]}])
def test_retired_xclip_is_not_accepted_as_a_source(scope):
    with pytest.raises(ValueError, match="Unsupported production video model"):
        _is_multimodal({"embedding_model": "microsoft/xclip-base-patch16-zero-shot", **scope})


def test_a_retired_frozen_xclip_model_cannot_be_built():
    with pytest.raises(ValueError, match="Unsupported production video model"):
        build_multimodal_embedding({"name": "xclip", "path": "/not-read"})


def test_a_missing_image_model_fails_at_construction_not_at_use(tmp_path, monkeypatch):
    """Loudly, and while someone is still looking at the response.

    If this were raised at the first embed instead, it would surface inside a
    background sync, after the asset was stored and the request had returned
    202 -- which reads as "indexing did nothing", not "the model is missing".
    Local models must always be prepared beforehand, so a missing package
    explains how to prepare one instead of trying to download or export it.
    """
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
    with pytest.raises(FileNotFoundError, match="[Pp]repare"):
        build_multimodal_embedding(
            {"name": "gme_qwen2vl", "id": GME_ID}
        )


def test_the_image_model_states_its_width_before_it_can_run():
    """The collection is created from this, so it has to be right up front."""
    from inference.gme_runtime import GME_DIMENSION

    assert GME_DIMENSION == 1536


def test_a_multimodal_source_without_a_recorded_model_must_be_recreated():
    from assetlib import Source

    from core.indexer import MultimodalIndexer
    from databasehub.models import VectorCollection

    source = Source(
        source_id="s1", name="old-source", source_type="vector",
        location=VectorCollection("chunks", 512), configuration={"asset_types": ["video"]},
    )
    with pytest.raises(ValueError, match="records no multimodal model"):
        MultimodalIndexer("p", "pool", source, None, {})


@pytest.mark.parametrize("configuration", [
    {}, {"asset_types": None}, {"asset_types": []},
    {"block_kinds": ["video"]}, {"embedding_model": VIDEO_ID},
])
def test_direct_multimodal_indexer_requires_asset_scope_on_the_source(configuration):
    from assetlib import Source

    from core.indexer import MultimodalIndexer
    from databasehub.models import VectorCollection

    source = Source(
        source_id="s1", source_type="vector", location=VectorCollection("chunks", 512),
        configuration=configuration,
    )
    with pytest.raises(ValueError, match="asset_types"):
        MultimodalIndexer("p", "pool", source, None, {
            "asset_types": ["video"], "multimodal_embedding_instance": object(),
        })
