# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""HTTP creation and frozen-source restore, without a running engine or models.

Keep the real library, source reconciliation, projection construction and filters.
Only the API registry, database adapter and inference/tokenizer boundaries are fake.
"""

from copy import deepcopy
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import Mock

import llama_index.core
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from llama_index.core import StorageContext
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.vector_stores import SimpleVectorStore

import config
from api import asset_library as source_api
from assetlib.pool import SourceSyncStatus
from core import embedding, file_asset_library, multimodal
from core.content import ContentBlock, ContentStream
from core.file_asset_library import FileAsset, FileAssetLibrary
from core.indexer import MultimodalIndexer, VectorIndexer, accepts_asset
from core.multimodal import registry as model_registry
from databasehub.adapters.vector import VectorAdapter


XCLIP_ID = "microsoft/xclip-base-patch16-zero-shot"
GME_ID = "Alibaba-NLP/gme-Qwen2-VL-2B-Instruct"
DATABASE = "isolated-vectors"
LIBRARY = "media-contract"
SOURCES_URL = f"{source_api.LIBRARY_API_PREFIX}/{LIBRARY}/sources"


def _forbidden(*args, **kwargs):
    raise AssertionError("Passive creation/restore must not resolve or load a runtime")


class _Hub:
    """Registration is passive; adapter access is observable and never dials out."""

    def __init__(self):
        self.adapter_requests = []
        self.stores = {}
        self.adapter = Mock(spec=VectorAdapter)
        self.adapter.reconcile.side_effect = _forbidden
        self.adapter.count_records.return_value = 0
        self.adapter.present_metadata_values.return_value = set()
        self.adapter.storage_context.side_effect = self._storage_context

    def get_registration(self, database_id):
        assert database_id == DATABASE
        return SimpleNamespace(database_id=DATABASE, database_type="vector")

    def get_adapter(self, database_id):
        self.get_registration(database_id)
        self.adapter_requests.append(database_id)
        return self.adapter

    def _storage_context(self, collection):
        store = self.stores.setdefault(collection.name, SimpleVectorStore())
        return StorageContext.from_defaults(vector_store=store)


class _Registry:
    def __init__(self, library):
        self.library = library
        self.save = Mock()

    def get(self, reference):
        return self.library if self.library.matches(reference) else None


@pytest.fixture(autouse=True)
def isolated_defaults(monkeypatch, tmp_path):
    """Do not inspect the user's model roots or depend on their model defaults."""
    root = tmp_path / "models"
    root.mkdir()
    for key in ("MODEL_DIR", "LEGACY_MODEL_DIR", "SHARED_MODEL_DIR"):
        monkeypatch.setattr(config, key, str(root))
    for prefix, backend, model_id, directory in (
        ("", "native_openvino_gme", "gme-Qwen2-VL-2B-Instruct-OV", "document-gme"),
        ("VIDEO_", "llamaindex_openvino", XCLIP_ID, "xclip"),
        ("IMAGE_", "llamaindex_openvino", GME_ID, "media-gme"),
    ):
        for suffix, value in (
            ("BACKEND", backend), ("MODEL_ID", model_id),
            ("MODEL_PATH", str(root / directory)), ("DEVICE", "CPU"),
        ):
            monkeypatch.setattr(config, f"{prefix}EMBEDDING_{suffix}", value)
    monkeypatch.setattr(embedding, "build_embedding", Mock(side_effect=_forbidden))
    monkeypatch.setattr(multimodal, "build_multimodal_embedding", Mock(side_effect=_forbidden))


@pytest.fixture
def http_library(monkeypatch):
    hub = _Hub()
    library = FileAssetLibrary(LIBRARY, idx="isolated-library", databasehub=hub)
    pool = library.create_asset_pool("empty-pool", "Existing pool")
    registry = _Registry(library)
    monkeypatch.setattr(source_api, "registry", registry)
    # POST registers a locator, not a reconciliation or attachment operation.
    reconcile = Mock(side_effect=_forbidden)
    monkeypatch.setattr(library, "reconcile_sources", reconcile)
    app = FastAPI()
    app.include_router(source_api.router)  # No main.app lifespan or live registry.
    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client, library=library, pool=pool, registry=registry, hub=hub,
        )
    reconcile.assert_not_called()
    assert hub.adapter_requests == []
    assert hub.adapter.mock_calls == []
    assert hub.stores == {}
    assert pool.projections == ()
    assert pool.source_statuses == {}
    assert pool.frozen_sources == pool.unavailable_sources == {}


