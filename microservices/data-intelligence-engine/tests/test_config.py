# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# pyright: reportMissingImports=false

import os
import runpy
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

import config
from core import embedding, postprocessor
from llama_index.core.schema import NodeWithScore, TextNode


ROOT = Path(__file__).resolve().parents[1]


def load_config(monkeypatch, tmp_path, **environment):
    for name in tuple(os.environ):
        if name.startswith("ENGINE_") or name == "MODEL_PATH":
            monkeypatch.delenv(name)
    monkeypatch.setenv("ENGINE_WORKSPACE", str(tmp_path / "workspace"))
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    return runpy.run_path(str(ROOT / "src/config.py"))


@pytest.mark.parametrize(
    ("setting", "variable", "default", "override", "expected"),
    [
        ("EMBEDDING_API_KEY", "ENGINE_DOC_EMBEDDING_API_KEY", "unused", "test-key", "test-key"),
        ("RERANK_API_KEY", "ENGINE_RERANK_API_KEY", "unused", "test-key", "test-key"),
    ],
)
def test_runtime_settings_have_defaults_and_environment_overrides(
    monkeypatch, tmp_path, setting, variable, default, override, expected
):
    assert load_config(monkeypatch, tmp_path)[setting] == default
    assert load_config(monkeypatch, tmp_path, **{variable: override})[setting] == expected


def test_media_reranker_defaults_to_int8_package(monkeypatch, tmp_path):
    settings = load_config(monkeypatch, tmp_path)
    assert settings["MEDIA_RERANK_MODEL_ID"] == "Qwen3-VL-Reranker-2B-INT8-OV"
    assert "MEDIA_RERANK_MODEL_PATH" not in settings

    fp16 = load_config(
        monkeypatch, tmp_path,
        ENGINE_MEDIA_RERANK_MODEL_ID="Qwen3-VL-Reranker-2B-OV",
    )
    assert fp16["MEDIA_RERANK_MODEL_ID"] == "Qwen3-VL-Reranker-2B-OV"


@pytest.mark.parametrize("endpoint", [None, "", "https://unused.invalid"])
def test_config_does_not_require_or_configure_a_model_download_endpoint(tmp_path, endpoint):
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("ENGINE_")
        and name != "HF_ENDPOINT"
    }
    environment.update(
        ENGINE_WORKSPACE=str(tmp_path / "workspace"),
        PYTHONPATH=str(ROOT / "src"),
        HF_HUB_OFFLINE="1",
    )
    if endpoint is not None:
        environment["HF_ENDPOINT"] = endpoint
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os\n"
            "before = os.environ.get('HF_ENDPOINT')\n"
            "import config\n"
            "assert not hasattr(config, 'HF_ENDPOINT')\n"
            "assert os.environ.get('HF_ENDPOINT') == before\n",
        ],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout == ""


def test_model_directories_follow_workspace_and_model_identifiers(monkeypatch, tmp_path):
    values = load_config(
        monkeypatch,
        tmp_path,
        ENGINE_DOC_EMBEDDING_MODEL_ID="example/dense",
        ENGINE_RERANK_MODEL_ID="example/reranker",
    )

    assert values["MODEL_DIR"] == str(tmp_path / "workspace/models")
    assert values["EMBEDDING_MODEL_ID"] == "example/dense"
    assert values["RERANK_MODEL_ID"] == "example/reranker"
    assert not [name for name in values if name.endswith("_MODEL_PATH")]


@pytest.mark.parametrize("root", [None, ""])
def test_unset_or_empty_model_root_defaults_to_workspace(monkeypatch, tmp_path, root):
    environment = {} if root is None else {"ENGINE_MODEL_ROOT_PATH": root}
    values = load_config(monkeypatch, tmp_path, **environment)

    model_root = tmp_path / "workspace/models"
    assert values["MODEL_DIR"] == str(model_root)
    for setting, name in (
        ("EMBEDDING_MODEL_ID", "gme-Qwen2-VL-2B-Instruct-OV"),
        ("VIDEO_EMBEDDING_MODEL_ID", "viclip-b-fp16"),
        ("IMAGE_EMBEDDING_MODEL_ID", "gme-Qwen2-VL-2B-Instruct-OV"),
        ("ASR_MODEL_ID", "whisper-small"),
        ("RERANK_MODEL_ID", "Qwen3-VL-Reranker-2B-INT8-OV"),
        ("LAYOUT_MODEL_ID", "PP-DocLayoutV3"),
    ):
        assert values[setting] == name


