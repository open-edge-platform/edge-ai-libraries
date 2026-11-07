# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""What models this engine can run, for the pickers in the UI.

Providers in `config.LOCAL_MODEL_BACKENDS` load a model directory out of the
shared model root (`ENGINE_MODEL_ROOT_PATH`, default `workspace/models`), so the
choice is "one of the directories that are actually there" -- which is what this
module reports, per kind:

    workspace/models/
    ├── bge-small-en-v1.5/          -> embedding
    ├── BAAI/bge-reranker-base/     -> reranker  (vendor subdirectories are walked)
    ├── PP-DocLayoutV3/             -> layout
    ├── viclip-b-fp16/             -> embedding (video)
    ├── viclip-l-fp16/             -> embedding (video)
    ├── cosmos-224p-fp16/          -> embedding (video)
    └── ...

A directory is classified by its name and structured model metadata. `ready` says
whether the model's inference artifacts are already prepared. A model that is
not ready must be downloaded/exported outside the engine before it can be used.
Video directories contain a validated video_embedding.json, root-level
video_encoder.xml/.bin and text_encoder.xml/.bin, and standard tokenizer assets.
All use eight 224x224 RGB frames; no checkpoint Python or PyTorch weights
are needed at runtime. Independent package IDs retain the canonical model
identity in the manifest's name field.