def _post(context, name, options):
    return context.client.post(SOURCES_URL, json={
        "name": name, "database_id": DATABASE, "operator_options": options,
    })


@pytest.mark.parametrize("family, model, model_id, kinds, roles", [
    ("video", "xclip", XCLIP_ID, ["video"], ["l1_segment", "long_video", "short_video"]),
    ("image", "gme_qwen2vl", GME_ID, ["image"], ["image"]),
    ("audio", "gme_qwen2vl", GME_ID, ["text"], ["l2_transcript"]),
])
def test_http_asset_types_alone_freeze_media_profile(
    http_library, family, model, model_id, kinds, roles,
):
    options = {"asset_types": [family]}
    response = _post(http_library, family, options)

    assert response.status_code == 201, response.text
    output = response.json()
    source = http_library.library.sources[output["id"]]
    profile = source.profile
    assert output["operator_options"] == source.configuration == options
    assert output["profile"] == profile
    assert profile["encoder_kind"] == "multimodal"
    assert profile["model"] == model_id
    assert profile["multimodal_model"]["name"] == model
    assert profile["params"] == {
        "asset_types": [family], "block_kinds": kinds, "block_roles": roles,
    }
    assert profile["profile_hash"]
    assert output["bindings"] == []
    assert output["reconciled"] is True
    assert len(http_library.library.sources) == 1
    http_library.registry.save.assert_called_once_with()


def test_http_original_video_and_caption_have_distinct_sources_and_collections(http_library):
    original_response = _post(http_library, "video-original", {"asset_types": ["video"]})
    caption_response = _post(http_library, "video-caption", {
        "asset_types": ["video"], "block_roles": ["l2_caption"],
    })

    assert original_response.status_code == 201, original_response.text
    assert caption_response.status_code == 201, caption_response.text
    original, caption = original_response.json(), caption_response.json()
    assert original["id"] != caption["id"]
    assert original["name"] != caption["name"]
    assert original["collection_name"] != caption["collection_name"]
    assert original["profile"]["multimodal_model"]["name"] == "xclip"
    assert caption["profile"]["multimodal_model"]["name"] == "gme_qwen2vl"
    assert caption["profile"]["params"] == {
        "asset_types": ["video"], "block_roles": ["l2_caption"], "block_kinds": ["text"],
    }
    assert original["profile"]["profile_hash"] != caption["profile"]["profile_hash"]
    assert original["bindings"] == caption["bindings"] == []
    assert len(http_library.library.sources) == 2
    assert http_library.registry.save.call_count == 2


def test_http_explicit_local_xclip_ir_variant_keeps_its_identity(http_library):
    from pathlib import Path
    from inference.multimodal.xclip_openvino import TEXT_IR, VIDEO_IR

    path = Path(config.MODEL_DIR) / 'xclip-base-patch16-zero-shot-fp16'
    path.mkdir()
    for name in (TEXT_IR, VIDEO_IR):
        (path / name).write_text('<xml/>')
        (path / name).with_suffix('.bin').touch()
    options = {'asset_types': ['video'], 'embedding_model': path.name}

    response = _post(http_library, 'my-video-variant', options)

    assert response.status_code == 201, response.text
    output = response.json()
    assert output['operator_options'] == options
    assert output['profile']['multimodal_model'] == {
        'name': 'xclip', 'category': 'video', 'id': path.name, 'path': path.name,
    }
    assert not model_registry.lookup(path.name, None).is_ready(path)