def test_model_root_is_shared_by_every_model_capability(monkeypatch, tmp_path):
    model_root = tmp_path / "shared-models"
    values = load_config(
        monkeypatch,
        tmp_path,
        ENGINE_MODEL_ROOT_PATH=str(model_root),
        ENGINE_DOC_EMBEDDING_MODEL_ID="example/dense",
        ENGINE_VIDEO_EMBEDDING_MODEL_ID="example/video",
        ENGINE_IMAGE_EMBEDDING_MODEL_ID="example/image",
        ENGINE_ASR_MODEL_ID="example/speech",
        ENGINE_RERANK_MODEL_ID="example/reranker",
    )

    assert values["MODEL_DIR"] == str(model_root)
    assert model_root.is_dir()
    for setting, name in (
        ("EMBEDDING_MODEL_ID", "example/dense"),
        ("VIDEO_EMBEDDING_MODEL_ID", "example/video"),
        ("IMAGE_EMBEDDING_MODEL_ID", "example/image"),
        ("ASR_MODEL_ID", "example/speech"),
        ("RERANK_MODEL_ID", "example/reranker"),
        ("LAYOUT_MODEL_ID", "PP-DocLayoutV3"),
    ):
        assert values[setting] == name


def test_default_gme_adapters_share_the_package_under_a_custom_root(monkeypatch, tmp_path):
    model_root = tmp_path / "shared-models"
    values = load_config(
        monkeypatch, tmp_path, ENGINE_MODEL_ROOT_PATH=str(model_root),
        MODEL_PATH=str(tmp_path / "legacy"),
    )

    assert values["EMBEDDING_MODEL_ID"] == values["IMAGE_EMBEDDING_MODEL_ID"]
    assert values["EMBEDDING_MODEL_ID"] == "gme-Qwen2-VL-2B-Instruct-OV"
    assert values["MODEL_DIR"] == str(model_root)
    assert values["SHARED_MODEL_DIR"] == str(Path.home() / "models")
    assert values["LEGACY_MODEL_DIR"] == str(tmp_path / "legacy")


def test_document_embedding_environment_configures_the_existing_factories(monkeypatch, tmp_path):
    values = load_config(
        monkeypatch, tmp_path,
        ENGINE_DOC_EMBEDDING_BACKEND="remote_openai_compatible",
        ENGINE_DOC_EMBEDDING_MODEL_ID="example/documents",
        ENGINE_DOC_EMBEDDING_DEVICE="GPU.0",
        ENGINE_DOC_EMBEDDING_API_BASE="http://embedding.internal/v1",
        ENGINE_DOC_EMBEDDING_API_KEY="test-key",
    )

    assert values["EMBEDDING_BACKEND"] == "remote_openai_compatible"
    assert values["EMBEDDING_MODEL_ID"] == "example/documents"
    assert values["EMBEDDING_DEVICE"] == "GPU.0"
    assert values["EMBEDDING_API_BASE"] == "http://embedding.internal/v1"
    assert values["EMBEDDING_API_KEY"] == "test-key"


def test_model_root_is_used_by_resolution_registry_and_discovery(monkeypatch, tmp_path):
    from core.multimodal import registry
    from inference import models

    model_root = tmp_path / "shared-models"
    values = load_config(monkeypatch, tmp_path, ENGINE_MODEL_ROOT_PATH=str(model_root))
    model = model_root / "dense"
    model.mkdir()
    for name in ("openvino_model.xml", "openvino_model.bin"):
        (model / name).touch()
    monkeypatch.setattr(config, "MODEL_DIR", values["MODEL_DIR"])

    assert embedding.resolve_model_path("dense") == str(model)
    assert embedding.workspace_model_dir("example/new") == str(model_root / "example/new")
    assert registry.local_path("dense") == model
    assert registry.path_for_id("example/video") == model_root / "video"
    assert models.workspace_models() == [
        {"name": "dense", "path": str(model), "ready": True, "model_type": "embedding",
         "supported_kinds": ["text"], "supported_asset_types": ["document"], "supported_roles": []},
    ]


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("ENGINE_PORT", "65536"),
        ("ENGINE_DOC_EMBEDDING_BACKEND", "unknown"),
    ],
)
def test_invalid_environment_values_name_the_setting(monkeypatch, tmp_path, variable, value):
    with pytest.raises(ValueError, match=variable):
        load_config(monkeypatch, tmp_path, **{variable: value})


