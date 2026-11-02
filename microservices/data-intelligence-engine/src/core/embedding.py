# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Embedding models, multimodal orchestration, and model factory.

Ported from edgecraftrag/components/model.py (OpenVINOEmbeddingModel,
OpenAIEmbeddingModel) + resolve_model_path/model_exist. Four model providers:

- "llamaindex_openvino" -> LlamaIndex/Optimum over a standard OpenVINO IR
- "openvino_genai"      -> OpenVINO GenAI over the same workspace models
- "openai_compatible"   -> an OpenAI-compatible endpoint (vLLM, TEI, ...)
- "native_openvino_gme" -> the model-specific native OV runtime for GME

Each asset library asks for its configured model, so `build_embedding`
takes the model per call and caches by (backend, model, device, endpoint): loading
an OpenVINO model is expensive, and several asset libraries usually share one.

All heavy imports are done lazily inside each builder, so importing this module
never requires openvino or a downloaded model.
"""

from pathlib import Path
from typing import Any, List, Optional, Protocol, Sequence, runtime_checkable

import config
from inference.model_cache import ModelCache


# --- model path resolution (ported from components/model.py) ------------------

def resolve_model_path(model_path: str) -> str:
    """Where this model actually is.

    Models live under `ENGINE_MODEL_ROOT_PATH` (by default `workspace/models`),
    so that is the first model root tried; the legacy `MODEL_PATH` root and
    `~/models` follow, keeping older deployments and explicit paths working.
    """
    if not model_path:
        return model_path
    path_obj = Path(model_path)
    if path_obj.is_absolute() and path_obj.exists():
        return str(path_obj)
    candidates = [Path.cwd() / path_obj]
    parts = [p for p in path_obj.parts if p not in (".", "models")]
    for root in (config.MODEL_DIR, config.LEGACY_MODEL_DIR, config.SHARED_MODEL_DIR):
        if not root or not parts:
            continue
        root_path = Path(root).expanduser()
        candidates += [root_path / Path(*parts), root_path / path_obj.name]
    for c in candidates:
        try:
            resolved = c.expanduser().resolve()
        except OSError:
            continue
        if resolved.exists():
            return str(resolved)
    return model_path


def model_exist(model_path: str) -> bool:
    model_dir = Path(resolve_model_path(model_path))
    return (
        model_dir.is_dir()
        and (model_dir / "openvino_model.xml").is_file()
        and (model_dir / "openvino_model.bin").is_file()
    )


def workspace_model_dir(model_path: str) -> str:
    """Where a model not yet present under the configured root should be written.

    An absolute path is taken as given; anything else becomes a directory under the
    shared model root, so an exported model lands with the others.
    """
    path_obj = Path(model_path or "")
    if path_obj.is_absolute():
        return str(path_obj)
    parts = [p for p in path_obj.parts if p not in (".", "models")] or [path_obj.name]
    return str(Path(config.MODEL_DIR).joinpath(*parts))


def require_openvino_model(model_path: str, capability: str) -> str:
    """A prepared local IR directory, never a Hub ID or an export fallback."""
    resolved = resolve_model_path(model_path)
    if not model_exist(resolved):
        raise FileNotFoundError(
            f"No prepared OpenVINO {capability} at {resolved!r}: expected "
            "openvino_model.xml and openvino_model.bin. Prepare the model, "
            "including its tokenizer files, before starting the engine and put "
            "it under ENGINE_MODEL_ROOT_PATH or configure an explicit model path. "
            "The engine does not download or export models."
        )
    return str(Path(resolved).resolve())


# --- factory ------------------------------------------------------------------

# Projections own the adapters and runtimes; dropping the last projection releases
# the model rather than keeping every historical source resident forever.
_CACHE = ModelCache()
_GME_RUNTIMES = ModelCache()


def build_gme_runtime(
    model_path: str,
    device: str,
    *,
    max_image_tokens: Optional[int] = None,
):
    """One GME runtime per canonical package path and device, across both adapters.

    The package determines its weights. Two sources cannot silently
    change the same runtime's processor settings underneath one
    another. Conflicting settings fail explicitly instead of loading another 2B
    model or changing the vectors an existing source produces.
    """
    from inference.gme_runtime import GmeOpenVINO
    from inference.multimodal.gme_qwen2vl import choose_precision, find_package

    package = find_package(resolve_model_path(model_path)).resolve()
    device = (device or "CPU").upper()
    selected_precision = choose_precision(package)
    metadata = config._model_json(str(package), "gme_openvino_config.json")
    processor = metadata.get("processor", {})
    tokens = int(
        processor.get("max_image_tokens", 1024)
        if max_image_tokens is None else max_image_tokens
    )
    if tokens < 1:
        raise ValueError("max_image_tokens must be positive")
    settings = (selected_precision, tokens)

    def build():
        runtime = GmeOpenVINO(
            str(package), device=device, precision=selected_precision,
            min_image_tokens=min(int(processor.get("min_image_tokens", 4)), tokens),
            max_image_tokens=tokens,
        )
        runtime._engine_settings = settings
        return runtime

    runtime = _GME_RUNTIMES.get_or_build((str(package), device), build)
    if runtime._engine_settings != settings:
        raise ValueError(
            f"GME runtime at {str(package)!r} on {device} is already in use with "
            f"precision/max_image_tokens={runtime._engine_settings}, requested {settings}; "
            "sources sharing a package and device must use the same settings"
        )
    return runtime


def build_embedding(
    backend: Optional[str] = None,
    model_id: Optional[str] = None,
    model_path: Optional[str] = None,
    device: Optional[str] = None,
    api_base: Optional[str] = None,
):
    """A llama-index embedding model, built at most once per configuration.

    Unset arguments fall back to the engine's configured defaults, so a caller that
    has no opinion still gets a working model.
    """
    backend = config.normalize_model_backend(backend or config.EMBEDDING_BACKEND)
    model_id = model_id or config.EMBEDDING_MODEL_ID
    # A local backend addresses a model directory; the model chosen in the UI is a
    # name under the workspace's model directory, which is also a valid path here.
    model_path = model_path or (
        config.EMBEDDING_MODEL_PATH if model_id == config.EMBEDDING_MODEL_ID else model_id
    )
    device = device or config.EMBEDDING_DEVICE
    api_base = api_base or config.EMBEDDING_API_BASE

    key = (backend, model_id, model_path, device, api_base)
    return _CACHE.get_or_build(
        key, lambda: _build(backend, model_id, model_path, device, api_base)
    )


def _build(backend: str, model_id: str, model_path: str, device: str, api_base: str):
    if backend == "openai_compatible":
        # OpenAI-compatible embedding endpoint (ported from OpenAIEmbeddingModel).
        from llama_index.embeddings.openai import OpenAIEmbedding

        if api_base and not api_base.endswith("/v1"):
            api_base = api_base + "/v1"
        return OpenAIEmbedding(
            model_name=model_id, api_base=api_base, api_key=config.EMBEDDING_API_KEY
        )

    if backend == "native_openvino_gme":
        # A multimodal OV model is a runtime + the model-neutral adapter, not a
        # bespoke class: GME is the runtime, `MultimodalOVEmbedding` the adapter
        # (the same one a future gme2/qwen3-vl runtime will reuse unchanged). The
        # GME package layout is a gme_openvino_config.json + language/visual IRs,
        # not the single openvino_model.xml that model_exist() checks, so resolve
        # the directory and let GmeOpenVINO validate it (raises FileNotFoundError).
        from inference.ov_adapter import MultimodalOVEmbedding

        # No precision: the package's IRs decide it (gme_runtime.package_ir_files).
        runtime = build_gme_runtime(model_path, device)
        return MultimodalOVEmbedding(
            runtime, fused_instruction=config.EMBEDDING_FUSED_INSTRUCTION
        )

    if backend == "llamaindex_openvino":
        # Ported from OpenVINOEmbeddingModel; serialized because the cached model
        # is shared by concurrent requests and the upstream class is not.
        resolved = require_openvino_model(model_path, "embedding model")
        from inference.ov_adapter import serialized_openvino_embedding

        return serialized_openvino_embedding(
            model_id_or_path=resolved,
            device=device,
            model_kwargs={
                "ov_config": dict(config.OPENVINO_CONFIG),
                "local_files_only": True,
                "export": False,
            },
        )

    if backend == "openvino_genai":
        resolved = require_openvino_model(model_path, "embedding model")
        from inference.ov_adapter import OpenVINOGenAIEmbedding

        return OpenVINOGenAIEmbedding(
            model_path=resolved,
            device=device,
            pad_to_max_length=True,
            max_length=config.embedding_max_length(resolved),
            normalize=True,
            pooling=config.embedding_pooling(resolved),
            padding_side="right",
        )

    raise ValueError(f"Embedding provider {backend!r} has no factory implementation")


# --- multimodal: embedding an image node is the embedding layer's job ----------


@runtime_checkable
class FusedEmbedding(Protocol):
    """What makes an embedding model multimodal, to everything downstream.

    Backend-neutral on purpose, and defined here rather than beside any one
    backend: the vector projection precomputes an image node's vector iff its
    embedding model satisfies this protocol (`embed_media_nodes` below,
    `core/indexer.py`), and it must not care whether that model is the OV runtime
    adapter (`inference.ov_adapter.MultimodalOVEmbedding`), a future remote/vLLM
    adapter, or anything else. A text-only model simply does not implement this
    and falls back to the text path. Nothing downstream names a concrete model --
    it names this.
    """

    def get_fused_embeddings(
        self, texts: Sequence[str], images: Sequence[Any]
    ) -> List[List[float]]:
        ...


def embed_media_nodes(embedding_model, nodes, read_blob, source_id=None) -> None:
    """Precompute each image node's vector in place, if the model can embed one.

    A figure's pixels cannot go through the text batch interface that
    `VectorStoreIndex.insert_nodes` uses, so an image node's vector is computed
    here and stamped on `node.embedding`; the index then inserts it unchanged and
    embeds only the nodes still without one. What a node's vector *is* stays the
    embedding model's concern -- the indexer builds the nodes and delegates, the
    same division it already relies on for text.

    The text side is `get_content(EMBED)` -- caption plus surrounding prose,
    exactly what the text path would embed -- so a fused vector is a strict
    superset of the text-only one, in the same space. A text-only model (one that
    is not a `FusedEmbedding`), a missing `read_blob`, or a figure whose bytes
    cannot be read leaves `embedding` at `None`: it falls back to the text path
    rather than being dropped.

    `read_blob` is passed in rather than held on the model because
    `build_embedding` caches one model per configuration across libraries, while a
    blob reader belongs to a single library's object store -- binding it to the
    shared model would cross those wires. So it is injected at the projection and
    handed down here per call.
    """
    from llama_index.core.schema import MetadataMode

    # The one place that decides "is this model multimodal" -- by protocol, not by
    # class: any model exposing get_fused_embeddings qualifies, GME or otherwise.
    if not isinstance(embedding_model, FusedEmbedding) or read_blob is None or not nodes:
        return
    texts, images, targets = [], [], []
    for node in nodes:
        media_key = node.metadata.get("media_key")
        if not media_key:
            continue
        try:
            data = read_blob(media_key, source_id)
        except Exception:  # noqa: BLE001 - unreadable pixels: text-only fallback
            continue
        texts.append(node.get_content(metadata_mode=MetadataMode.EMBED))
        images.append(data)
        targets.append(node)
    if not targets:
        return
    for node, vector in zip(targets, embedding_model.get_fused_embeddings(texts, images)):
        node.embedding = list(vector)