@pytest.mark.parametrize("options", [
    pytest.param({"block_kinds": ["video"]}, id="legacy-video"),
    pytest.param({"block_kinds": ["image"]}, id="legacy-image"),
    pytest.param({"block_kinds": ["audio"]}, id="legacy-audio"),
    pytest.param({"embedding_model": XCLIP_ID}, id="xclip-without-scope"),
    pytest.param({"embedding_backend": "native_openvino_gme", "embedding_model": GME_ID,
                  "block_kinds": ["video"]}, id="native-video-bypass"),
    pytest.param({"embedding_backend": "native_openvino_gme", "embedding_model": GME_ID,
                  "block_kinds": ["image"]}, id="native-image-only-bypass"),
    pytest.param({"embedding_backend": "native_openvino_gme", "embedding_model": GME_ID,
                  "block_roles": ["l2_caption"]}, id="native-derived-bypass"),
])
def test_http_unscoped_media_is_400_and_does_not_register(http_library, options):
    _assert_bad_source_is_atomic(http_library, options)


@pytest.mark.parametrize("asset_types", [
    pytest.param(None, id="null"), pytest.param([], id="empty"),
    pytest.param("video", id="not-array"), pytest.param([None], id="null-entry"),
    pytest.param([""], id="empty-string"), pytest.param(["video", 42], id="mixed-entry-types"),
])
def test_http_invalid_asset_types_with_media_declaration_is_400(http_library, asset_types):
    _assert_bad_source_is_atomic(http_library, {
        "asset_types": asset_types, "embedding_model": XCLIP_ID, "block_kinds": ["video"],
    })


def _assert_bad_source_is_atomic(context, options, message="asset_types"):
    # A refused request must preserve previously registered sources as well.
    accepted = _post(context, "existing-document", {})
    assert accepted.status_code == 201, accepted.text
    before = deepcopy(context.library.to_record())
    saves = context.registry.save.call_count

    response = _post(context, "invalid-media", options)

    assert response.status_code == 400, response.text
    assert message in response.json()["detail"]
    assert context.library.to_record() == before
    assert context.registry.save.call_count == saves
    listed = context.client.get(SOURCES_URL)
    assert listed.status_code == 200, listed.text
    assert [source["id"] for source in listed.json()] == [accepted.json()["id"]]


@pytest.mark.parametrize("scope", [[], ["pdf"], ["video"], ["image"], ["audio"]])
@pytest.mark.parametrize("precision", ["fp16", None])
def test_http_precision_is_rejected_for_all_vector_sources(http_library, scope, precision):
    _assert_bad_source_is_atomic(http_library, {
        "asset_types": scope, "precision": precision,
    }, message="precision")


@pytest.mark.parametrize("scope", [[], ["pdf"], ["video"], ["image"], ["audio"]])
@pytest.mark.parametrize("path", [None, "", "/explicit/model", "relative/model"])
def test_http_model_path_is_rejected_atomically(http_library, scope, path):
    _assert_bad_source_is_atomic(http_library, {
        "asset_types": scope, "embedding_model_path": path,
    }, message="embedding_model_path")


@pytest.mark.parametrize("routing", [
    pytest.param({"block_kinds": ["text", "image"]}, id="document-prose-and-figures"),
    pytest.param({"asset_types": ["pdf"], "block_kinds": ["text", "image"],
                  "block_roles": [], "chunk_size": 768, "chunk_overlap": 32,
                  "figure_context_chars": 99}, id="pdf-options"),
])
def test_http_native_document_and_pdf_options_are_preserved(http_library, routing):
    options = {"embedding_backend": "native_openvino_gme", "embedding_model": GME_ID, **routing}
    response = _post(http_library, "document", options)

    assert response.status_code == 201, response.text
    output = response.json()
    assert output["operator_options"] == options
    profile = output["profile"]
    assert profile["encoder_kind"] == "text"
    assert profile["backend"] == "native_openvino_gme"
    assert profile["model"] == GME_ID
    for key, value in routing.items():
        assert profile["params"][key] == value


@pytest.mark.parametrize('routing', [
    {'asset_types': ['pdf'], 'block_roles': ['doc_image']},
    {'asset_types': ['pdf'], 'block_kinds': ['image']},
    {'block_kinds': ['text', 'image']},
    {'block_roles': ['doc_image']},
])
def test_http_document_figure_filters_need_no_redundant_backend(http_library, routing):
    response = _post(http_library, 'figures', routing)

    assert response.status_code == 201, response.text
    profile = response.json()['profile']
    assert profile['encoder_kind'] == 'text'
    assert profile['backend'] == 'native_openvino_gme'
    for key, value in routing.items():
        assert profile['params'][key] == value