def test_request_defaults_use_global_retrieval_configuration(monkeypatch):
    monkeypatch.setattr(config, "RETRIEVE_TOP_K", 17)
    monkeypatch.setattr(config, "RERANK_TOP_N", 7)
    schemas = runpy.run_path(str(ROOT / "src/schemas.py"))
    requests = runpy.run_path(str(ROOT / "src/assetlib/models.py"))

    assert schemas["RetrieveRequest"](query="q", libraries=["docs"]).top_k == 17
    assert schemas["PostprocessOptions"]().top_n == 7
    assert requests["VectorRetrieveRequest"](query="q").top_k == 17
    assert schemas["RetrieveRequest"](query="q", libraries=["docs"], top_k=2).top_k == 2
    assert schemas["PostprocessOptions"](top_n=1).top_n == 1


def test_shared_model_root_is_used_by_path_resolution(monkeypatch, tmp_path):
    shared = tmp_path / "shared"
    model = shared / "model"
    model.mkdir(parents=True)
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path / "workspace"))
    monkeypatch.setattr(config, "LEGACY_MODEL_DIR", "", raising=False)
    monkeypatch.setattr(config, "SHARED_MODEL_DIR", str(shared), raising=False)

    assert embedding.resolve_model_path("model") == str(model)


def test_genai_factory_uses_configured_input_length(monkeypatch, tmp_path):
    from inference import ov_adapter

    (tmp_path / "model").mkdir()
    for name in ("openvino_model.xml", "openvino_model.bin"):
        (tmp_path / "model" / name).touch()
    monkeypatch.setattr(config, "MODEL_DIR", str(tmp_path))
    monkeypatch.setattr(config, "EMBEDDING_MAX_LENGTH", 384, raising=False)
    monkeypatch.setattr(ov_adapter, "OpenVINOGenAIEmbedding", lambda **options: options)

    options = embedding._build(config.LOCAL_OPENVINO, "model", "CPU", "")

    assert options["max_length"] == 384


@pytest.mark.parametrize(
    ("module", "factory", "prefix", "path_index"),
    [
        (embedding, "build_embedding", "EMBEDDING", 1),
        (postprocessor, "build_reranker", "RERANK", 2),
    ],
)
@pytest.mark.parametrize(
    ("options", "expected"),
    [
        ({}, "configured"),
        ({"model_id": "configured"}, "configured"),
        ({"model_id": "another"}, "another"),
    ],
)
def test_model_factories_honor_configured_paths_and_explicit_overrides(
    monkeypatch, module, factory, prefix, path_index, options, expected
):
    monkeypatch.setattr(config, f"{prefix}_MODEL_ID", "configured")
    monkeypatch.setattr(module, "_CACHE", embedding.ModelCache() if module is embedding else {})
    monkeypatch.setattr(module, "_build", lambda *arguments: arguments)

    assert getattr(module, factory)(**options)[path_index] == expected


def test_openai_embedding_uses_configured_api_key(monkeypatch):
    from inference import remote_adapter

    monkeypatch.setattr(remote_adapter, "remote_openai_embedding", lambda **options: options)
    monkeypatch.setattr(config, "EMBEDDING_API_KEY", "test-key")

    options = embedding._build(config.REMOTE_OPENAI_COMPATIBLE, "model", "CPU", "http://embed")

    assert options["api_key"] == "test-key"
    assert options["api_base"] == "http://embed/v1"


def test_graph_retriever_explicit_options_override_deployment_defaults(monkeypatch):
    from core.graph_search import GraphSearchRetriever, InMemoryConceptGraphBackend

    monkeypatch.setattr(
        config,
        "GRAPH_SEARCH_DEFAULTS",
        {**config.GRAPH_SEARCH_DEFAULTS, "seed_m": 11, "hops": 4, "inverse_freq": False},
    )
    backend = InMemoryConceptGraphBackend({}, {})
    indexer = SimpleNamespace(as_retriever=lambda: SimpleNamespace())
    retriever = GraphSearchRetriever([], indexer, backend, seed_m=2, hops=0)

    assert retriever.seed_m == 2
    assert retriever.hops == 0
    assert retriever.inverse_freq is False
    assert config.GRAPH_SEARCH_DEFAULTS["seed_m"] == 11


