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
    └── ...

A directory is classified by its name and structured model metadata. `ready` says
whether the model's inference artifacts are already prepared. A model that is
not ready must be downloaded/exported outside the engine before it can be used.

The `openai_compatible` provider addresses a remote endpoint instead, so there is
nothing local to list: the configured model id is reported as the only option.
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
MODEL_TYPES = (EMBEDDING, RERANKER, LAYOUT, MULTIMODAL, ASR)
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
    """The multimodal model a directory holds, by its contents, not its name.

    X-CLIP is media-only; GME also serves main's text/fused embedding provider,
    so the scan reports it in both pickers without duplicating its runtime.
    """
    from core.multimodal import registry  # noqa: PLC0415

    for model in registry.MODELS:
        if model.matches_dir(Path(path)):
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


def _scan(root: str, prefix: str = "", depth: int = 1) -> List[dict]:
    """Model directories under `root`, as {name, path, ready, model_type}."""
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
            kinds = (EMBEDDING, MULTIMODAL) if mm.name == "gme_qwen2vl" else (MULTIMODAL,)
            ready = _gme_model_exist(path) if mm.name == "gme_qwen2vl" else mm.is_ready(Path(path))
            models.extend(
                {"name": name, "path": path, "ready": ready, "model_type": kind}
                for kind in kinds
            )
            continue
        if _is_asr(path):
            from core.multimodal.asr import find_ir_dir  # noqa: PLC0415

            models.append(
                {
                    "name": name,
                    "path": path,
                    "ready": find_ir_dir(path) is not None,
                    "model_type": ASR,
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
            models.append(model)
            continue
        # A vendor directory (no model files of its own): look one level deeper.
        nested = _scan(path, prefix=f"{name}/", depth=depth + 1)
        models.extend(nested or [{"name": name, "path": path, "ready": False,
                                  "model_type": _classify(name, path)}])
    return models


def workspace_models(model_type: str = None) -> List[dict]:
    """The models present in the workspace, optionally of one kind only."""
    models = _scan(config.MODEL_DIR)
    if model_type:
        models = [model for model in models if model["model_type"] == model_type]
    return models


def model_options(model_type: str) -> dict:
    """Everything a picker needs for one kind of model: the backend the engine runs
    it on, the device, the configured default, and what it can choose from."""
    if model_type not in MODEL_TYPES:
        raise ValueError(f"Unknown model type '{model_type}'; expected one of {', '.join(MODEL_TYPES)}")
    if model_type == EMBEDDING:
        backend, device, model_id = config.EMBEDDING_BACKEND, config.EMBEDDING_DEVICE, config.EMBEDDING_MODEL_ID
        api_base = config.EMBEDDING_API_BASE
        backends = config.MODEL_BACKENDS
    elif model_type == RERANKER:
        backend, device, model_id = config.RERANK_BACKEND, config.RERANK_DEVICE, config.RERANK_MODEL_ID
        api_base = config.RERANK_API_BASE
        backends = config.MODEL_BACKENDS
    elif model_type == ASR:
        backend, device, model_id = config.ASR_BACKEND, config.ASR_DEVICE, config.ASR_MODEL_ID
        api_base = ""
        backends = ("openvino",)
    elif model_type == MULTIMODAL:
        # Local OpenVINO models of more than one category (video, image); what a
        # source runs is fixed in its profile, so there is no single default to
        # report here -- only which of them are on disk.
        backend, device, model_id = config.VIDEO_EMBEDDING_BACKEND, "", ""
        api_base = ""
        backends = ("llamaindex_openvino",)
    else:
        backend, device, model_id = config.LAYOUT_BACKEND, config.LAYOUT_DEVICE, config.LAYOUT_MODEL_ID
        api_base = None
        backends = config.LAYOUT_BACKENDS

    if model_type in (LAYOUT, MULTIMODAL, ASR) or backend in config.LOCAL_MODEL_BACKENDS:
        models = workspace_models(model_type)
    else:
        # Remote endpoint: the engine has no local directory to offer.
        models = [{"name": model_id, "path": api_base, "ready": True, "model_type": model_type}]
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
        # Media (multimodal) search reranks with its own default, so the picker can
        # name what "Media default" resolves to.
        options["media_model_id"] = config.MEDIA_RERANK_MODEL_ID
    return options


def all_model_options() -> Dict[str, dict]:
    return {model_type: model_options(model_type) for model_type in MODEL_TYPES}