def test_media_reference_uses_frozen_normalized_source_filters():
    library = FileAssetLibrary(LIBRARY, databasehub=_Hub())
    source = library.create_source('images', DATABASE, configuration={
        'asset_types': ['.PNG'], 'block_roles': ['IMAGE'],
    })
    source_id = source.source_id
    key = 'file:///not-read/picture.png'
    asset = FileAsset('image', origin=key, cached=ContentStream('image', [
        ContentBlock('image:0', kind='image', media_key=key, metadata={'role': 'image'}),
    ]))
    library.register_assets([asset])
    # Authorization needs membership and a binding, not a loaded model.
    pool = library.create_asset_pool('images', 'Images', asset_ids=['image'])
    pool.source_statuses[source_id] = SourceSyncStatus(source_id)

    assert library._referenced_media_asset(key, source_id) is asset
    with pytest.raises(FileNotFoundError):
        library._referenced_media_asset('file:///not-read/neighbor.png', source_id)


def _pool_record(library, source):
    """Persist a previously indexed binding without building a live projection."""
    asset = FileAsset(
        asset_id="stored-video", origin="file:///not-read/clip.mp4",
        cached=ContentStream(asset_id="stored-video", blocks=[ContentBlock(
            "stored-video:0", kind="video", media_key="file:///not-read/clip.mp4",
            metadata={"role": "short_video"},
        )]),
    )
    library.register_assets([asset])
    library.create_asset_pool("pool", "Persisted pool", asset_ids=[asset.asset_id], revision=4)
    record = library.to_record()
    pool = record["asset_pools"][0]
    pool["sources"] = [deepcopy(source.to_record())]
    pool["source_statuses"] = {source.source_id: asdict(SourceSyncStatus(
        source_id=source.source_id, status="ready", indexed_revision=4,
        indexed_asset_ids=[asset.asset_id],
    ))}
    return record


def _forbid_rebinding(monkeypatch):
    # Poison both category defaults and the document default. Frozen records
    # must validate their own routing, not ask what a newly created source wants.
    for prefix in ("", "VIDEO_", "IMAGE_"):
        for suffix in ("BACKEND", "MODEL_ID", "MODEL_PATH"):
            monkeypatch.setattr(config, f"{prefix}EMBEDDING_{suffix}", "invalid-current-default")
    resolve = Mock(side_effect=_forbidden)
    describe = Mock(side_effect=_forbidden)
    vector_description = Mock(side_effect=_forbidden)
    monkeypatch.setattr(model_registry, "resolve", resolve)
    monkeypatch.setattr(FileAssetLibrary, "describe_source", describe)
    monkeypatch.setattr(file_asset_library, "describe_vector_source", vector_description)
    return resolve, describe, vector_description