@pytest.mark.parametrize(
    "message",
    [
        "No schema found",
        "Storage Error: Tag not found.",
        "Storage Error: Edge not found.",
    ],
)
def test_nebula_schema_retries_use_configured_attempts_and_delay(monkeypatch, message):
    from databasehub.adapters import nebula

    sleeps = []
    writes = []
    monkeypatch.setattr(config, "NEBULA_SCHEMA_WRITE_ATTEMPTS", 3)
    monkeypatch.setattr(config, "NEBULA_SCHEMA_RETRY_INTERVAL", 0.25)
    monkeypatch.setattr(nebula.time, "sleep", sleeps.append)

    def write():
        writes.append(None)
        raise RuntimeError(message)

    with pytest.raises(RuntimeError) as caught:
        nebula.NebulaAdapter._retry_schema_write(write)

    assert str(caught.value) == message
    assert len(writes) == 3
    assert sleeps == [0.25, 0.25]


def test_nebula_schema_write_recovers_after_graph_and_storage_propagate(monkeypatch):
    from databasehub.adapters import nebula

    sleeps = []
    writes = []
    errors = iter(("No schema found for `Entity__`", "Storage Error: Tag not found."))
    monkeypatch.setattr(config, "NEBULA_SCHEMA_WRITE_ATTEMPTS", 3)
    monkeypatch.setattr(config, "NEBULA_SCHEMA_RETRY_INTERVAL", 0.25)
    monkeypatch.setattr(nebula.time, "sleep", sleeps.append)

    def write():
        writes.append(None)
        message = next(errors, None)
        if message is not None:
            raise Exception("NebulaGraph query failed:", message, "Statement:", "INSERT VERTEX")

    nebula.NebulaAdapter._retry_schema_write(write)

    assert len(writes) == 3
    assert sleeps == [0.25, 0.25]


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("permission denied"),
        RuntimeError("SyntaxError: invalid statement"),
        Exception(
            "NebulaGraph query failed:",
            "permission denied",
            "Statement:",
            'INSERT VERTEX `Entity__` (`name`) VALUES "Storage Error: Tag not found.":("No schema found")',
        ),
    ],
)
def test_nebula_does_not_retry_unrelated_write_errors(monkeypatch, error):
    from databasehub.adapters import nebula

    sleeps = []
    monkeypatch.setattr(nebula.time, "sleep", sleeps.append)

    def write():
        raise error

    with pytest.raises(type(error)) as caught:
        nebula.NebulaAdapter._retry_schema_write(write)

    assert caught.value is error
    assert sleeps == []


@pytest.mark.parametrize(
    ("method", "arguments"),
    [
        ("_ensure_space", ("docs",)),
        ("_wait_for_entity_schema", ("docs",)),
        ("existing_store", ("docs",)),
        ("ping", ()),
    ],
)
def test_nebula_connections_use_configured_timeout(monkeypatch, method, arguments):
    from databasehub.adapters import nebula

    timeouts = []
    result = SimpleNamespace(is_succeeded=lambda: True)
    session = SimpleNamespace(execute=lambda statement: result, release=lambda: None)

    def initialize(addresses, options):
        timeouts.append(options.timeout)
        return True

    pool = SimpleNamespace(
        init=initialize,
        get_session=lambda username, password: session,
        close=lambda: None,
    )
    monkeypatch.setattr(config, "NEBULA_TIMEOUT_MS", 7500)
    monkeypatch.setattr(nebula, "ConnectionPool", lambda: pool)
    adapter = nebula.NebulaAdapter({"url": "nebula://graph:9669"})
    adapter._stores["docs"] = object()

    getattr(adapter, method)(*arguments)

    assert timeouts == [7500]