The `openai_compatible` provider addresses a remote endpoint. Its configured
embedding model is listed alongside local packages, with text capability.
"""

import json
import os
from pathlib import Path
from typing import Dict, List

import config
from core.embedding import model_exist

EMBEDDING = "embedding"
RERANKER = "reranker"
LAYOUT = "layout"
OCR = "ocr"
MULTIMODAL = "multimodal"
ASR = "asr"
MODEL_TYPES = (EMBEDDING, RERANKER, LAYOUT, ASR)
# How deep to walk under workspace/models: the directory itself, and one level of
# vendor prefix ("BAAI/bge-reranker-base").
_MAX_DEPTH = 2


def _gme_model_exist(path: str) -> bool:
    from inference.multimodal.gme_qwen2vl import choose_precision, find_package

    try:
        package = find_package(path)
        config_path = package / "gme_openvino_config.json"
        with open(config_path, encoding="utf-8") as handle:
            metadata = json.load(handle)
        choose_precision(package)
    except (OSError, ValueError, KeyError, TypeError):
        return False
    # The Python runtime (inference.gme_runtime) tokenizes with the package's
    # Hugging Face processor files; only a package exported for the C++ runtime
    # names a tokenizer IR, and then that file must be there.
    tokenizer = metadata.get("tokenizer_model")
    if tokenizer:
        return (package / str(tokenizer)).is_file()
    return (package / "preprocessor_config.json").is_file() and (
        (package / "tokenizer.json").is_file()
        or all((package / name).is_file() for name in ("vocab.json", "merges.txt"))
    )


def _qwen3_vl_reranker_ready(path: str) -> bool:
    """The custom Qwen3-VL reranker export: reranker_{text,image,video}.xml/.bin
    plus tokenizer files, not the single openvino_model.xml model_exist() checks."""
    directory = Path(path)
    return (directory / "reranker_text.xml").is_file() and (
        directory / "reranker_text.bin"
    ).is_file()


def _model_ready(path: str) -> bool:
    from core.layout import pp_doclayout_v3_onnx_path

    return (
        model_exist(path)
        or _gme_model_exist(path)
        or _qwen3_vl_reranker_ready(path)
        or os.path.isfile(pp_doclayout_v3_onnx_path(path))
    )


def _classify(name: str, path: str) -> str:
    normalized = name.lower()
    if "rerank" in normalized:
        return RERANKER
    if "ocr" in normalized:
        return OCR
    if "layout" in normalized:
        return LAYOUT
    try:
        with open(os.path.join(path, "config.json"), encoding="utf-8") as handle:
            metadata = json.load(handle)
    except (OSError, ValueError, TypeError):
        metadata = {}
    architecture = " ".join(str(value) for value in metadata.get("architectures", []))
    if "layout" in f"{metadata.get('model_type', '')} {architecture}".lower():
        return LAYOUT
    return EMBEDDING


def _multimodal(path: str):
    """The multimodal identity a directory declares, with canonical IDs exact.

    All recognized packages are embeddings; their supported kinds distinguish
    text, image, audio and video inputs. Video identity and readiness come from
    the validated manifest.
    """
    from core.multimodal import registry  # noqa: PLC0415

    candidate = Path(path)
    # A canonical directory name is also an explicit identity. In particular,
    # a directory called viclip-b-fp16 containing an L manifest is not a ready B.
    for model in registry.MODELS:
        if model.category == registry.VIDEO_CATEGORY and model.matches_id(candidate.name):
            return model
    for model in registry.MODELS:
        if model.matches_dir(candidate):
            return model
    return None


def _is_asr(path: str) -> bool:
    """A speech-recognition checkpoint (Whisper), which embeds nothing.

    Its exported IR lives in its own `openvino/` subdirectory, so without this the
    scan would descend into it and list that as a text embedding model.
    """
    try:
        with open(os.path.join(path, "config.json"), encoding="utf-8") as handle:
            return json.load(handle).get("model_type") == "whisper"
    except (OSError, ValueError, AttributeError):
        return False


def _capabilities(model_type: str, backend: str = None, mm=None) -> dict:
    """Catalog metadata only: asset families do not imply raw-input support."""
    roles = []
    if mm is not None:
        kinds = set(mm.supported_kinds)
        asset_types = set(mm.supported_asset_types)
        if "text" in kinds:
            asset_types.add("document")
        roles = sorted(mm.supported_roles)
    elif model_type == EMBEDDING:
        kinds, asset_types = {"text"}, {"document"}
    elif model_type == RERANKER:
        # Audio is supplied as transcript text, never raw sound.
        kinds, asset_types = {"text"}, {"audio", "document"}
        if backend == "openvino_vl":
            kinds.update(("image", "video"))
            asset_types.update(("image", "video"))
    elif model_type == LAYOUT:
        kinds, asset_types = {"image"}, {"document", "image"}
    elif model_type == ASR:
        # ASR produces transcripts, not embedding-role vectors.
        kinds, asset_types = {"audio"}, {"audio"}
    else:
        kinds, asset_types = set(), set()
    return {
        "supported_kinds": sorted(kinds),
        "supported_asset_types": sorted(asset_types),
        "supported_roles": roles,
    }


def _scan(root: str, prefix: str = "", depth: int = 1) -> List[dict]:
    """Model directories under `root`, with declared capability metadata."""
    from core.multimodal.registry import is_video_package

    models = []
    try:
        entries = sorted(os.listdir(root))
    except OSError:
        return models
    for entry in entries:
        path = os.path.join(root, entry)
        if not os.path.isdir(path) or entry.startswith("."):
            continue
        name = f"{prefix}{entry}"
        mm = _multimodal(path)
        if mm is not None:
            ready = _gme_model_exist(path) if mm.name == "gme_qwen2vl" else mm.is_ready(Path(path))
            models.append({
                "name": name, "path": path, "ready": ready,
                "model_type": EMBEDDING, **_capabilities(EMBEDDING, mm=mm),
            })
            continue
        if is_video_package(Path(path)):
            # Unsupported or malformed video packages are not text models.
            continue
        if _is_asr(path):
            from core.multimodal.asr import find_ir_dir  # noqa: PLC0415

            models.append(
                {
                    "name": name,
                    "path": path,
                    "ready": find_ir_dir(path) is not None,
                    "model_type": ASR,
                    **_capabilities(ASR),
                }
            )
            continue
        ready = _model_ready(path)
        if ready or depth >= _MAX_DEPTH:
            model = {
                "name": name,
                "path": path,
                "ready": ready,
                "model_type": _classify(name, path),
            }
            if _qwen3_vl_reranker_ready(path):
                # The picker must route this reranker to the VL backend; the
                # text reranker backends cannot load this export.
                model["backend"] = "openvino_vl"
            model.update(_capabilities(model["model_type"], model.get("backend")))
            models.append(model)
            continue
        # A vendor directory (no model files of its own): look one level deeper.
        nested = _scan(path, prefix=f"{name}/", depth=depth + 1)
        if nested:
            models.extend(nested)
        elif not any(
            is_video_package(Path(path) / child)
            for child in os.listdir(path)
            if os.path.isdir(os.path.join(path, child)) and not child.startswith(".")
        ):
            model = {"name": name, "path": path, "ready": False,
                     "model_type": _classify(name, path)}
            model.update(_capabilities(model["model_type"]))
            models.append(model)
    return models


def workspace_models(model_type: str = None) -> List[dict]:
    """Local models by type; `multimodal` aliases media-capable embeddings."""
    models = _scan(config.MODEL_DIR)
    if model_type == MULTIMODAL:
        models = [
            model for model in models
            if model["model_type"] == EMBEDDING
            and {"image", "video", "audio"}.intersection(model.get("supported_kinds", ()))
        ]
    elif model_type:
        models = [model for model in models if model["model_type"] == model_type]
    return models


def _configured_default(prefix: str, *, api_base=None) -> dict:
    """Report configuration, not readiness or a constructed runtime."""
    return {
        "backend": getattr(config, f"{prefix}_BACKEND"),
        "model_id": getattr(config, f"{prefix}_MODEL_ID"),
        "model_path": getattr(config, f"{prefix}_MODEL_PATH"),
        "device": getattr(config, f"{prefix}_DEVICE"),
        "api_base": api_base,
    }


def _media_embedding_default(asset_type: str) -> dict:
    """Resolve exactly what a new single-asset source inherits; never load it."""
    from core.multimodal import registry

    # Keep configured values visible even if the category cannot be resolved.
    category = registry.VIDEO_CATEGORY if asset_type == "video" else registry.IMAGE_CATEGORY
    try:
        resolved = registry.resolve({"asset_types": [asset_type]})
        return {
            **registry._category_defaults(resolved.model.category),
            "backend": resolved.backend,
            "model_id": resolved.model_id,
            "model_path": str(registry.local_path(resolved.model_path).resolve()),
            "api_base": None,
        }
    except (ValueError, OSError):
        return {**registry._category_defaults(category), "api_base": None}


def _model_defaults(model_type: str) -> Dict[str, dict]:
    defaults = {}
    if model_type == EMBEDDING:
        defaults["document"] = _configured_default(
            "EMBEDDING", api_base=config.EMBEDDING_API_BASE,
        )
    defaults.update({
        asset: _media_embedding_default(asset) for asset in ("image", "video", "audio")
    })
    return defaults


def model_options(model_type: str) -> dict:
    """Available models, backends and per-asset defaults for a model picker.

    `multimodal` is a compatibility view of local media-capable embeddings.
    """
    if model_type not in (*MODEL_TYPES, MULTIMODAL):
        raise ValueError(
            f"Unknown model type '{model_type}'; expected one of {', '.join(MODEL_TYPES)} "
            f"or the '{MULTIMODAL}' compatibility alias"
        )
    if model_type in (RERANKER, LAYOUT, ASR):
        # Preserve the original non-embedding catalog contracts.
        if model_type == RERANKER:
            backend, device, model_id = config.RERANK_BACKEND, config.RERANK_DEVICE, config.RERANK_MODEL_ID
            api_base = config.RERANK_API_BASE
            backends = (*config.MODEL_BACKENDS, "openvino_vl")
        elif model_type == ASR:
            backend, device, model_id = config.ASR_BACKEND, config.ASR_DEVICE, config.ASR_MODEL_ID
            api_base = ""
            backends = ("openvino",)
        else:
            backend, device, model_id = config.LAYOUT_BACKEND, config.LAYOUT_DEVICE, config.LAYOUT_MODEL_ID
            api_base = None
            backends = config.LAYOUT_BACKENDS
        if model_type in (LAYOUT, ASR) or backend in config.LOCAL_MODEL_BACKENDS:
            models = [
                {key: model[key] for key in ("name", "path", "ready", "model_type", "backend")
                 if key in model}
                for model in workspace_models(model_type)
            ]
        else:
            models = [{
                "name": model_id, "path": api_base,
                "ready": True, "model_type": model_type,
            }]
        options = {
            "model_type": model_type,
            "backend": backend,
            "backends": list(backends),
            "device": device,
            "model_id": model_id,
            "api_base": api_base,
            "workspace": config.MODEL_DIR,
            "models": models,
        }
        if model_type == RERANKER:
            options.update({
                "media_model_id": config.MEDIA_RERANK_MODEL_ID,
                "media_backend": config.MEDIA_RERANK_BACKEND,
                "media_device": config.MEDIA_RERANK_DEVICE,
            })
        return options
    if model_type == EMBEDDING:
        backend, model_id = config.EMBEDDING_BACKEND, config.EMBEDDING_MODEL_ID
        api_base = config.EMBEDDING_API_BASE
        backends = config.MODEL_BACKENDS
    else:
        backends = ("llamaindex_openvino",)

    if model_type == EMBEDDING:
        models = workspace_models(EMBEDDING)
        if backend not in config.LOCAL_MODEL_BACKENDS:
            models.append({
                "name": model_id, "path": api_base, "ready": True,
                "model_type": EMBEDDING, **_capabilities(EMBEDDING),
            })
        by_identity = {}
        for model in models:
            by_identity.setdefault((model["name"], model["path"]), model)
        models = list(by_identity.values())
    else:
        models = workspace_models(model_type)
    return {
        "model_type": model_type,
        "backends": list(backends),
        "workspace": config.MODEL_DIR,
        "models": models,
        "defaults": _model_defaults(model_type),
    }


def all_model_options() -> Dict[str, dict]:
    return {model_type: model_options(model_type) for model_type in MODEL_TYPES}