def test_restore_unscoped_frozen_media_reports_error_and_keeps_source_collection_assets(monkeypatch):
    hub = _Hub()
    library = FileAssetLibrary(LIBRARY, databasehub=hub)
    source = library.create_source("old-video", DATABASE, configuration={"asset_types": ["video"]})
    record = _pool_record(library, source)
    # Even a profile carrying valid frozen filters cannot repair a missing
    # operator declaration on an old standalone-media source.
    for source_record in (record["sources"][0], record["asset_pools"][0]["sources"][0]):
        source_record["operator_options"] = {"embedding_model": XCLIP_ID, "block_kinds": ["video"]}
    frozen_record = deepcopy(record["sources"][0])
    guards = _forbid_rebinding(monkeypatch)

    # Check reconciliation before attachment can overwrite its diagnostic.
    restored = FileAssetLibrary.from_record({**record, "asset_pools": []}, databasehub=hub)
    source_id = source.source_id
    assert source_id in restored.sources
    reason = restored.source_reconciliation_errors[source_id]
    assert "asset_types" in reason
    assert "recreate" in reason.lower() or "replace" in reason.lower()
    assert hub.adapter_requests == []

    saved_pool = record["asset_pools"][0]
    pool = restored.create_asset_pool(
        "pool", saved_pool["name"], source_configurations=saved_pool["sources"],
        asset_ids=saved_pool["asset_ids"], revision=saved_pool["revision"],
        source_statuses={source_id: SourceSyncStatus(**saved_pool["source_statuses"][source_id])},
        tolerant=True,
    )

    assert pool.projections == pool.serving == ()
    assert pool.unavailable_sources[source_id] == restored.sources[source_id]
    assert pool.source_statuses[source_id].status == "failed"
    assert "asset_types" in pool.source_statuses[source_id].error
    assert pool.source_statuses[source_id].indexed_asset_ids == ["stored-video"]
    assert pool.source_statuses[source_id].indexed_revision == pool.revision == 4
    assert pool.asset_ids == ["stored-video"]
    assert set(restored.assets) == {"stored-video"}
    assert restored.sources[source_id].to_record() == frozen_record
    output = restored.to_out().sources[0]
    assert output.reconciled is False
    assert "asset_types" in output.reconciliation_error

    persisted = restored.to_record()
    assert persisted["sources"] == [frozen_record]
    assert persisted["asset_pools"][0]["sources"] == [frozen_record]
    assert persisted["assets"] == record["assets"]
    assert hub.stores == {}
    hub.adapter.reconcile.assert_not_called()
    hub.adapter.delete_by_metadata.assert_not_called()
    embedding.build_embedding.assert_not_called()
    multimodal.build_multimodal_embedding.assert_not_called()
    for guard in guards:
        guard.assert_not_called()


@pytest.mark.parametrize("caption", [False, True], ids=["xclip-original", "gme-caption"])
def test_restore_frozen_media_builds_from_profile_not_current_defaults(monkeypatch, caption):
    hub = _Hub()
    library = FileAssetLibrary(LIBRARY, databasehub=hub)
    model_id = f"{GME_ID}-int4" if caption else f"{XCLIP_ID}-fp16"
    options = {"asset_types": [".MP4"], "embedding_model": model_id}
    if caption:
        options["block_roles"] = ["l2_caption"]
    else:
        options["frames_per_clip"] = 8
    source = library.create_source("frozen-video", DATABASE, configuration=options)
    record = _pool_record(library, source)
    frozen_source = deepcopy(source.to_record())
    frozen_profile = deepcopy(source.profile)
    guards = _forbid_rebinding(monkeypatch)
    # A tokenizer and embedding runtime are the only inference substitutes;
    # build_projection and both indexer constructors remain real.
    monkeypatch.setattr(llama_index.core, "global_tokenizer", lambda text: text.split())
    runtime = SimpleNamespace(dimension=8, supported_roles=frozenset(frozen_profile["supported_roles"]))
    loader = Mock(return_value=runtime)
    monkeypatch.setattr(multimodal, "build_multimodal_embedding", loader)
    hub.adapter.reconcile.side_effect = None

    restored = FileAssetLibrary.from_record(record, databasehub=hub)

    assert restored.source_reconciliation_errors == {}
    assert restored.sources[source.source_id].to_record() == frozen_source
    assert restored.sources[source.source_id].profile == frozen_profile
    projection, = restored.asset_pools["pool"].projections
    assert isinstance(projection, MultimodalIndexer)
    assert projection.source.source_id == source.source_id
    assert projection.collection.name == source.location.name
    assert projection.dimension == projection.collection.dimension == 8
    loader.assert_called_once()
    model_record, runtime_options = loader.call_args.args
    assert model_record == frozen_profile["multimodal_model"]
    for key, value in frozen_profile["params"].items():
        assert runtime_options[key] == projection.configuration[key] == value
    assert runtime_options["embedding_backend"] == frozen_profile["backend"]
    assert projection.configuration["asset_types"] == ["mp4"]
    assert model_record["id"] == model_id
    assert model_record["path"] == model_id.rsplit("/", 1)[-1]
    assert "precision" not in projection.configuration
    # Selector precision is a file contract, not just model-family inference.
    mp4 = FileAsset("mp4", origin="file:///not-read/clip.mp4", loader=_forbidden)
    avi = FileAsset("avi", origin="file:///not-read/clip.avi", loader=_forbidden)
    assert projection.accepts(mp4)
    assert not projection.accepts(avi)
    assert accepts_asset(mp4, source.configuration)
    assert not accepts_asset(avi, source.configuration)
    caption_block = ContentBlock("caption", kind="text", text="A caption", metadata={"role": "l2_caption"})
    original_block = ContentBlock("original", kind="video", metadata={"role": "short_video"})
    assert projection.covers(caption_block) is caption
    assert projection.covers(original_block) is not caption
    persisted = restored.to_record()
    assert persisted["sources"] == [frozen_source]
    assert persisted["asset_pools"][0]["sources"][0]["profile"] == frozen_profile
    assert persisted["assets"] == record["assets"]
    hub.adapter.reconcile.assert_called_once_with(projection.collection)
    embedding.build_embedding.assert_not_called()
    for guard in guards:
        guard.assert_not_called()