def test_milvus_iterator_uses_configured_batch_size(monkeypatch):
    from databasehub.adapters.milvus import MilvusAdapter
    from databasehub.models import VectorCollection

    calls = []
    closed = []
    batches = iter([[{"id": "concept", "cid": "concept"}], []])
    iterator = SimpleNamespace(next=lambda: next(batches), close=lambda: closed.append(True))

    def query_iterator(**options):
        calls.append(options)
        return iterator

    adapter = object.__new__(MilvusAdapter)
    adapter._milvus_client = SimpleNamespace(
        has_collection=lambda name: True,
        describe_collection=lambda name: {
            "fields": [{"name": "embedding", "params": {"dim": 4}}]
        },
        load_collection=lambda name: None,
        query_iterator=query_iterator,
    )
    monkeypatch.setattr(config, "MILVUS_QUERY_BATCH_SIZE", 200)
    monkeypatch.setattr(adapter, "vector_store", lambda collection: "existing-store")

    assert adapter.existing_concept_store(
        VectorCollection("concepts", 4), {"concept"}
    ) == "existing-store"
    assert calls[0]["batch_size"] == 200
    assert closed == [True]


def test_image_url_loading_uses_configured_timeout(monkeypatch):
    from io import BytesIO
    from PIL import Image

    runtime = pytest.importorskip("inference.gme_runtime", exc_type=ImportError)
    image_data = BytesIO()
    Image.new("RGB", (56, 56)).save(image_data, format="PNG")
    image_data.seek(0)
    calls = []

    def get(url, **options):
        calls.append(options)
        return SimpleNamespace(raw=image_data)

    monkeypatch.setattr(config, "IMAGE_HTTP_TIMEOUT", 12.5)
    monkeypatch.setattr(runtime.requests, "get", get)

    assert runtime.load_image("http://images.example/test.png").size == (56, 56)
    assert calls == [{"stream": True, "timeout": 12.5}]
    assert runtime.DEFAULT_BATCH_SIZE == config.GME_BATCH_SIZE
    assert runtime._IMAGE_LOAD_WORKERS == config.IMAGE_LOAD_WORKERS


def test_remote_reranker_uses_configured_timeout(monkeypatch):
    import httpx

    calls = []

    def post(url, **options):
        calls.append((url, options))
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"results": [{"index": 0, "relevance_score": 0.9}]},
        )

    monkeypatch.setattr(config, "REMOTE_RERANK_TIMEOUT", 42.5, raising=False)
    monkeypatch.setattr(httpx, "post", post)
    nodes = [NodeWithScore(node=TextNode(text="document"))]

    result = postprocessor._RemoteReranker("model", "http://reranker", 1).postprocess_nodes(
        nodes, query_str="q"
    )

    assert result[0].score == 0.9
    assert calls[0][1]["timeout"] == 42.5


def _fake_rerank_server(monkeypatch, payload):
    import httpx

    calls = []

    def post(url, **options):
        calls.append((url, options))
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload)

    monkeypatch.setattr(httpx, "post", post)
    return calls


def test_remote_reranker_sends_api_key_and_both_document_fields(monkeypatch):
    calls = _fake_rerank_server(monkeypatch, {"results": [{"index": 0, "relevance_score": 0.9}]})
    monkeypatch.setattr(config, "RERANK_API_KEY", "test-key")
    nodes = [NodeWithScore(node=TextNode(text="document"))]

    postprocessor._RemoteReranker("model", "http://reranker/v1", 1).postprocess_nodes(
        nodes, query_str="q"
    )

    url, options = calls[0]
    assert url == "http://reranker/v1/rerank"
    assert options["headers"] == {"Authorization": "Bearer test-key"}
    assert options["json"]["documents"] == options["json"]["texts"] == ["document"]


def test_remote_reranker_accepts_tei_list_response_and_applies_top_n(monkeypatch):
    # TEI answers a bare list and ignores top_n; the reranker sorts and cuts itself.
    _fake_rerank_server(
        monkeypatch,
        [{"index": 0, "score": 0.1}, {"index": 2, "score": 0.8}, {"index": 1, "score": 0.5}],
    )
    nodes = [NodeWithScore(node=TextNode(text=text)) for text in ("a", "b", "c")]

    result = postprocessor._RemoteReranker("model", "http://tei", 2).postprocess_nodes(
        nodes, query_str="q"
    )

    assert [item.node.text for item in result] == ["c", "b"]
    assert [item.score for item in result] == [0.8, 0.5]


