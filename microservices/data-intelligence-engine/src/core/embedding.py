# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
from pathlib import Path
from typing import Any, List, Optional, Protocol, Sequence, runtime_checkable

import config
from inference.model_cache import ModelCache

logger = logging.getLogger(__name__)


# --- model path resolution ----------------------------------------------------

def resolve_model_path(model_path: str) -> str:
    """Resolve a model path against the cwd and the configured model roots."""
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
    """Target directory for a model: absolute paths as given, else under the model root."""
    path_obj = Path(model_path or "")
    if path_obj.is_absolute():
        return str(path_obj)
    parts = [p for p in path_obj.parts if p not in (".", "models")] or [path_obj.name]
    return str(Path(config.MODEL_DIR).joinpath(*parts))


def require_openvino_model(model_path: str, capability: str) -> str:
    """Return the resolved local IR directory, raising if it is not prepared."""
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

_CACHE = ModelCache()
_GME_RUNTIMES = ModelCache()


def build_gme_runtime(
    model_path: str,
    device: str,
    *,
    max_image_tokens: Optional[int] = None,
):
    """Shared GME runtime per package path and device; conflicting settings raise."""
    from inference.gme_runtime import GmeOpenVINO
    from inference.gme_runtime import choose_precision, find_package

    package = find_package(resolve_model_path(model_path)).resolve()
    device = (device or "CPU").upper()
    choose_precision(package)
    metadata = config._model_json(str(package), "gme_openvino_config.json")
    processor = metadata.get("processor", {})
    tokens = int(
        processor.get("max_image_tokens", 1024)
        if max_image_tokens is None else max_image_tokens
    )
    if tokens < 1:
        raise ValueError("max_image_tokens must be positive")

    def build():
        return GmeOpenVINO(
            str(package), device=device,
            min_image_tokens=min(int(processor.get("min_image_tokens", 4)), tokens),
            max_image_tokens=tokens,
        )

    runtime = _GME_RUNTIMES.get_or_build((str(package), device), build)
    if runtime.max_image_tokens != tokens:
        raise ValueError(
            f"GME runtime at {str(package)!r} on {device} is already in use with "
            f"max_image_tokens={runtime.max_image_tokens}, requested {tokens}; "
            "sources sharing a package and device must use the same settings"
        )
    return runtime


def is_gme_package(model_path: str) -> bool:
    from inference.gme_runtime import find_package

    try:
        find_package(resolve_model_path(model_path))
    except (FileNotFoundError, OSError):
        return False
    return True


def embedding_class(backend: str, model_path: str):
    """The class `build_embedding` instantiates for this backend and model."""
    if backend == config.REMOTE_OPENAI_COMPATIBLE:
        from inference.remote_adapter import _remote_embedding_class

        return _remote_embedding_class()
    if is_gme_package(model_path):
        from inference.ov_adapter import MultimodalOVEmbedding

        return MultimodalOVEmbedding
    from inference.ov_adapter import OpenVINOGenAIEmbedding

    return OpenVINOGenAIEmbedding


def embedding_runtime(backend: str, model_path: str) -> str:
    """The runtime name `build_embedding` would use."""
    return embedding_class(backend, model_path).RUNTIME


def embedding_is_fused(backend: str, model_path: str) -> bool:
    """Whether the model embeds figures: multimodal, with a fused path."""
    cls = embedding_class(backend, model_path)
    return cls.SUPPORT_MULTIMODAL is True and issubclass(cls, FusedEmbedding)


def build_embedding(
    backend: Optional[str] = None,
    model_id: Optional[str] = None,
    device: Optional[str] = None,
    api_base: Optional[str] = None,
):
    """A cached llama-index embedding model; unset arguments use engine defaults."""
    backend = config.normalize_model_backend(backend or config.EMBEDDING_BACKEND)
    model_id = model_id or config.EMBEDDING_MODEL_ID
    device = device or config.EMBEDDING_DEVICE
    api_base = api_base or config.EMBEDDING_API_BASE

    key = (backend, model_id, device, api_base)
    return _CACHE.get_or_build(
        key, lambda: _build(backend, model_id, device, api_base)
    )


def _build(backend: str, model_id: str, device: str, api_base: str):
    if backend == config.REMOTE_OPENAI_COMPATIBLE:
        from inference.remote_adapter import remote_openai_embedding

        if api_base and not api_base.endswith("/v1"):
            api_base = api_base + "/v1"
        return remote_openai_embedding(
            model_name=model_id, api_base=api_base, api_key=config.EMBEDDING_API_KEY
        )

    if is_gme_package(model_id):
        from inference.ov_adapter import MultimodalOVEmbedding

        return MultimodalOVEmbedding(
            build_gme_runtime(model_id, device),
            fused_instruction=config.EMBEDDING_FUSED_INSTRUCTION,
        )

    resolved = require_openvino_model(model_id, "embedding model")
    from inference.ov_adapter import OpenVINOGenAIEmbedding, serialized_openvino_embedding

    try:
        return OpenVINOGenAIEmbedding(
            model_path=resolved,
            device=device,
            pad_to_max_length=True,
            max_length=config.embedding_max_length(resolved),
            normalize=True,
            pooling=config.embedding_pooling(resolved),
            padding_side="right",
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "ov_genai embedding failed for %s; falling back to ov_llamaindex",
            resolved, exc_info=True,
        )
    return serialized_openvino_embedding(
        model_id_or_path=resolved,
        device=device,
        model_kwargs={
            "ov_config": dict(config.OPENVINO_CONFIG),
            "local_files_only": True,
            "export": False,
        },
    )


# --- multimodal ---------------------------------------------------------------


@runtime_checkable
class FusedEmbedding(Protocol):
    """An embedding model that can embed text and image together."""

    def get_fused_embeddings(
        self, texts: Sequence[str], images: Sequence[Any]
    ) -> List[List[float]]:
        ...


def embed_media_nodes(embedding_model, nodes, read_blob, source_id=None) -> None:
    """Set `node.embedding` on image nodes via fused embedding; others fall back to text."""
    from llama_index.core.schema import MetadataMode

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