@pytest.mark.parametrize("location", ["operator_options", "profile"])
@pytest.mark.parametrize("scope", [["video"], ["pdf"]])
@pytest.mark.parametrize("option, value", [("precision", "fp16"), ("embedding_model_path", "/old/model")])
def test_restore_obsolete_model_option_preserves_record_without_rebinding(monkeypatch, location, scope, option, value):
    hub = _Hub()
    library = FileAssetLibrary(LIBRARY, databasehub=hub)
    source = library.create_source("old-precision", DATABASE, configuration={"asset_types": scope})
    record = library.to_record()
    saved = record["sources"][0]
    target = saved["profile"]["params"] if location == "profile" else saved[location]
    target[option] = value
    frozen = deepcopy(saved)
    guards = _forbid_rebinding(monkeypatch)

    restored = FileAssetLibrary.from_record(record, databasehub=hub)

    assert restored.sources[source.source_id].to_record() == frozen
    assert option in restored.source_reconciliation_errors[source.source_id]
    assert "embedding_model" in restored.source_reconciliation_errors[source.source_id]
    assert hub.adapter_requests == []
    embedding.build_embedding.assert_not_called()
    multimodal.build_multimodal_embedding.assert_not_called()
    for guard in guards:
        guard.assert_not_called()


def test_restore_frozen_document_does_not_resolve_defaults_at_source_problem(monkeypatch):
    hub = _Hub()
    library = FileAssetLibrary(LIBRARY, databasehub=hub)
    source = library.create_source("document-default", DATABASE)
    frozen_record = deepcopy(source.to_record())
    record = library.to_record()
    guards = _forbid_rebinding(monkeypatch)

    # No pool is needed to exercise _source_problem during real reconciliation.
    restored = FileAssetLibrary.from_record(record, databasehub=hub)

    assert restored.source_reconciliation_errors == {}
    assert restored.sources[source.source_id].to_record() == frozen_record
    assert restored._source_problem(restored.sources[source.source_id]) == ""
    assert restored.sources[source.source_id].profile["encoder_kind"] == "text"
    assert restored.sources[source.source_id].profile["profile_hash"] == source.profile["profile_hash"]
    assert hub.adapter_requests == []
    assert hub.adapter.mock_calls == []
    for guard in guards:
        guard.assert_not_called()

    # Building it later must likewise use the recorded document runtime options.
    monkeypatch.setattr(llama_index.core, "global_tokenizer", lambda text: text.split())
    builder = Mock(return_value=MockEmbedding(embed_dim=8))
    monkeypatch.setattr(embedding, "build_embedding", builder)
    hub.adapter.reconcile.side_effect = None
    projection = restored.build_projection("document-projection", "pool", restored.sources[source.source_id])
    assert isinstance(projection, VectorIndexer)
    assert not isinstance(projection, MultimodalIndexer)
    assert builder.call_args.kwargs == {
        "backend": source.profile["backend"], "model_id": source.profile["model_id"],
        "model_path": source.profile["model_path"], "device": source.profile["device"], "api_base": None,
    }
    for key, value in source.profile["params"].items():
        assert projection.configuration[key] == value
    assert restored.sources[source.source_id].to_record() == frozen_record
    hub.adapter.reconcile.assert_called_once_with(projection.collection)
    for guard in guards:
        guard.assert_not_called()