def test_request_backend_selects_remote_reranker(monkeypatch):
    monkeypatch.setattr(config, "RERANK_BACKEND", config.LOCAL_OPENVINO)
    monkeypatch.setattr(postprocessor, "_CACHE", {})
    built = []
    monkeypatch.setattr(
        postprocessor,
        "_build",
        lambda *arguments: built.append(arguments) or SimpleNamespace(run=lambda **_: []),
    )

    postprocessor.postprocess_nodes(
        "q", [], "reranker", 3,
        {"backend": config.REMOTE_OPENAI_COMPATIBLE, "model_id": "m", "api_base": "http://reranker"},
    )

    backend, _, model_id, _, api_base = built[0]
    assert (backend, model_id, api_base) == (config.REMOTE_OPENAI_COMPATIBLE, "m", "http://reranker")


def test_remote_reranks_run_concurrently_with_their_own_top_n(monkeypatch):
    import threading

    import httpx

    # Both calls must be inside the HTTP request at once: a lock would leave the
    # second waiting and the barrier would time out.
    barrier = threading.Barrier(2, timeout=5)

    def post(url, **options):
        barrier.wait()
        results = [{"index": index, "relevance_score": 1.0 - index / 10} for index in range(3)]
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"results": results})

    monkeypatch.setattr(httpx, "post", post)
    processor = postprocessor._build(config.REMOTE_OPENAI_COMPATIBLE, 3, "m", "CPU", "http://reranker")
    nodes = [NodeWithScore(node=TextNode(text=text)) for text in ("a", "b", "c")]
    sizes = {}

    def rerank(top_n):
        sizes[top_n] = len(processor.run(retri_res=nodes, query_str="q", top_n=top_n))

    threads = [threading.Thread(target=rerank, args=(top_n,)) for top_n in (1, 2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sizes == {1: 1, 2: 2}


def test_llamaindex_openvino_embedding_serializes_inference(monkeypatch):
    # The upstream class infers through one cached InferRequest; concurrent calls
    # failed with "Infer Request is busy". The engine's subclass must never let
    # two `_embed` calls overlap.
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    from inference import ov_adapter
    from llama_index.embeddings.huggingface_openvino import OpenVINOEmbedding

    state = {"in_flight": 0, "peak": 0}
    guard = threading.Lock()

    def upstream_embed(self, sentences):
        with guard:
            state["in_flight"] += 1
            state["peak"] = max(state["peak"], state["in_flight"])
        time.sleep(0.02)
        with guard:
            state["in_flight"] -= 1
        return [[float(len(sentence))] for sentence in sentences]

    monkeypatch.setattr(OpenVINOEmbedding, "_embed", upstream_embed)
    # Skip __init__ (it loads a model); private attributes still get their defaults.
    model = ov_adapter._serialized_openvino_embedding_class().model_construct(
        model_name="m", max_length=8, pooling="cls", normalize=True,
        query_instruction=None, text_instruction=None,
    )

    with ThreadPoolExecutor(8) as pool:
        vectors = list(pool.map(model._embed, [["a" * n] for n in range(1, 9)]))

    assert state["peak"] == 1
    assert vectors == [[[float(n)]] for n in range(1, 9)]


def _concept_adapter(rows):
    from databasehub.adapters.milvus import MilvusAdapter

    batches = iter([rows, []])
    adapter = object.__new__(MilvusAdapter)
    adapter._milvus_client = SimpleNamespace(
        has_collection=lambda name: True,
        describe_collection=lambda name: {"fields": [{"name": "embedding", "params": {"dim": 4}}]},
        load_collection=lambda name: None,
        query_iterator=lambda **options: SimpleNamespace(next=lambda: next(batches), close=lambda: None),
    )
    adapter.vector_store = lambda collection: "existing-store"
    return adapter


def test_a_shared_concept_collection_may_hold_other_pools_concepts():
    from databasehub.models import VectorCollection

    rows = [{"id": "mine", "cid": "mine"}, {"id": "theirs", "cid": "theirs"}]
    collection = VectorCollection("docs_concept", 4)
    # Exactly this set: another pool's concept makes it fail, as before.
    assert _concept_adapter(rows).existing_concept_store(collection, {"mine"}) is None
    # Containment: every expected concept is there, keyed by its own id.
    assert _concept_adapter(rows).existing_concept_store(collection, {"mine"}, exact=False) == "existing-store"
    assert _concept_adapter(rows).existing_concept_store(collection, {"mine", "missing"}, exact=False) is None
    bad = [{"id": "row-1", "cid": "mine"}]
    assert _concept_adapter(bad).existing_concept_store(collection, {"mine"}, exact=False) is None
